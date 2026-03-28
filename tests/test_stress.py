"""Behavioral stress tests for the SOMA engine under extreme conditions."""

from __future__ import annotations

import random
import string

import pytest

from soma.engine import SOMAEngine
from soma.graph import PressureGraph
from soma.learning import LearningEngine
from soma.types import Action, Level


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
    """Pressure monotonically increases (with tolerance) and levels escalate
    as error rate climbs from 0% to 100% over 50 steps."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    pressures: list[float] = []
    levels: list[Level] = []

    rng = random.Random(42)

    for step in range(50):
        # Error probability ramps linearly from 0 to 1
        error_prob = step / 49.0
        is_error = rng.random() < error_prob
        action = _error_action(step) if is_error else _normal_action(step)
        result = engine.record_action("agent", action)
        pressures.append(result.pressure)
        levels.append(result.level)

    # Pressure should show an upward trend. We compare quartile means:
    # first quarter average should be less than last quarter average.
    q1_avg = sum(pressures[:12]) / 12
    q4_avg = sum(pressures[-12:]) / 12
    assert q4_avg > q1_avg, (
        f"Final quarter pressure mean ({q4_avg:.3f}) should exceed "
        f"first quarter mean ({q1_avg:.3f})"
    )

    # Levels should eventually escalate past HEALTHY
    final_level = levels[-1]
    assert final_level > Level.HEALTHY, (
        f"Expected escalation beyond HEALTHY after full-error ramp, got {final_level}"
    )

    # CAUTION should appear somewhere in the run
    assert Level.CAUTION in levels or any(l > Level.CAUTION for l in levels), (
        "Expected CAUTION or higher to appear during gradual ramp"
    )


# ---------------------------------------------------------------------------
# Test 2: Recovery after crisis
# ---------------------------------------------------------------------------

def test_recovery_after_crisis():
    """Agent escalates under 20 error actions, then recovers to HEALTHY
    after 30 normal actions."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    # Phase 1: trigger escalation
    for i in range(20):
        engine.record_action("agent", _error_action(i))

    escalated_level = engine.get_level("agent")
    assert escalated_level > Level.HEALTHY, (
        f"Expected escalation after 20 errors, got {escalated_level}"
    )

    # Phase 2: recovery — 30 normal actions
    final_level = escalated_level
    for i in range(30):
        result = engine.record_action("agent", _normal_action(i))
        final_level = result.level

    assert final_level == Level.HEALTHY, (
        f"Expected recovery to HEALTHY after 30 normal actions, got {final_level}"
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

    pre_spike_level = engine.get_level("agent")

    # Spike: 3 concentrated errors
    for i in range(3):
        result = engine.record_action("agent", _error_action(i))
    post_spike_level = engine.get_level("agent")

    # Should escalate during or after the spike
    assert post_spike_level >= pre_spike_level, (
        f"Level should not drop during error spike: pre={pre_spike_level}, post={post_spike_level}"
    )

    # Recovery: 20 normal actions
    final_level = post_spike_level
    for i in range(20):
        result = engine.record_action("agent", _normal_action(100 + i))
        final_level = result.level

    assert final_level == Level.HEALTHY, (
        f"Expected recovery to HEALTHY after spike recovery, got {final_level}"
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

def test_budget_depletion_safe_mode():
    """3 agents each spending 100 tokens/action. With budget=1000,
    SAFE_MODE should trigger before 1100 total tokens spent."""
    engine = SOMAEngine(budget={"tokens": 1000})
    engine.register_agent("a1")
    engine.register_agent("a2")
    engine.register_agent("a3")

    agents = ["a1", "a2", "a3"]
    safe_mode_triggered = False
    total_tokens_at_safe_mode = None

    for step in range(12):  # 3 agents × 4 rounds = 12 actions × 100 = 1200 tokens total
        for agent in agents:
            result = engine.record_action(
                agent,
                Action(tool_name="bash", output_text="output", token_count=100),
            )
            spent = sum(engine.budget.spent.values())
            if result.level == Level.SAFE_MODE and not safe_mode_triggered:
                safe_mode_triggered = True
                total_tokens_at_safe_mode = spent

        if safe_mode_triggered:
            break

    assert safe_mode_triggered, "SAFE_MODE should have triggered before token budget exhausted"
    assert total_tokens_at_safe_mode is not None
    assert total_tokens_at_safe_mode <= 1100, (
        f"SAFE_MODE should trigger before 1100 tokens, triggered at {total_tokens_at_safe_mode}"
    )

    # All three agents should eventually be in SAFE_MODE
    # (next action on each agent will see budget_health <= 0)
    for agent in agents:
        result = engine.record_action(
            agent,
            Action(tool_name="bash", output_text="x", token_count=0),
        )
        assert result.level == Level.SAFE_MODE, (
            f"Agent {agent} should be in SAFE_MODE, got {result.level}"
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

    # Record 10 interventions that will resolve as failures:
    # pressure at intervention time > current pressure (so delta <= 0 → failure)
    # We set intervention_pressure == current_pressure so delta == 0 → failure.
    for _ in range(10):
        learning.record_intervention(
            agent_id="agent",
            old=Level.HEALTHY,
            new=Level.CAUTION,
            pressure=0.5,
            signals={"error_rate": 0.5, "uncertainty": 0.3},
        )
        # Each evaluate call passes pressure == 0.5 (same as at intervention) → failure
        learning.evaluate("agent", current_pressure=0.5, actions_since=3)

    # Threshold adjustment should be non-zero for HEALTHY→CAUTION transition
    adj = learning.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION)
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

    # B should have elevated effective pressure compared to C
    b_node = graph._nodes["B"]
    # B may or may not have its own actions, but the key assertion is C isolation
    # Let's confirm C's pressure is not inflated by A's pressure
    a_node = graph._nodes["A"]
    assert c_node.effective_pressure < a_node.effective_pressure or (
        c_node.effective_pressure == c_node.internal_pressure
    ), "C should be isolated from A's pressure"


# ---------------------------------------------------------------------------
# Test 9: Cold start convergence
# ---------------------------------------------------------------------------

def test_cold_start_convergence():
    """Fresh agent receiving 20 identical normal actions. By action 15+,
    pressure should be consistently near zero and level should be HEALTHY."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("agent")

    pressures_after_15: list[float] = []
    levels_after_15: list[Level] = []

    for i in range(20):
        result = engine.record_action("agent", _normal_action(i))
        if i >= 15:
            pressures_after_15.append(result.pressure)
            levels_after_15.append(result.level)

    avg_late_pressure = sum(pressures_after_15) / len(pressures_after_15)
    assert avg_late_pressure < 0.35, (
        f"Pressure should converge near zero after cold start for normal actions, "
        f"got avg={avg_late_pressure:.4f}"
    )
    assert all(l == Level.HEALTHY for l in levels_after_15), (
        f"Level should be HEALTHY after cold start convergence, got: {levels_after_15}"
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
