"""Behavioral stress tests for the SOMA engine under extreme conditions."""

from __future__ import annotations

import random
import string

import pytest

from soma.engine import SOMAEngine
from soma.graph import PressureGraph
from soma.learning import LearningEngine
from soma.types import Action, ResponseMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normal_action(i: int = 0) -> Action:
    """A representative normal action with low error rate."""
    return Action(
        tool_name="search",
        output_text=f"Normal output step {i}: result data found successfully " + "ok " * 10,
        token_count=100,
        cost=0.001,
        error=False,
        retried=False,
        duration_sec=1.0,
    )


def _error_action(i: int = 0) -> Action:
    """An action that represents a clear failure."""
    return Action(
        tool_name="bash",
        output_text="error: command failed " * 5,
        token_count=100,
        cost=0.001,
        error=True,
        retried=True,
        duration_sec=0.5,
    )


# ---------------------------------------------------------------------------
# Test 1: Gradual degradation
# ---------------------------------------------------------------------------

def test_gradual_degradation_pressure_and_levels():
    """Pressure monotonically increases (with tolerance) and modes escalate
    as error rate climbs from 0% to 100% over 50 steps."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    pressures: list[float] = []
    modes: list[ResponseMode] = []

    rng = random.Random(42)

    for step in range(50):
        # Error probability ramps linearly from 0 to 1
        error_prob = step / 49.0
        is_error = rng.random() < error_prob
        action = _error_action(step) if is_error else _normal_action(step)
        result = engine.record_action("agent", action)
        pressures.append(result.pressure)
        modes.append(result.mode)

    # Pressure should show an upward trend. We compare quartile means:
    # first quarter average should be less than last quarter average.
    q1_avg = sum(pressures[:12]) / 12
    q4_avg = sum(pressures[-12:]) / 12
    assert q4_avg > q1_avg, (
        f"Final quarter pressure mean ({q4_avg:.3f}) should exceed "
        f"first quarter mean ({q1_avg:.3f})"
    )

    # Modes should eventually escalate past OBSERVE
    final_mode = modes[-1]
    assert final_mode > ResponseMode.OBSERVE, (
        f"Expected escalation beyond OBSERVE after full-error ramp, got {final_mode}"
    )

    # GUIDE should appear somewhere in the run
    assert ResponseMode.GUIDE in modes or any(m > ResponseMode.GUIDE for m in modes), (
        "Expected GUIDE or higher to appear during gradual ramp"
    )


# ---------------------------------------------------------------------------
# Test 2: Recovery after crisis
# ---------------------------------------------------------------------------

def test_recovery_after_crisis():
    """Agent escalates under 20 error actions, then recovers to OBSERVE
    after 30 normal actions."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    # Phase 1: trigger escalation
    for i in range(20):
        engine.record_action("agent", _error_action(i))

    escalated_mode = engine.get_level("agent")
    assert escalated_mode > ResponseMode.OBSERVE, (
        f"Expected escalation after 20 errors, got {escalated_mode}"
    )

    # Phase 2: recovery — 30 normal actions
    final_mode = escalated_mode
    for i in range(30):
        result = engine.record_action("agent", _normal_action(i))
        final_mode = result.mode

    assert final_mode == ResponseMode.OBSERVE, (
        f"Expected recovery to OBSERVE after 30 normal actions, got {final_mode}"
    )


# ---------------------------------------------------------------------------
# Test 3: Sudden spike then recovery
# ---------------------------------------------------------------------------

def test_sudden_spike_then_recovery():
    """10 normal → 3 sudden errors → 20 normal: temporary escalation then recovery."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    # Warm-up: 10 normal actions
    for i in range(10):
        engine.record_action("agent", _normal_action(i))

    pre_spike_mode = engine.get_level("agent")

    # Spike: 3 concentrated errors
    for i in range(3):
        result = engine.record_action("agent", _error_action(i))
    post_spike_mode = engine.get_level("agent")

    # Should escalate during or after the spike
    assert post_spike_mode >= pre_spike_mode, (
        f"Mode should not drop during error spike: pre={pre_spike_mode}, post={post_spike_mode}"
    )

    # Recovery: 20 normal actions
    final_mode = post_spike_mode
    for i in range(20):
        result = engine.record_action("agent", _normal_action(100 + i))
        final_mode = result.mode

    assert final_mode == ResponseMode.OBSERVE, (
        f"Expected recovery to OBSERVE after spike recovery, got {final_mode}"
    )


# ---------------------------------------------------------------------------
# Test 4: Contagion test — A→B edge propagation
# ---------------------------------------------------------------------------

def test_contagion_agent_b_pressure_increases():
    """Agent A (bad) connected to B; B's pressure should exceed what it
    would have without the edge."""
    # --- Baseline: B alone (no edge), warmed up past grace period ---
    engine_solo = SOMAEngine(budget={"tokens": 500_000})
    engine_solo.register_agent("B_solo")
    # Warm B_solo past the grace period (min_samples=10)
    for i in range(10):
        engine_solo.record_action("B_solo", _normal_action(i))
    result_solo = engine_solo.record_action(
        "B_solo", _normal_action(10)
    )
    solo_pressure = result_solo.pressure

    # --- With edge: A goes bad, B gets contaminated ---
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("A")
    engine.register_agent("B")
    engine.add_edge("A", "B", trust_weight=1.0)

    # A performs many error actions
    for i in range(15):
        engine.record_action("A", _error_action(i))

    # Warm B past the grace period with normal actions
    for i in range(10):
        engine.record_action("B", _normal_action(i))

    # B performs one more normal action after A is bad and grace period is over
    result_b = engine.record_action("B", _normal_action(10))
    b_pressure_with_edge = result_b.pressure

    # B's pressure should be higher with the edge than without
    assert b_pressure_with_edge > solo_pressure, (
        f"B's pressure with edge ({b_pressure_with_edge:.4f}) should exceed "
        f"solo pressure ({solo_pressure:.4f})"
    )


# ---------------------------------------------------------------------------
# Test 5: Budget depletion race
# ---------------------------------------------------------------------------

def test_budget_depletion_raises_pressure():
    """3 agents each spending 100 tokens/action. With budget=1000,
    pressure should rise as budget depletes."""
    engine = SOMAEngine(budget={"tokens": 1000})
    engine.register_agent("a1")
    engine.register_agent("a2")
    engine.register_agent("a3")

    agents = ["a1", "a2", "a3"]

    # Record enough actions to deplete budget and pass grace period
    for step in range(20):
        for agent in agents:
            result = engine.record_action(
                agent,
                Action(tool_name="bash", output_text="output", token_count=100),
            )

    # After 60 actions at 100 tokens each (6000 total, 6x budget),
    # all agents should have elevated pressure
    for agent in agents:
        result = engine.record_action(
            agent,
            Action(tool_name="bash", output_text="x", token_count=0),
        )
        assert result.pressure > 0.1, (
            f"Agent {agent} should have elevated pressure after budget depletion, got {result.pressure:.3f}"
        )


# ---------------------------------------------------------------------------
# Test 6: Trust decay under sustained pressure
# ---------------------------------------------------------------------------

def test_trust_decay_under_sustained_uncertainty():
    """Source agent sends high-uncertainty actions for 20 steps.
    The trust weight on the edge from source to target should decay."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("source")
    engine.register_agent("target")
    engine.add_edge("source", "target", trust_weight=1.0)

    initial_trust = engine._graph.get_trust("source", "target")
    assert initial_trust == 1.0

    # High-uncertainty actions: retried + error to push uncertainty > 0.5
    high_uncertainty_action = Action(
        tool_name="bash",
        output_text="error: unexpected failure " * 3,
        token_count=100,
        error=True,
        retried=True,
        duration_sec=0.5,
    )

    for _ in range(20):
        engine.record_action("source", high_uncertainty_action)

    final_trust = engine._graph.get_trust("source", "target")
    assert final_trust < initial_trust, (
        f"Trust weight should decay under sustained high-uncertainty actions: "
        f"initial={initial_trust:.4f}, final={final_trust:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 7: Learning adapts thresholds after failed escalations
# ---------------------------------------------------------------------------

def test_learning_adjusts_thresholds():
    """Trigger repeated failed escalations (escalate but pressure doesn't drop).
    Verify learning has adjusted thresholds."""
    learning = LearningEngine(
        evaluation_window=2,
        min_interventions=3,
        threshold_adj_step=0.02,
    )

    for _ in range(10):
        learning.record_intervention(
            agent_id="agent",
            old=ResponseMode.OBSERVE,
            new=ResponseMode.GUIDE,
            pressure=0.5,
            signals={"error_rate": 0.5, "uncertainty": 0.3},
        )
        learning.evaluate("agent", current_pressure=0.5, actions_since=3)

    # Threshold adjustment should be non-zero for OBSERVE→GUIDE transition
    adj = learning.get_threshold_adjustment(ResponseMode.OBSERVE, ResponseMode.GUIDE)
    assert adj > 0.0, (
        f"Expected positive threshold adjustment after repeated failures, got {adj}"
    )

    # Weight adjustments should be negative for at least one signal
    err_adj = learning.get_weight_adjustment("error_rate")
    unc_adj = learning.get_weight_adjustment("uncertainty")
    assert err_adj < 0.0 or unc_adj < 0.0, (
        f"Expected negative weight adjustment after failures: "
        f"error_rate={err_adj}, uncertainty={unc_adj}"
    )


# ---------------------------------------------------------------------------
# Test 8: Pressure graph isolation — C isolated from A→B
# ---------------------------------------------------------------------------

def test_pressure_graph_isolation():
    """3 agents: A→B, C isolated. A goes bad. C.effective_pressure == C.internal_pressure."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("A")
    engine.register_agent("B")
    engine.register_agent("C")
    engine.add_edge("A", "B", trust_weight=1.0)
    # No edge to/from C

    # A goes bad
    for i in range(15):
        engine.record_action("A", _error_action(i))

    # C stays normal
    engine.record_action("C", _normal_action(0))

    # Inspect the graph directly
    graph = engine._graph
    c_node = graph._nodes["C"]

    # C has no incoming edges, so effective_pressure must equal internal_pressure
    assert c_node.effective_pressure == c_node.internal_pressure, (
        f"C should not be contaminated: effective={c_node.effective_pressure:.4f}, "
        f"internal={c_node.internal_pressure:.4f}"
    )

    # C should be isolated from A's pressure
    a_node = graph._nodes["A"]
    assert c_node.effective_pressure < a_node.effective_pressure or (
        c_node.effective_pressure == c_node.internal_pressure
    ), "C should be isolated from A's pressure"


# ---------------------------------------------------------------------------
# Test 9: Cold start convergence
# ---------------------------------------------------------------------------

def test_cold_start_convergence():
    """Fresh agent receiving 20 identical normal actions. By action 15+,
    pressure should be consistently near zero and mode should be OBSERVE."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    pressures_after_15: list[float] = []
    modes_after_15: list[ResponseMode] = []

    for i in range(20):
        result = engine.record_action("agent", _normal_action(i))
        if i >= 15:
            pressures_after_15.append(result.pressure)
            modes_after_15.append(result.mode)

    avg_late_pressure = sum(pressures_after_15) / len(pressures_after_15)
    assert avg_late_pressure < 0.35, (
        f"Pressure should converge near zero after cold start for normal actions, "
        f"got avg={avg_late_pressure:.4f}"
    )
    assert all(m == ResponseMode.OBSERVE for m in modes_after_15), (
        f"Mode should be OBSERVE after cold start convergence, got: {modes_after_15}"
    )


# ---------------------------------------------------------------------------
# Test 10: Maximum entropy attack — uncertainty detection
# ---------------------------------------------------------------------------

def test_maximum_entropy_attack_detected():
    """Agent outputs random characters (high entropy deviation). After warm-up
    with normal text, the switch to random noise should raise uncertainty."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    rng = random.Random(99)

    # Warm up with consistent normal outputs to establish a baseline
    for i in range(12):
        engine.record_action(
            "agent",
            Action(
                tool_name="search",
                output_text="the quick brown fox jumps over the lazy dog " * 3,
                token_count=100,
                error=False,
                retried=False,
            ),
        )

    # Now inject high-entropy random character output
    random_text = "".join(
        rng.choices(string.printable, k=300)
    )
    high_entropy_results = []
    for _ in range(5):
        result = engine.record_action(
            "agent",
            Action(
                tool_name="search",
                output_text=random_text,
                token_count=100,
                error=False,
                retried=False,
            ),
        )
        high_entropy_results.append(result)

    # Uncertainty should be elevated — at least one result should have noticeable uncertainty
    max_uncertainty = max(r.vitals.uncertainty for r in high_entropy_results)
    assert max_uncertainty > 0.05, (
        f"Expected elevated uncertainty during max-entropy attack, "
        f"got max_uncertainty={max_uncertainty:.4f}"
    )
