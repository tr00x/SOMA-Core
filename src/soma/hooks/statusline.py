"""SOMA status line for Claude Code UI.

The agent's vital signs — always visible, always honest.

Must be fast (<50ms) and never crash.

Output examples:
    🧠 SOMA ✦ healthy ░░░░░░░░░░  0% · #3 · warming up
    🧠 SOMA ✦ healthy ░░░░░░░░░░  8% · u:0.04 d:0.12 · #42 · quality A
    🧠 SOMA ⚡ caution ███░░░░░░░ 32% · d:0.45↑ · #87 · quality B
    🧠 SOMA 🔥 degrade ██████░░░░ 62% · e:0.38↑ · #130 · quality D
    🧠 SOMA 🚨 lockdown █████████░ 85% · e:0.72↑ · #201 · quality F
"""

from __future__ import annotations

import json
from pathlib import Path

# Level display config: (emoji, label, color_hint)
LEVEL_STYLE = {
    "HEALTHY":    ("✦", "healthy"),
    "CAUTION":    ("⚡", "caution"),
    "DEGRADE":    ("🔥", "degrade"),
    "QUARANTINE": ("🚨", "lockdown"),
    "RESTART":    ("💀", "restart"),
    "SAFE_MODE":  ("⛔", "no-budget"),
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


def _quality_badge() -> str:
    """Load quality grade if available."""
    try:
        from soma.hooks.common import QUALITY_PATH
        if QUALITY_PATH.exists():
            data = json.loads(QUALITY_PATH.read_text())
            from soma.quality import QualityTracker
            qt = QualityTracker.from_dict(data)
            report = qt.get_report()
            if report.total_writes + report.total_bashes >= 3:
                return f"quality {report.grade}"
    except Exception:
        pass
    return ""


def _phase_badge() -> str:
    """Load current task phase if available."""
    try:
        from soma.hooks.common import TASK_TRACKER_PATH
        if TASK_TRACKER_PATH.exists():
            data = json.loads(TASK_TRACKER_PATH.read_text())
            from soma.task_tracker import TaskTracker
            tt = TaskTracker.from_dict(data)
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

        emoji, label = LEVEL_STYLE.get(level, ("?", level.lower()))
        bar = _bar(pressure)

        # Build parts
        parts = [f"🧠 SOMA {emoji} {label} {bar} {pressure:>3.0%}"]

        # Vitals
        v_str = _vitals_compact(vitals, actions)
        if v_str:
            parts.append(v_str)

        # Action count
        parts.append(f"#{actions}")

        # Badges
        phase = _phase_badge()
        quality = _quality_badge()
        if quality:
            parts.append(quality)
        if phase:
            parts.append(phase)

        print(" · ".join(parts))

    except Exception:
        print("🧠 SOMA · --")


if __name__ == "__main__":
    main()
