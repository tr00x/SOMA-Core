"""Tests for soma.testing.Monitor."""

from __future__ import annotations

import pytest

from soma.types import Action, Level
from soma.engine import SOMAEngine, ActionResult
from soma.testing import Monitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action(
    tool_name: str = "test_tool",
    output_text: str = "normal output text with some content here",
    error: bool = False,
    cost: float = 0.0,
    token_count: int = 100,
) -> Action:
    return Action(
        tool_name=tool_name,
        output_text=output_text,
        error=error,
        cost=cost,
        token_count=token_count,
    )


def _warm_up(mon: Monitor, agent_id: str = "agent1", n: int = 10) -> None:
    """Record n normal actions to let the engine baseline stabilise from cold start."""
    tools = ["search", "edit", "bash", "read"]
    for i in range(n):
        mon.record(agent_id, _action(
            tool_name=tools[i % len(tools)],
            output_text=f"normal output text {i} with some varied content here for baseline",
        ))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_basic_usage():
    """Record one action; total_actions == 1 and max_level is a valid Level."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        mon.record("agent1", _action())

    assert mon.total_actions == 1
    assert isinstance(mon.max_level, Level)


def test_tracks_max_level():
    """15 error actions should push max_level to at least CAUTION."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        for _ in range(15):
            mon.record("agent1", _action(error=True))

    assert mon.max_level >= Level.CAUTION


def test_assert_healthy_passes_when_healthy():
    """assert_healthy does not raise after warm-up + checkpoint with clean actions."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        _warm_up(mon)          # let engine baseline settle
        mon.checkpoint()       # reset history so cold-start escalations are excluded
        mon.record("agent1", _action())

    # assert_healthy checks current_level (most recent result) — must not raise
    mon.assert_healthy()


def test_assert_healthy_fails_on_escalation():
    """assert_below raises AssertionError after max_level reaches CAUTION or above."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        for _ in range(15):
            mon.record("agent1", _action(error=True))

    # max_level must be >= CAUTION after sustained errors
    assert mon.max_level >= Level.CAUTION, (
        "Engine did not escalate after 15 errors — test pre-condition not met"
    )
    with pytest.raises(AssertionError):
        mon.assert_below(Level.CAUTION)


def test_cost_tracking():
    """Two actions with cost 0.05 and 0.10 should sum to approximately 0.15."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        mon.record("agent1", _action(cost=0.05))
        mon.record("agent1", _action(cost=0.10))

    assert abs(mon.total_cost - 0.15) < 1e-9


def test_history_length():
    """len(mon.history) must equal the number of recorded actions."""
    n = 7
    with Monitor(budget={"tokens": 100_000}) as mon:
        for _ in range(n):
            mon.record("agent1", _action())

    assert len(mon.history) == n


def test_assert_below_passes():
    """assert_below(DEGRADE) passes once the engine has settled on clean input."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        _warm_up(mon)
        mon.checkpoint()           # clear cold-start escalations from history
        mon.record("agent1", _action())

    # max_level after checkpoint reflects only clean post-warmup actions
    mon.assert_below(Level.DEGRADE)


def test_assert_below_fails():
    """assert_below(CAUTION) raises AssertionError when max_level >= CAUTION."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        for _ in range(15):
            mon.record("agent1", _action(error=True))

    assert mon.max_level >= Level.CAUTION, (
        "Engine did not reach CAUTION after 15 errors — test pre-condition not met"
    )
    with pytest.raises(AssertionError):
        mon.assert_below(Level.CAUTION)
