"""soma.testing — lightweight test harness for SOMA pipelines."""

from __future__ import annotations

from soma.engine import SOMAEngine, ActionResult
from soma.types import Action, Level, ResponseMode


class Monitor:
    """Context manager that wraps a SOMAEngine for use in tests.

    Usage::

        with Monitor(budget={"tokens": 10000}) as mon:
            mon.record("agent", action)
        mon.assert_healthy()
        mon.assert_below(ResponseMode.WARN)
    """

    def __init__(self, budget: dict[str, float] | None = None) -> None:
        self._budget = budget
        self._engine: SOMAEngine | None = None
        self._history: list[ActionResult] = []
        self._registered: set[str] = set()
        self._total_cost: float = 0.0

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "Monitor":
        self._engine = SOMAEngine(budget=self._budget)
        self._history.clear()
        self._registered.clear()
        self._total_cost = 0.0
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Don't suppress exceptions.
        return None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def record(self, agent_id: str, action: Action) -> ActionResult:
        """Record *action* for *agent_id*, auto-registering the agent if needed."""
        if self._engine is None:
            raise RuntimeError("Monitor must be used as a context manager.")
        if agent_id not in self._registered:
            self._engine.register_agent(agent_id)
            self._registered.add(agent_id)
        result = self._engine.record_action(agent_id, action)
        self._history.append(result)
        self._total_cost += action.cost
        return result

    def checkpoint(self) -> None:
        """Reset history, total_actions, and cost tracking without resetting the engine.

        Call this after a warm-up phase so that ``max_level``, ``total_actions``,
        ``total_cost``, and ``history`` reflect only the actions recorded *after*
        the checkpoint.  The underlying engine state (baselines, agent ladder) is
        preserved, which is what makes warm-up useful.
        """
        self._history.clear()
        self._total_cost = 0.0

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def history(self) -> list[ActionResult]:
        """All ActionResult objects in recording order."""
        return list(self._history)

    @property
    def total_actions(self) -> int:
        """Total number of actions recorded across all agents."""
        return len(self._history)

    @property
    def total_cost(self) -> float:
        """Cumulative cost (sum of action.cost) across all recorded actions."""
        return self._total_cost

    @property
    def current_level(self) -> Level:
        """Escalation level from the most recently recorded action."""
        if not self._history:
            return ResponseMode.OBSERVE
        return self._history[-1].level

    @property
    def max_level(self) -> Level:
        """Highest escalation level observed across all recorded results."""
        if not self._history:
            return ResponseMode.OBSERVE
        return max(r.level for r in self._history)

    # ------------------------------------------------------------------ #
    # Assertions                                                           #
    # ------------------------------------------------------------------ #

    def assert_healthy(self) -> None:
        """Raise AssertionError if the current (final) level is not HEALTHY.

        Uses ``current_level`` (most recent result) rather than ``max_level``
        so that transient cold-start escalation does not cause false failures.
        """
        if self.current_level != ResponseMode.OBSERVE:
            raise AssertionError(
                f"Expected current_level HEALTHY but got {self.current_level.name}"
                f" (max_level={self.max_level.name})"
            )

    def assert_below(self, level: Level) -> None:
        """Raise AssertionError if max_level is >= *level*.

        Uses ``max_level`` so any transient escalation is captured.
        For checking the final stable state only, use ``current_level``.
        """
        if self.max_level >= level:
            raise AssertionError(
                f"Expected max_level below {level.name} but got {self.max_level.name}"
            )
