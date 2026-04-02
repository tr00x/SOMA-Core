"""SOMA Cursor hook adapter (HOOK-01).

Translates Cursor's camelCase events and input format to SOMA canonical types.

Usage:
    soma-hook PreToolUse  (called from .cursor/hooks.json)
"""

from __future__ import annotations

import json
import sys

from soma.hooks.base import HookInput, HookResult, dispatch_hook


# Cursor uses camelCase event names
_CURSOR_EVENT_MAP: dict[str, str] = {
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "stop": "Stop",
    "sessionStart": "Notification",
}


class CursorAdapter:
    """Hook adapter for Cursor AI coding tool."""

    @property
    def platform_name(self) -> str:
        return "cursor"

    def get_event_type(self, raw: dict) -> str:
        """Map Cursor's camelCase event to SOMA canonical event type."""
        hook_type = raw.get("hook_type", "")
        if not hook_type and len(sys.argv) > 1:
            hook_type = sys.argv[1]
        # Try camelCase mapping first, then pass through (for direct canonical names)
        return _CURSOR_EVENT_MAP.get(hook_type, hook_type)

    def parse_input(self, raw: dict) -> HookInput:
        """Translate Cursor-specific input to HookInput."""
        return HookInput(
            tool_name=raw.get("tool_name", ""),
            tool_input=raw.get("tool_input", {}),
            output=raw.get("tool_response", ""),
            error=raw.get("error", False),
            session_id=raw.get("conversation_id", ""),
            platform="cursor",
            raw=raw,
        )

    def format_output(self, result: HookResult) -> None:
        """Cursor reads JSON from stdout with user_message field."""
        if result.message:
            # Cursor expects JSON on stdout
            output = {"user_message": result.message}
            print(json.dumps(output))
            # Also print to stderr for compatibility
            print(result.message, file=sys.stderr)


def generate_cursor_config() -> dict:
    """Generate .cursor/hooks.json configuration for SOMA.

    Returns the hooks config dict that should be written to
    .cursor/hooks.json in the project root.
    """
    return {
        "version": 1,
        "hooks": {
            "preToolUse": [
                {
                    "command": "soma-hook PreToolUse",
                    "type": "command",
                    "timeout": 10,
                }
            ],
            "postToolUse": [
                {
                    "command": "soma-hook PostToolUse",
                    "type": "command",
                    "timeout": 10,
                }
            ],
            "stop": [
                {
                    "command": "soma-hook Stop",
                    "type": "command",
                    "timeout": 5,
                }
            ],
        },
    }


def main() -> None:
    """Entry point for Cursor hook invocation."""
    from soma.hooks.common import read_stdin
    adapter = CursorAdapter()
    raw = read_stdin()
    dispatch_hook(adapter, raw)


if __name__ == "__main__":
    main()
