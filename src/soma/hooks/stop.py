"""SOMA Stop hook — runs when Claude Code session ends.

Final state save + summary to stderr. This ensures no data is lost
and gives the user a quick session summary. Cleans up the action log
so the next session starts fresh.
"""

from __future__ import annotations

import sys
from pathlib import Path

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

    # Persist subagent data to session store
    try:
        from soma.subagent_monitor import aggregate as sub_aggregate
        sub_vitals = sub_aggregate(agent_id)
        if sub_vitals:
            import json as _json
            sub_path = Path.home() / ".soma" / "sessions" / agent_id / "subagents.json"
            sub_path.parent.mkdir(parents=True, exist_ok=True)
            sub_path.write_text(_json.dumps(sub_vitals, indent=2))
    except Exception:
        pass  # Never crash for subagent persistence

    try:
        snap = engine.get_snapshot(agent_id)
        action_count = snap['action_count']
        pressure = snap['pressure']

        # Read action log for session stats
        log = read_action_log(agent_id)
        errors = sum(1 for e in log if e.get("error"))

        # Count interventions from analytics. Strict-mode PreToolUse
        # blocks are stored with mode="strict" (not "BLOCK"), so we
        # count both here.
        blocks = 0
        guides = 0
        warns = 0
        try:
            from soma.analytics import AnalyticsStore
            analytics = AnalyticsStore()
            cursor = analytics._conn.execute(
                "SELECT mode, COUNT(*) FROM actions WHERE session_id = ? GROUP BY mode",
                (agent_id,),
            )
            for mode, cnt in cursor.fetchall():
                if mode in ("BLOCK", "strict"):
                    blocks += cnt
                elif mode == "GUIDE":
                    guides = cnt
                elif mode == "WARN":
                    warns = cnt
        except Exception:
            pass

        # Pressure trajectory
        traj = read_pressure_trajectory(agent_id)
        start_p = traj[0] if traj else 0.0
        end_p = traj[-1] if traj else pressure

        # Guidance effectiveness
        effectiveness_str = ""
        try:
            from soma.analytics import AnalyticsStore
            analytics_eff = AnalyticsStore()
            eff = analytics_eff.get_guidance_effectiveness(session_id=agent_id)
            if eff["total"] > 0:
                effectiveness_str = f", guidance {eff['helped']}/{eff['total']} effective ({eff['effectiveness_rate']:.0%})"
        except Exception:
            pass

        # Always print a useful one-liner
        interventions = []
        if errors:
            interventions.append(f"{errors} errors")
        if blocks:
            interventions.append(f"{blocks} blocks")
        if guides:
            interventions.append(f"{guides} guides")
        if warns:
            interventions.append(f"{warns} warns")
        intervention_str = ", ".join(interventions) if interventions else "clean"

        print(
            f"SOMA: {action_count} actions, {intervention_str}, "
            f"pressure {start_p:.0%}\u2192{end_p:.0%}{effectiveness_str}",
            file=sys.stderr,
        )

        # Enhanced summary for notable sessions
        if action_count >= 10 or pressure > 0.3:
            peak = max(traj) if traj else pressure
            peak_action = traj.index(peak) + 1 if traj else action_count

            # Duration
            duration_min = 0
            if log and len(log) >= 2:
                first_ts = log[0].get("ts", 0)
                last_ts = log[-1].get("ts", 0)
                if first_ts and last_ts:
                    duration_min = int((last_ts - first_ts) / 60)

            # Quality grade
            grade = "?"
            try:
                qt = get_quality_tracker(agent_id=agent_id)
                report = qt.get_report()
                if report.total_writes + report.total_bashes >= 3:
                    grade = f"{report.grade} ({report.score:.0%})"
            except Exception:
                pass

            parts = [
                f"  Duration: {duration_min}min | Grade: {grade} | Peak: {peak:.0%} at #{peak_action}",
            ]
            print("\n".join(parts), file=sys.stderr)

        # v2026.5.0 session summary to stdout so Claude Code surfaces
        # the report in the model's context — the user sees SOMA work
        # naturally in the assistant's final reply instead of having to
        # open a dashboard.
        try:
            lines = ["[SOMA session summary]"]
            intervention_total = blocks + guides + warns
            if intervention_total:
                lines.append(
                    f"- {intervention_total} interventions "
                    f"({blocks} blocked, {guides} guided, {warns} warned)"
                )
            if effectiveness_str:
                lines.append(f"- guidance effectiveness{effectiveness_str}")
            # Calibration progress
            try:
                from soma.calibration import (
                    WARMUP_EXIT_ACTIONS, CALIBRATED_EXIT_ACTIONS, load_profile,
                )
                prof = load_profile(agent_id)
                if prof.is_warmup():
                    lines.append(
                        f"- calibration: learning "
                        f"{prof.action_count}/{WARMUP_EXIT_ACTIONS}"
                    )
                elif prof.is_calibrated():
                    lines.append(
                        f"- calibration: calibrated "
                        f"({prof.action_count}/{CALIBRATED_EXIT_ACTIONS})"
                    )
                else:
                    silenced = ", ".join(prof.silenced_patterns) or "none"
                    lines.append(f"- calibration: adaptive, silenced={silenced}")
            except Exception:
                pass
            # Strict-mode blocks held at session end
            try:
                from soma.blocks import load_block_state
                bs = load_block_state(agent_id)
                if bs.blocks:
                    pats = ",".join(sorted({b.pattern for b in bs.blocks}))
                    lines.append(f"- unresolved blocks: {pats}")
            except Exception:
                pass
            # Only print summary if there's something beyond the header.
            if len(lines) > 1:
                print("\n".join(lines))
        except Exception:
            pass
    except Exception:
        pass  # Never crash Claude Code


if __name__ == "__main__":
    main()
