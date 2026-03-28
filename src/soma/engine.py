"""SOMA Engine — the main pipeline. SPEC.md §11."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from soma.types import Action, Level, AutonomyMode, VitalsSnapshot, AgentConfig, DriftMode
from soma.ring_buffer import RingBuffer
from soma.vitals import (
    compute_uncertainty, compute_drift, compute_behavior_vector,
    compute_resource_vitals, determine_drift_mode, compute_output_entropy,
)
from soma.baseline import Baseline
from soma.pressure import compute_signal_pressure, compute_aggregate_pressure
from soma.budget import MultiBudget
from soma.ladder import Ladder
from soma.graph import PressureGraph
from soma.learning import LearningEngine
from soma.events import EventBus


@dataclass(frozen=True, slots=True)
class ActionResult:
    level: Level
    pressure: float
    vitals: VitalsSnapshot


class _AgentState:
    __slots__ = ("config", "ring_buffer", "baseline", "ladder", "known_tools",
                 "baseline_vector", "action_count")

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.ring_buffer: RingBuffer[Action] = RingBuffer(capacity=10)
        self.baseline = Baseline()
        self.ladder = Ladder()
        self.known_tools: list[str] = list(config.tools_allowed) if config.tools_allowed else []
        self.baseline_vector: list[float] | None = None
        self.action_count = 0


class SOMAEngine:
    """Main SOMA pipeline. Records actions, computes vitals -> pressure -> level."""

    def __init__(self, budget: dict[str, float] | None = None) -> None:
        self._agents: dict[str, _AgentState] = {}
        self._budget = MultiBudget(budget or {"tokens": 100_000})
        self._graph = PressureGraph()
        self._learning = LearningEngine()
        self._events = EventBus()

    @property
    def events(self) -> EventBus:
        return self._events

    @property
    def budget(self) -> MultiBudget:
        return self._budget

    def register_agent(
        self,
        agent_id: str,
        autonomy: AutonomyMode = AutonomyMode.HUMAN_ON_THE_LOOP,
        system_prompt: str = "",
        tools: list[str] | None = None,
    ) -> None:
        config = AgentConfig(
            agent_id=agent_id, autonomy=autonomy,
            system_prompt=system_prompt, tools_allowed=tools or [],
        )
        self._agents[agent_id] = _AgentState(config)
        self._graph.add_agent(agent_id)

    def add_edge(self, source: str, target: str, trust_weight: float = 1.0) -> None:
        self._graph.add_edge(source, target, trust_weight)

    def get_level(self, agent_id: str) -> Level:
        return self._agents[agent_id].ladder.current

    def get_snapshot(self, agent_id: str) -> dict[str, Any]:
        s = self._agents[agent_id]
        return {
            "level": s.ladder.current,
            "pressure": self._graph.get_effective_pressure(agent_id),
            "vitals": {
                "uncertainty": s.baseline.get("uncertainty"),
                "drift": s.baseline.get("drift"),
                "error_rate": s.baseline.get("error_rate"),
            },
            "action_count": s.action_count,
            "budget_health": self._budget.health(),
        }

    def record_action(self, agent_id: str, action: Action) -> ActionResult:
        s = self._agents[agent_id]

        # Track tool
        if action.tool_name not in s.known_tools:
            s.known_tools.append(action.tool_name)

        s.ring_buffer.append(action)
        s.action_count += 1
        actions = list(s.ring_buffer)

        # 1. Behavioral vitals
        uncertainty = compute_uncertainty(
            actions,
            baseline_tool_calls_avg=s.baseline.get("tool_calls"),
            baseline_tool_calls_std=s.baseline.get_std("tool_calls"),
            baseline_entropy=s.baseline.get("entropy"),
            baseline_entropy_std=s.baseline.get_std("entropy"),
            expected_format=None,
        )

        current_vec = compute_behavior_vector(actions, s.known_tools)
        drift = 0.0
        if s.baseline_vector is not None:
            drift = compute_drift(actions, s.baseline_vector, s.known_tools)
        if s.action_count % 10 == 0 or s.baseline_vector is None:
            s.baseline_vector = current_vec

        # 2. Resource vitals
        error_count = sum(1 for a in actions if a.error)
        rv = compute_resource_vitals(
            token_used=int(self._budget.spent.get("tokens", 0)),
            token_limit=int(self._budget.limits.get("tokens", 100000)),
            cost_spent=self._budget.spent.get("cost_usd", 0),
            cost_budget=self._budget.limits.get("cost_usd", 100),
            errors_in_window=error_count,
            actions_in_window=len(actions),
        )

        # 3. Drift mode
        drift_mode = determine_drift_mode(
            drift=drift, drift_threshold=0.3,
            error_rate=rv.error_rate, error_rate_baseline=s.baseline.get("error_rate"),
            progress_stalled=False,
            uncertainty=uncertainty, uncertainty_threshold=0.3,
        )

        # 4. Update baselines
        s.baseline.update("uncertainty", uncertainty)
        s.baseline.update("drift", drift)
        s.baseline.update("error_rate", rv.error_rate)
        s.baseline.update("tool_calls", float(len(actions)))
        s.baseline.update("entropy", compute_output_entropy(action.output_text))

        # 5. Per-signal pressure
        error_pressure = compute_signal_pressure(
            rv.error_rate, s.baseline.get("error_rate"), s.baseline.get_std("error_rate"))
        # Absolute floor: error_rate is objectively bad — baseline must not "normalize" errors.
        # If error_rate > 0.3, pressure floor = error_rate itself (high errors = high pressure).
        if rv.error_rate > 0.3:
            error_pressure = max(error_pressure, rv.error_rate)

        uncertainty_pressure = compute_signal_pressure(
            uncertainty, s.baseline.get("uncertainty"), s.baseline.get_std("uncertainty"))
        # Same for uncertainty: if retry_rate is high, uncertainty should not adapt away.
        retry_rate = sum(1 for a in actions if a.retried) / len(actions) if actions else 0.0
        if retry_rate > 0.3:
            uncertainty_pressure = max(uncertainty_pressure, retry_rate)

        signal_pressures = {
            "uncertainty": uncertainty_pressure,
            "drift": compute_signal_pressure(
                drift, s.baseline.get("drift"), s.baseline.get_std("drift")),
            "error_rate": error_pressure,
            "cost": rv.cost,
            "token_usage": rv.token_usage,
        }

        # 6. Aggregate
        internal = compute_aggregate_pressure(signal_pressures, drift_mode)

        # 7. Budget
        spend_kwargs = {}
        if "tokens" in self._budget.limits:
            spend_kwargs["tokens"] = float(action.token_count)
        if "cost_usd" in self._budget.limits:
            spend_kwargs["cost_usd"] = action.cost
        if spend_kwargs:
            self._budget.spend(**spend_kwargs)

        # 8. Graph
        self._graph.set_internal_pressure(agent_id, internal)
        self._graph.propagate()
        effective = self._graph.get_effective_pressure(agent_id)

        # 9. Trust
        if uncertainty > 0.5:
            self._graph.decay_trust(agent_id, uncertainty)
        else:
            self._graph.recover_trust(agent_id, uncertainty)

        # 10. Ladder
        old_level = s.ladder.current
        new_level = s.ladder.evaluate(effective, self._budget.health())

        # 11. Events + Learning
        if new_level != old_level:
            self._events.emit("level_changed", {
                "agent_id": agent_id,
                "old_level": old_level,
                "new_level": new_level,
                "pressure": effective,
            })
            self._learning.record_intervention(
                agent_id, old_level, new_level, effective, signal_pressures,
            )

        self._learning.evaluate(agent_id, effective, actions_since=1)

        return ActionResult(
            level=new_level,
            pressure=effective,
            vitals=VitalsSnapshot(
                uncertainty=uncertainty, drift=drift, drift_mode=drift_mode,
                token_usage=rv.token_usage, cost=rv.cost, error_rate=rv.error_rate,
            ),
        )
