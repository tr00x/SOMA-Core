"""
Regression for v2026.6.2 fix #5 — SomaBlocked and SomaBudgetExhausted
must be catchable as SOMAError so SDK consumers can wrap "anything
SOMA threw" with a single except clause.

Previously they inherited from raw Exception while proxy.py's
SOMABlockError already inherits from SOMAError — divergent classes
for the same concept.
"""
from __future__ import annotations

from soma.errors import SOMAError
from soma.wrap import SomaBlocked, SomaBudgetExhausted


def test_soma_blocked_is_soma_error() -> None:
    assert issubclass(SomaBlocked, SOMAError), (
        "SomaBlocked must inherit from SOMAError so consumers can "
        "`except SOMAError` and catch the entire family"
    )


def test_soma_budget_exhausted_is_soma_error() -> None:
    assert issubclass(SomaBudgetExhausted, SOMAError)


def test_can_catch_blocked_as_soma_error() -> None:
    from soma.types import ResponseMode
    try:
        raise SomaBlocked("agent-x", ResponseMode.BLOCK, 0.95)
    except SOMAError:
        return  # pass
    raise AssertionError("SomaBlocked was not caught by SOMAError handler")


def test_can_catch_budget_exhausted_as_soma_error() -> None:
    try:
        raise SomaBudgetExhausted("tokens")
    except SOMAError:
        return
    raise AssertionError("SomaBudgetExhausted was not caught by SOMAError handler")
