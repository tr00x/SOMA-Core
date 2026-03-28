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
from soma.hooks.stop import main as stop
from soma.hooks.notification import main as notification


DISPATCH = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
    "Stop": stop,
    "UserPromptSubmit": notification,
    "Notification": notification,
}


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
