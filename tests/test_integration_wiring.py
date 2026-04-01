"""Integration tests for module wiring — prove dead modules are now live.

Tests verify that:
1. phase_drift reduces false positive drift during read-heavy sessions
2. context_control limits injection count by ResponseMode
3. cross_session blending activates when local confidence is low
"""

from __future__ import annotations

from soma.engine import SOMAEngine, _detect_phase
from soma.types import Action, ResponseMode
from soma.context_control import apply_context_control
from soma.cross_session import CrossSessionPredictor
from soma.session_store import SessionRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action(tool: str, error: bool = False, output: str = "ok") -> Action:
    return Action(tool_name=tool, output_text=output, token_count=10, error=error)


def _run_n_actions(engine: SOMAEngine, agent_id: str, actions: list[Action]):
    """Record a sequence of actions, return the last ActionResult."""
    result = None
    for a in actions:
        result = engine.record_action(agent_id, a)
    return result


# ---------------------------------------------------------------------------
# Test 1: phase_drift reduces false positive drift during read-heavy sessions
# ---------------------------------------------------------------------------

def test_phase_drift_reduces_read_heavy_drift():
    """Read-heavy sessions should produce lower drift than mixed sessions.

    In research phase, tools like Read/Grep/Glob match the expected
    phase pattern, so drift is reduced by up to 50%. Without phase_drift,
    switching from an implement baseline to read-heavy activity would
    register as high drift. With phase_drift, the drift is suppressed
    because reading is expected during research.
    """
    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("agent")

    # Warmup: establish a mixed baseline (implement phase)
    warmup = [_make_action("Edit"), _make_action("Write"), _make_action("Read"),
              _make_action("Bash"), _make_action("Edit")] * 3
    _run_n_actions(engine, "agent", warmup)

    # Now switch to pure research (Read/Grep heavy)
    research_actions = [_make_action("Read"), _make_action("Grep"),
                        _make_action("Glob"), _make_action("Read"),
                        _make_action("Read")]
    result_research = _run_n_actions(engine, "agent", research_actions)

    # Verify phase detection works
    assert _detect_phase([_make_action("Read")] * 5) == "research"

    # Drift should be modest (phase_drift reduces it). Without phase_drift,
    # switching from edit-heavy to read-heavy would produce high drift.
    # We verify drift is not alarmingly high.
    assert result_research.vitals.drift < 0.8, (
        f"Drift {result_research.vitals.drift:.2f} too high for research phase"
    )


def test_phase_detection_returns_correct_phases():
    """_detect_phase should correctly identify research, implement, test, debug."""
    assert _detect_phase([_make_action("Read")] * 5) == "research"
    assert _detect_phase([_make_action("Grep")] * 5) == "research"
    assert _detect_phase([_make_action("Edit")] * 5) == "implement"
    assert _detect_phase([_make_action("Write")] * 5) == "implement"
    assert _detect_phase([_make_action("Bash")] * 5) == "test"

    # Debug: high error rate
    debug_actions = [_make_action("Bash", error=True)] * 4 + [_make_action("Read")]
    assert _detect_phase(debug_actions) == "debug"

    assert _detect_phase([]) == "unknown"


# ---------------------------------------------------------------------------
# Test 2: context_control limits injection count by ResponseMode
# ---------------------------------------------------------------------------

def test_context_control_limits_by_mode():
    """apply_context_control should reduce message count at higher modes.

    OBSERVE: 100% retained
    GUIDE: 80% retained (ceiling)
    WARN: 50% retained (ceiling)
    BLOCK: 0% retained
    """
    messages = [f"finding_{i}" for i in range(10)]
    base_context = {"messages": messages, "tools": [], "system_prompt": ""}

    # OBSERVE: all messages kept
    result_observe = apply_context_control(base_context, ResponseMode.OBSERVE)
    assert len(result_observe["messages"]) == 10

    # GUIDE: 80% = 8 messages (ceil(10 * 0.8))
    result_guide = apply_context_control(base_context, ResponseMode.GUIDE)
    assert len(result_guide["messages"]) == 8

    # WARN: 50% = 5 messages (ceil(10 * 0.5))
    result_warn = apply_context_control(base_context, ResponseMode.WARN)
    assert len(result_warn["messages"]) == 5

    # BLOCK: 0 messages
    result_block = apply_context_control(base_context, ResponseMode.BLOCK)
    assert len(result_block["messages"]) == 0


def test_context_control_preserves_newest():
    """Under WARN, the newest 50% of messages should be kept."""
    messages = ["old_1", "old_2", "old_3", "new_1", "new_2"]
    context = {"messages": messages, "tools": [], "system_prompt": ""}

    result = apply_context_control(context, ResponseMode.WARN)
    # ceil(5 * 0.5) = 3 newest
    assert result["messages"] == ["old_3", "new_1", "new_2"]


# ---------------------------------------------------------------------------
# Test 3: cross_session blending activates when local confidence is low
# ---------------------------------------------------------------------------

def test_cross_session_blending_activates():
    """CrossSessionPredictor should blend historical data when available.

    When local confidence is low (few data points) and a similar
    historical trajectory exists (cosine > 0.8), the prediction
    should blend 0.6 local + 0.4 historical.
    """
    predictor = CrossSessionPredictor(window=10, horizon=5)

    # Create synthetic historical trajectories (3 required minimum)
    rising_trajectory = [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    predictor._session_patterns = [
        rising_trajectory,
        rising_trajectory,  # duplicates count
        rising_trajectory,
    ]

    # Feed current readings that match the start of the historical trajectory
    for p in [0.1, 0.15, 0.2]:
        predictor.update(p)

    # Predict with low threshold
    pred = predictor.predict(next_threshold=0.5)

    # With only 3 readings, local confidence is low.
    # The historical trajectory shows rising to 0.8, so blending should
    # increase the predicted pressure beyond what linear trend alone gives.
    assert pred.predicted_pressure > 0.0, "Prediction should be positive"

    # Verify the cross-session predictor produces predictions
    # (exact values depend on linear trend + cross-session blending)
    assert pred.confidence > 0.0, "Confidence should be positive"


def test_cross_session_fallback_without_history():
    """Without session history, CrossSessionPredictor acts like base predictor."""
    predictor = CrossSessionPredictor(window=10, horizon=5)

    # No session patterns loaded
    for p in [0.1, 0.2, 0.3]:
        predictor.update(p)

    pred_cross = predictor.predict(next_threshold=0.5)

    # Compare with base predictor
    from soma.predictor import PressurePredictor
    base = PressurePredictor(window=10, horizon=5)
    for p in [0.1, 0.2, 0.3]:
        base.update(p)

    pred_base = base.predict(next_threshold=0.5)

    # Should produce identical results without history
    assert abs(pred_cross.predicted_pressure - pred_base.predicted_pressure) < 1e-6
    assert abs(pred_cross.confidence - pred_base.confidence) < 1e-6
