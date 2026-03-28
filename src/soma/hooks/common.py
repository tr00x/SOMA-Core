"""Shared utilities for SOMA Claude Code hooks."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


SOMA_DIR = Path.home() / ".soma"
ENGINE_STATE_PATH = SOMA_DIR / "engine_state.json"
STATE_PATH = SOMA_DIR / "state.json"
ACTION_LOG_PATH = SOMA_DIR / "action_log.json"

CLAUDE_TOOLS = [
    "Bash", "Edit", "Read", "Write", "Grep", "Glob",
    "Agent", "WebSearch", "WebFetch", "Skill", "NotebookEdit",
]

# Maximum actions to keep in the log
ACTION_LOG_MAX = 20


def read_action_log() -> list[dict]:
    """Read recent action log for pattern analysis."""
    try:
        if ACTION_LOG_PATH.exists():
            return json.loads(ACTION_LOG_PATH.read_text())
    except (json.JSONDecodeError, IOError):
        pass
    return []


def append_action_log(tool_name: str, error: bool = False, file_path: str = "") -> list[dict]:
    """Append an action to the log and return updated log."""
    log = read_action_log()
    log.append({
        "tool": tool_name,
        "error": error,
        "file": file_path,
        "ts": time.time(),
    })
    # Keep only last N entries
    log = log[-ACTION_LOG_MAX:]
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        ACTION_LOG_PATH.write_text(json.dumps(log))
    except IOError:
        pass
    return log


def _get_session_agent_id() -> str:
    """Return a session-scoped agent ID.

    Uses CLAUDE_CODE_SESSION env var if set, otherwise falls back to PPID.
    This ensures each Claude Code window gets its own agent — no more
    multi-session race conditions where two windows fight over one state.
    """
    session = os.environ.get("CLAUDE_CODE_SESSION", "")
    if session:
        return f"cc-{session[:8]}"
    # Fallback: PPID groups all hooks from one Claude Code process
    ppid = os.getppid()
    return f"cc-{ppid}"


def get_engine():
    """Load or create SOMA engine with session-scoped agent registered.

    Uses Claude Code optimized config (higher thresholds, relaxed sensitivity).
    Returns (engine, agent_id) tuple. Returns (None, None) on import failure.
    """
    try:
        from soma.engine import SOMAEngine
        from soma.persistence import load_engine_state
        from soma.cli.config_loader import CLAUDE_CODE_CONFIG
    except ImportError:
        return None, None

    SOMA_DIR.mkdir(parents=True, exist_ok=True)

    engine = load_engine_state(str(ENGINE_STATE_PATH))
    if engine is None:
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )

    agent_id = _get_session_agent_id()
    try:
        engine.get_level(agent_id)
    except Exception:
        engine.register_agent(agent_id, tools=CLAUDE_TOOLS)

    return engine, agent_id


def save_state(engine):
    """Persist engine state for dashboard, Paperclip, and status line."""
    try:
        from soma.persistence import save_engine_state

        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        engine.export_state(str(STATE_PATH))
        save_engine_state(engine, str(ENGINE_STATE_PATH))
    except Exception:
        pass


def read_stdin() -> dict:
    """Read JSON payload from stdin (Claude Code passes hook data this way)."""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if raw:
                return json.loads(raw)
    except (json.JSONDecodeError, IOError):
        pass
    return {}
