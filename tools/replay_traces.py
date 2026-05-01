#!/usr/bin/env python3
"""Replay public agent trajectories through SOMA detectors.

Reads HuggingFace's ``SWE-Gym/OpenHands-Sampled-Trajectories`` dataset
(GPT-4o + Claude-3.5-Sonnet runs on real GitHub issues, ~6k traces).
Converts each trace into a stream of ``Action`` events and feeds it
to ``SOMAEngine``, capturing every ``ContextualGuidance.evaluate()``
firing along the way.

For each pattern, aggregates:
  * total firings across the corpus
  * % of firings that occurred on a *failed* trace
  * % of *failed* traces that had at least one firing
  * % of *successful* traces that had at least one firing
  * natural recovery rate (fraction of firings followed by a recovery
    action within 3 steps)

This is observational — no injection, no treatment effect. Tells us
whether the detectors *detect* real problems on independent data.
Treatment effect is a separate question.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

# Local SOMA imports (after sys.path setup if running outside repo).
from soma.contextual_guidance import ContextualGuidance, REAL_PATTERN_KEYS
from soma.engine import SOMAEngine
from soma.types import Action

DATASET = "SWE-Gym/OpenHands-Sampled-Trajectories"
SPLIT = "train.raw"


# ────────────────────────────────────────────────────────────────────
# Trace → Action stream

# Map OpenHands tool names to SOMA's tool taxonomy.
_OH_TO_SOMA = {
    "execute_bash": "Bash",
    "str_replace_editor": "Edit",  # specialized below by command
    "finish": "Finish",
}


def _classify_str_replace_editor(args: dict) -> str:
    """The OpenHands str_replace_editor tool covers Read/Write/Edit
    via a ``command`` argument. Map to SOMA's discrete tools so
    detectors see meaningful tool diversity.
    """
    cmd = (args or {}).get("command", "")
    if cmd == "view":
        return "Read"
    if cmd == "create":
        return "Write"
    # str_replace, insert, undo_edit → all edits
    return "Edit"


def _looks_like_error(output: str) -> bool:
    """Heuristic error detection in tool output. Mirrors the live
    hook's strategy 2 (scan response text) since the dataset doesn't
    expose a structured per-call error flag.
    """
    if not output:
        return False
    lower = output.lower()
    error_markers = (
        "traceback (most recent call last)",
        "command not found",
        "permission denied",
        "no such file or directory",
        "syntaxerror",
        "modulenotfounderror",
        "importerror",
        "filenotfounderror",
        "exit code: 1",
        "error: ",
        "fatal: ",
    )
    return any(m in lower for m in error_markers)


@dataclass
class ConvertedAction:
    tool: str
    output: str
    error: bool
    args: dict


def trace_to_actions(messages: list[dict]) -> list[ConvertedAction]:
    """Walk the OpenAI-style message list and pair each tool_call
    with its tool_result message. Returns a list of converted
    actions in chronological order.
    """
    # Index tool messages by tool_call_id so we can look up the
    # corresponding result.
    results_by_id: dict[str, str] = {}
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id"):
            results_by_id[m["tool_call_id"]] = m.get("content", "") or ""

    actions: list[ConvertedAction] = []
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool = _OH_TO_SOMA.get(name, name)
            if name == "str_replace_editor":
                tool = _classify_str_replace_editor(args)
            tcid = tc.get("id", "")
            output = results_by_id.get(tcid, "")
            actions.append(ConvertedAction(
                tool=tool, output=output,
                error=_looks_like_error(output),
                args=args,
            ))
    return actions


# ────────────────────────────────────────────────────────────────────
# Replay

@dataclass
class Firing:
    trace_idx: int
    action_idx: int
    pattern: str
    severity: str
    resolved: bool


def replay_trace(
    trace_idx: int,
    actions: list[ConvertedAction],
    resolved: bool,
) -> tuple[list[Firing], int]:
    """Run a fresh engine through the action stream. Return all
    firings + the action count actually fed into the engine.
    """
    engine = SOMAEngine()
    agent_id = f"public-{trace_idx}"
    engine.register_agent(agent_id, display_name="public-trace")

    cg = ContextualGuidance(cooldown_actions=0)
    firings: list[Firing] = []
    action_log: list[dict] = []

    base_ts = time.time()
    for i, ca in enumerate(actions):
        action = Action(
            tool_name=ca.tool,
            output_text=ca.output,
            token_count=len(ca.output) // 4,
            error=ca.error,
            duration_sec=1.0,
        )
        engine.record_action(agent_id, action)
        action_log.append({
            "tool": ca.tool,
            "error": ca.error,
            "ts": base_ts + i,
            "output": ca.output[:100],
        })

        snap = engine.get_snapshot(agent_id)
        vitals = {
            "uncertainty": snap["vitals"].get("uncertainty", 0.0),
            "drift":       snap["vitals"].get("drift", 0.0),
            "error_rate":  snap["vitals"].get("error_rate", 0.0),
            "token_usage": snap["vitals"].get("token_usage", 0.0),
            "cost":        snap["vitals"].get("cost", 0.0),
        }
        try:
            budget_health = engine.get_budget_health()
        except Exception:
            budget_health = 1.0

        msg = cg.evaluate(
            action_log=action_log,
            current_tool=ca.tool,
            current_input=ca.args,
            vitals=vitals,
            budget_health=budget_health,
            action_number=i,
        )
        if msg is not None:
            firings.append(Firing(
                trace_idx=trace_idx,
                action_idx=i,
                pattern=msg.pattern,
                severity=msg.severity,
                resolved=resolved,
            ))
    return firings, len(actions)


# ────────────────────────────────────────────────────────────────────
# Aggregation

def _recovery_within(actions: list[ConvertedAction], from_idx: int, window: int = 3) -> bool:
    """Did the agent recover within ``window`` actions after a firing?

    Recovery = a different tool family from ``from_idx`` AND no error.
    """
    base_tool = actions[from_idx].tool
    end = min(from_idx + 1 + window, len(actions))
    for j in range(from_idx + 1, end):
        a = actions[j]
        if a.tool != base_tool and not a.error:
            return True
    return False


def aggregate(
    firings: list[Firing],
    actions_by_trace: dict[int, list[ConvertedAction]],
    resolved_by_trace: dict[int, bool],
) -> dict:
    by_pattern: dict[str, dict] = defaultdict(lambda: {
        "fires": 0,
        "fires_failed": 0,
        "fires_successful": 0,
        "traces_with_fire": set(),
        "traces_with_fire_failed": set(),
        "traces_with_fire_successful": set(),
        "recoveries": 0,
        "actions_after_fire": 0,
    })

    for f in firings:
        e = by_pattern[f.pattern]
        e["fires"] += 1
        e["traces_with_fire"].add(f.trace_idx)
        if f.resolved:
            e["fires_successful"] += 1
            e["traces_with_fire_successful"].add(f.trace_idx)
        else:
            e["fires_failed"] += 1
            e["traces_with_fire_failed"].add(f.trace_idx)
        actions = actions_by_trace.get(f.trace_idx) or []
        if f.action_idx < len(actions):
            recovered = _recovery_within(actions, f.action_idx, window=3)
            if recovered:
                e["recoveries"] += 1
            e["actions_after_fire"] += 1

    total_traces = len(resolved_by_trace)
    failed_traces = sum(1 for r in resolved_by_trace.values() if not r)
    successful_traces = total_traces - failed_traces

    out = {
        "total_traces": total_traces,
        "failed_traces": failed_traces,
        "successful_traces": successful_traces,
        "patterns": {},
    }
    for pat, e in by_pattern.items():
        n_failed = len(e["traces_with_fire_failed"])
        n_succ = len(e["traces_with_fire_successful"])
        precision_failed = (
            e["fires_failed"] / e["fires"] if e["fires"] else 0.0
        )
        prevalence_failed = n_failed / failed_traces if failed_traces else 0.0
        prevalence_succ = n_succ / successful_traces if successful_traces else 0.0
        recovery_rate = (
            e["recoveries"] / e["actions_after_fire"]
            if e["actions_after_fire"] else 0.0
        )
        # Lift = how much more likely a fire is on a failed trace
        # vs the base failure rate. lift > 1 → detector is predictive.
        base_fail_rate = (
            failed_traces / total_traces if total_traces else 0.0
        )
        lift = (
            precision_failed / base_fail_rate
            if base_fail_rate > 0 else 0.0
        )
        out["patterns"][pat] = {
            "fires": e["fires"],
            "fires_on_failed": e["fires_failed"],
            "fires_on_successful": e["fires_successful"],
            "precision_failed": round(precision_failed, 4),
            "base_fail_rate": round(base_fail_rate, 4),
            "lift": round(lift, 3),
            "traces_fired_failed": n_failed,
            "traces_fired_successful": n_succ,
            "prevalence_failed": round(prevalence_failed, 4),
            "prevalence_successful": round(prevalence_succ, 4),
            "natural_recovery_rate_3": round(recovery_rate, 4),
        }
    return out


# ────────────────────────────────────────────────────────────────────
# Main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=200,
                        help="Max traces to process (default: 200)")
    parser.add_argument("--out", default="public_traces_report.json",
                        help="Output JSON path")
    args = parser.parse_args(argv)

    print(f"[replay] loading {DATASET} (streaming, limit={args.limit})...")
    from datasets import load_dataset
    ds = load_dataset(DATASET, split=SPLIT, streaming=True)

    firings: list[Firing] = []
    actions_by_trace: dict[int, list[ConvertedAction]] = {}
    resolved_by_trace: dict[int, bool] = {}
    tool_distribution: Counter = Counter()
    error_count = 0
    total_actions = 0

    for idx, row in enumerate(ds):
        if idx >= args.limit:
            break
        messages = row.get("messages") or []
        resolved = bool(row.get("resolved", False))
        actions = trace_to_actions(messages)
        if not actions:
            continue

        actions_by_trace[idx] = actions
        resolved_by_trace[idx] = resolved
        for a in actions:
            tool_distribution[a.tool] += 1
            if a.error:
                error_count += 1
        total_actions += len(actions)

        trace_firings, _ = replay_trace(idx, actions, resolved)
        firings.extend(trace_firings)

        if (idx + 1) % 25 == 0:
            print(f"  [replay] processed {idx + 1} traces, "
                  f"{len(firings)} firings so far")

    print(f"\n[replay] DONE — {len(actions_by_trace)} traces, "
          f"{total_actions} actions, {error_count} errors")
    print(f"[replay] tool distribution: {dict(tool_distribution.most_common())}")

    report = aggregate(firings, actions_by_trace, resolved_by_trace)
    report["meta"] = {
        "dataset": DATASET,
        "split": SPLIT,
        "total_actions": total_actions,
        "total_errors": error_count,
        "active_patterns": list(REAL_PATTERN_KEYS),
        "tool_distribution": dict(tool_distribution),
    }

    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)

    # Print human-readable summary.
    print("\n=== Replay summary ===")
    print(f"  traces       : {report['total_traces']}")
    print(f"  failed       : {report['failed_traces']}")
    print(f"  successful   : {report['successful_traces']}")
    print(f"  total actions: {total_actions}")
    print()
    if not report["patterns"]:
        print("  NO PATTERN FIRINGS — all detectors silent on this corpus.")
    else:
        base = report["failed_traces"] / report["total_traces"] if report["total_traces"] else 0.0
        print(f"  base failure rate: {base:.3f}  (lift > 1 → predictive)")
        print()
        hdr = (
            f"  {'pattern':<22} {'fires':>6} {'on_fail':>8} {'on_succ':>8} "
            f"{'prec_fail':>10} {'lift':>6} "
            f"{'prev_fail':>10} {'prev_succ':>10} {'recov':>6}"
        )
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for pat, m in sorted(
            report["patterns"].items(), key=lambda x: -x[1]["fires"]
        ):
            print(
                f"  {pat:<22} {m['fires']:>6} "
                f"{m['fires_on_failed']:>8} {m['fires_on_successful']:>8} "
                f"{m['precision_failed']:>10.3f} {m['lift']:>6.2f} "
                f"{m['prevalence_failed']:>10.3f} "
                f"{m['prevalence_successful']:>10.3f} "
                f"{m['natural_recovery_rate_3']:>6.3f}"
            )
    print(f"\n  Report written to: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
