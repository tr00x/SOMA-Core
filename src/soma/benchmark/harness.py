"""Benchmark harness — A/B engine runner with deep metric collection.

Runs identical action sequences through SOMAEngine with guidance enabled
vs disabled, collecting per-action metrics for controlled comparison.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import asdict

from soma.benchmark.metrics import (
    ActionMetric,
    BenchmarkMetrics,
    BenchmarkResult,
    ScenarioAction,
    ScenarioResult,
)
from soma.benchmark.scenarios import (
    context_exhaustion,
    degrading_session,
    healthy_session,
    multi_agent_coordination,
    retry_storm,
)
from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode


# ------------------------------------------------------------------
# Single-scenario runner
# ------------------------------------------------------------------


def _collect_metrics(
    engine: SOMAEngine,
    agent_id: str,
    actions: list[ScenarioAction],
    soma_enabled: bool,
) -> BenchmarkMetrics:
    """Process *actions* through *engine* and return collected metrics."""
    per_action: list[dict[str, object]] = []
    mode_transitions: list[dict[str, object]] = []
    total_errors = 0
    total_retries = 0
    total_tokens = 0
    processed_count = 0
    prev_mode: ResponseMode | None = None

    t0 = time.monotonic()

    for idx, sa in enumerate(actions):
        # Guidance-responsive skipping
        guidance_followed = False
        if soma_enabled and sa.guidance_responsive:
            current_level = engine.get_level(agent_id)
            if current_level >= ResponseMode.GUIDE:
                # Record the skip as a metric entry
                per_action.append(asdict(ActionMetric(
                    action_index=idx,
                    pressure=0.0,
                    uncertainty=0.0,
                    drift=0.0,
                    error_rate=0.0,
                    token_usage=0.0,
                    cost=0.0,
                    mode=current_level.name,
                    guidance_issued=True,
                    guidance_followed=True,
                )))
                continue  # skip this action

        # Feed action to engine
        action = Action(
            tool_name=sa.tool_name,
            output_text=sa.output_text,
            token_count=sa.token_count,
            error=sa.error,
            retried=sa.retried,
        )
        result = engine.record_action(agent_id, action)
        processed_count += 1

        if sa.error:
            total_errors += 1
        if sa.retried:
            total_retries += 1
        total_tokens += sa.token_count

        guidance_issued = result.mode >= ResponseMode.GUIDE

        per_action.append(asdict(ActionMetric(
            action_index=idx,
            pressure=result.pressure,
            uncertainty=result.vitals.uncertainty,
            drift=result.vitals.drift,
            error_rate=result.vitals.error_rate,
            token_usage=result.vitals.token_usage,
            cost=result.vitals.cost,
            mode=result.mode.name,
            guidance_issued=guidance_issued,
            guidance_followed=False,
        )))

        # Track mode transitions
        if prev_mode is not None and result.mode != prev_mode:
            mode_transitions.append({
                "from": prev_mode.name,
                "to": result.mode.name,
                "at_action": idx,
                "pressure": result.pressure,
            })
        prev_mode = result.mode

    elapsed = time.monotonic() - t0
    total_actions = processed_count

    # Compute error/retry rates
    error_rate = total_errors / total_actions if total_actions > 0 else 0.0
    retry_rate = total_retries / total_actions if total_actions > 0 else 0.0

    # Compute true/false positives:
    # For each action where guidance_issued=True, look ahead 3 actions.
    # If any of those has error=True in the original action list => true positive,
    # otherwise false positive.
    true_positives = 0
    false_positives = 0
    for entry in per_action:
        if not entry.get("guidance_issued") or entry.get("guidance_followed"):
            continue
        action_idx = entry["action_index"]
        # Look at next 3 actions in the original list
        lookahead = actions[action_idx + 1: action_idx + 4]
        if any(a.error for a in lookahead):
            true_positives += 1
        else:
            false_positives += 1

    return BenchmarkMetrics(
        total_errors=total_errors,
        error_rate=error_rate,
        total_retries=total_retries,
        retry_rate=retry_rate,
        total_tokens=total_tokens,
        duration_seconds=elapsed,
        total_actions=total_actions,
        mode_transitions=mode_transitions,
        false_positives=false_positives,
        true_positives=true_positives,
        per_action=per_action,
    )


def run_scenario(
    actions: list[ScenarioAction],
    soma_enabled: bool,
    agent_id: str = "benchmark-agent",
    budget: dict[str, float] | None = None,
) -> BenchmarkMetrics:
    """Run a scenario through a fresh SOMAEngine and collect metrics.

    With ``soma_enabled=True``, guidance_responsive actions are skipped when
    the engine's mode is >= GUIDE.  With ``soma_enabled=False``, all actions
    are processed unconditionally (guidance is still computed but not acted on).
    """
    engine = SOMAEngine(
        budget=budget or {"tokens": 500_000},
        auto_export=False,
        audit_enabled=False,
    )
    engine.register_agent(agent_id)
    return _collect_metrics(engine, agent_id, actions, soma_enabled)


# ------------------------------------------------------------------
# Multi-agent scenario runner
# ------------------------------------------------------------------


def run_multi_agent_scenario(
    agent_a_actions: list[ScenarioAction],
    agent_b_actions: list[ScenarioAction],
    soma_enabled: bool,
    budget: dict[str, float] | None = None,
) -> tuple[BenchmarkMetrics, BenchmarkMetrics]:
    """Run two interleaved agents through a shared engine with trust graph edges."""
    engine = SOMAEngine(
        budget=budget or {"tokens": 500_000},
        auto_export=False,
        audit_enabled=False,
    )
    engine.register_agent("agent-a")
    engine.register_agent("agent-b")
    engine.add_edge("agent-a", "agent-b", trust_weight=0.8)

    # Interleave: process one action from each agent alternately
    per_agent_actions: dict[str, list[ScenarioAction]] = {
        "agent-a": agent_a_actions,
        "agent-b": agent_b_actions,
    }
    # Build interleaved processing order
    max_len = max(len(agent_a_actions), len(agent_b_actions))

    # Track per-agent state for metric collection
    agent_metrics: dict[str, list[dict[str, object]]] = {"agent-a": [], "agent-b": []}
    agent_transitions: dict[str, list[dict[str, object]]] = {"agent-a": [], "agent-b": []}
    agent_errors: dict[str, int] = {"agent-a": 0, "agent-b": 0}
    agent_retries: dict[str, int] = {"agent-a": 0, "agent-b": 0}
    agent_tokens: dict[str, int] = {"agent-a": 0, "agent-b": 0}
    agent_processed: dict[str, int] = {"agent-a": 0, "agent-b": 0}
    agent_prev_mode: dict[str, ResponseMode | None] = {"agent-a": None, "agent-b": None}

    t0 = time.monotonic()

    for i in range(max_len):
        for aid, action_list in per_agent_actions.items():
            if i >= len(action_list):
                continue
            sa = action_list[i]

            # Guidance-responsive skipping
            if soma_enabled and sa.guidance_responsive:
                current_level = engine.get_level(aid)
                if current_level >= ResponseMode.GUIDE:
                    agent_metrics[aid].append(asdict(ActionMetric(
                        action_index=i,
                        pressure=0.0, uncertainty=0.0, drift=0.0,
                        error_rate=0.0, token_usage=0.0, cost=0.0,
                        mode=current_level.name,
                        guidance_issued=True, guidance_followed=True,
                    )))
                    continue

            action = Action(
                tool_name=sa.tool_name,
                output_text=sa.output_text,
                token_count=sa.token_count,
                error=sa.error,
                retried=sa.retried,
            )
            result = engine.record_action(aid, action)
            agent_processed[aid] += 1

            if sa.error:
                agent_errors[aid] += 1
            if sa.retried:
                agent_retries[aid] += 1
            agent_tokens[aid] += sa.token_count

            guidance_issued = result.mode >= ResponseMode.GUIDE
            agent_metrics[aid].append(asdict(ActionMetric(
                action_index=i,
                pressure=result.pressure,
                uncertainty=result.vitals.uncertainty,
                drift=result.vitals.drift,
                error_rate=result.vitals.error_rate,
                token_usage=result.vitals.token_usage,
                cost=result.vitals.cost,
                mode=result.mode.name,
                guidance_issued=guidance_issued,
                guidance_followed=False,
            )))

            pm = agent_prev_mode[aid]
            if pm is not None and result.mode != pm:
                agent_transitions[aid].append({
                    "from": pm.name,
                    "to": result.mode.name,
                    "at_action": i,
                    "pressure": result.pressure,
                })
            agent_prev_mode[aid] = result.mode

    elapsed = time.monotonic() - t0

    def _build_metrics(aid: str, action_list: list[ScenarioAction]) -> BenchmarkMetrics:
        processed = agent_processed[aid]
        er = agent_errors[aid] / processed if processed > 0 else 0.0
        rr = agent_retries[aid] / processed if processed > 0 else 0.0

        # TP/FP analysis
        tp = fp = 0
        for entry in agent_metrics[aid]:
            if not entry.get("guidance_issued") or entry.get("guidance_followed"):
                continue
            action_idx = entry["action_index"]
            lookahead = action_list[action_idx + 1: action_idx + 4]
            if any(a.error for a in lookahead):
                tp += 1
            else:
                fp += 1

        return BenchmarkMetrics(
            total_errors=agent_errors[aid],
            error_rate=er,
            total_retries=agent_retries[aid],
            retry_rate=rr,
            total_tokens=agent_tokens[aid],
            duration_seconds=elapsed,
            total_actions=processed,
            mode_transitions=agent_transitions[aid],
            false_positives=fp,
            true_positives=tp,
            per_action=agent_metrics[aid],
        )

    return _build_metrics("agent-a", agent_a_actions), _build_metrics("agent-b", agent_b_actions)


# ------------------------------------------------------------------
# Full benchmark runner
# ------------------------------------------------------------------


def _safe_reduction(baseline_val: float, soma_val: float) -> float:
    """Compute (baseline - soma) / baseline, safe against zero division."""
    if baseline_val <= 0:
        return 0.0
    return (baseline_val - soma_val) / baseline_val


def run_benchmark(runs_per_scenario: int = 5) -> BenchmarkResult:
    """Run all scenarios with SOMA on/off and compute A/B comparison.

    Each scenario is run ``runs_per_scenario`` times with seeds 1..N for
    both SOMA-enabled and baseline (disabled) conditions.
    """
    scenarios_defs = [
        ("healthy_session", "Healthy session — 50 actions, ~5% error, baseline for FP rate", healthy_session, False),
        ("degrading_session", "Degrading session — 80 actions, error ramp 0% to 60%", degrading_session, False),
        ("multi_agent_coordination", "Multi-agent coordination — 2 agents, 60 actions each", multi_agent_coordination, True),
        ("retry_storm", "Retry storm — 40 actions, 15 consecutive Bash failures", retry_storm, False),
        ("context_exhaustion", "Context exhaustion — 100 actions, tokens 100 to 5000", context_exhaustion, False),
    ]

    scenario_results: list[ScenarioResult] = []

    for name, description, gen_fn, is_multi in scenarios_defs:
        soma_runs: list[BenchmarkMetrics] = []
        baseline_runs: list[BenchmarkMetrics] = []

        for seed in range(1, runs_per_scenario + 1):
            if is_multi:
                a_actions, b_actions = gen_fn(seed=seed)
                # Use agent-b metrics (agent that receives propagated pressure)
                _, soma_m = run_multi_agent_scenario(a_actions, b_actions, soma_enabled=True)
                _, baseline_m = run_multi_agent_scenario(a_actions, b_actions, soma_enabled=False)
            else:
                actions = gen_fn(seed=seed)
                soma_m = run_scenario(actions, soma_enabled=True)
                baseline_m = run_scenario(actions, soma_enabled=False)

            soma_runs.append(soma_m)
            baseline_runs.append(baseline_m)

        # Average metrics across runs
        avg_soma_errors = sum(r.error_rate for r in soma_runs) / len(soma_runs)
        avg_base_errors = sum(r.error_rate for r in baseline_runs) / len(baseline_runs)
        avg_soma_retries = sum(r.retry_rate for r in soma_runs) / len(soma_runs)
        avg_base_retries = sum(r.retry_rate for r in baseline_runs) / len(baseline_runs)
        avg_soma_tokens = sum(r.total_tokens for r in soma_runs) / len(soma_runs)
        avg_base_tokens = sum(r.total_tokens for r in baseline_runs) / len(baseline_runs)
        avg_soma_time = sum(r.duration_seconds for r in soma_runs) / len(soma_runs)
        avg_base_time = sum(r.duration_seconds for r in baseline_runs) / len(baseline_runs)

        scenario_results.append(ScenarioResult(
            scenario_name=name,
            description=description,
            soma_runs=soma_runs,
            baseline_runs=baseline_runs,
            error_reduction=_safe_reduction(avg_base_errors, avg_soma_errors),
            retry_reduction=_safe_reduction(avg_base_retries, avg_soma_retries),
            token_savings=_safe_reduction(avg_base_tokens, avg_soma_tokens),
            time_savings=_safe_reduction(avg_base_time, avg_soma_time),
        ))

    # Overall averages across all scenarios
    n = len(scenario_results)
    overall_err = sum(s.error_reduction for s in scenario_results) / n if n else 0.0
    overall_retry = sum(s.retry_reduction for s in scenario_results) / n if n else 0.0
    overall_tokens = sum(s.token_savings for s in scenario_results) / n if n else 0.0

    return BenchmarkResult(
        scenarios=scenario_results,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        runs_per_scenario=runs_per_scenario,
        overall_error_reduction=overall_err,
        overall_retry_reduction=overall_retry,
        overall_token_savings=overall_tokens,
    )
