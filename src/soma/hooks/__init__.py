"""SOMA hooks for AI coding tool integration.

Supports multiple platforms via the HookAdapter protocol (LAYER-01):
    - Claude Code (default, backward compatible)
    - Cursor (HOOK-01)
    - Windsurf (HOOK-01)

Each hook is a separate module that can run standalone:
    python -m soma.hooks.pre_tool_use       # Block blind mutations
    python -m soma.hooks.post_tool_use      # Record + validate code
    python -m soma.hooks.notification       # Actionable tips injection
    python -m soma.hooks.stop               # Session cleanup
    python -m soma.hooks.statusline         # UI status bar

Or via the unified dispatcher:
    soma-hook PreToolUse
    soma-hook PostToolUse
    soma-hook UserPromptSubmit
    soma-hook Stop
"""

from soma.hooks.base import HookAdapter, HookInput, HookResult
from soma.hooks.cursor import CursorAdapter
from soma.hooks.windsurf import WindsurfAdapter
from soma.hooks.claude_code import ClaudeCodeAdapter

__all__ = [
    "HookAdapter",
    "HookInput",
    "HookResult",
    "CursorAdapter",
    "WindsurfAdapter",
    "ClaudeCodeAdapter",
]
