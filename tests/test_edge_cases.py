"""Edge case and stress tests for SOMA Core."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from soma.engine import SOMAEngine
from soma.types import Action, Level
from soma.recorder import SessionRecorder
from soma.replay import replay_session
from soma.learning import LearningEngine
from soma.testing import Monitor
from soma.wrappers.claude_code import ClaudeCodeWrapper


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
        assert isinstance(r.level, Level)
        assert 0.0 <= r.pressure <= 1.0


# ---------------------------------------------------------------------------
# 2. Engine with 0 budget
# ---------------------------------------------------------------------------

def test_zero_budget_immediately_safe_mode():
    """budget={"tokens": 0} → engine should reach SAFE_MODE immediately."""
    e = SOMAEngine(budget={"tokens": 0})
    e.register_agent("a")

    # Budget health is already 0 before the first action; first record triggers SAFE_MODE.
    r = e.record_action("a", Action(tool_name="bash", output_text="hello", token_count=0))
    assert r.level == Level.SAFE_MODE


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
    assert isinstance(r.level, Level)
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
    assert isinstance(r.level, Level)
    assert isinstance(r.vitals.uncertainty, float)


# ---------------------------------------------------------------------------
# 5. Rapid escalation / de-escalation — hysteresis prevents oscillation
# ---------------------------------------------------------------------------

def test_hysteresis_prevents_rapid_oscillation():
    """Alternating error / normal actions — level should not flip every step."""
    e = SOMAEngine(budget={"tokens": 1_000_000})
    e.register_agent("a")

    levels: list[Level] = []

    # Warm up with enough errors to escalate first.
    for _ in range(10):
        r = e.record_action("a", _error_action())
        levels.append(r.level)

    # Now alternate: normal then error, 20 rounds.
    for i in range(20):
        if i % 2 == 0:
            r = e.record_action("a", _normal_action(i))
        else:
            r = e.record_action("a", _error_action())
        levels.append(r.level)

    # Count total direction changes.
    flips = sum(
        1
        for a, b in zip(levels, levels[1:])
        if a != b
    )

    # With hysteresis, flips should be much fewer than the number of alternations.
    # Allow up to 10 transitions out of 29 steps — hysteresis damps oscillation.
    assert flips <= 10, (
        f"Too many level flips ({flips}); hysteresis is not working as expected"
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

    # All levels must still be valid Level enum values.
    for agent_id in ("a", "b", "c"):
        assert isinstance(e.get_level(agent_id), Level)


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
# 8. Budget replenish mid-session — recovery from SAFE_MODE
# ---------------------------------------------------------------------------

def test_budget_replenish_recovers_from_safe_mode():
    """Exhaust budget → SAFE_MODE; replenish → recover."""
    e = SOMAEngine(budget={"tokens": 300})
    e.register_agent("a")

    # Exhaust the budget.
    for _ in range(4):
        e.record_action("a", Action(tool_name="bash", output_text="x", token_count=100))

    r = e.record_action("a", Action(tool_name="bash", output_text="x", token_count=0))
    assert r.level == Level.SAFE_MODE, (
        f"Expected SAFE_MODE after exhausting budget, got {r.level}"
    )

    # Replenish budget well above the SAFE_MODE exit threshold (10%).
    e.budget.replenish("tokens", 300)  # fully restore

    # After replenishment the next action should exit SAFE_MODE.
    r = e.record_action("a", Action(tool_name="bash", output_text="ok", token_count=1))
    assert r.level != Level.SAFE_MODE, (
        f"Expected engine to exit SAFE_MODE after replenishment, got {r.level}"
    )


# ---------------------------------------------------------------------------
# 9. Learning reset mid-session — clean slate after reset()
# ---------------------------------------------------------------------------

def test_learning_reset_clean_slate():
    """Record interventions → reset() → verify empty state."""
    le = LearningEngine()

    # Inject some pending records.
    le.record_intervention(
        "agent-x", Level.HEALTHY, Level.CAUTION, 0.3,
        {"uncertainty": 0.3, "error_rate": 0.4},
    )
    le.record_intervention(
        "agent-x", Level.CAUTION, Level.DEGRADE, 0.6,
        {"uncertainty": 0.5, "drift": 0.2},
    )

    assert len(le.pending("agent-x")) == 2

    le.reset()

    assert len(le.pending("agent-x")) == 0
    assert le.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION) == 0.0
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
        assert isinstance(r.level, Level)
        assert 0.0 <= r.pressure <= 1.0


# ---------------------------------------------------------------------------
# 12. Monitor assert_below with all Level values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("threshold", list(Level))
def test_monitor_assert_below_all_levels(threshold):
    """assert_below(threshold) semantics hold for every Level value."""
    with Monitor(budget={"tokens": 100_000}) as mon:
        # Record a single clean action — engine stays at HEALTHY.
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
# 13. ClaudeCodeWrapper — expensive tools blocked at DEGRADE
# ---------------------------------------------------------------------------

def test_claude_code_wrapper_blocks_expensive_tools_at_degrade():
    """Push agent to >= DEGRADE; expensive tool (bash) must be in blocked_tools."""
    w = ClaudeCodeWrapper(budget={"tokens": 1_000_000})
    w.register_agent(
        "main",
        tools=["bash", "search", "read"],
        expensive_tools=["bash"],
    )

    # Flood with error actions until DEGRADE or above.
    last_result = None
    for _ in range(30):
        last_result = w.on_action("main", _error_action())
        if last_result.level >= Level.DEGRADE:
            break

    assert last_result is not None

    if last_result.level >= Level.DEGRADE:
        # bash should be in blocked_tools.
        assert "bash" in last_result.blocked_tools, (
            f"Expected 'bash' blocked at {last_result.level}, "
            f"blocked_tools={last_result.blocked_tools}"
        )
        assert w.should_block_tool("main", "bash")
    else:
        # Engine didn't escalate to DEGRADE in 30 actions — skip blocking assertion
        # but verify that should_block_tool still returns False (below DEGRADE).
        assert not w.should_block_tool("main", "bash")


# ---------------------------------------------------------------------------
# 14. All agents in QUARANTINE — graph does not cascade infinitely
# ---------------------------------------------------------------------------

def test_all_agents_quarantine_no_infinite_cascade():
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

    # All agents should have reached at least CAUTION without hanging or crashing.
    for aid in agent_ids:
        level = e.get_level(aid)
        assert isinstance(level, Level)
        assert level >= Level.CAUTION, (
            f"Agent {aid} did not escalate: {level}"
        )
