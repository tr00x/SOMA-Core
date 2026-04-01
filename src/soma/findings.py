"""SOMA Findings Collector — gather all monitoring insights.

Core module: layer-agnostic. Collects pattern results, quality,
predictions, scope drift, fingerprint divergence, and RCA into
a structured findings list.

Layers call collect() and format the results for their output channel.
State loaders come from soma.state (core), not hooks.
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
    agent_id: str = "claude-code",
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
    u = vitals.get("uncertainty", 0)
    d = vitals.get("drift", 0)
    e = vitals.get("error_rate", 0)
    if level_name == "WARN":
        findings.append(Finding(
            priority=0, category="status",
            message=f"p={pressure:.0%} u={u:.2f} d={d:.2f} e={e:.0%}",
        ))
    elif level_name == "BLOCK":
        findings.append(Finding(
            priority=0, category="status",
            message=f"p={pressure:.0%} u={u:.2f} d={d:.2f} e={e:.0%} — destructive ops blocked",
        ))

    # ── Quality ──
    if hook_config.get("quality", True):
        try:
            from soma.state import get_quality_tracker
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
            from soma.state import get_predictor
            predictor = get_predictor()
            if predictor._pressures:
                boundaries = [0.25, 0.50, 0.75]
                next_boundary = next((b for b in boundaries if b > pressure), None)
                if next_boundary:
                    pred = predictor.predict(next_boundary)
                    if pred.will_escalate:
                        reason = pred.dominant_reason
                        findings.append(Finding(
                            priority=1, category="predict",
                            message=f"escalation in ~{pred.actions_ahead} actions, trigger={reason}, confidence={pred.confidence:.0%}",
                        ))
        except Exception:
            pass

    # ── Workflow mode ──
    try:
        from soma.context import detect_workflow_mode
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
                # Data tone: report the pattern and its data, not instructions
                data_parts = [f"pattern={pr.kind}"]
                if pr.data:
                    for k, v in pr.data.items():
                        data_parts.append(f"{k}={v}")
                findings.append(Finding(
                    priority=1, category="pattern",
                    message=", ".join(data_parts),
                ))
    except Exception:
        pass

    # ── Scope drift (suppressed during planning) ──
    if hook_config.get("task_tracking", True) and workflow_mode not in ("plan", "discuss"):
        try:
            from soma.state import get_task_tracker
            tracker = get_task_tracker()
            ctx = tracker.get_context()
            if ctx.scope_drift >= 0.7 and ctx.drift_explanation:
                findings.append(Finding(
                    priority=1, category="scope",
                    message=f"scope_drift={ctx.scope_drift:.2f}, {ctx.drift_explanation}",
                ))
            elif ctx.scope_drift >= 0.5 and ctx.drift_explanation:
                findings.append(Finding(
                    priority=2, category="scope",
                    message=f"scope_drift={ctx.scope_drift:.2f}, {ctx.drift_explanation}",
                ))
        except Exception:
            pass

    # ── Fingerprint divergence ──
    if hook_config.get("fingerprint", True):
        try:
            from soma.state import get_fingerprint_engine
            fp_engine = get_fingerprint_engine()
            div, explanation = fp_engine.check_divergence(agent_id, action_log)
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
