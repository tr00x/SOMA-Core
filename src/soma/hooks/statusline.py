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


_STATUSLINE_CACHE_PATH = None  # set lazily to allow monkeypatching SOMA_DIR
_STATUSLINE_CACHE_TTL_SEC = 1.0


def _statusline_cache_path():
    global _STATUSLINE_CACHE_PATH
    if _STATUSLINE_CACHE_PATH is None:
        from pathlib import Path as _P
        _STATUSLINE_CACHE_PATH = _P.home() / ".soma" / "statusline_cache.json"
    return _STATUSLINE_CACHE_PATH


def _try_print_cached() -> bool:
    """Print last rendered statusline if engine_state.json mtime is unchanged
    AND the cache is within TTL. Returns True iff cache was used.

    Statusline runs every ~5s in Claude Code; the full path opens
    engine_state.json + soma.toml + calibration_<family>.json + block
    files + circuit_<aid>.json — that's 5-6 JSON parses per render.
    Caching keyed on engine state mtime cuts the warm path to a single
    stat() + json.loads of one tiny cache file.
    """
    import json as _json
    import time as _time
    from pathlib import Path as _P
    try:
        engine_path = _P.home() / ".soma" / "engine_state.json"
        if not engine_path.exists():
            return False
        mtime = engine_path.stat().st_mtime

        cache_path = _statusline_cache_path()
        if not cache_path.exists():
            return False
        cache = _json.loads(cache_path.read_text())
        if cache.get("mtime_engine") != mtime:
            return False
        if _time.time() - cache.get("cached_at", 0) > _STATUSLINE_CACHE_TTL_SEC:
            return False
        rendered = cache.get("rendered")
        if not isinstance(rendered, str):
            return False
        print(rendered)
        return True
    except Exception:
        return False


def _save_cache(rendered: str) -> None:
    import json as _json
    import time as _time
    from pathlib import Path as _P
    try:
        engine_path = _P.home() / ".soma" / "engine_state.json"
        if not engine_path.exists():
            return
        cache_path = _statusline_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(_json.dumps({
            "mtime_engine": engine_path.stat().st_mtime,
            "rendered": rendered,
            "cached_at": _time.time(),
        }))
    except Exception:
        pass


def _render(parts: list[str]) -> str:
    return " · ".join(parts)


def _emit(rendered: str) -> None:
    """Print and persist into the 1-second mtime-keyed cache."""
    print(rendered)
    _save_cache(rendered)


def main():
    if _try_print_cached():
        return
    try:
        from soma.hooks.common import get_engine

        engine, agent_id = get_engine()
        if engine is None:
            _emit("🧠 SOMA · waiting")
            return

        try:
            snap = engine.get_snapshot(agent_id)
        except Exception:
            _emit("🧠 SOMA · waiting")
            return

        level_obj = snap["level"]
        level = level_obj.name if hasattr(level_obj, "name") else str(level_obj)
        pressure = snap["pressure"]
        actions = snap["action_count"]
        vitals = snap.get("vitals", {})

        emoji, label = MODE_STYLE.get(level, ("?", level.lower()))
        bar = _bar(pressure)

        # Calibration phase overrides everything in warmup — show learning
        # progress instead of pressure so user knows SOMA isn't dead,
        # just collecting baseline.
        # Cheap mtime-based warmup probe — avoids parsing JSON on every
        # statusline render (Claude Code polls this on a hot path).
        try:
            from soma.calibration import (
                WARMUP_EXIT_ACTIONS, calibration_family, load_profile,
            )
            from soma.state import SOMA_DIR as _SD
            fam = calibration_family(agent_id)
            prof_path = _SD / f"calibration_{fam}.json"
            if prof_path.exists():
                profile = load_profile(agent_id)
                if profile.is_warmup():
                    _emit(
                        f"🧠 SOMA · learning {profile.action_count}/"
                        f"{WARMUP_EXIT_ACTIONS}"
                    )
                    return
        except Exception:
            pass

        # Build parts
        parts = [f"🧠 SOMA {emoji} {label} {bar} {pressure:>3.0%}"]

        # Vitals or actionable metrics
        v_str = _metrics_display(vitals, actions, pressure)
        if v_str:
            parts.append(v_str)

        # Action count
        parts.append(f"#{actions}")

        # Block count and mode (per D-21)
        try:
            from soma.hooks.common import get_block_count, get_soma_mode
            bc = get_block_count(agent_id)
            if bc > 0:
                parts.append(f"⛔{bc}")
            sm = get_soma_mode(agent_id)
            if sm and sm != "guide":
                parts.append(sm.upper())
        except Exception:
            pass

        # Live strict-mode block indicator — red if any pattern currently
        # gates a tool. Gives the user (not just the agent) a visible
        # signal that SOMA is actively enforcing.
        try:
            from soma.blocks import load_block_state
            bs = load_block_state(agent_id)
            active = [b for b in bs.blocks if not bs.is_silenced(b.pattern)]
            if active:
                patterns = ",".join(sorted({b.pattern for b in active}))
                parts.append(f"🔴 {patterns}")
        except Exception:
            pass

        # Escalation indicator from circuit file
        try:
            from pathlib import Path
            import json as _json
            circuit_path = Path.home() / ".soma" / f"circuit_{agent_id}.json"
            if circuit_path.exists():
                _cdata = _json.loads(circuit_path.read_text())
                _gs = _cdata.get("guidance_state", {})
                _esc = _gs.get("escalation_level", 0)
                if _esc > 0:
                    parts.append(f"esc:{_esc}")
        except Exception:
            pass

        # Badges
        phase = _phase_badge(agent_id)
        quality = _quality_badge(agent_id)
        if quality:
            parts.append(quality)
        if phase:
            parts.append(phase)

        _emit(" · ".join(parts))

    except Exception:
        # Don't cache fault lines — next render gets a fresh shot.
        print("🧠 SOMA · --")


if __name__ == "__main__":
    main()
