"""Stateless wrapper — state passed explicitly each call."""

from __future__ import annotations

from typing import Any

from soma.engine import SOMAEngine
from soma.types import Action, AgentConfig, AutonomyMode, Level, VitalsSnapshot
from soma.budget import MultiBudget
from soma.context_control import apply_context_control

_MAX_HISTORY = 20


class StatelessWrapper:
    """Stateless wrapper — state passed explicitly each call.

    The engine is reconstructed from the supplied *state* on every call so
    this object itself holds no per-agent mutable state beyond the optional
    default budget.
    """

    def __init__(self, budget: dict[str, float] | None = None) -> None:
        self._default_budget: dict[str, float] = budget or {"tokens": 100_000}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wrap(
        self,
        agent_id: str,
        context: dict[str, Any],
        action: Action,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process *action* for *agent_id* and return updated state.

        Parameters
        ----------
        agent_id:
            Identifier for the agent.
        context:
            Current context dict (``messages``, ``tools``, ``system_prompt``,
            etc.).  Passed through :func:`~soma.context_control.apply_context_control`.
        action:
            The :class:`~soma.types.Action` to record.
        state:
            Opaque state dict returned by a previous call to :meth:`wrap`.
            Pass ``None`` (or omit) on the first call.

        Returns
        -------
        dict with keys:

        ``context``
            Modified context after applying context control for the current level.
        ``level``
            Current :class:`~soma.types.Level`.
        ``pressure``
            Aggregate pressure float.
        ``vitals``
            :class:`~soma.types.VitalsSnapshot`.
        ``state``
            Opaque dict to pass to the next :meth:`wrap` call.
        """
        state = state or {}

        # Reconstruct engine from serialised state.
        engine = self._engine_from_state(agent_id, state)

        # Record action.
        result = engine.record_action(agent_id, action)

        # Append action to history (keep last 20).
        history: list[dict[str, Any]] = list(state.get("history", []))
        history.append(self._action_to_dict(action))
        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]

        # Apply context control based on resulting level.
        modified_context = apply_context_control(context, result.level)

        # Serialise engine state for next call.
        new_state = self._state_from_engine(engine, agent_id, history)

        return {
            "context": modified_context,
            "level": result.level,
            "pressure": result.pressure,
            "vitals": result.vitals,
            "state": new_state,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _engine_from_state(
        self, agent_id: str, state: dict[str, Any]
    ) -> SOMAEngine:
        """Rebuild a :class:`~soma.engine.SOMAEngine` from *state*."""
        budget_data: dict[str, Any] | None = state.get("budget")
        if budget_data:
            budget = MultiBudget.from_dict(budget_data)
            engine = SOMAEngine(budget=budget.limits)
            # Restore spent amounts.
            for dim, spent in budget.spent.items():
                if spent > 0:
                    engine.budget.spend(**{dim: spent})
        else:
            engine = SOMAEngine(budget=self._default_budget)

        # Register the agent if not yet present.
        engine.register_agent(agent_id)

        # Replay history so the engine has context.
        history: list[dict[str, Any]] = state.get("history", [])
        for action_dict in history:
            engine.record_action(agent_id, self._action_from_dict(action_dict))

        return engine

    def _state_from_engine(
        self,
        engine: SOMAEngine,
        agent_id: str,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "budget": engine.budget.to_dict(),
            "history": history,
        }

    @staticmethod
    def _action_to_dict(action: Action) -> dict[str, Any]:
        return {
            "tool_name": action.tool_name,
            "output_text": action.output_text,
            "token_count": action.token_count,
            "cost": action.cost,
            "error": action.error,
            "retried": action.retried,
            "duration_sec": action.duration_sec,
            "timestamp": action.timestamp,
            "metadata": dict(action.metadata),
        }

    @staticmethod
    def _action_from_dict(data: dict[str, Any]) -> Action:
        return Action(
            tool_name=data["tool_name"],
            output_text=data["output_text"],
            token_count=data.get("token_count", 0),
            cost=data.get("cost", 0.0),
            error=data.get("error", False),
            retried=data.get("retried", False),
            duration_sec=data.get("duration_sec", 0.0),
            timestamp=data.get("timestamp", 0.0),
            metadata=data.get("metadata", {}),
        )
