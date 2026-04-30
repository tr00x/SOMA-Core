"""
Regression for v2026.6.2 fix #4 — check_followthrough() must
short-circuit on retired patterns.

context and entropy_drop were retired 2026-04-25 (RETIRED_PATTERN_KEYS),
but check_followthrough still has live branches that resolve them via
their old pattern-specific logic. If a circuit_*.json on disk carries
a pre-retire pending row, the next hook hits retired code paths
unexpectedly.
"""
from __future__ import annotations

from soma.contextual_guidance import (
    RETIRED_PATTERN_KEYS,
    check_followthrough,
)


def test_retired_pattern_returns_none() -> None:
    """A pending row with a retired pattern must resolve as inconclusive
    (None), not silently take the retired path's True/False decision."""
    for retired in RETIRED_PATTERN_KEYS:
        pending = {
            "pattern": retired,
            "actions_since": 1,
            "pressure_at_injection": 0.6,
            "suggestion": "ignored",
        }
        result = check_followthrough(
            pending=pending,
            tool_name="Bash",
            tool_input={},
            file_path="",
            error=False,
            pressure_after=0.4,
        )
        assert result is None, (
            f"retired pattern {retired!r} resolved as {result!r}, "
            f"expected None (short-circuit)"
        )


def test_active_pattern_unchanged() -> None:
    """Sanity — non-retired pattern still resolves through its branch."""
    pending = {
        "pattern": "blind_edit",
        "actions_since": 0,
        "pressure_at_injection": 0.6,
        "file": "/tmp/x.py",
    }
    result = check_followthrough(
        pending=pending,
        tool_name="Read",
        tool_input={},
        file_path="/tmp/x.py",
        error=False,
        pressure_after=0.5,
    )
    assert result is True
