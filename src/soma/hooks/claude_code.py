#!/usr/bin/env python3
"""
SOMA Claude Code Hook — monitors EVERYTHING Claude Code does.

Hooks into ALL Claude Code lifecycle events:
- PreToolUse    — before tool call (can block)
- PostToolUse   — after tool call (record result)
- PostMessage   — after every Claude response
- Stop          — session ended

Install:
    soma setup-claude
    # Or manually add to ~/.claude/settings.json

SOMA will appear in your dashboard and Paperclip plugin automatically.
"""

import json
import os
import sys
import time
from pathlib import Path


def _get_engine():
    """Load or create SOMA engine."""
    try:
        from soma.engine import SOMAEngine
        from soma.persistence import load_engine_state
    except ImportError:
        return None, None

    soma_dir = Path.home() / ".soma"
    soma_dir.mkdir(parents=True, exist_ok=True)
    engine_path = soma_dir / "engine_state.json"

    engine = load_engine_state(str(engine_path))
    if engine is None:
        engine = SOMAEngine(budget={"tokens": 1_000_000, "cost_usd": 50.0})

    # Register claude-code agent
    agent_id = "claude-code"
    try:
        engine.get_level(agent_id)
    except Exception:
        engine.register_agent(
            agent_id,
            tools=["Bash", "Edit", "Read", "Write", "Grep", "Glob", "Agent",
                   "WebSearch", "WebFetch", "Skill", "NotebookEdit"],
        )

    return engine, agent_id


def _read_stdin():
    """Read JSON from stdin if available."""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if raw:
                return json.loads(raw)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save(engine):
    """Export state for dashboard + Paperclip."""
    try:
        from soma.persistence import save_engine_state
        soma_dir = Path.home() / ".soma"
        engine.export_state(str(soma_dir / "state.json"))
        save_engine_state(engine, str(soma_dir / "engine_state.json"))
    except Exception:
        pass


def hook_pre_tool_use():
    """Called BEFORE every tool call. Can block if agent is in QUARANTINE+."""
    engine, agent_id = _get_engine()
    if engine is None:
        return

    from soma.types import Level

    level = engine.get_level(agent_id)

    # SOMA control: block tool calls at QUARANTINE or above
    if level.value >= Level.QUARANTINE.value:
        snap = engine.get_snapshot(agent_id)
        pressure = snap["pressure"]
        print(f"SOMA BLOCKED: {level.name} (pressure: {pressure:.1%})", file=sys.stderr)
        print(f"Agent is under SOMA control. Pressure too high.", file=sys.stderr)
        # Exit with non-zero to signal Claude Code to skip this tool
        sys.exit(2)


def hook_post_tool_use():
    """Called AFTER every tool call. Records the action in SOMA."""
    engine, agent_id = _get_engine()
    if engine is None:
        return

    from soma.types import Action

    data = _read_stdin()
    tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", "unknown"))
    output = str(data.get("output", ""))[:500]
    error = data.get("error", False) or data.get("is_error", False)
    duration = float(data.get("duration_ms", 0)) / 1000.0

    action = Action(
        tool_name=tool_name,
        output_text=output,
        token_count=len(output) // 4,
        error=error,
        duration_sec=duration,
    )

    result = engine.record_action(agent_id, action)
    _save(engine)

    # Show level changes
    if result.level.name != "HEALTHY":
        print(f"SOMA: {result.level.name} ({result.pressure:.1%})", file=sys.stderr)


def hook_post_message():
    """Called after every Claude response. Tracks message-level metrics."""
    engine, agent_id = _get_engine()
    if engine is None:
        return

    from soma.types import Action

    data = _read_stdin()
    message = str(data.get("message", ""))[:500]
    tokens = data.get("usage", {}).get("output_tokens", len(message) // 4)

    action = Action(
        tool_name="message",
        output_text=message,
        token_count=tokens,
        error=False,
    )

    result = engine.record_action(agent_id, action)
    _save(engine)


def hook_stop():
    """Called when Claude Code session ends. Final state save."""
    engine, agent_id = _get_engine()
    if engine is None:
        return

    _save(engine)
    snap = engine.get_snapshot(agent_id)
    print(
        f"SOMA session end: {snap['level'].name} "
        f"(pressure: {snap['pressure']:.1%}, actions: {snap['action_count']})",
        file=sys.stderr,
    )


def main():
    """Dispatch based on CLAUDE_HOOK environment variable or argv."""
    hook_type = os.environ.get("CLAUDE_HOOK", "")
    if not hook_type and len(sys.argv) > 1:
        hook_type = sys.argv[1]

    dispatch = {
        "PreToolUse": hook_pre_tool_use,
        "PostToolUse": hook_post_tool_use,
        "PostMessage": hook_post_message,
        "Stop": hook_stop,
    }

    handler = dispatch.get(hook_type, hook_post_tool_use)
    handler()


if __name__ == "__main__":
    main()
