"""
SOMA Core Integration Run — практический тест всего pipeline.

Симулирует три сценария агентской работы:
  A) Здоровая сессия — нормальная работа
  B) Деградирующая сессия — нарастающие ошибки → эскалация режима
  C) Мульти-агент — propagation давления через trust-граф

Конфиг движка берётся из soma.toml (как в проде).
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from typing import NamedTuple

# ── project root on path ────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode, AutonomyMode, AgentConfig
from soma.policy import PolicyEngine, PolicyCondition, PolicyAction, Rule
from soma.halflife import compute_half_life, predict_success_rate

# ── reproducible randomness ─────────────────────────────────────────────────
SEED = 42
rng = random.Random(SEED)

# ── colour helpers ───────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"

def mode_colour(mode: ResponseMode) -> str:
    return {
        ResponseMode.OBSERVE: GREEN,
        ResponseMode.GUIDE:   CYAN,
        ResponseMode.WARN:    YELLOW,
        ResponseMode.BLOCK:   RED,
    }.get(mode, RESET)

def bar(value: float, width: int = 30) -> str:
    filled = int(value * width)
    c = GREEN if value < 0.4 else (YELLOW if value < 0.6 else RED)
    return c + "█" * filled + DIM + "░" * (width - filled) + RESET

# ── engine factory matching soma.toml ────────────────────────────────────────

def make_engine(token_budget: int = 1_000_000) -> SOMAEngine:
    return SOMAEngine(
        budget={"tokens": token_budget, "cost_usd": 50.0},
        custom_weights={
            "uncertainty": 1.2,
            "drift":       1.5,
            "error_rate":  2.5,
            "cost":        1.0,
            "token_usage": 0.6,
        },
        custom_thresholds={
            "guide": 0.40,
            "warn":  0.60,
            "block": 0.80,
        },
    )


# ── action helpers ────────────────────────────────────────────────────────────

TOOL_POOL = ["Bash", "Edit", "Read", "Write", "Grep", "Glob", "Agent", "WebFetch"]

def make_action(
    tool: str = "Bash",
    error: bool = False,
    tokens: int = 500,
    output_len: int = 200,
    cost: float = 0.002,
) -> Action:
    output = "x" * output_len if not error else "Error: " + "x" * 30
    return Action(
        tool_name=tool,
        output_text=output,
        token_count=tokens,
        duration_sec=rng.uniform(0.1, 2.0),
        error=error,
        cost=cost,
        metadata={},
    )


# ── scenario A: healthy session ──────────────────────────────────────────────

class StepRecord(NamedTuple):
    action_n: int
    tool: str
    error: bool
    pressure: float
    mode: ResponseMode
    vitals_uncertainty: float
    vitals_error_rate: float
    vitals_drift: float


def run_scenario_a() -> tuple[list[StepRecord], dict]:
    """50 actions, ~4% error rate — agent in good health."""
    engine = make_engine()
    engine.register_agent("agent-healthy",
        system_prompt="You are a senior developer. Complete tasks methodically.")

    records = []
    for i in range(50):
        error = rng.random() < 0.04
        tool = rng.choice(["Read", "Bash", "Grep", "Edit"])
        result = engine.record_action("agent-healthy", make_action(
            tool=tool, error=error, tokens=rng.randint(200, 800)
        ))
        records.append(StepRecord(
            action_n=i+1, tool=tool, error=error,
            pressure=result.pressure, mode=result.mode,
            vitals_uncertainty=result.vitals.uncertainty,
            vitals_error_rate=result.vitals.error_rate,
            vitals_drift=result.vitals.drift,
        ))

    snap = engine.get_snapshot("agent-healthy")
    return records, snap


def run_scenario_b() -> tuple[list[StepRecord], dict]:
    """70 actions: first 30 healthy, then errors spike (70%), tracking mode escalation."""
    engine = make_engine()
    engine.register_agent("agent-degrading",
        system_prompt="Analyze and refactor legacy codebase with unclear dependencies.")

    records = []
    for i in range(70):
        # Phase 1 (0-29): healthy; Phase 2 (30-69): high error rate
        error_rate = 0.04 if i < 30 else 0.70
        tool = rng.choice(TOOL_POOL)
        error = rng.random() < error_rate
        result = engine.record_action("agent-degrading", make_action(
            tool=tool, error=error,
            tokens=rng.randint(300, 1200),
            cost=rng.uniform(0.001, 0.008),
        ))
        records.append(StepRecord(
            action_n=i+1, tool=tool, error=error,
            pressure=result.pressure, mode=result.mode,
            vitals_uncertainty=result.vitals.uncertainty,
            vitals_error_rate=result.vitals.error_rate,
            vitals_drift=result.vitals.drift,
        ))

    snap = engine.get_snapshot("agent-degrading")
    return records, snap


def run_scenario_c() -> tuple[dict, dict]:
    """
    Multi-agent graph: orchestrator → [worker-a, worker-b]
    orchestrator накапливает давление → смотрим propagation к воркерам.
    """
    engine = make_engine()
    engine.register_agent("orchestrator",
        system_prompt="Orchestrate multi-step research pipeline.")
    engine.register_agent("worker-a",
        system_prompt="Execute code generation tasks.")
    engine.register_agent("worker-b",
        system_prompt="Execute data retrieval tasks.")

    engine.add_edge("orchestrator", "worker-a", trust_weight=0.9)
    engine.add_edge("orchestrator", "worker-b", trust_weight=0.7)

    # orchestrator gets stressed (40% errors)
    for i in range(40):
        error = rng.random() < (0.05 if i < 15 else 0.40)
        engine.record_action("orchestrator", make_action(
            tool="Agent", error=error, tokens=rng.randint(500, 2000)
        ))

    # workers do clean work
    for _ in range(20):
        engine.record_action("worker-a", make_action(
            tool="Bash", error=False, tokens=300
        ))
        engine.record_action("worker-b", make_action(
            tool="Read", error=False, tokens=200
        ))

    snaps = {
        "orchestrator": engine.get_snapshot("orchestrator"),
        "worker-a":     engine.get_snapshot("worker-a"),
        "worker-b":     engine.get_snapshot("worker-b"),
    }
    graph_data = {
        "trust_orch_a": engine._graph.get_trust("orchestrator", "worker-a"),
        "trust_orch_b": engine._graph.get_trust("orchestrator", "worker-b"),
        "snr_a": engine._graph.get_snr("worker-a"),
        "snr_b": engine._graph.get_snr("worker-b"),
    }
    return snaps, graph_data


def run_scenario_d() -> dict:
    """Policy engine + guardrail live on engine from scenario B."""
    engine = make_engine()
    engine.register_agent("policy-subject")

    # Pump up pressure via errors
    for i in range(30):
        error = i > 15
        engine.record_action("policy-subject", make_action(
            tool="Bash", error=error, tokens=500
        ))

    rules = [
        Rule("high-error",
             [PolicyCondition("error_rate", ">=", 0.3)],
             PolicyAction("warn", "Error rate > 30%")),
        Rule("combined-stress",
             [PolicyCondition("pressure", ">=", 0.5),
              PolicyCondition("error_rate", ">=", 0.2)],
             PolicyAction("block", "Combined stress: pressure + errors")),
    ]
    pe = PolicyEngine(rules)
    # grab last vitals from most recent ActionResult by running a dummy action
    result = engine.record_action("policy-subject", make_action("Bash", error=True, tokens=100))
    actions = pe.evaluate(result.vitals, result.pressure)

    return {
        "pressure": result.pressure,
        "mode": result.mode,
        "error_rate": result.vitals.error_rate,
        "policy_actions": [(a.action, a.message) for a in actions],
        "rules_fired": len(actions),
    }


# ── half-life benchmark ──────────────────────────────────────────────────────

def run_pressure_sensitivity() -> dict:
    """
    Analytical: what aggregate pressure does each raw error_rate produce?
    Exposes whether the formula is sensitive enough to escalate modes.
    """
    from soma.pressure import compute_aggregate_pressure
    from soma.vitals import sigmoid_clamp
    from soma.types import DriftMode

    weights = {"uncertainty": 1.2, "drift": 1.5, "error_rate": 2.5, "cost": 1.0, "token_usage": 0.6}
    results = {}
    for er in [0.10, 0.20, 0.30, 0.35, 0.50, 0.70, 0.80, 0.95]:
        # After baseline adapts to earlier healthy behavior (mean≈0.02, min_std=0.05 kicks in)
        # First contact: z is high → signal_p = 1.0. After a few actions, floor dominates.
        # Sustained: signal_p = floor = er (when er > 0.3), else 0.
        er_p = max(sigmoid_clamp((er - 0.02) / 0.05), er if er > 0.3 else 0)
        sp = {"error_rate": er_p, "uncertainty": 0.03, "drift": 0.02, "cost": 0.01, "token_usage": 0.01}
        p = compute_aggregate_pressure(sp, DriftMode.DIRECTIVE, weights=weights)
        mode = (ResponseMode.OBSERVE if p < 0.40
                else ResponseMode.GUIDE if p < 0.60
                else ResponseMode.WARN if p < 0.80
                else ResponseMode.BLOCK)
        results[er] = {"signal_p": er_p, "aggregate": p, "mode": mode}
    return results


def run_halflife_benchmark() -> dict:
    profiles = [
        ("junior",   20, 0.20),
        ("mid",      40, 0.10),
        ("senior",   70, 0.04),
        ("expert",  120, 0.01),
    ]
    results = {}
    for name, avg_len, err_rate in profiles:
        hl = compute_half_life(avg_len, err_rate)
        p10 = predict_success_rate(10, hl)
        p25 = predict_success_rate(25, hl)
        p50 = predict_success_rate(50, hl)
        results[name] = {"half_life": hl, "p@10": p10, "p@25": p25, "p@50": p50}
    return results


# ── report printing ───────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")


def print_timeline(records: list[StepRecord], stride: int = 5) -> None:
    prev_mode = None
    transitions = []
    print(f"\n  {'#':>3}  {'tool':<10} {'err'}  {'pressure':>8}  {'mode':<9}  {'bar'}")
    print(f"  {'─'*3}  {'─'*10} {'─'*3}  {'─'*8}  {'─'*9}  {'─'*30}")
    for r in records:
        if r.mode != prev_mode:
            transitions.append((r.action_n, prev_mode, r.mode))
            prev_mode = r.mode
        if r.action_n % stride == 0 or r.error or r.action_n == 1:
            c = mode_colour(r.mode)
            err_marker = RED + "ERR" + RESET if r.error else DIM + "   " + RESET
            print(f"  {r.action_n:>3}  {r.tool:<10} {err_marker}  {r.pressure:>8.3f}  "
                  f"{c}{r.mode.name:<9}{RESET}  {bar(r.pressure)}")

    if len(transitions) > 1:
        print(f"\n  {BOLD}Mode transitions:{RESET}")
        for n, frm, to in transitions[1:]:
            fc = mode_colour(frm) if frm else DIM
            tc = mode_colour(to)
            frm_name = frm.name if frm else "—"
            print(f"    action #{n:>2}: {fc}{frm_name}{RESET} → {tc}{to.name}{RESET}")


def main() -> None:
    t0 = time.time()

    # ── SCENARIO A ────────────────────────────────────────────────────────────
    section("SCENARIO A — Healthy session (50 actions, ~4% errors)")
    rec_a, snap_a = run_scenario_a()
    final_a = rec_a[-1]
    errors_a = sum(1 for r in rec_a if r.error)
    modes_a = {m: sum(1 for r in rec_a if r.mode == m) for m in ResponseMode}

    print(f"\n  Final pressure   : {bar(final_a.pressure)} {final_a.pressure:.3f}")
    print(f"  Final mode       : {mode_colour(final_a.mode)}{final_a.mode.name}{RESET}")
    print(f"  Errors           : {errors_a}/{len(rec_a)} ({errors_a/len(rec_a):.0%})")
    print(f"  Vitals (final)   : uncertainty={rec_a[-1].vitals_uncertainty:.3f}  "
          f"drift={rec_a[-1].vitals_drift:.3f}  error_rate={rec_a[-1].vitals_error_rate:.3f}")
    print(f"  Mode distribution: ", end="")
    for m, cnt in modes_a.items():
        if cnt:
            print(f"{mode_colour(m)}{m.name}×{cnt}{RESET}", end="  ")
    print()
    print_timeline(rec_a, stride=10)

    # ── SCENARIO B ────────────────────────────────────────────────────────────
    section("SCENARIO B — Degrading session (30 healthy → 40 high-error)")
    rec_b, snap_b = run_scenario_b()
    errors_b = sum(1 for r in rec_b if r.error)
    modes_b = {m: sum(1 for r in rec_b if r.mode == m) for m in ResponseMode}
    peak_b = max(r.pressure for r in rec_b)
    # Find escalation point (first non-OBSERVE mode)
    escalation_n = next((r.action_n for r in rec_b if r.mode != ResponseMode.OBSERVE), None)

    print(f"\n  Final pressure   : {bar(rec_b[-1].pressure)} {rec_b[-1].pressure:.3f}")
    print(f"  Peak pressure    : {bar(peak_b)} {peak_b:.3f}")
    print(f"  Final mode       : {mode_colour(rec_b[-1].mode)}{rec_b[-1].mode.name}{RESET}")
    print(f"  Errors           : {errors_b}/{len(rec_b)} ({errors_b/len(rec_b):.0%})")
    print(f"  First escalation : action #{escalation_n}")
    print(f"  Mode distribution: ", end="")
    for m, cnt in modes_b.items():
        if cnt:
            print(f"{mode_colour(m)}{m.name}×{cnt}{RESET}", end="  ")
    print()
    print(f"\n  Vitals phase-1 avg (actions 1-30):")
    ph1 = rec_b[:30]
    print(f"    uncertainty={sum(r.vitals_uncertainty for r in ph1)/len(ph1):.3f}  "
          f"error_rate={sum(r.vitals_error_rate for r in ph1)/len(ph1):.3f}  "
          f"drift={sum(r.vitals_drift for r in ph1)/len(ph1):.3f}")
    print(f"  Vitals phase-2 avg (actions 31-70):")
    ph2 = rec_b[30:]
    print(f"    uncertainty={sum(r.vitals_uncertainty for r in ph2)/len(ph2):.3f}  "
          f"error_rate={sum(r.vitals_error_rate for r in ph2)/len(ph2):.3f}  "
          f"drift={sum(r.vitals_drift for r in ph2)/len(ph2):.3f}")
    print_timeline(rec_b, stride=5)

    # ── SCENARIO C ────────────────────────────────────────────────────────────
    section("SCENARIO C — Multi-agent graph (orchestrator → worker-a, worker-b)")
    snaps_c, graph_c = run_scenario_c()

    for agent, snap in snaps_c.items():
        p = snap["pressure"]
        m = snap["mode"]
        ac = snap["action_count"]
        print(f"\n  {BOLD}{agent}{RESET}")
        print(f"    pressure   : {bar(p)} {p:.3f}")
        print(f"    mode       : {mode_colour(m)}{m.name}{RESET}")
        print(f"    actions    : {ac}")

    print(f"\n  Trust weights (after decay):")
    print(f"    orchestrator → worker-a : {graph_c['trust_orch_a']:.4f}")
    print(f"    orchestrator → worker-b : {graph_c['trust_orch_b']:.4f}")
    print(f"  Coordination SNR:")
    print(f"    worker-a SNR : {graph_c['snr_a']:.4f}")
    print(f"    worker-b SNR : {graph_c['snr_b']:.4f}")

    orch_p = snaps_c["orchestrator"]["pressure"]
    wa_p   = snaps_c["worker-a"]["pressure"]
    wb_p   = snaps_c["worker-b"]["pressure"]
    if orch_p > 0:
        print(f"\n  Propagation ratio:")
        print(f"    worker-a got {wa_p/orch_p:.1%} of orchestrator pressure "
              f"(trust=0.9, SNR={graph_c['snr_a']:.2f})")
        print(f"    worker-b got {wb_p/orch_p:.1%} of orchestrator pressure "
              f"(trust=0.7, SNR={graph_c['snr_b']:.2f})")

    # ── SCENARIO D ────────────────────────────────────────────────────────────
    section("SCENARIO D — PolicyEngine live evaluation")
    scenario_d = run_scenario_d()
    d = scenario_d
    print(f"\n  Agent state:")
    print(f"    pressure   : {bar(scenario_d['pressure'])} {scenario_d['pressure']:.3f}")
    print(f"    mode       : {mode_colour(scenario_d['mode'])}{scenario_d['mode'].name}{RESET}")
    print(f"    error_rate : {scenario_d['error_rate']:.3f}")
    print(f"\n  Policy results ({scenario_d['rules_fired']} rule(s) fired):")
    if scenario_d["policy_actions"]:
        for action, msg in scenario_d["policy_actions"]:
            c = RED if action == "block" else YELLOW
            print(f"    {c}[{action.upper()}]{RESET} {msg}")
    else:
        print(f"    {DIM}no rules fired{RESET}")

    # ── PRESSURE SENSITIVITY ──────────────────────────────────────────────────────
    section("PRESSURE SENSITIVITY — aggregate vs raw error_rate (guide=0.40  warn=0.60  block=0.80)")
    ps = run_pressure_sensitivity()
    print(f"\n  {'error_rate':>10}  {'signal_p':>8}  aggregate                      mode")
    print(f"  {'─'*10}  {'─'*8}  {'─'*30}  {'─'*9}")
    for er, d in ps.items():
        c = mode_colour(d["mode"])
        agg = d["aggregate"]
        print(f"  {er:>10.0%}  {d['signal_p']:>8.3f}  {bar(agg)}  {c}{d['mode'].name}{RESET}")

    first_guide = next((er for er, d in ps.items() if d["mode"] != ResponseMode.OBSERVE), None)
    first_warn  = next((er for er, d in ps.items() if d["mode"] == ResponseMode.WARN), None)
    first_block = next((er for er, d in ps.items() if d["mode"] == ResponseMode.BLOCK), None)
    print(f"\n  First GUIDE : {f'{first_guide:.0%}' if first_guide else 'never'}")
    print(f"  First WARN  : {f'{first_warn:.0%}' if first_warn else 'never'}")
    print(f"  First BLOCK : {f'{first_block:.0%}' if first_block else 'never'}")

    # ── HALF-LIFE BENCHMARK ────────────────────────────────────────────────────
    section("HALF-LIFE — P(success) across agent profiles")
    hl_data = run_halflife_benchmark()
    print(f"\n  {'profile':<10} {'half-life':>9}  {'P@10':>6}  {'P@25':>6}  {'P@50':>6}")
    print(f"  {'─'*10} {'─'*9}  {'─'*6}  {'─'*6}  {'─'*6}")
    for name, d2 in hl_data.items():
        c = GREEN if d2["p@25"] > 0.7 else (YELLOW if d2["p@25"] > 0.5 else RED)
        print(f"  {name:<10} {d2['half_life']:>9.1f}  "
              f"{c}{d2['p@10']:>6.3f}{RESET}  "
              f"{c}{d2['p@25']:>6.3f}{RESET}  "
              f"{c}{d2['p@50']:>6.3f}{RESET}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    section("SUMMARY")
    print(f"\n  Scenarios run    : 4 (A: healthy, B: degrading, C: multi-agent, D: policy)")
    print(f"  Total actions    : {len(rec_a) + len(rec_b) + 40 + 40 + 31}")
    print(f"  Elapsed          : {elapsed:.2f}s")
    print()

    # Core behaviour assertions — if any fail, something is wrong
    checks = [
        ("A: final mode = OBSERVE",         final_a.mode == ResponseMode.OBSERVE),
        ("A: final pressure < 0.40",        final_a.pressure < 0.40),
        ("B: escalated to GUIDE or above",  any(r.mode != ResponseMode.OBSERVE for r in rec_b[30:])),
        ("B: peak pressure ≥ GUIDE",        peak_b >= 0.40),
        ("C: workers absorbed propagation", wa_p > 0 or wb_p > 0),
        ("D: policy fired on high stress",  scenario_d["rules_fired"] >= 1),
    ]
    all_pass = True
    for label, passed in checks:
        icon = GREEN + "✓" + RESET if passed else RED + "✗" + RESET
        print(f"  {icon}  {label}")
        all_pass = all_pass and passed

    print()
    if all_pass:
        print(f"  {GREEN}{BOLD}All checks passed — core pipeline operating correctly.{RESET}")
    else:
        print(f"  {RED}{BOLD}Some checks failed — investigate above.{RESET}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
