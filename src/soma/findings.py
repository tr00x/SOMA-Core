"""SOMA Findings Collector — gather all monitoring insights.

Core module: layer-agnostic. Collects pattern results, quality,
predictions, scope drift, fingerprint divergence, and RCA into
a structured findings list.

Layers call collect() and format the results for their output channel.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """A single monitoring finding."""
    priority: int       # 0=critical (always show), 1=important, 2=informational
    category: str       # "status", "quality", "predict", "pattern", "scope",
                        # "fingerprint", "rca", "positive"
    message: str        # What's happening
    action: str = ""    # What to do about it


def collect(
    action_log: list[dict],
    vitals: dict,
    pressure: float,
    level_name: str,
    actions: int,
    hook_config: dict,
) -> list[Finding]:
    """Collect all monitoring findings.

    Args:
        action_log: Recent action log
        vitals: Current vital signs dict
        pressure: Current pressure (0-1)
        level_name: Current mode name (OBSERVE, GUIDE, WARN, BLOCK)
        actions: Total action count
        hook_config: Hook configuration dict

    Returns:
        List of Finding objects, sorted by priority (critical first).
    """
    findings: list[Finding] = []

    # ── Level status ──
    if level_name == "WARN":
        findings.append(Finding(
            priority=0, category="status",
            message=f"Pressure elevated (p={pressure:.0%})",
            action="Slow down. Read→Think→Act, not Act→Fix→Retry",
        ))
    elif level_name == "BLOCK":
        findings.append(Finding(
            priority=0, category="status",
            message=f"Destructive ops blocked (p={pressure:.0%})",
            action="Normal Read/Write/Edit/Bash/Agent still allowed",
        ))

    # ── Quality ──
    if hook_config.get("quality", True):
        try:
            from soma.hooks.common import get_quality_tracker
            qt = get_quality_tracker()
            report = qt.get_report()
            if report.total_writes + report.total_bashes >= 3:
                if report.grade in ("D", "F"):
                    issues_str = ", ".join(report.issues) if report.issues else "quality declining"
                    findings.append(Finding(
                        priority=0, category="quality",
                        message=f"grade={report.grade} ({issues_str})",
                    ))
                elif report.grade == "C":
                    findings.append(Finding(
                        priority=2, category="quality",
                        message=f"grade={report.grade}",
                    ))
        except Exception:
            pass

    # ── Prediction ──
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
                            "error_streak": "stop retrying, try something different",
                            "blind_writes": "Read the target files before editing",
                            "thrashing": "plan the complete change first, one clean edit",
                            "retry_storm": "investigate root cause instead of retrying",
                            "trend": "pressure climbing — slow down and verify",
                        }.get(reason, "slow down and verify your approach")
                        findings.append(Finding(
                            priority=1, category="predict",
                            message=f"escalation in ~{pred.actions_ahead} actions ({reason})",
                            action=advice,
                        ))
        except Exception:
            pass

    # ── Workflow mode ──
    try:
        from soma.hooks.common import detect_workflow_mode
        workflow_mode = detect_workflow_mode()
    except Exception:
        workflow_mode = ""

    # ── Patterns (via core module) ──
    try:
        from soma.patterns import analyze as analyze_patterns
        pattern_results = analyze_patterns(action_log, workflow_mode=workflow_mode)
        for pr in pattern_results:
            if pr.severity == "positive":
                findings.append(Finding(
                    priority=2, category="positive",
                    message=pr.action,
                ))
            else:
                findings.append(Finding(
                    priority=1, category="pattern",
                    message=pr.detail,
                    action=pr.action,
                ))
    except Exception:
        pass

    # ── Scope drift (suppressed during planning) ──
    if hook_config.get("task_tracking", True) and workflow_mode not in ("plan", "discuss"):
        try:
            from soma.hooks.common import get_task_tracker
            tracker = get_task_tracker()
            ctx = tracker.get_context()
            if ctx.scope_drift >= 0.7 and ctx.drift_explanation:
                findings.append(Finding(
                    priority=1, category="scope",
                    message=ctx.drift_explanation,
                    action="Finish current task before expanding scope",
                ))
            elif ctx.scope_drift >= 0.5 and ctx.drift_explanation:
                findings.append(Finding(
                    priority=2, category="scope",
                    message=ctx.drift_explanation,
                ))
        except Exception:
            pass

    # ── Fingerprint divergence ──
    if hook_config.get("fingerprint", True):
        try:
            from soma.hooks.common import get_fingerprint_engine, _get_session_agent_id
            fp_engine = get_fingerprint_engine()
            div, explanation = fp_engine.check_divergence(_get_session_agent_id(), action_log)
            if div >= 0.3 and explanation:
                findings.append(Finding(
                    priority=2, category="fingerprint",
                    message=explanation,
                ))
        except Exception:
            pass

    # ── RCA ──
    try:
        from soma.rca import diagnose
        rca = diagnose(action_log, vitals, pressure, level_name, actions)
        if rca:
            priority = 1 if level_name != "OBSERVE" else 2
            findings.append(Finding(
                priority=priority, category="rca",
                message=rca,
            ))
    except Exception:
        pass

    findings.sort(key=lambda f: f.priority)
    return findings
