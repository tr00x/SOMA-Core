"""SOMA PreToolUse hook — guidance-based.

SOMA is a nervous system that GUIDES, not blocks.
Only truly destructive operations are blocked, and only at extreme pressure (75%+).

Exit codes:
    0 — allow tool call (with optional guidance message on stderr)
    2 — block tool call (destructive op at high pressure)
"""

from __future__ import annotations

import os
import sys

from soma.hooks.common import get_engine, read_stdin


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    snap = engine.get_snapshot(agent_id)
    pressure = snap["pressure"]

    data = read_stdin()
    tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", ""))
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    from soma.guidance import evaluate
    from soma.hooks.common import read_action_log, get_guidance_thresholds

    action_log = read_action_log()
    thresholds = get_guidance_thresholds()

    gsd_active = False
    try:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
        gsd_active = os.path.isdir(os.path.join(cwd, ".planning"))
    except Exception:
        pass

    response = evaluate(
        pressure=pressure,
        tool_name=tool_name,
        tool_input=tool_input,
        action_log=action_log,
        gsd_active=gsd_active,
        thresholds=thresholds,
    )

    if response.message:
        print(response.message, file=sys.stderr)

    if not response.allow:
        sys.exit(2)


if __name__ == "__main__":
    main()
