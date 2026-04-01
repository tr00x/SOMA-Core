"""SOMA Stop hook — runs when Claude Code session ends.

Final state save + summary to stderr. This ensures no data is lost
and gives the user a quick session summary. Cleans up the action log
so the next session starts fresh.
"""

from __future__ import annotations

import sys

from soma.hooks.common import (
    get_engine, save_state, read_action_log,
    get_fingerprint_engine, save_fingerprint_engine,
    get_quality_tracker,
    read_pressure_trajectory,
)


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    save_state(engine)

    # Update fingerprint before cleaning up (fingerprint persists across sessions)
    try:
        log = read_action_log(agent_id)
        if len(log) >= 5:  # Only update if session had meaningful activity
            fp_engine = get_fingerprint_engine()
            fp_engine.update_from_session(agent_id, log)
            save_fingerprint_engine(fp_engine)
    except Exception:
        pass

    # NOTE: Don't delete session files here. Claude Code calls Stop during
    # context compression (mid-session), not just at real session end.
    # Deleting action_log/quality/predictor kills SOMA's memory mid-session.
    # These files are bounded (max 20 entries) and don't grow indefinitely.
    # Real cleanup happens when user runs `soma setup-claude` or `rm -rf ~/.soma`.

    # Persist session to session_store for cross-session intelligence
    try:
        snap = engine.get_snapshot(agent_id)
        log = read_action_log(agent_id)
        if len(log) >= 3:
            import time as _time
            from soma.session_store import SessionRecord, append_session

            tools_dist = {}
            for e in log:
                t = e.get("tool", "?")
                tools_dist[t] = tools_dist.get(t, 0) + 1

            # Read full trajectory from per-action buffer (written by post_tool_use)
            pressure_traj = read_pressure_trajectory(agent_id)
            if not pressure_traj:
                pressure_traj = [snap["pressure"]]  # fallback: at least final pressure

            max_p = max(pressure_traj) if pressure_traj else snap["pressure"]
            avg_p = sum(pressure_traj) / len(pressure_traj) if pressure_traj else snap["pressure"]

            record = SessionRecord(
                session_id=agent_id,
                agent_id=agent_id,
                started=log[0].get("ts", 0.0) if log else 0.0,
                ended=_time.time(),
                action_count=snap["action_count"],
                final_pressure=snap["pressure"],
                max_pressure=max_p,
                avg_pressure=avg_p,
                error_count=sum(1 for e in log if e.get("error")),
                retry_count=0,
                total_tokens=0,
                mode_transitions=[],
                pressure_trajectory=pressure_traj,
                tool_distribution=tools_dist,
                phase_sequence=[],
                fingerprint_divergence=0.0,
            )
            append_session(record)
    except Exception:
        pass  # Never crash for session store failures

    try:
        snap = engine.get_snapshot(agent_id)
        action_count = snap['action_count']
        level = snap['level'].name
        pressure = snap['pressure']

        # Read action log for session stats
        log = read_action_log(agent_id)
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
            qt = get_quality_tracker(agent_id=agent_id)
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
