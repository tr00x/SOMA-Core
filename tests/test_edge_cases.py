"""Edge case and stress tests for SOMA Core."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode
from soma.recorder import SessionRecorder
from soma.replay import replay_session
from soma.learning import LearningEngine
from soma.testing import Monitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normal_action(i: int = 0) -> Action:
    tools = ["search", "edit", "bash", "read"]
    return Action(
        tool_name=tools[i % len(tools)],
        output_text=f"Normal output from step {i}: " + "abcdefghij " * 5,
        token_count=50 + i,
        cost=0.001,
        duration_sec=0.5,
    )


def _error_action() -> Action:
    return Action(
        tool_name="bash",
        output_text="error error error " * 10,
        token_count=200,
        cost=0.01,
        error=True,
        retried=True,
        duration_sec=0.5,
    )


# ---------------------------------------------------------------------------
# 1. Engine with 100 agents
# ---------------------------------------------------------------------------

def test_100_agents_no_crash():
    """Register 100 agents, record 1 action each — must not crash."""
    e = SOMAEngine(budget={"tokens": 10_000_000})
    for i in range(100):
        agent_id = f"agent-{i:03d}"
        e.register_agent(agent_id)

    results = []
    for i in range(100):
        agent_id = f"agent-{i:03d}"
        result = e.record_action(agent_id, _normal_action(i))
        results.append(result)

    assert len(results) == 100
    for r in results:
        assert isinstance(r.mode, ResponseMode)
        assert 0.0 <= r.pressure <= 1.0


# ---------------------------------------------------------------------------
# 2. Engine with 0 budget
# ---------------------------------------------------------------------------

def test_depleted_budget_raises_pressure():
    """Spending well past budget limit → pressure should rise significantly."""
    e = SOMAEngine(budget={"tokens": 100})
    e.register_agent("a")

    # Spend well past the budget (each action costs 100 tokens, budget is 100)
    # After grace period, burn rate pressure should cause escalation.
    for _ in range(15):
        r = e.record_action("a", Action(tool_name="bash", output_text="hello", token_count=100))
    # Budget is 15x exhausted — engine should be above OBSERVE
    assert r.mode >= ResponseMode.GUIDE, (
        f"Expected at least GUIDE after depleting budget, got {r.mode}"
    )
    assert r.pressure > 0.2, (
        f"Expected elevated pressure after depleting budget, got {r.pressure:.3f}"
    )


# ---------------------------------------------------------------------------
# 3. Empty action
# ---------------------------------------------------------------------------

def test_empty_action_does_not_crash():
    """Action with empty output_text, tool_name='', token_count=0 — must not crash."""
    e = SOMAEngine(budget={"tokens": 100_000})
    e.register_agent("a")
    r = e.record_action(
        "a",
        Action(tool_name="", output_text="", token_count=0),
    )
    assert isinstance(r.mode, ResponseMode)
    assert isinstance(r.pressure, float)


# ---------------------------------------------------------------------------
# 4. Very long output
# ---------------------------------------------------------------------------

def test_very_long_output_text():
    """Action with output_text = 'x' * 100_000 — must not crash or OOM."""
    e = SOMAEngine(budget={"tokens": 10_000_000})
    e.register_agent("a")
    r = e.record_action(
        "a",
        Action(tool_name="bash", output_text="x" * 100_000, token_count=100),
    )
    assert isinstance(r.mode, ResponseMode)
    assert isinstance(r.vitals.uncertainty, float)


# ---------------------------------------------------------------------------
# 5. Rapid mode changes — pressure-based system prevents oscillation
# ---------------------------------------------------------------------------

def test_mode_stability_under_alternating_actions():
    """Alternating error / normal actions — mode should not flip every step."""
    e = SOMAEngine(budget={"tokens": 1_000_000})
    e.register_agent("a")

    modes: list[ResponseMode] = []

    # Warm up with enough errors to escalate first.
    for _ in range(10):
        r = e.record_action("a", _error_action())
        modes.append(r.mode)

    # Now alternate: normal then error, 20 rounds.
    for i in range(20):
        if i % 2 == 0:
            r = e.record_action("a", _normal_action(i))
        else:
            r = e.record_action("a", _error_action())
        modes.append(r.mode)

    # Count total direction changes.
    flips = sum(
        1
        for a, b in zip(modes, modes[1:])
        if a != b
    )

    # With EMA-based pressure, flips should be much fewer than the number of alternations.
    assert flips <= 10, (
        f"Too many mode flips ({flips}); pressure smoothing is not working as expected"
    )


# ---------------------------------------------------------------------------
# 6. Graph cycle — a→b→c→a propagation must not infinite-loop
# ---------------------------------------------------------------------------

def test_graph_cycle_no_infinite_loop():
    """a→b→c→a: propagate() must complete without hanging."""
    e = SOMAEngine(budget={"tokens": 1_000_000})
    e.register_agent("a")
    e.register_agent("b")
    e.register_agent("c")
    e.add_edge("a", "b")
    e.add_edge("b", "c")
    e.add_edge("c", "a")

    # Record actions for all three agents — should not loop.
    for _ in range(5):
        e.record_action("a", _normal_action())
        e.record_action("b", _normal_action())
        e.record_action("c", _normal_action())

    # All levels must still be valid ResponseMode enum values.
    for agent_id in ("a", "b", "c"):
        assert isinstance(e.get_level(agent_id), ResponseMode)


# ---------------------------------------------------------------------------
# 7. Single agent with no edges — graph propagation is a no-op
# ---------------------------------------------------------------------------

def test_single_agent_no_edges_propagation_noop():
    """An isolated agent: effective_pressure == internal_pressure after propagate."""
    from soma.graph import PressureGraph

    g = PressureGraph()
    g.add_agent("solo")
    g.set_internal_pressure("solo", 0.42)
    g.propagate()

    assert abs(g.get_effective_pressure("solo") - 0.42) < 1e-9


# ---------------------------------------------------------------------------
# 8. Budget replenish mid-session — recovery from BLOCK
# ---------------------------------------------------------------------------

def test_budget_replenish_recovers_pressure():
    """Exhaust budget → elevated pressure; replenish → pressure drops."""
    e = SOMAEngine(budget={"tokens": 100})
    e.register_agent("a")

    # Exhaust the budget with enough actions to pass grace period.
    for _ in range(15):
        r = e.record_action("a", Action(tool_name="bash", output_text="x", token_count=100))
    pressure_before = r.pressure
    assert pressure_before > 0.2, (
        f"Expected elevated pressure after budget depletion, got {pressure_before}"
    )

    # Replenish budget.
    e.budget.replenish("tokens", 10000)  # generously restore

    # After replenishment, continued normal actions should lower pressure.
    for _ in range(10):
        r = e.record_action("a", Action(tool_name="search", output_text="ok " * 20, token_count=10))
    assert r.pressure < pressure_before, (
        f"Expected pressure to drop after replenishment: before={pressure_before:.3f}, after={r.pressure:.3f}"
    )


# ---------------------------------------------------------------------------
# 9. Learning reset mid-session — clean slate after reset()
# ---------------------------------------------------------------------------

def test_learning_reset_clean_slate():
    """Record interventions → reset() → verify empty state."""
    le = LearningEngine()

    # Inject some pending records.
    le.record_intervention(
        "agent-x", ResponseMode.OBSERVE, ResponseMode.GUIDE, 0.3,
        {"uncertainty": 0.3, "error_rate": 0.4},
    )
    le.record_intervention(
        "agent-x", ResponseMode.GUIDE, ResponseMode.WARN, 0.6,
        {"uncertainty": 0.5, "drift": 0.2},
    )

    assert len(le.pending("agent-x")) == 2

    le.reset()

    assert len(le.pending("agent-x")) == 0
    assert le.get_threshold_adjustment(ResponseMode.OBSERVE, ResponseMode.GUIDE) == 0.0
    assert le.get_weight_adjustment("uncertainty") == 0.0


# ---------------------------------------------------------------------------
# 10. Recorder with 10 000 actions — export/import roundtrip at scale
# ---------------------------------------------------------------------------

def test_recorder_10000_actions_roundtrip(tmp_path):
    """Record 10 000 actions, export to JSON, reload, verify integrity."""
    rec = SessionRecorder()
    n = 10_000
    for i in range(n):
        rec.record(
            f"agent-{i % 5}",
            Action(
                tool_name="bash",
                output_text=f"output {i}",
                token_count=i,
                cost=0.001 * i,
            ),
        )

    assert len(rec.actions) == n

    out = tmp_path / "large_session.json"
    rec.export(out)
    assert out.exists()

    loaded = SessionRecorder.load(out)
    assert len(loaded.actions) == n

    # Spot-check first, middle, and last entries.
    for idx in (0, n // 2, n - 1):
        orig = rec.actions[idx]
        rest = loaded.actions[idx]
        assert rest.agent_id == orig.agent_id
        assert rest.action.token_count == orig.action.token_count
        assert abs(rest.action.cost - orig.action.cost) < 1e-9
        assert rest.action.output_text == orig.action.output_text


# ---------------------------------------------------------------------------
# 11. Replay with edges — multi-agent session replayed preserves results
# ---------------------------------------------------------------------------

def test_replay_with_edges():
    """Record a two-agent session with an edge, replay, verify result count."""
    rec = SessionRecorder()
    actions_per_agent = 5

    for i in range(actions_per_agent):
        rec.record("orch", _normal_action(i))
    for i in range(actions_per_agent):
        rec.record("sub", _normal_action(i + actions_per_agent))

    edges = [("orch", "sub", 0.8)]

    results = replay_session(
        rec,
        budget={"tokens": 1_000_000},
        edges=edges,
    )

    assert len(results) == actions_per_agent * 2
    for r in results:
        assert isinstance(r.mode, ResponseMode)
        assert 0.0 <= r.pressure <= 1.0


# ---------------------------------------------------------------------------
# 12. Monitor assert_below with all ResponseMode values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("threshold", list(ResponseMode))
def test_monitor_assert_below_all_levels(threshold):
    """assert_below(threshold) semantics hold for every ResponseMode value."""
    # Skip legacy aliases that have value > 3
    if threshold.value > 3:
        pytest.skip("Legacy alias — not a real mode")

    with Monitor(budget={"tokens": 100_000}) as mon:
        # Record a single clean action — engine stays at OBSERVE.
        mon.record(
            "agent1",
            Action(tool_name="search", output_text="ok result", token_count=50),
        )

    max_lv = mon.max_level

    if max_lv < threshold:
        # Should not raise.
        mon.assert_below(threshold)
    else:
        # Should raise AssertionError.
        with pytest.raises(AssertionError):
            mon.assert_below(threshold)


# ---------------------------------------------------------------------------
# 13. (removed — ClaudeCodeWrapper moved to hooks)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 14. All agents in BLOCK — graph does not cascade infinitely
# ---------------------------------------------------------------------------

def test_all_agents_block_no_infinite_cascade():
    """Flood all agents with errors; propagate() must terminate without recursion."""
    n_agents = 5
    e = SOMAEngine(budget={"tokens": 10_000_000})
    agent_ids = [f"qa-agent-{i}" for i in range(n_agents)]
    for aid in agent_ids:
        e.register_agent(aid)

    # Connect in a ring so pressure can flow between all agents.
    for i in range(n_agents):
        e.add_edge(agent_ids[i], agent_ids[(i + 1) % n_agents])

    # Flood every agent with many error actions.
    for _ in range(25):
        for aid in agent_ids:
            e.record_action(aid, _error_action())

    # All agents should have reached at least GUIDE without hanging or crashing.
    for aid in agent_ids:
        level = e.get_level(aid)
        assert isinstance(level, ResponseMode)
        assert level >= ResponseMode.GUIDE, (
            f"Agent {aid} did not escalate: {level}"
        )
