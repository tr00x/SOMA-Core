"""SOMA Hook Adapter Protocol and common types (LAYER-01).

Defines the contract for platform-specific hook adapters. Any AI coding
tool integration implements HookAdapter to get SOMA monitoring.

Usage:
    from soma.hooks.base import HookAdapter, HookInput, HookResult, dispatch_hook
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class HookInput:
    """Normalized hook input from any platform."""

    tool_name: str
    tool_input: dict
    output: str = ""
    error: bool = False
    session_id: str = ""
    file_path: str = ""
    duration_ms: float = 0
    platform: str = ""
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HookResult:
    """Result from hook processing."""

    allow: bool = True
    message: str = ""
    exit_code: int = 0


@runtime_checkable
class HookAdapter(Protocol):
    """Protocol for platform-specific hook adapters.

    Implement this to add SOMA monitoring to a new AI coding tool.
    """

    @property
    def platform_name(self) -> str:
        """Human-readable platform name (e.g., 'cursor', 'windsurf')."""
        ...

    def parse_input(self, raw: dict) -> HookInput:
        """Translate platform-specific stdin JSON to common HookInput."""
        ...

    def format_output(self, result: HookResult) -> None:
        """Write platform-specific output (stderr, stdout JSON, etc.)."""
        ...

    def get_event_type(self, raw: dict) -> str:
        """Map platform event name to SOMA canonical event type.

        Returns one of: 'PreToolUse', 'PostToolUse', 'Stop', 'Notification'
        """
        ...


# ------------------------------------------------------------------
# Canonical event dispatch table
# ------------------------------------------------------------------

def _get_dispatch() -> dict:
    """Lazy-load dispatch table to avoid circular imports."""
    from soma.hooks.pre_tool_use import main as pre_tool_use
    from soma.hooks.post_tool_use import main as post_tool_use
    from soma.hooks.stop import main as stop
    from soma.hooks.notification import main as notification

    return {
        "PreToolUse": pre_tool_use,
        "PostToolUse": post_tool_use,
        "Stop": stop,
        "Notification": notification,
        "UserPromptSubmit": notification,
    }


_DISPATCH: dict | None = None


def dispatch_hook(adapter: HookAdapter, raw: dict) -> None:
    """Dispatch a hook event through the adapter to the correct handler.

    1. Calls adapter.get_event_type(raw) to determine canonical event
    2. Calls adapter.parse_input(raw) to normalize input
    3. Routes to the correct core handler (pre_tool_use, post_tool_use, etc.)
    4. Calls adapter.format_output(result) for platform-specific output
    """
    global _DISPATCH
    if _DISPATCH is None:
        _DISPATCH = _get_dispatch()

    event_type = adapter.get_event_type(raw)
    _hook_input = adapter.parse_input(raw)

    handler = _DISPATCH.get(event_type)
    if handler is None:
        # Default to PostToolUse for backward compatibility
        handler = _DISPATCH.get("PostToolUse")

    if handler is not None:
        handler()
