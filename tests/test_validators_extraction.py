"""
Regression for v2026.6.x fix #23 — lint/syntax helpers extracted from
hooks/post_tool_use.py to soma.validators. The hook still re-exports
the private aliases so legacy tests keep working, but new code should
import from the public soma.validators surface.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch


def test_validate_python_file_in_validators_package():
    from soma.validators import validate_python_file
    assert callable(validate_python_file)


def test_lint_python_file_in_validators_package():
    from soma.validators import lint_python_file
    assert callable(lint_python_file)


def test_validate_js_file_in_validators_package():
    from soma.validators import validate_js_file
    assert callable(validate_js_file)


def test_post_tool_use_aliases_resolve_to_validators():
    """Legacy private-name imports from hooks/post_tool_use must
    resolve to the same callables as the public validators package.
    """
    from soma.hooks.post_tool_use import (
        _lint_python_file, _validate_js_file, _validate_python_file,
    )
    from soma.validators import (
        lint_python_file, validate_js_file, validate_python_file,
    )
    assert _lint_python_file is lint_python_file
    assert _validate_js_file is validate_js_file
    assert _validate_python_file is validate_python_file


def test_validators_smoke_dash_prefix_rejected():
    """All three reject flag-shaped paths (defense-in-depth)."""
    from soma.validators import (
        lint_python_file, validate_js_file, validate_python_file,
    )
    assert validate_python_file("--config=evil.py") is None
    assert lint_python_file("--config=evil.py") is None
    assert validate_js_file("--require=evil.js") is None


def test_validate_python_detects_syntax_error_in_file(tmp_path):
    from soma.validators import validate_python_file
    f = tmp_path / "broken.py"
    f.write_text("def x(:\n  pass\n")
    result = validate_python_file(str(f))
    assert result is not None
    assert "SyntaxError" in result or "syntax" in result.lower()


def test_lint_python_uses_double_dash_separator():
    from soma.validators import lint_python_file
    with patch("soma.validators.python_validator.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        lint_python_file("/tmp/legit.py")
    args, kwargs = run.call_args
    argv = args[0]
    assert "--" in argv
    assert argv[-1] == "/tmp/legit.py"
    # Tightened timeout from 5s to 0.5s in v2026.6.2.
    assert kwargs.get("timeout", 999) <= 0.5


def test_validate_js_uses_double_dash_separator():
    from soma.validators import validate_js_file
    with patch("soma.validators.js_validator.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        validate_js_file("/tmp/legit.js")
    args, kwargs = run.call_args
    argv = args[0]
    assert "--" in argv
    assert argv[-1] == "/tmp/legit.js"
    assert kwargs.get("timeout", 999) <= 0.5
