"""
Regression for v2026.6.1 fix #3 — defense-in-depth around the
`--definition` SQL identifier. CLI argparse already restricts the
flag, but the function-level guard ensures programmatic callers
(future scripts, internal APIs, replay tools) cannot bypass the
allowlist and inject SQL via the column name.
"""
from __future__ import annotations

import pytest

from soma.cli.main import _validate_definition  # to be added in fix


def test_validate_definition_accepts_known() -> None:
    for ok in ("delta", "pressure_drop", "tool_switch", "error_resolved"):
        assert _validate_definition(ok) == ok


def test_validate_definition_rejects_injection() -> None:
    with pytest.raises(ValueError) as exc:
        _validate_definition("delta; DROP TABLE ab_outcomes; --")
    assert "definition" in str(exc.value).lower()


def test_validate_definition_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _validate_definition("")


def test_validate_definition_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        _validate_definition("custom_helped_bool")
