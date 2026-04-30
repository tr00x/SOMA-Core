"""Python source validators — syntax check + ruff lint.

Extracted from ``hooks/post_tool_use.py`` in 2026-04-27 onward.
"""
from __future__ import annotations

import subprocess


def validate_python_file(file_path: str) -> str | None:
    """In-process syntax check via ``compile()``.

    Returns a one-line error string (``SyntaxError: <msg> (line N)``)
    or ``None`` when the file parses cleanly. Non-``.py`` paths and
    flag-shaped paths return ``None`` silently.

    2026-04-29: previously forked a fresh Python interpreter for
    py_compile (~25ms cost on every .py edit). ``compile`` gives the
    same SyntaxError detection at near-zero cost.
    """
    if not file_path or not file_path.endswith(".py"):
        return None
    if file_path.startswith("-"):
        # Defense in depth: refuse paths that look like flags.
        return None
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError:
        return None
    try:
        compile(source, file_path, "exec")
    except SyntaxError as e:
        msg = e.msg or "syntax error"
        line = f" (line {e.lineno})" if e.lineno else ""
        return f"SyntaxError: {msg}{line}"
    except (ValueError, TypeError) as e:
        # Source containing null bytes etc. — surface but don't crash.
        return f"compile error: {e}"
    return None


def lint_python_file(file_path: str) -> str | None:
    """Run ``ruff check --select F --no-fix --quiet`` on the file.

    Returns the first ruff diagnostic line (string) or ``None`` if the
    file passes lint, ruff is missing, or the timeout fires.

    The ``--select F`` set is pyflakes-only (undefined names, unused
    imports, etc.) — fast and high-signal. We don't want style
    warnings showing up in agent guidance.
    """
    if not file_path or not file_path.endswith(".py"):
        return None
    if file_path.startswith("-"):
        return None
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "F", "--no-fix", "--quiet",
             "--", file_path],
            # 2026-04-29: 500ms cap so a hung ruff doesn't freeze the
            # user's terminal. Pyflakes-F should finish in ms.
            capture_output=True, text=True, timeout=0.5,
        )
        if result.returncode != 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None
