"""
Regression test for v2026.6.1 fix #1 — hook subprocess argument injection.

Threat model: agent-controlled file_path is passed to ruff/node as a
positional argument. Without `--` end-of-options, an attacker-supplied
file_path like `--config=/tmp/evil.toml` is interpreted as a flag.
"""
from __future__ import annotations

from unittest.mock import patch

from soma.hooks.post_tool_use import _lint_python_file, _validate_js_file


def test_lint_python_rejects_dash_prefixed_path() -> None:
    """A file_path starting with `-` must NOT be passed to ruff at all."""
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        result = _lint_python_file("--config=/tmp/evil.toml.py")
    assert result is None
    run.assert_not_called()


def test_lint_python_uses_double_dash_separator() -> None:
    """Legitimate paths flow through, but argv must include `--`
    before the path so a future malicious-looking path is treated
    as a path, not a flag."""
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        _lint_python_file("/tmp/legit.py")
    args, _kwargs = run.call_args
    argv = args[0]
    assert "--" in argv, f"missing -- separator in {argv}"
    assert argv.index("--") == len(argv) - 2, (
        f"-- must be immediately before the path; got {argv}"
    )
    assert argv[-1] == "/tmp/legit.py"


def test_js_check_rejects_dash_prefixed_path() -> None:
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        result = _validate_js_file("--require=/tmp/x.js")
    assert result is None
    run.assert_not_called()


def test_js_check_uses_double_dash_separator() -> None:
    with patch("soma.hooks.post_tool_use.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        _validate_js_file("/tmp/legit.js")
    args, _kwargs = run.call_args
    argv = args[0]
    assert "--" in argv
    assert argv[-1] == "/tmp/legit.js"
