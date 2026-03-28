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

        # Inherit baseline from most recent session (cross-session memory)
        _inherit_baseline(engine, agent_id)

        # Clean up dead sessions (keep only this one + last 2)
        _cleanup_old_agents(engine, agent_id, keep=2)

    return engine, agent_id


def _inherit_baseline(engine, new_agent_id: str) -> None:
    """Copy baseline from the most active previous session.

    This gives the new session a warm start — SOMA already knows what
    'normal' looks like for this user instead of starting cold.
    """
    try:
        best_id = None
        best_count = 0
        for aid, s in engine._agents.items():
            if aid == new_agent_id or aid == "default":
                continue
            if s.action_count > best_count:
                best_count = s.action_count
                best_id = aid

        if best_id and best_count >= 10:
            donor = engine._agents[best_id]
            new_agent = engine._agents[new_agent_id]

            # Copy baseline (the learned signal averages)
            from soma.baseline import Baseline
            new_agent.baseline = Baseline.from_dict(donor.baseline.to_dict())

            # Copy baseline behavior vector (for drift detection)
            if donor.baseline_vector is not None:
                new_agent.baseline_vector = list(donor.baseline_vector)

            # Copy known tools
            new_agent.known_tools = list(donor.known_tools)
    except Exception:
        pass  # Never crash


def _cleanup_old_agents(engine, current_id: str, keep: int = 2) -> None:
    """Remove old session agents, keeping only the N most active + current."""
    try:
        agents = {
            aid: s for aid, s in engine._agents.items()
            if aid != current_id and aid != "default"
        }
        if len(agents) <= keep:
            return

        # Sort by action_count descending, keep top N
        sorted_agents = sorted(agents.items(), key=lambda x: x[1].action_count, reverse=True)
        to_remove = [aid for aid, _ in sorted_agents[keep:]]
        for aid in to_remove:
            del engine._agents[aid]
            engine._graph._nodes.pop(aid, None)
    except Exception:
        pass  # Never crash


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
