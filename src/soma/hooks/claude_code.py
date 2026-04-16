"""SOMA Claude Code hook dispatcher.

Routes to the correct hook based on CLAUDE_HOOK env var or first argument.

Usage:
    CLAUDE_HOOK=PreToolUse soma-hook
    soma-hook PostToolUse
    python -m soma.hooks.claude_code PreToolUse
"""

from __future__ import annotations

import os
import sys

from soma.hooks.pre_tool_use import main as pre_tool_use
from soma.hooks.post_tool_use import main as post_tool_use
from soma.hooks.post_tool_use import main_failure as post_tool_use_failure
from soma.hooks.stop import main as stop
from soma.hooks.notification import main as notification
from soma.hooks.base import HookInput, HookResult


DISPATCH = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
    "PostToolUseFailure": post_tool_use_failure,
    "Stop": stop,
    "UserPromptSubmit": notification,
    "Notification": notification,
}


class ClaudeCodeAdapter:
    """Hook adapter for Claude Code (LAYER-01 compliance).

    The existing main() and DISPATCH are kept for backward compatibility.
    This adapter class provides HookAdapter protocol conformance for
    the cross-platform dispatch system.
    """

    @property
    def platform_name(self) -> str:
        return "claude-code"

    def get_event_type(self, raw: dict) -> str:
        """Get event type from CLAUDE_HOOK env var or sys.argv."""
        hook_type = os.environ.get("CLAUDE_HOOK", "")
        if not hook_type and len(sys.argv) > 1:
            hook_type = sys.argv[1]
        return hook_type

    def parse_input(self, raw: dict) -> HookInput:
        """Translate Claude Code input to HookInput."""
        tool_input = raw.get("tool_input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        file_path = ""
        if isinstance(tool_input, dict):
            file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
        return HookInput(
            tool_name=raw.get("tool_name", ""),
            tool_input=tool_input,
            output=str(raw.get("tool_response", "") or raw.get("output", "") or ""),
            error=raw.get("error", False) or raw.get("is_error", False),
            file_path=file_path,
            duration_ms=float(raw.get("duration_ms", 0)),
            platform="claude-code",
            raw=raw,
        )

    def format_output(self, result: HookResult) -> None:
        """Claude Code reads stderr for messages."""
        if result.message:
            print(result.message, file=sys.stderr)


def main():
    hook_type = os.environ.get("CLAUDE_HOOK", "")
    if not hook_type and len(sys.argv) > 1:
        hook_type = sys.argv[1]

    handler = DISPATCH.get(hook_type)
    if handler is None:
        # Default to PostToolUse for backwards compatibility
        post_tool_use()
    else:
        handler()


if __name__ == "__main__":
    main()
