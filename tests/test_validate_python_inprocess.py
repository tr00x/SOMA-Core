"""
Regression for v2026.6.2 fix #3 — _validate_python_file must NOT
fork a subprocess. Forking a fresh Python interpreter to run
py_compile costs ~25ms per .py edit on top of the hook's own boot.
In-process compile(source, path, 'exec') gives the same syntax-error
detection at near-zero cost.

Also asserts the lint/js subprocess timeouts are tightened from 5s
to 500ms so a hung ruff/node can't freeze the user's terminal.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from soma.hooks.post_tool_use import (
    _lint_python_file,
    _validate_js_file,
    _validate_python_file,
)


def test_validate_python_does_not_fork(tmp_path: Path) -> None:
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n")
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        result = _validate_python_file(str(f))
    assert result is None
    run.assert_not_called(), (
        "_validate_python_file must use in-process compile(), not subprocess"
    )


def test_validate_python_detects_syntax_error_inprocess(tmp_path: Path) -> None:
    f = tmp_path / "broken.py"
    f.write_text("def x(:\n  pass\n")  # syntax error
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        result = _validate_python_file(str(f))
    run.assert_not_called()
    assert result is not None
    assert "SyntaxError" in result or "syntax" in result.lower()


def test_validate_python_rejects_dash_prefixed_path() -> None:
    """Defense in depth — even though we no longer subprocess, a
    flag-shaped path is still suspicious and should not be processed."""
    result = _validate_python_file("--config=/tmp/evil.toml.py")
    assert result is None


def test_lint_python_timeout_tightened() -> None:
    """5s timeout would freeze terminal for 5s on a hung ruff. 500ms cap."""
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        _lint_python_file("/tmp/legit.py")
    _, kwargs = run.call_args
    assert kwargs.get("timeout", 999) <= 0.5, (
        f"ruff timeout={kwargs.get('timeout')}s — should be <=0.5s"
    )


def test_js_check_timeout_tightened() -> None:
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        _validate_js_file("/tmp/legit.js")
    _, kwargs = run.call_args
    assert kwargs.get("timeout", 999) <= 0.5
