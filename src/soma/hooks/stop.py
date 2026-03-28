"""SOMA Stop hook — runs when Claude Code session ends.

Final state save + summary to stderr. This ensures no data is lost
and gives the user a quick session summary. Cleans up the action log
so the next session starts fresh.
"""

from __future__ import annotations

import sys

from soma.hooks.common import get_engine, save_state, ACTION_LOG_PATH


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    save_state(engine)

    # Clean up action log — next session starts fresh
    try:
        ACTION_LOG_PATH.unlink(missing_ok=True)
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

        print("\n".join(parts), file=sys.stderr)
    except Exception:
        pass  # Never crash Claude Code


if __name__ == "__main__":
    main()
