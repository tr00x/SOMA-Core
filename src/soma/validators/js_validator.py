"""JavaScript source validator — `node --check` syntax pass.

Extracted from ``hooks/post_tool_use.py`` in 2026-04-27 onward.
"""
from __future__ import annotations

import subprocess


def validate_js_file(file_path: str) -> str | None:
    """Run ``node --check`` on the file.

    Returns a one-line error string or ``None`` if the file is clean,
    Node is missing, or the timeout fires. Non-JS paths and flag-shaped
    paths return ``None`` silently.

    Uses ``--`` end-of-options separator so an attacker-crafted path
    like ``--require=/tmp/x.js`` cannot be interpreted as a flag.
    """
    if not file_path:
        return None
    if not any(file_path.endswith(ext) for ext in (".js", ".mjs", ".cjs")):
        return None
    if file_path.startswith("-"):
        # Defense in depth (matches lint_python_file).
        return None
    try:
        result = subprocess.run(
            ["node", "--check", "--", file_path],
            # 2026-04-29: 500ms cap (was 5s — froze terminal on a hung
            # node). node --check is sub-millisecond on real files.
            capture_output=True, text=True, timeout=0.5,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            for line in stderr.split("\n"):
                if "SyntaxError" in line or "Error" in line:
                    return line.strip()
            return stderr.split("\n")[-1].strip() if stderr else "syntax error"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None
