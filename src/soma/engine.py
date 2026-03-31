"""SOMA Engine — the main pipeline. SPEC.md §11."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from soma.types import Action, ResponseMode, AutonomyMode, VitalsSnapshot, AgentConfig, PressureVector
from soma.errors import AgentNotFound
from soma.ring_buffer import RingBuffer
from soma.vitals import (
    compute_uncertainty, compute_drift, compute_behavior_vector,
    compute_resource_vitals, determine_drift_mode, compute_output_entropy,
    sigmoid_clamp, compute_goal_coherence, compute_baseline_integrity,
    classify_uncertainty, estimate_task_complexity,
)
from soma.halflife import compute_half_life, predict_success_rate, generate_handoff_suggestion
from soma.baseline import Baseline
from soma.pressure import compute_signal_pressure, compute_aggregate_pressure, DEFAULT_WEIGHTS
from soma.budget import MultiBudget
from soma.guidance import pressure_to_mode, DEFAULT_THRESHOLDS
from soma.graph import PressureGraph
from soma.learning import LearningEngine
from soma.events import EventBus


@dataclass(frozen=True)
class ActionResult:
    mode: ResponseMode
    pressure: float
    vitals: VitalsSnapshot
    context_action: str = "pass"
    pressure_vector: PressureVector | None = None
    handoff_suggestion: str | None = None

    @property
    def level(self) -> ResponseMode:
        """Backward-compatible alias for mode."""
        return self.mode


class _AgentState:
    __slots__ = ("config", "ring_buffer", "baseline", "mode", "known_tools",
                 "baseline_vector", "action_count", "_last_active",
                 "initial_task_vector", "initial_known_tools", "task_complexity_score")

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.ring_buffer: RingBuffer[Action] = RingBuffer(capacity=10)
        self.baseline = Baseline()
        self.mode: ResponseMode = ResponseMode.OBSERVE
        self.known_tools: list[str] = list(config.tools_allowed) if config.tools_allowed else []
        self.baseline_vector: list[float] | None = None
        self.action_count = 0
        self._last_active: float = time.time()
        self.initial_task_vector: list[float] | None = None
        self.initial_known_tools: list[str] | None = None
        self.task_complexity_score: float | None = None


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
        self._vitals_config: dict[str, Any] = {}

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
        state = _AgentState(config)
        # Compute task complexity from system_prompt if available (most accurate source).
        # Falls back to first action output in record_action() if prompt is empty.
        if system_prompt:
            vitals_cfg = self._vitals_config or {}
            complexity_cfg = {
                k[len("complexity_"):]: v
                for k, v in vitals_cfg.items()
                if k.startswith("complexity_")
            }
            state.task_complexity_score = estimate_task_complexity(
                system_prompt, complexity_cfg or None
            )
        self._agents[agent_id] = state
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
        engine._vitals_config = config.get("vitals", {})
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

        # Capture task complexity on first action (PRS-03)
        vitals_cfg = self._vitals_config or {}
        if s.action_count == 1 and s.task_complexity_score is None:
            complexity_cfg = {
                k[len("complexity_"):]: v
                for k, v in vitals_cfg.items()
                if k.startswith("complexity_")
            }
            s.task_complexity_score = estimate_task_complexity(
                action.output_text, complexity_cfg or None
            )

        # Capture initial task signature after warmup window (per D-01)
        warmup_actions = vitals_cfg.get("goal_coherence_warmup_actions", 5)
        if s.action_count == warmup_actions and s.initial_task_vector is None:
            s.initial_known_tools = list(s.known_tools)  # snapshot, not reference
            s.initial_task_vector = compute_behavior_vector(actions, s.initial_known_tools)

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

        # Uncertainty classification (VIT-02)
        uncertainty_type: str | None = None
        if actions:
            task_entropy_text = " ".join(a.output_text for a in actions)
            task_entropy = compute_output_entropy(task_entropy_text)
            uc_cfg = {
                k[len("uncertainty_classification_"):]: v
                for k, v in vitals_cfg.items()
                if k.startswith("uncertainty_classification_")
            }
            uncertainty_type = classify_uncertainty(uncertainty, task_entropy, uc_cfg or None)

        # Apply epistemic/aleatoric pressure modulation
        epistemic_multiplier = vitals_cfg.get("epistemic_pressure_multiplier", 1.3)
        aleatoric_multiplier = vitals_cfg.get("aleatoric_pressure_multiplier", 0.7)
        if uncertainty_type == "epistemic":
            uncertainty_pressure = min(1.0, uncertainty_pressure * epistemic_multiplier)
        elif uncertainty_type == "aleatoric":
            uncertainty_pressure = uncertainty_pressure * aleatoric_multiplier

        signal_pressures = {
            "uncertainty": uncertainty_pressure,
            "drift": compute_signal_pressure(
                drift, s.baseline.get("drift"), s.baseline.get_std("drift")),
            "error_rate": error_pressure,
            "cost": rv.cost,
            "token_usage": rv.token_usage,
        }

        # Load fingerprint once — used for both baseline integrity and half-life
        baseline_integrity = True  # Default: intact
        predicted_success_rate: float | None = None
        half_life_warning = False
        handoff_suggestion: str | None = None
        min_samples = vitals_cfg.get("baseline_integrity_min_samples", 10)
        error_ratio = vitals_cfg.get("baseline_integrity_error_ratio", 2.0)
        min_error_rate = vitals_cfg.get("baseline_integrity_min_error_rate", 0.20)
        hl_min_samples = vitals_cfg.get("half_life_min_samples", 3)
        hl_lookahead = int(vitals_cfg.get("half_life_lookahead_actions", 10))
        hl_threshold = vitals_cfg.get("half_life_success_threshold", 0.5)
        try:
            from soma.state import get_fingerprint_engine
            fp_engine = get_fingerprint_engine()
            fp = fp_engine.get(agent_id)
            if fp is not None:
                # Baseline integrity (D-08, D-10, D-11)
                baseline_integrity = compute_baseline_integrity(
                    baseline_error_rate=s.baseline.get("error_rate"),
                    current_error_rate=rv.error_rate,
                    fingerprint_avg_error_rate=fp.avg_error_rate,
                    fingerprint_sample_count=fp.sample_count,
                    min_samples=min_samples,
                    error_ratio_threshold=error_ratio,
                    min_current_error_rate=min_error_rate,
                )
                # Half-life estimation (HLF-01, HLF-02)
                if fp.sample_count >= hl_min_samples:
                    half_life = compute_half_life(fp.avg_session_length, fp.avg_error_rate)
                    predicted_success_rate = predict_success_rate(s.action_count, half_life)
                    # Warn when projected success rate will cross threshold within lookahead
                    projected = predict_success_rate(s.action_count + hl_lookahead, half_life)
                    if projected < hl_threshold:
                        half_life_warning = True
                        handoff_suggestion = generate_handoff_suggestion(
                            agent_id, s.action_count, half_life, predicted_success_rate
                        )
                        self._events.emit("half_life_warning", {
                            "agent_id": agent_id,
                            "action_count": s.action_count,
                            "predicted_success_rate": predicted_success_rate,
                            "half_life": half_life,
                            "handoff_suggestion": handoff_suggestion,
                        })
        except Exception:
            pass  # Fingerprint unavailable — defaults apply

        # Goal coherence (None during warmup)
        goal_coherence: float | None = None
        if s.initial_task_vector is not None and s.initial_known_tools is not None:
            goal_coherence = compute_goal_coherence(actions, s.initial_task_vector, s.initial_known_tools)
            # Invert: low coherence = high divergence = high pressure (per research pitfall 4)
            goal_coherence_divergence = 1.0 - goal_coherence
            signal_pressures["goal_coherence"] = compute_signal_pressure(
                goal_coherence_divergence,
                s.baseline.get("goal_coherence"),
                s.baseline.get_std("goal_coherence"),
            )
            s.baseline.update("goal_coherence", goal_coherence_divergence)

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

        # 6. Apply upstream vector influence (PRS-01): if this agent has incoming edges,
        # boost per-signal pressures based on the upstream effective_pressure_vector
        # from the previous propagation round. This lets downstream agents react
        # precisely to the *cause* of upstream pressure, not just its magnitude.
        upstream_vec = self._graph.get_effective_pressure_vector(agent_id)
        if upstream_vec is not None and self._graph._edges.get(agent_id):
            signal_pressures["uncertainty"] = max(
                signal_pressures["uncertainty"], self._graph.damping * upstream_vec.uncertainty
            )
            signal_pressures["drift"] = max(
                signal_pressures["drift"], self._graph.damping * upstream_vec.drift
            )
            signal_pressures["error_rate"] = max(
                signal_pressures["error_rate"], self._graph.damping * upstream_vec.error_rate
            )
            signal_pressures["cost"] = max(
                signal_pressures["cost"], self._graph.damping * upstream_vec.cost
            )

        # 6b. Aggregate with adjusted weights
        internal = compute_aggregate_pressure(signal_pressures, drift_mode, weights=adjusted_weights)

        # Build pressure vector from (possibly upstream-boosted) signal pressures
        pressure_vector = PressureVector(
            uncertainty=signal_pressures.get("uncertainty", 0.0),
            drift=signal_pressures.get("drift", 0.0),
            error_rate=signal_pressures.get("error_rate", 0.0),
            cost=signal_pressures.get("cost", 0.0),
        )

        # 7. Budget
        spend_kwargs = {}
        if "tokens" in self._budget.limits:
            spend_kwargs["tokens"] = float(action.token_count)
        if "cost_usd" in self._budget.limits:
            spend_kwargs["cost_usd"] = action.cost
        if spend_kwargs:
            self._budget.spend(**spend_kwargs)

        # 8. Graph — set both scalar and vector, then propagate
        self._graph.set_internal_pressure(agent_id, internal)
        self._graph.set_internal_pressure_vector(agent_id, pressure_vector)
        self._graph.propagate()
        effective = self._graph.get_effective_pressure(agent_id)

        # Grace period: don't penalize during cold start
        # Also zero the graph so get_snapshot returns 0
        if s.action_count <= s.baseline.min_samples:
            effective = 0.0
            self._graph.set_internal_pressure(agent_id, 0.0)
            self._graph._nodes[agent_id].effective_pressure = 0.0
            zero_vec = PressureVector()
            self._graph.set_internal_pressure_vector(agent_id, zero_vec)
            self._graph._nodes[agent_id].effective_pressure_vector = zero_vec

        # 9. Trust
        if uncertainty > 0.5:
            self._graph.decay_trust(agent_id, uncertainty)
        else:
            self._graph.recover_trust(agent_id, uncertainty)

        # 10. Mode — apply task-complexity threshold adjustment (PRS-03)
        # High complexity lowers thresholds so escalation happens faster.
        effective_thresholds = dict(self._custom_thresholds) if self._custom_thresholds else {}
        if s.task_complexity_score is not None and s.task_complexity_score > 0.5:
            # Complexity in (0.5, 1.0] → reduce thresholds by up to 0.20
            reduction = 0.4 * (s.task_complexity_score - 0.5)  # up to 0.20
            for key in ("guide", "warn", "block"):
                base = effective_thresholds.get(key, DEFAULT_THRESHOLDS[key])
                effective_thresholds[key] = max(0.10, base - reduction)

        old_mode = s.mode
        new_mode = pressure_to_mode(effective, effective_thresholds or None)
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
                goal_coherence=goal_coherence,
                baseline_integrity=baseline_integrity,
                uncertainty_type=uncertainty_type,
                task_complexity=s.task_complexity_score,
                predicted_success_rate=predicted_success_rate,
                half_life_warning=half_life_warning,
            ),
            context_action=context_action,
            pressure_vector=pressure_vector,
            handoff_suggestion=handoff_suggestion,
        )

        if self._auto_export:
            self.export_state(self._state_path)

        return result
