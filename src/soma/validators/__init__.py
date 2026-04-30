"""Source validators used by the PostToolUse hook.

v2026.6.x: extracted from hooks/post_tool_use.py — these functions
have nothing to do with hook dispatch and were inflating the
god-object's surface to 1100+ lines. Now they live under
``soma.validators`` where they're reusable and testable in
isolation.

Each validator returns either a one-line error string (suitable for
inclusion in agent feedback) or ``None`` when no issue was found.
All three honour the same defense-in-depth contract:

  * Non-matching extension → return None silently.
  * File path starts with ``-`` → return None (refuse flag-shaped
    inputs even though our subprocess calls already pass ``--``
    end-of-options separators).
"""
from __future__ import annotations

from soma.validators.python_validator import (  # noqa: F401
    lint_python_file,
    validate_python_file,
)
from soma.validators.js_validator import validate_js_file  # noqa: F401

__all__ = ["lint_python_file", "validate_python_file", "validate_js_file"]
