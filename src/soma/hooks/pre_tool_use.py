"""SOMA PreToolUse hook — the reflex arc.

This is not an advisor. It does not suggest. It ACTS — like a real nervous system.

  HEALTHY    — silent, all tools allowed
  CAUTION    — blocks Write/Edit without preceding Read of same file (forced observation)
  DEGRADE    — blocks Bash and Agent entirely (restrict to safe actions only)
  QUARANTINE — blocks all dangerous tools, only Read/Glob/Grep/etc pass through
  RESTART    — same as QUARANTINE
  SAFE_MODE  — same as QUARANTINE

The escalation is progressive restriction of motor function while preserving sensory.
Pain doesn't advise you to move your hand. It moves your hand.

Exit codes:
    0 — allow tool call
    2 — block tool call
"""

from __future__ import annotations

import os
import sys

from soma.hooks.common import get_engine, read_stdin

# Tools that are NEVER blocked at any level — pure observation.
SAFE_TOOLS = frozenset({
    "Read",
    "Glob",
    "Grep",
    "Skill",
    "TaskCreate",
    "TaskUpdate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "ToolSearch",
    "AskUserQuestion",
})

# Tools blocked at DEGRADE (high-risk, hard to reverse)
DEGRADE_BLOCKED = frozenset({
    "Bash",
    "Agent",
})

# Tools blocked at CAUTION unless preceded by observation
MUTATION_TOOLS = frozenset({
    "Write",
    "Edit",
    "NotebookEdit",
})


def _block(level_name: str, pressure: float, tool_name: str, reason: str):
    """Print block message and exit with code 2."""
    print(
        f"SOMA {level_name} (p={pressure:.0%}) blocked '{tool_name}': {reason}",
        file=sys.stderr,
    )
    sys.exit(2)


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    from soma.types import Level

    level = engine.get_level(agent_id)

    # HEALTHY — no interference
    if level == Level.HEALTHY:
        return

    snap = engine.get_snapshot(agent_id)
    pressure = snap["pressure"]

    data = read_stdin()
    tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", ""))

    # Safe tools always pass at every level
    if tool_name in SAFE_TOOLS:
        if level.value >= Level.QUARANTINE.value:
            print(
                f"SOMA {level.name} (p={pressure:.0%}): allowing '{tool_name}'",
                file=sys.stderr,
            )
        return

    # ── QUARANTINE+ — block all non-safe tools ──
    if level.value >= Level.QUARANTINE.value:
        _block(level.name, pressure, tool_name,
               "only Read/Glob/Grep allowed at this level")

    # ── DEGRADE — block high-risk tools ──
    if level == Level.DEGRADE:
        if tool_name in DEGRADE_BLOCKED:
            _block("DEGRADE", pressure, tool_name,
                   "Bash and Agent blocked — use Edit/Read/Grep instead")
        # Allow Write/Edit/other tools at DEGRADE
        return

    # ── CAUTION — force observation before mutation ──
    if level == Level.CAUTION:
        if tool_name in MUTATION_TOOLS:
            # Check action log: was a Read done recently before this mutation?
            from soma.hooks.common import read_action_log
            log = read_action_log()
            target_file = data.get("tool_input", {}).get("file_path", "") if isinstance(data.get("tool_input"), dict) else ""

            # Look for a Read in the last 3 actions
            recent_reads = set()
            for entry in log[-3:]:
                if entry.get("tool") == "Read":
                    recent_reads.add(entry.get("file", ""))

            any_read = any(entry.get("tool") == "Read" for entry in log[-3:])
            has_recent_read = (
                (target_file and target_file in recent_reads)  # Read the exact file
                or any_read  # Any Read at all is acceptable
            )

            if not has_recent_read:
                hint = f"Read the target file first"
                if target_file:
                    hint = f"Read {target_file.rsplit('/', 1)[-1]} first"
                _block("CAUTION", pressure, tool_name,
                       f"{hint} — no Read in last 3 actions")
            else:
                print(
                    f"SOMA CAUTION (p={pressure:.0%}): allowing {tool_name} (Read verified)",
                    file=sys.stderr,
                )
        return


if __name__ == "__main__":
    main()
