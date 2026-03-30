"""SOMA Engine — the main pipeline. SPEC.md §11."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from soma.types import Action, ResponseMode, AutonomyMode, VitalsSnapshot, AgentConfig
from soma.errors import AgentNotFound
from soma.ring_buffer import RingBuffer
from soma.vitals import (
    compute_uncertainty, compute_drift, compute_behavior_vector,
    compute_resource_vitals, determine_drift_mode, compute_output_entropy,
    sigmoid_clamp,
)
from soma.baseline import Baseline
from soma.pressure import compute_signal_pressure, compute_aggregate_pressure, DEFAULT_WEIGHTS
from soma.budget import MultiBudget
from soma.guidance import pressure_to_mode
from soma.graph import PressureGraph
from soma.learning import LearningEngine
from soma.events import EventBus


@dataclass(frozen=True)
class ActionResult:
    mode: ResponseMode
    pressure: float
    vitals: VitalsSnapshot
    context_action: str = "pass"

    @property
    def level(self) -> ResponseMode:
        """Backward-compatible alias for mode."""
        return self.mode


class _AgentState:
    __slots__ = ("config", "ring_buffer", "baseline", "mode", "known_tools",
                 "baseline_vector", "action_count", "_last_active")

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.ring_buffer: RingBuffer[Action] = RingBuffer(capacity=10)
        self.baseline = Baseline()
        self.mode: ResponseMode = ResponseMode.OBSERVE
        self.known_tools: list[str] = list(config.tools_allowed) if config.tools_allowed else []
        self.baseline_vector: list[float] | None = None
        self.action_count = 0
        self._last_active: float = time.time()


class SOMAEngine:
    """Main SOMA pipeline. Records actions, computes vitals -> pressure -> level."""

    def __init__(
        self,
        budget: dict[str, float] | None = None,
        auto_export: bool = False,
        state_path: str | None = None,
        custom_weights: dict | None = None,
        custom_thresholds: dict | None = None,
    ) -> None:
        self._agents: dict[str, _AgentState] = {}
        self._budget = MultiBudget(budget or {"tokens": 100_000})
        self._graph = PressureGraph()
        self._learning = LearningEngine()
        self._events = EventBus()
        self._auto_export = auto_export
        self._state_path = state_path
        self._custom_weights = custom_weights
        self._custom_thresholds = custom_thresholds
        self._default_autonomy = AutonomyMode.HUMAN_ON_THE_LOOP

    @property
    def events(self) -> EventBus:
        return self._events

    @property
    def budget(self) -> MultiBudget:
        return self._budget

    def register_agent(
        self,
        agent_id: str,
        autonomy: AutonomyMode | None = None,
        system_prompt: str = "",
        tools: list[str] | None = None,
    ) -> None:
        if autonomy is None:
            autonomy = self._default_autonomy
        config = AgentConfig(
            agent_id=agent_id, autonomy=autonomy,
            system_prompt=system_prompt, tools_allowed=tools or [],
        )
        self._agents[agent_id] = _AgentState(config)
        self._graph.add_agent(agent_id)

    def add_edge(self, source: str, target: str, trust_weight: float = 1.0) -> None:
        self._graph.add_edge(source, target, trust_weight)

    def get_level(self, agent_id: str) -> ResponseMode:
        if agent_id not in self._agents:
            raise AgentNotFound(agent_id)
        return self._agents[agent_id].mode

    def get_snapshot(self, agent_id: str) -> dict[str, Any]:
        if agent_id not in self._agents:
            raise AgentNotFound(agent_id)
        s = self._agents[agent_id]
        pressure = self._graph.get_effective_pressure(agent_id)
        return {
            "level": s.mode,
            "mode": s.mode,
            "pressure": pressure,
            "vitals": {
                "uncertainty": s.baseline.get("uncertainty"),
                "drift": s.baseline.get("drift"),
                "error_rate": s.baseline.get("error_rate"),
                "cost": s.baseline.get("cost"),
                "token_usage": s.baseline.get("token_usage"),
            },
            "action_count": s.action_count,
            "budget_health": self._budget.health(),
        }

    def export_state(self, path: str | None = None) -> None:
        """Write current state to JSON file for dashboard polling."""
        import json
        from pathlib import Path

        if path is None:
            state_dir = Path.home() / ".soma"
            state_dir.mkdir(parents=True, exist_ok=True)
            path = str(state_dir / "state.json")

        state = {
            "agents": {},
            "budget": {
                "health": self._budget.health(),
                "limits": self._budget.limits,
                "spent": self._budget.spent,
            },
        }

        for agent_id, s in self._agents.items():
            # Skip the "default" placeholder agent — it's created by
            # create_engine_from_config() but has no real purpose in Claude Code
            if agent_id == "default":
                continue
            pressure = self._graph.get_effective_pressure(agent_id)
            state["agents"][agent_id] = {
                "level": s.mode.name,
                "pressure": pressure,
                "vitals": {
                    "uncertainty": s.baseline.get("uncertainty"),
                    "drift": s.baseline.get("drift"),
                    "error_rate": s.baseline.get("error_rate"),
                    "cost": s.baseline.get("cost"),
                    "token_usage": s.baseline.get("token_usage"),
                },
                "action_count": s.action_count,
            }

        Path(path).write_text(json.dumps(state, indent=2))

        # Also persist full engine state for restart recovery
        from soma.persistence import save_engine_state
        save_engine_state(self)

    def approve_escalation(self, agent_id: str) -> ResponseMode:
        """Human approves pending escalation. Re-evaluates and applies."""
        s = self._agents[agent_id]
        snap = self.get_snapshot(agent_id)
        s.mode = pressure_to_mode(snap["pressure"], self._custom_thresholds)
        return s.mode

    @classmethod
    def from_config(cls, config: dict | None = None) -> "SOMAEngine":
        """Create engine from soma.toml config."""
        if config is None:
            from soma.cli.config_loader import load_config
            config = load_config()

        budget = {}
        budget_cfg = config.get("budget", {})
        if "tokens" in budget_cfg:
            budget["tokens"] = budget_cfg["tokens"]
        if "cost_usd" in budget_cfg:
            budget["cost_usd"] = budget_cfg["cost_usd"]

        custom_weights = config.get("weights") or None
        custom_thresholds = config.get("thresholds") or None

        # Read default autonomy mode
        agents_cfg = config.get("agents", {}).get("default", {})
        autonomy_str = agents_cfg.get("autonomy", "human_on_the_loop")
        try:
            default_autonomy = AutonomyMode(autonomy_str)
        except ValueError:
            default_autonomy = AutonomyMode.HUMAN_ON_THE_LOOP

        engine = cls(
            budget=budget or {"tokens": 100_000},
            auto_export=True,
            custom_weights=custom_weights,
            custom_thresholds=custom_thresholds,
        )
        engine._default_autonomy = default_autonomy
        return engine

    def evict_stale_agents(self, ttl_seconds: float = 3600) -> list[str]:
        """Remove agents inactive for longer than ttl_seconds. Returns evicted IDs."""
        now = time.time()
        to_evict = [
            aid for aid, s in self._agents.items()
            if aid != "default" and (now - s._last_active) > ttl_seconds
        ]
        for aid in to_evict:
            del self._agents[aid]
            self._graph._nodes.pop(aid, None)
            self._graph._edges.pop(aid, None)
            self._graph._out_edges.pop(aid, None)
            self._learning._pending.pop(aid, None)
            self._learning._history.pop(aid, None)
        return to_evict

    def record_action(self, agent_id: str, action: Action) -> ActionResult:
        if agent_id not in self._agents:
            raise AgentNotFound(agent_id)
        s = self._agents[agent_id]

        # Track tool
        if action.tool_name not in s.known_tools:
            s.known_tools.append(action.tool_name)

        s.ring_buffer.append(action)
        s.action_count += 1
        s._last_active = time.time()
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

        # Time anomaly: if this action took much longer than average
        if action.duration_sec > 0 and s.action_count > 5:
            avg_duration = s.baseline.get("duration")
            std_duration = s.baseline.get_std("duration")
            if avg_duration > 0:
                time_deviation = (action.duration_sec - avg_duration) / max(std_duration, 0.1)
                if time_deviation > 2.0:  # > 2 std devs slower
                    # Boost uncertainty proportionally
                    time_boost = min(sigmoid_clamp(time_deviation) * 0.3, 0.3)
                    uncertainty = min(1.0, uncertainty + time_boost)

        # Also update duration baseline
        s.baseline.update("duration", action.duration_sec)

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

        # Add burn rate pressure
        if self._budget.health() < 1.0:
            # If burning faster than sustainable, add pressure
            for dim in self._budget.limits:
                overshoot = self._budget.projected_overshoot(dim, estimated_total_steps=100, current_step=s.action_count)
                if overshoot > 0:
                    signal_pressures["burn_rate"] = min(overshoot, 1.0)
                    break

        # Apply learning adjustments to weights, using custom_weights as base if set
        base_weights = dict(self._custom_weights) if self._custom_weights else dict(DEFAULT_WEIGHTS)
        # Merge: custom overrides defaults, learning adjustments applied on top
        adjusted_weights = dict(DEFAULT_WEIGHTS)
        adjusted_weights.update(base_weights)
        for signal in list(adjusted_weights):
            adj = self._learning.get_weight_adjustment(signal)
            adjusted_weights[signal] = max(0.2, adjusted_weights[signal] + adj)

        # 6. Aggregate with adjusted weights
        internal = compute_aggregate_pressure(signal_pressures, drift_mode, weights=adjusted_weights)



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

        # Grace period: don't penalize during cold start
        # Also zero the graph so get_snapshot returns 0
        if s.action_count <= s.baseline.min_samples:
            effective = 0.0
            self._graph.set_internal_pressure(agent_id, 0.0)
            self._graph._nodes[agent_id].effective_pressure = 0.0

        # 9. Trust
        if uncertainty > 0.5:
            self._graph.decay_trust(agent_id, uncertainty)
        else:
            self._graph.recover_trust(agent_id, uncertainty)

        # 10. Mode (replaces old Ladder evaluation)
        old_mode = s.mode
        new_mode = pressure_to_mode(effective, self._custom_thresholds)
        s.mode = new_mode

        # 11. Events + Learning
        if new_mode != old_mode:
            self._events.emit("level_changed", {
                "agent_id": agent_id,
                "old_level": old_mode,
                "new_level": new_mode,
                "pressure": effective,
            })
            self._learning.record_intervention(
                agent_id, old_mode, new_mode, effective, signal_pressures,
            )

        self._learning.evaluate(agent_id, effective, actions_since=1)

        context_action = "pass"
        if new_mode == ResponseMode.GUIDE:
            context_action = "guide"
        elif new_mode == ResponseMode.WARN:
            context_action = "warn"
        elif new_mode == ResponseMode.BLOCK:
            context_action = "block_destructive"

        result = ActionResult(
            mode=new_mode,
            pressure=effective,
            vitals=VitalsSnapshot(
                uncertainty=uncertainty, drift=drift, drift_mode=drift_mode,
                token_usage=rv.token_usage, cost=rv.cost, error_rate=rv.error_rate,
            ),
            context_action=context_action,
        )

        if self._auto_export:
            self.export_state(self._state_path)

        return result
