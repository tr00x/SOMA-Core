"""SOMA Context — session and workflow awareness.

Core module: provides structured context about the agent's working environment.
Used by patterns, findings, and layers for context-aware behavior.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    """Current session context."""
    cwd: str                    # Working directory
    workflow_mode: str          # "", "plan", "execute", "discuss", "fast"
    gsd_active: bool            # .planning/ directory exists
    action_count: int           # Total actions in session
    pressure: float             # Current pressure level


def detect_workflow_mode(cwd: str = "") -> str:
    """Detect GSD workflow mode from .planning/STATE.md.

    Returns: "" (default), "plan", "execute", "discuss", "fast"
    """
    if not cwd:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", "")
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            return ""
    planning_dir = os.path.join(cwd, ".planning")
    if not os.path.isdir(planning_dir):
        return ""
    state_path = os.path.join(planning_dir, "STATE.md")
    if not os.path.exists(state_path):
        return ""
    try:
        with open(state_path) as f:
            content = f.read(500)
        lower = content.lower()
        if "executing" in lower:
            return "execute"
        if "planning" in lower or "discussing" in lower:
            return "plan"
    except Exception:
        pass
    return ""


def get_session_context(
    cwd: str = "",
    action_count: int = 0,
    pressure: float = 0.0,
) -> SessionContext:
    """Build current session context."""
    if not cwd:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", "")
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            cwd = ""

    gsd_active = bool(cwd) and os.path.isdir(os.path.join(cwd, ".planning"))
    workflow_mode = detect_workflow_mode(cwd) if gsd_active else ""

    return SessionContext(
        cwd=cwd,
        workflow_mode=workflow_mode,
        gsd_active=gsd_active,
        action_count=action_count,
        pressure=pressure,
    )
