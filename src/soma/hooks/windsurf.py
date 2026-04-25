"""SOMA Windsurf hook adapter (HOOK-01).

Translates Windsurf's split-event model (pre_write_code, pre_run_command, etc.)
to SOMA canonical PreToolUse/PostToolUse events.

Usage:
    soma-hook PreToolUse  (called from .windsurf/hooks.json)
"""

from __future__ import annotations

import sys

from soma.hooks.base import HookInput, HookResult, dispatch_hook


# Windsurf has separate events per tool category
_WINDSURF_EVENT_MAP: dict[str, str] = {
    "pre_run_command": "PreToolUse",
    "pre_write_code": "PreToolUse",
    "pre_read_code": "PreToolUse",
    "pre_mcp_tool_use": "PreToolUse",
    "post_run_command": "PostToolUse",
    "post_write_code": "PostToolUse",
    "post_read_code": "PostToolUse",
    "post_mcp_tool_use": "PostToolUse",
    "post_cascade_response": "Stop",
}

# Map Windsurf event names to SOMA tool names
_WINDSURF_EVENT_TO_TOOL: dict[str, str] = {
    "pre_run_command": "Bash",
    "post_run_command": "Bash",
    "pre_write_code": "Write",
    "post_write_code": "Write",
    "pre_read_code": "Read",
    "post_read_code": "Read",
    "pre_mcp_tool_use": "mcp",
    "post_mcp_tool_use": "mcp",
}


class WindsurfAdapter:
    """Hook adapter for Windsurf (Codeium) AI coding tool."""

    @property
    def platform_name(self) -> str:
        return "windsurf"

    def get_event_type(self, raw: dict) -> str:
        """Map Windsurf's split event name to SOMA canonical event type."""
        event = raw.get("agent_action_name", "")
        if not event and len(sys.argv) > 1:
            event = sys.argv[1]
        return _WINDSURF_EVENT_MAP.get(event, event)

    def parse_input(self, raw: dict) -> HookInput:
        """Translate Windsurf-specific input to HookInput.

        Windsurf puts tool data in tool_info, and the tool type
        is inferred from the event name.
        """
        tool_info = raw.get("tool_info", {})
        event = raw.get("agent_action_name", "")
        tool_name = _WINDSURF_EVENT_TO_TOOL.get(event, "unknown")

        return HookInput(
            tool_name=tool_name,
            tool_input=tool_info,
            output=tool_info.get("response", ""),
            error=False,
            session_id=raw.get("trajectory_id", ""),
            platform="windsurf",
            raw=raw,
        )

    def format_output(self, result: HookResult) -> None:
        """Windsurf reads stderr for messages."""
        if result.message:
            print(result.message, file=sys.stderr)


def generate_windsurf_config() -> dict:
    """Generate .windsurf/hooks.json configuration for SOMA.

    Returns the hooks config dict that should be written to
    .windsurf/hooks.json in the project root.
    """
    return {
        "hooks": {
            "pre_run_command": [
                {"command": "soma-hook PreToolUse", "show_output": True}
            ],
            "pre_write_code": [
                {"command": "soma-hook PreToolUse", "show_output": True}
            ],
            "pre_read_code": [
                {"command": "soma-hook PreToolUse", "show_output": True}
            ],
            "post_run_command": [
                {"command": "soma-hook PostToolUse", "show_output": True}
            ],
            "post_write_code": [
                {"command": "soma-hook PostToolUse", "show_output": True}
            ],
            "post_read_code": [
                {"command": "soma-hook PostToolUse", "show_output": True}
            ],
            "post_cascade_response": [
                {"command": "soma-hook Stop", "show_output": False}
            ],
        },
    }


def main() -> None:
    """Entry point for Windsurf hook invocation."""
    import os
    # Tag agent_ids with the windsurf family so analytics, calibration
    # profiles, and ROI metrics segregate cleanly from claude-code
    # sessions. Without this prefix every windsurf session landed in the
    # cc-* family and silently contaminated each other's data.
    os.environ.setdefault("SOMA_AGENT_FAMILY", "windsurf")
    from soma.hooks.common import read_stdin
    adapter = WindsurfAdapter()
    raw = read_stdin()
    dispatch_hook(adapter, raw)


if __name__ == "__main__":
    main()
