"""SOMA Notification — Claude Code output formatter.

Thin layer: calls core (soma.findings, soma.patterns), formats for
Claude Code's UserPromptSubmit hook (stdout injection).

Output goes to stdout as "additional context" in Claude Code.
"""

from __future__ import annotations


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
        action_log = read_action_log(agent_id)

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
