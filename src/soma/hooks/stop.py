"""SOMA Stop hook — runs when Claude Code session ends.

Final state save + summary to stderr. This ensures no data is lost
and gives the user a quick session summary. Cleans up the action log
so the next session starts fresh.
"""

from __future__ import annotations

import sys

from soma.hooks.common import (
    get_engine, save_state, ACTION_LOG_PATH, PREDICTOR_PATH, TASK_TRACKER_PATH, QUALITY_PATH,
    get_fingerprint_engine, save_fingerprint_engine, read_action_log, _get_session_agent_id,
    get_quality_tracker,
)


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    save_state(engine)

    # Update fingerprint before cleaning up (fingerprint persists across sessions)
    try:
        log = read_action_log()
        if len(log) >= 5:  # Only update if session had meaningful activity
            fp_engine = get_fingerprint_engine()
            fp_engine.update_from_session(_get_session_agent_id(), log)
            save_fingerprint_engine(fp_engine)
    except Exception:
        pass

    # Clean up session artifacts — next session starts fresh
    try:
        ACTION_LOG_PATH.unlink(missing_ok=True)
        PREDICTOR_PATH.unlink(missing_ok=True)
        TASK_TRACKER_PATH.unlink(missing_ok=True)
        QUALITY_PATH.unlink(missing_ok=True)
    except OSError:
        pass

    try:
        snap = engine.get_snapshot(agent_id)
        action_count = snap['action_count']
        level = snap['level'].name
        pressure = snap['pressure']

        # Read action log for session stats
        from soma.hooks.common import read_action_log
        log = read_action_log()
        errors = sum(1 for e in log if e.get("error"))
        tools_used = {}
        for e in log:
            t = e.get("tool", "?")
            tools_used[t] = tools_used.get(t, 0) + 1

        # Build summary
        parts = [f"SOMA session end: {level} (p={pressure:.0%}, #{action_count})"]
        if errors:
            parts.append(f"  errors: {errors}/{len(log)}")
        if tools_used:
            top_3 = sorted(tools_used.items(), key=lambda x: -x[1])[:3]
            parts.append(f"  top tools: {', '.join(f'{t}={c}' for t, c in top_3)}")

        # Quality grade
        try:
            qt = get_quality_tracker()
            report = qt.get_report()
            if report.total_writes + report.total_bashes >= 3:
                q_str = f"  quality: {report.grade} ({report.score:.0%})"
                if report.issues:
                    q_str += f" — {', '.join(report.issues)}"
                parts.append(q_str)
        except Exception:
            pass

        print("\n".join(parts), file=sys.stderr)
    except Exception:
        pass  # Never crash Claude Code


if __name__ == "__main__":
    main()
