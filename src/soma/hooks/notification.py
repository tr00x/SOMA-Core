"""SOMA Notification hook — injects agent state into LLM context.

Runs on UserPromptSubmit — before the agent starts reasoning.

v3: Structured output with configurable verbosity.
- minimal: status line only (1 line)
- normal: status + top 2 findings (2-4 lines)
- verbose: everything (up to 8 lines)

Output goes to stdout as "additional context" in Claude Code.
"""

from __future__ import annotations

import time


def _analyze_patterns(action_log: list[dict], workflow_mode: str = "") -> list[str]:
    """Analyze recent action log and return actionable tips.

    Each tip is a short, specific instruction — not a metric.
    workflow_mode: "" (default), "plan", "execute", "discuss", "fast"
    Returns at most 3 tips to avoid noise.
    """
    if not action_log:
        return []

    tips: list[str] = []
    recent = action_log[-10:]

    # Pattern 1: Blind edits — editing files without reading them first.
    # Build set of recently-read files and directories (last 30 actions).
    # Read/Grep/Glob all provide "read context" for a file or directory.
    # Write is creating new files — never triggers this warning.
    read_context: set[str] = set()
    read_dirs: set[str] = set()
    for entry in action_log[-30:]:
        if entry["tool"] in ("Read", "Grep", "Glob"):
            f = entry.get("file", "")
            if f:
                read_context.add(f)
                if "/" in f:
                    read_dirs.add(f.rsplit("/", 1)[0])

    blind_edits = 0
    blind_files: list[str] = []
    for entry in reversed(recent):
        if entry["tool"] in ("Edit", "NotebookEdit"):
            f = entry.get("file", "")
            if not f:
                continue
            # Check if this file or its directory was read
            if f in read_context:
                continue
            parent = f.rsplit("/", 1)[0] if "/" in f else ""
            if parent and parent in read_dirs:
                continue
            blind_edits += 1
            blind_files.append(f.rsplit("/", 1)[-1])
        elif entry["tool"] == "Read":
            break
    if blind_edits >= 3:
        files_hint = f" ({', '.join(dict.fromkeys(blind_files[:3]))})" if blind_files else ""
        tips.append(
            f"[do] Read before editing{files_hint} — "
            f"you made {blind_edits} edits to files you haven't read"
        )

    # Pattern 2: Consecutive Bash failures
    consecutive_bash_errors = 0
    last_bash_cmds: list[str] = []
    for entry in reversed(recent):
        if entry["tool"] == "Bash" and entry.get("error"):
            consecutive_bash_errors += 1
            last_bash_cmds.append(entry.get("file", ""))
        elif entry["tool"] == "Bash":
            break
        else:
            continue
    if consecutive_bash_errors >= 2:
        tips.append(
            f"[do] Stop retrying — {consecutive_bash_errors} Bash failures in a row. "
            f"Read the error, check assumptions, try a different approach"
        )

    # Pattern 3: High error rate
    if len(recent) >= 5:
        error_count = sum(1 for e in recent if e.get("error"))
        error_rate = error_count / len(recent)
        if error_rate >= 0.3:
            # Identify which tools are failing
            error_tools: dict[str, int] = {}
            for e in recent:
                if e.get("error"):
                    t = e["tool"]
                    error_tools[t] = error_tools.get(t, 0) + 1
            worst_tool = max(error_tools, key=error_tools.get) if error_tools else "?"
            tips.append(
                f"[do] Pause and rethink — {error_count}/{len(recent)} actions failed "
                f"(mostly {worst_tool}). Change approach, don't repeat"
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
                    f"[do] Collect changes for {short} — "
                    f"you've edited it {count}x. Read it, plan all changes, one edit"
                )

    # Pattern 5: Agent/subagent spam — lots of Agent calls without progress
    # Suppressed during planning/discuss (agent spawning is expected)
    if workflow_mode not in ("plan", "discuss"):
        agent_calls = sum(1 for e in recent if e["tool"] == "Agent")
        if agent_calls >= 3:
            tips.append(
                f"[do] Check agent results — {agent_calls} spawned in {len(recent)} actions. "
                f"Are they producing? Consider doing it directly"
            )

    # Pattern 6: Read-only stall (research paralysis)
    # Suppressed during planning/discuss (reading is the whole point)
    if workflow_mode not in ("plan", "discuss"):
        if len(recent) >= 8:
            read_tools = {"Read", "Grep", "Glob", "WebSearch", "WebFetch"}
            reads = sum(1 for e in recent if e["tool"] in read_tools)
            writes = sum(1 for e in recent if e["tool"] in ("Write", "Edit"))
            if reads >= 7 and writes == 0:
                tips.append(
                    f"[do] Start implementing — {reads} reads, 0 writes. "
                    f"You have enough context. Write code or ask the user"
                )

    # Pattern 7: Long sequence without user interaction
    # Suppressed during execute/plan (autonomous work is expected)
    if workflow_mode not in ("execute", "plan"):
        if len(action_log) >= 30:
            last_30 = action_log[-30:]
            user_tools = {"AskUserQuestion"}
            user_interactions = sum(1 for e in last_30 if e["tool"] in user_tools)
            edits = sum(1 for e in last_30 if e["tool"] in ("Write", "Edit", "Bash"))
            if user_interactions == 0 and edits >= 15:
                tips.append(
                    f"[do] Check in with user — {edits} mutations without asking. "
                    f"Verify you're on track before continuing"
                )

    # ── Positive feedback (only if no negative tips) ──
    if not tips:
        # Check for read-before-edit streak
        read_files_set: set[str] = set()
        read_edit_pairs = 0
        for entry in action_log[-20:]:
            if entry["tool"] in ("Read", "Grep"):
                f = entry.get("file", "")
                if f:
                    read_files_set.add(f)
            elif entry["tool"] in ("Edit", "Write") and entry.get("file", "") in read_files_set:
                read_edit_pairs += 1

        if read_edit_pairs >= 5:
            tips.append(f"[✓] read-before-edit maintained ({read_edit_pairs} pairs)")
        # Check for zero-error streak
        elif len(action_log) >= 15:
            recent_errors = sum(1 for e in action_log[-15:] if e.get("error"))
            if recent_errors == 0:
                tips.append(f"[✓] clean streak — {min(len(action_log), 15)} actions, 0 errors")

    return tips[:3]


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
    if level_name == "WARN":
        findings.append((0,
            f"[⚡ WARN p={pressure:.0%}] Slow down. Verify each step before proceeding. "
            f"Read→Think→Act, not Act→Fix→Retry"
        ))
    elif level_name == "BLOCK":
        findings.append((0,
            f"[🚨 BLOCK p={pressure:.0%}] Destructive ops blocked (rm -rf, git push -f, .env writes). "
            f"Normal Read/Write/Edit/Bash/Agent still allowed"
        ))

    # Quality (priority 0 if bad)
    if hook_config.get("quality", True):
        try:
            from soma.hooks.common import get_quality_tracker
            qt = get_quality_tracker()
            report = qt.get_report()
            if report.total_writes + report.total_bashes >= 3:
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
            predictor = get_predictor()
            if predictor._pressures:
                boundaries = [0.25, 0.50, 0.75]
                next_boundary = next((b for b in boundaries if b > pressure), None)
                if next_boundary:
                    pred = predictor.predict(next_boundary)
                    if pred.will_escalate:
                        reason = pred.dominant_reason
                        advice = {
                            "error_streak": "stop retrying the failing approach, try something different",
                            "blind_writes": "Read the target files before editing",
                            "thrashing": "plan the complete change first, then make one clean edit",
                            "retry_storm": "investigate the root cause instead of retrying",
                            "trend": "pressure is climbing — slow down and verify each step",
                        }.get(reason, "slow down and verify your approach")
                        findings.append((
                            1,
                            f"[predict] escalation in ~{pred.actions_ahead} actions "
                            f"({reason}) — {advice}"
                        ))
        except Exception:
            pass

    # Detect workflow mode for severity adjustment
    try:
        from soma.hooks.common import detect_workflow_mode
        workflow_mode = detect_workflow_mode()
    except Exception:
        workflow_mode = ""

    # Patterns (priority 1)
    tips = _analyze_patterns(action_log, workflow_mode=workflow_mode)
    for tip in tips:
        findings.append((1, tip))

    # Scope drift (priority 1) + phase info
    # Suppressed during planning (touching many files is expected)
    if hook_config.get("task_tracking", True) and workflow_mode not in ("plan", "discuss"):
        try:
            from soma.hooks.common import get_task_tracker
            tracker = get_task_tracker()
            ctx = tracker.get_context()
            if ctx.scope_drift >= 0.7 and ctx.drift_explanation:
                findings.append((1,
                    f"[do] Refocus — {ctx.drift_explanation}. "
                    f"Finish current task before expanding scope"
                ))
            elif ctx.scope_drift >= 0.5 and ctx.drift_explanation:
                findings.append((2, f"[scope] {ctx.drift_explanation}"))
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
            priority = 1 if level_name != "OBSERVE" else 2
            findings.append((priority, f"[why] {rca}"))
    except Exception:
        pass

    return findings


def main():
    try:
        from soma.hooks.common import (
            get_engine, read_action_log, get_hook_config,
        )

        engine, agent_id = get_engine()
        if engine is None:
            return

        try:
            snap = engine.get_snapshot(agent_id)
        except Exception:
            return

        level_name = snap["level"].name if hasattr(snap["level"], "name") else str(snap["level"])
        pressure = snap["pressure"]
        actions = snap["action_count"]
        vitals = snap.get("vitals", {})

        # Show real pressure always — cold start suppression caused confusion

        hook_config = get_hook_config()
        verbosity = hook_config.get("verbosity", "normal")

        # ── Load action log ──
        action_log = read_action_log()

        # ── Stale session detection ──
        # If the last action is older than 30 minutes, this is a new session.
        # Clean task tracker to prevent false scope drift from previous work.
        stale_timeout = hook_config.get("stale_timeout", 1800)
        if action_log:
            last_ts = action_log[-1].get("ts", 0)
            if last_ts and (time.time() - last_ts) > stale_timeout:
                try:
                    from soma.hooks.common import TASK_TRACKER_PATH
                    TASK_TRACKER_PATH.unlink(missing_ok=True)
                except Exception:
                    pass

        # In OBSERVE mode with very low pressure, skip expensive analysis entirely
        if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.10:
            return

        # ── Collect all findings ──
        findings = _collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)

        # ── Determine if we should output anything ──
        has_critical = any(p == 0 for p, _ in findings)

        # In OBSERVE mode with low pressure, only show if critical or positive findings
        has_positive = any("[✓]" in m for _, m in findings)
        if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.25:
            if not has_critical and not has_positive:
                return

        # ── Build output ──
        lines = []

        # ── Header: context-aware status line ──
        u = vitals.get("uncertainty", 0)
        d = vitals.get("drift", 0)
        e = vitals.get("error_rate", 0)

        # Detect phase and quality for header
        phase_str = ""
        quality_str = ""
        try:
            from soma.hooks.common import get_task_tracker
            tracker = get_task_tracker()
            ctx = tracker.get_context()
            if ctx.phase != "unknown":
                phase_str = f" [{ctx.phase}]"
            if actions >= 10:
                m = tracker.get_efficiency()
                if m and "context_efficiency" in m:
                    ctx_pct = int(m["context_efficiency"] * 100)
                    focus_val = m.get("focus", 1.0)
                    focus_label = "focused" if focus_val >= 0.7 else "drifting" if focus_val < 0.4 else "ok"
                    quality_str = f" ctx={ctx_pct}% {focus_label}"
        except Exception:
            pass

        if pressure < 0.25:
            lines.append(f"SOMA: #{actions}{phase_str}{quality_str}")
        else:
            lines.append(
                f"SOMA: p={pressure:.0%} #{actions}{phase_str} "
                f"[u={u:.2f} d={d:.2f} e={e:.2f}]"
            )

        # ── Findings by verbosity ──
        findings.sort(key=lambda x: x[0])

        if verbosity == "minimal":
            for p, msg in findings:
                if p == 0:
                    lines.append(msg)
                    break

        elif verbosity == "normal":
            count = 0
            for p, msg in findings:
                if p <= 1 and count < 3:
                    lines.append(msg)
                    count += 1

        else:  # verbose
            for p, msg in findings[:6]:
                lines.append(msg)

        if lines:
            print("\n".join(lines))

    except Exception:
        pass  # Never crash


if __name__ == "__main__":
    main()
