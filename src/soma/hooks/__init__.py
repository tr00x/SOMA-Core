"""SOMA hooks for Claude Code integration.

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
