"""SOMA Notification hook — injects agent state into LLM context.

Runs on UserPromptSubmit — before the agent starts reasoning.

v3: Structured output with configurable verbosity.
- minimal: status line only (1 line)
- normal: status + top 2 findings (2-4 lines)
- verbose: everything (up to 8 lines)

Output goes to stdout as "additional context" in Claude Code.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def _analyze_patterns(action_log: list[dict]) -> list[str]:
    """Analyze recent action log and return actionable tips.

    Each tip is a short, specific instruction — not a metric.
    Returns at most 2 tips to avoid noise.
    """
    if not action_log:
        return []

    tips: list[str] = []
    recent = action_log[-10:]

    # Pattern 1: Writes without Reads
    writes_since_read = 0
    for entry in reversed(recent):
        if entry["tool"] in ("Write", "Edit", "NotebookEdit"):
            writes_since_read += 1
        elif entry["tool"] == "Read":
            break
    if writes_since_read >= 2:
        tips.append(
            f"[pattern] {writes_since_read} writes without a Read — "
            f"read the file before editing to avoid blind mutations"
        )

    # Pattern 2: Consecutive Bash failures
    consecutive_bash_errors = 0
    for entry in reversed(recent):
        if entry["tool"] == "Bash" and entry.get("error"):
            consecutive_bash_errors += 1
        elif entry["tool"] == "Bash":
            break
        else:
            continue
    if consecutive_bash_errors >= 2:
        tips.append(
            f"[pattern] {consecutive_bash_errors} consecutive Bash failures — "
            f"stop retrying, check assumptions and environment first"
        )

    # Pattern 3: High error rate
    if len(recent) >= 5:
        error_count = sum(1 for e in recent if e.get("error"))
        error_rate = error_count / len(recent)
        if error_rate >= 0.3:
            tips.append(
                f"[pattern] {error_count}/{len(recent)} recent actions failed — "
                f"slow down, read relevant files and verify approach before acting"
            )

    # Pattern 4: Thrashing same file
    if len(recent) >= 4:
        edit_files = [
            e["file"] for e in recent
            if e["tool"] in ("Write", "Edit") and e.get("file")
        ]
        if edit_files:
            from collections import Counter
            file_counts = Counter(edit_files)
            thrashed = [(f, c) for f, c in file_counts.items() if c >= 3]
            if thrashed:
                fname, count = thrashed[0]
                short = fname.rsplit("/", 1)[-1] if "/" in fname else fname
                tips.append(
                    f"[pattern] edited {short} {count}x in {len(recent)} actions — "
                    f"plan the full change before editing, avoid incremental fixes"
                )

    return tips[:2]


def _collect_findings(
    action_log: list[dict],
    vitals: dict,
    pressure: float,
    level_name: str,
    actions: int,
    hook_config: dict,
) -> list[tuple[int, str]]:
    """Collect all findings as (priority, message) tuples.

    Priority: 0 = critical (always show), 1 = important, 2 = informational.
    """
    findings: list[tuple[int, str]] = []

    # Level status (priority 0 at elevated levels)
    if level_name == "CAUTION":
        findings.append((0, "[status] CAUTION — verify before mutating"))
    elif level_name == "DEGRADE":
        findings.append((0, "[status] DEGRADED — Bash/Agent blocked"))
    elif level_name in ("QUARANTINE", "RESTART", "SAFE_MODE"):
        findings.append((0, f"[status] {level_name} — only Read/Glob/Grep available"))

    # Quality (priority 0 if bad)
    if hook_config.get("quality", True):
        try:
            from soma.hooks.common import get_quality_tracker
            qt = get_quality_tracker()
            report = qt.get_report()
            if report.total_writes + report.total_bashes >= 5:
                if report.grade in ("D", "F"):
                    issues_str = ", ".join(report.issues) if report.issues else "quality declining"
                    findings.append((0, f"[quality] grade={report.grade} ({issues_str})"))
                elif report.grade == "C":
                    findings.append((2, f"[quality] grade={report.grade}"))
        except Exception:
            pass

    # Prediction (priority 1)
    if hook_config.get("predict", True):
        try:
            from soma.hooks.common import get_predictor
            from soma.ladder import THRESHOLDS as _LADDER_THRESHOLDS
            predictor = get_predictor()
            if predictor._pressures:
                thresholds = sorted(t[0] for t in _LADDER_THRESHOLDS if t[0] > pressure)
                if thresholds:
                    pred = predictor.predict(thresholds[0])
                    if pred.will_escalate:
                        findings.append((
                            1,
                            f"[predict] escalation in ~{pred.actions_ahead} actions "
                            f"({pred.dominant_reason}) — slow down"
                        ))
        except Exception:
            pass

    # Patterns (priority 1)
    tips = _analyze_patterns(action_log)
    for tip in tips:
        findings.append((1, tip))

    # Scope drift (priority 1)
    if hook_config.get("task_tracking", True):
        try:
            from soma.hooks.common import get_task_tracker
            tracker = get_task_tracker()
            ctx = tracker.get_context()
            if ctx.scope_drift >= 0.4 and ctx.drift_explanation:
                findings.append((1, f"[scope] {ctx.drift_explanation}"))
        except Exception:
            pass

    # Fingerprint divergence (priority 2)
    if hook_config.get("fingerprint", True):
        try:
            from soma.hooks.common import get_fingerprint_engine, _get_session_agent_id
            fp_engine = get_fingerprint_engine()
            div, explanation = fp_engine.check_divergence(_get_session_agent_id(), action_log)
            if div >= 0.3 and explanation:
                findings.append((2, f"[fingerprint] {explanation}"))
        except Exception:
            pass

    # RCA (priority 1 at elevated, 2 at healthy)
    try:
        from soma.rca import diagnose
        rca = diagnose(action_log, vitals, pressure, level_name, actions)
        if rca:
            priority = 1 if level_name != "HEALTHY" else 2
            findings.append((priority, f"[why] {rca}"))
    except Exception:
        pass

    return findings


def main():
    try:
        from soma.hooks.common import (
            STATE_PATH, _get_session_agent_id, read_action_log, get_hook_config,
        )

        if not STATE_PATH.exists():
            return

        state = json.loads(STATE_PATH.read_text())
        agents = state.get("agents", {})

        my_id = _get_session_agent_id()
        agent = agents.get(my_id)
        if agent is None:
            # Fallback: pick the most active cc-* agent (highest action_count)
            best_agent = None
            best_count = -1
            for aid, adata in agents.items():
                if aid.startswith("cc-") or aid == "claude-code":
                    count = adata.get("action_count", 0)
                    if count > best_count:
                        best_count = count
                        best_agent = adata
            agent = best_agent
        if agent is None:
            return

        level_name = agent.get("level", "HEALTHY")
        pressure = agent.get("pressure", 0.0)
        actions = agent.get("action_count", 0)
        vitals = agent.get("vitals", {})

        # During cold start (< 10 actions), pressure is unreliable (baseline defaults)
        # Only show if we have enough data
        if actions < 10:
            pressure = 0.0

        hook_config = get_hook_config()
        verbosity = hook_config.get("verbosity", "normal")

        # ── Load and clean action log ──
        action_log = read_action_log()
        if action_log:
            last_ts = action_log[-1].get("ts", 0)
            if time.time() - last_ts > 1800:
                action_log = []
                try:
                    from soma.hooks.common import ACTION_LOG_PATH
                    ACTION_LOG_PATH.unlink(missing_ok=True)
                except OSError:
                    pass

        # ── Collect all findings ──
        findings = _collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)

        # ── Determine if we should output anything ──
        has_critical = any(p == 0 for p, _ in findings)
        has_important = any(p <= 1 for p, _ in findings)

        if level_name == "HEALTHY" and pressure < 0.15 and not has_critical and not has_important:
            return

        # ── Build output based on verbosity ──
        lines = []

        # Status line — always present
        u = vitals.get("uncertainty", 0)
        d = vitals.get("drift", 0)
        e = vitals.get("error_rate", 0)
        lines.append(f"SOMA: p={pressure:.0%} #{actions} [u={u:.2f} d={d:.2f} e={e:.2f}]")

        # Sort findings by priority
        findings.sort(key=lambda x: x[0])

        if verbosity == "minimal":
            # Only critical findings (1 extra line max)
            for p, msg in findings:
                if p == 0:
                    lines.append(msg)
                    break  # Only 1

        elif verbosity == "normal":
            # Critical + top 2 important (3 extra lines max)
            count = 0
            for p, msg in findings:
                if p <= 1 and count < 3:
                    lines.append(msg)
                    count += 1

        else:  # verbose
            # Everything (up to 6 extra lines)
            for p, msg in findings[:6]:
                lines.append(msg)

        if lines:
            print("\n".join(lines))

    except Exception:
        pass  # Never crash


if __name__ == "__main__":
    main()
