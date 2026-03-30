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

    # Patterns (via core patterns module)
    try:
        from soma.patterns import analyze as analyze_patterns
        pattern_results = analyze_patterns(action_log, workflow_mode=workflow_mode)
        for pr in pattern_results:
            if pr.severity == "positive":
                findings.append((2, f"[✓] {pr.action}"))
            else:
                msg = f"[do] {pr.action} — {pr.detail}" if pr.detail else f"[do] {pr.action}"
                findings.append((1, msg))
    except Exception:
        pass

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

        hook_config = get_hook_config()
        verbosity = hook_config.get("verbosity", "normal")

        # ── Load action log ──
        action_log = read_action_log()

        # ── Stale session detection ──
        stale_timeout = hook_config.get("stale_timeout", 1800)
        if action_log:
            last_ts = action_log[-1].get("ts", 0)
            if last_ts and (time.time() - last_ts) > stale_timeout:
                try:
                    from soma.hooks.common import TASK_TRACKER_PATH
                    TASK_TRACKER_PATH.unlink(missing_ok=True)
                except Exception:
                    pass

        # ── Grace period: first 3 actions, stay silent (cold start) ──
        if actions < 3:
            return

        # ── Always collect findings — SOMA must be present, not silent ──
        findings = _collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)

        # ── Build header ──
        lines = []
        u = vitals.get("uncertainty", 0)
        d = vitals.get("drift", 0)
        e = vitals.get("error_rate", 0)

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

        if pressure >= 0.25:
            lines.append(
                f"SOMA: p={pressure:.0%} #{actions}{phase_str} "
                f"[u={u:.2f} d={d:.2f} e={e:.2f}]"
            )
        else:
            lines.append(f"SOMA: #{actions}{phase_str}{quality_str}")

        # ── Collect finding lines by verbosity ──
        findings.sort(key=lambda x: x[0])
        finding_lines: list[str] = []

        if verbosity == "minimal":
            for p, msg in findings:
                if p == 0:
                    finding_lines.append(msg)
                    break

        elif verbosity == "normal":
            count = 0
            for p, msg in findings:
                if p <= 1 and count < 3:
                    finding_lines.append(msg)
                    count += 1

        else:  # verbose
            for p, msg in findings[:6]:
                finding_lines.append(msg)

        # ── Decide what to output ──
        # Always show header + findings when there are findings.
        # At low pressure with no findings: show header every 15 actions
        # (periodic check-in so agent knows SOMA is present).
        if finding_lines:
            lines.extend(finding_lines)
            print("\n".join(lines))
        elif actions % 15 == 0 and actions > 0:
            # Periodic presence: just the header, no findings
            print(lines[0])

    except Exception:
        pass  # Never crash


if __name__ == "__main__":
    main()
