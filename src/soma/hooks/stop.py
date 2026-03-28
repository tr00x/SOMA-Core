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
        print(
            f"SOMA session end: {snap['level'].name} "
            f"(pressure: {snap['pressure']:.1%}, actions: {snap['action_count']})",
            file=sys.stderr,
        )
    except Exception:
        pass  # Never crash Claude Code


if __name__ == "__main__":
    main()
