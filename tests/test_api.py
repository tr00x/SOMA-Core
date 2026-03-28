"""Tests for public SOMA API exports."""

from __future__ import annotations

import importlib


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

def test_public_exports_exist():
    """All documented public names should be importable from soma directly."""
    import soma

    expected = [
        "SOMAEngine",
        "Action",
        "Level",
        "AutonomyMode",
        "ActionResult",
        "DriftMode",
        "VitalsSnapshot",
        "AgentConfig",
        "InterventionOutcome",
        "MultiBudget",
        "EventBus",
        "SessionRecorder",
        "replay_session",
    ]
    for name in expected:
        assert hasattr(soma, name), f"soma.{name} is missing from public API"


def test_all_list_complete():
    """Every name in __all__ should actually exist in the soma namespace."""
    import soma

    for name in soma.__all__:
        assert hasattr(soma, name), f"{name!r} listed in __all__ but missing from soma"


# ---------------------------------------------------------------------------
# Quickstart smoke test
# ---------------------------------------------------------------------------

def test_quickstart():
    """Create engine, register agent, record action — basic smoke test."""
    from soma import SOMAEngine, Action, Level

    engine = SOMAEngine(budget={"tokens": 50_000})
    engine.register_agent("agent-1")

    action = Action(
        tool_name="bash",
        output_text="hello world",
        token_count=10,
        cost=0.001,
    )
    result = engine.record_action("agent-1", action)

    assert isinstance(result.level, Level)
    assert isinstance(result.pressure, float)
    assert result.pressure >= 0.0


# ---------------------------------------------------------------------------
# soma.testing importable
# ---------------------------------------------------------------------------

def test_soma_testing_importable():
    """soma.testing must be importable and expose Monitor."""
    import soma.testing as testing

    assert hasattr(testing, "Monitor"), "soma.testing.Monitor is missing"


def test_soma_testing_monitor_works():
    """soma.testing.Monitor context manager records actions correctly."""
    from soma.testing import Monitor
    from soma.types import Action, Level

    action = Action(tool_name="read_file", output_text="content", token_count=5)

    with Monitor(budget={"tokens": 10_000}) as mon:
        mon.record("agent-x", action)

    assert len(mon._history) == 1
    result = mon._history[0]
    assert isinstance(result.level, Level)
