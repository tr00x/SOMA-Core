"""SOMA status line for Claude Code UI.

The agent's vital signs — always visible, always honest.

Must be fast (<50ms) and never crash.

Output examples:
    🧠 SOMA ✦ observe ░░░░░░░░░░  0% · ctx:high focus:focused · #42 · quality A
    🧠 SOMA 💡 guide  ███░░░░░░░ 32% · d:0.45↑ · #87 · quality B
    🧠 SOMA ⚡ warn   ██████░░░░ 62% · e:0.38↑ · #130 · quality D
    🧠 SOMA 🚨 block  █████████░ 85% · e:0.72↑ · #201 · quality F
"""

from __future__ import annotations

MODE_STYLE = {
    "OBSERVE":  ("✦", "observe"),
    "GUIDE":    ("💡", "guide"),
    "WARN":     ("⚡", "warn"),
    "BLOCK":    ("🚨", "block"),
    # Backward compat for old state files
    "HEALTHY":  ("✦", "observe"),
    "CAUTION":  ("💡", "guide"),
    "DEGRADE":  ("⚡", "warn"),
    "QUARANTINE": ("🚨", "block"),
    "RESTART":  ("🚨", "block"),
    "SAFE_MODE": ("🚨", "block"),
}


def _bar(pressure: float, width: int = 10) -> str:
    """Pressure bar: ███░░░░░░░"""
    filled = min(int(pressure * width), width)
    return "█" * filled + "░" * (width - filled)


def _vitals_compact(vitals: dict, actions: int) -> str:
    """Compact vitals: show top 2 non-trivial signals."""
    if not vitals or actions < 10:
        return ""

    signals = []
    labels = {"uncertainty": "u", "drift": "d", "error_rate": "e", "cost": "$", "token_usage": "t"}
    thresholds = {"uncertainty": 0.10, "drift": 0.10, "error_rate": 0.05, "cost": 0.15, "token_usage": 0.25}

    for key in ("uncertainty", "drift", "error_rate", "cost", "token_usage"):
        val = vitals.get(key, 0)
        if val > thresholds.get(key, 0.1):
            arrow = "↑" if val > 0.3 else ""
            signals.append(f"{labels[key]}:{val:.2f}{arrow}")

    return " ".join(signals[:2])


def _metrics_display(vitals: dict, actions: int, pressure: float) -> str:
    """Show actionable metrics when healthy, vital signals when stressed."""
    if pressure >= 0.25 or actions < 10:
        return _vitals_compact(vitals, actions)

    # Healthy — show actionable metrics (agent_id not available here, use legacy path)
    try:
        from soma.hooks.common import get_task_tracker
        tracker = get_task_tracker()
        m = tracker.get_efficiency()
        parts = []
        if "context_efficiency" in m:
            pct = int(m["context_efficiency"] * 100)
            label = "high" if pct >= 70 else "mid" if pct >= 40 else "low"
            parts.append(f"ctx:{label}")
        if "focus" in m:
            label = "focused" if m["focus"] >= 0.7 else "ok" if m["focus"] >= 0.4 else "drift"
            parts.append(f"focus:{label}")
        if parts:
            return " ".join(parts)
    except Exception:
        pass
    return _vitals_compact(vitals, actions)


def _quality_badge(agent_id: str = "") -> str:
    """Load quality grade if available."""
    try:
        from soma.hooks.common import get_quality_tracker
        qt = get_quality_tracker(agent_id=agent_id)
        report = qt.get_report()
        if report.total_writes + report.total_bashes >= 3:
            return f"quality {report.grade}"
    except Exception:
        pass
    return ""


def _phase_badge(agent_id: str = "") -> str:
    """Load current task phase if available."""
    try:
        from soma.hooks.common import get_task_tracker
        tt = get_task_tracker(agent_id=agent_id)
        ctx = tt.get_context()
        if ctx.phase != "unknown":
            return ctx.phase
    except Exception:
        pass
    return ""


def main():
    try:
        from soma.hooks.common import get_engine

        engine, agent_id = get_engine()
        if engine is None:
            print("🧠 SOMA · waiting")
            return

        try:
            snap = engine.get_snapshot(agent_id)
        except Exception:
            print("🧠 SOMA · waiting")
            return

        level_obj = snap["level"]
        level = level_obj.name if hasattr(level_obj, "name") else str(level_obj)
        pressure = snap["pressure"]
        actions = snap["action_count"]
        vitals = snap.get("vitals", {})

        emoji, label = MODE_STYLE.get(level, ("?", level.lower()))
        bar = _bar(pressure)

        # Build parts
        parts = [f"🧠 SOMA {emoji} {label} {bar} {pressure:>3.0%}"]

        # Vitals or actionable metrics
        v_str = _metrics_display(vitals, actions, pressure)
        if v_str:
            parts.append(v_str)

        # Action count
        parts.append(f"#{actions}")

        # Badges
        phase = _phase_badge(agent_id)
        quality = _quality_badge(agent_id)
        if quality:
            parts.append(quality)
        if phase:
            parts.append(phase)

        print(" · ".join(parts))

    except Exception:
        print("🧠 SOMA · --")


if __name__ == "__main__":
    main()
