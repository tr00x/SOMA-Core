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
        pressure = snap['pressure']

        # Read action log for session stats
        log = read_action_log(agent_id)
        errors = sum(1 for e in log if e.get("error"))

        # Only print enhanced summary for notable sessions
        if action_count < 10 and pressure <= 0.3:
            # Minimal summary for short/quiet sessions
            print(f"SOMA: {action_count} actions, p={pressure:.0%}", file=sys.stderr)
        else:
            # Enhanced summary
            traj = read_pressure_trajectory(agent_id)
            peak = max(traj) if traj else pressure
            peak_action = traj.index(peak) + 1 if traj else action_count

            # Duration
            duration_min = 0
            if log and len(log) >= 2:
                first_ts = log[0].get("ts", 0)
                last_ts = log[-1].get("ts", 0)
                if first_ts and last_ts:
                    duration_min = int((last_ts - first_ts) / 60)

            error_rate = errors / action_count if action_count > 0 else 0.0

            # Quality grade
            grade = "?"
            try:
                qt = get_quality_tracker(agent_id=agent_id)
                report = qt.get_report()
                if report.total_writes + report.total_bashes >= 3:
                    grade = f"{report.grade} ({report.score:.0%})"
            except Exception:
                pass

            # Pattern detection
            tools_used: dict[str, int] = {}
            for e in log:
                t = e.get("tool", "?")
                tools_used[t] = tools_used.get(t, 0) + 1
            pattern_line = ""
            if tools_used:
                total_t = sum(tools_used.values())
                for t, c in tools_used.items():
                    if total_t > 5 and c / total_t > 0.6:
                        pattern_line = f"Pattern: {t} heavy ({c}/{total_t} actions)"
                        break

            parts = [
                "\u2500\u2500 SOMA Session \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                f"Duration: {duration_min}min  Actions: {action_count}  Grade: {grade}",
                f"Peak: {peak:.0%} at action #{peak_action}",
                f"Errors: {errors}/{action_count} ({error_rate:.0%})",
            ]
            if pattern_line:
                parts.append(pattern_line)
            parts.append("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

            print("\n".join(parts), file=sys.stderr)
    except Exception:
        pass  # Never crash Claude Code


if __name__ == "__main__":
    main()
