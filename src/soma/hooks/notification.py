"""SOMA Notification — Claude Code output formatter.

Thin layer: calls core (soma.findings, soma.patterns), formats for
Claude Code's UserPromptSubmit hook (stdout injection).

Output goes to stdout as "additional context" in Claude Code.
Injects agent awareness prompt on first action of session (D-18/D-19/D-20).
"""

from __future__ import annotations

# Agent awareness prompt — injected on first action only (per D-18/D-19)
AGENT_AWARENESS_PROMPT = """[SOMA Active] This session is monitored by SOMA, a behavioral safety system.
- SOMA may BLOCK actions that match harmful patterns (blind edits, retry loops, file thrashing)
- When blocked, read the reason and follow the suggested fix
- Do NOT retry blocked actions without changing approach
- SOMA guidance appears in [SOMA] prefixed messages
- Current mode: {mode}"""


def _format_finding(f) -> str:
    """Format a Finding for Claude Code output."""
    if f.category == "positive":
        return f"[✓] {f.message}"
    if f.category == "status":
        # Include level name explicitly for clarity
        if "elevated" in f.message.lower():
            return f"[⚡ WARN {f.message}] {f.action}"
        if "blocked" in f.message.lower():
            return f"[🚨 BLOCK {f.message}] {f.action}"
        return f"[status] {f.message}"
    if f.action:
        return f"[do] {f.action} — {f.message}" if f.message else f"[do] {f.action}"
    return f"[{f.category}] {f.message}"


def main():
    try:
        from soma.hooks.common import (
            get_engine, read_action_log, get_hook_config,
            get_soma_mode,
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

        # ── Load action log early (needed for awareness check) ──
        action_log = read_action_log(agent_id)

        # ── Agent awareness prompt — first action only (per D-18/D-20) ──
        if len(action_log) == 0:
            soma_mode = get_soma_mode()
            print(AGENT_AWARENESS_PROMPT.format(mode=soma_mode))
            return  # Don't also print findings on first prompt

        hook_config = get_hook_config()
        verbosity = hook_config.get("verbosity", "normal")

        # ── Grace period: first 3 actions, stay silent ──
        if actions < 3:
            return

        # ── Collect findings from core ──
        from soma.findings import collect as collect_findings
        findings = collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)

        # ── Build header ──
        lines = []
        u = vitals.get("uncertainty", 0)
        d = vitals.get("drift", 0)
        e = vitals.get("error_rate", 0)

        phase_str = ""
        quality_str = ""
        try:
            from soma.hooks.common import get_task_tracker
            tracker = get_task_tracker(agent_id=agent_id)
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

        # ── Format findings by verbosity ──
        finding_lines: list[str] = []

        if verbosity == "minimal":
            for f in findings:
                if f.priority == 0:
                    finding_lines.append(_format_finding(f))
                    break

        elif verbosity == "normal":
            count = 0
            for f in findings:
                if f.priority <= 1 and count < 3:
                    finding_lines.append(_format_finding(f))
                    count += 1

        else:  # verbose
            for f in findings[:6]:
                finding_lines.append(_format_finding(f))

        # ── Signal reflex injections (guide + reflex modes, per D-17) ──
        try:
            soma_mode = get_soma_mode()
            if soma_mode in ("guide", "reflex") and actions >= 3:
                from soma.signal_reflexes import evaluate_all_signals

                # Gather signal inputs
                sig_prediction = None
                try:
                    from soma.hooks.common import get_predictor
                    predictor = get_predictor(agent_id=agent_id)
                    boundaries = [0.25, 0.50, 0.75]
                    next_boundary = next((b for b in boundaries if b > pressure), None)
                    if next_boundary:
                        sig_prediction = predictor.predict(next_boundary)
                except Exception:
                    pass

                sig_success_rate = 1.0
                sig_handoff_text = ""
                try:
                    from soma.halflife import predict_success_rate, generate_handoff_suggestion, estimate_half_life
                    hl = estimate_half_life(action_log)
                    sig_success_rate = predict_success_rate(actions, hl)
                    sig_handoff_text = generate_handoff_suggestion(agent_id, actions, hl, sig_success_rate)
                except Exception:
                    pass

                sig_original_task = ""
                sig_current_activity = ""
                try:
                    from soma.hooks.common import get_task_tracker
                    tracker = get_task_tracker(agent_id=agent_id)
                    ctx = tracker.get_context()
                    sig_original_task = getattr(ctx, "original_task", "") or ""
                    sig_current_activity = getattr(ctx, "current_activity", "") or getattr(ctx, "phase", "")
                except Exception:
                    pass

                sig_drift = vitals.get("drift", 0.0)
                sig_error_rate = vitals.get("error_rate", 0.0)

                sig_rca_text = None
                if sig_error_rate > 0.3:
                    try:
                        from soma.rca import diagnose
                        sig_rca_text = diagnose(action_log, vitals, pressure, level_name, actions)
                    except Exception:
                        pass

                reflex_results = evaluate_all_signals(
                    prediction=sig_prediction,
                    soma_mode=soma_mode,
                    drift=sig_drift,
                    original_task=sig_original_task,
                    current_activity=sig_current_activity,
                    error_rate=sig_error_rate,
                    rca_text=sig_rca_text,
                    success_rate=sig_success_rate,
                    handoff_text=sig_handoff_text,
                    agent_id=agent_id,
                )

                for rr in reflex_results:
                    if rr.inject_message:
                        finding_lines.append(rr.inject_message)

                    # Auto-checkpoint in reflex mode
                    if rr.reflex_kind == "predictor_checkpoint" and soma_mode == "reflex":
                        try:
                            from soma.hooks.common import _auto_checkpoint, increment_checkpoint_count
                            cp_num = increment_checkpoint_count(agent_id)
                            _auto_checkpoint(cp_num)
                        except Exception:
                            pass

                    # Trust weight reduction on handoff (per D-09)
                    if rr.reflex_kind == "handoff_suggestion":
                        try:
                            edges = engine._graph._adj.get(agent_id, {})
                            for target, weight in list(edges.items()):
                                engine._graph.update_edge(agent_id, target, weight * sig_success_rate)
                        except Exception:
                            pass

                    # Audit log each signal reflex event (per D-17)
                    try:
                        from soma.audit import AuditLogger
                        logger = AuditLogger()
                        logger.append(
                            agent_id=agent_id,
                            tool_name="notification",
                            error=False,
                            pressure=pressure,
                            mode="reflex",
                            type="reflex",
                            reflex_kind=rr.reflex_kind,
                            detail=rr.detail,
                        )
                    except Exception:
                        pass
        except Exception:
            pass  # Never crash notification for signal reflex failures

        # ── Output ──
        if finding_lines:
            lines.extend(finding_lines)
            print("\n".join(lines))
        elif actions % 15 == 0 and actions > 0:
            print(lines[0])

    except Exception:
        pass  # Never crash


# Keep backward compat for tests that import _collect_findings
def _collect_findings(
    action_log: list[dict],
    vitals: dict,
    pressure: float,
    level_name: str,
    actions: int,
    hook_config: dict,
) -> list[tuple[int, str]]:
    """Backward-compatible wrapper — returns (priority, message) tuples."""
    from soma.findings import collect as collect_findings
    findings = collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)
    return [(f.priority, _format_finding(f)) for f in findings]


if __name__ == "__main__":
    main()
