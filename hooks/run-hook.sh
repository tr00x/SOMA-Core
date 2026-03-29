#!/usr/bin/env bash
set -euo pipefail

HOOK_TYPE="${1:-PostToolUse}"

# Try soma-hook first (installed via pip), fall back to module invocation
if command -v soma-hook &>/dev/null; then
    exec soma-hook "$HOOK_TYPE"
else
    exec python3 -m soma.hooks.claude_code "$HOOK_TYPE"
fi
