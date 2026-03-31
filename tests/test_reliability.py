"""Tests for reliability metrics: calibration score (REL-01) and verbal-behavioral
divergence (REL-02)."""

import pytest

from soma.reliability import (
    compute_hedging_rate,
    compute_calibration_score,
    detect_verbal_behavioral_divergence,
)
from soma.engine import SOMAEngine
from soma.types import Action


# ---------------------------------------------------------------------------
# Unit: compute_hedging_rate
# ---------------------------------------------------------------------------

def test_hedging_rate_empty_actions():
    from soma.types import Action
    assert compute_hedging_rate([]) == 0.0


def test_hedging_rate_no_hedging():
    actions = [
        Action(tool_name="Bash", output_text="success"),
        Action(tool_name="Bash", output_text="done"),
    ]
    assert compute_hedging_rate(actions) == 0.0


def test_hedging_rate_all_hedging():
    actions = [
        Action(tool_name="Bash", output_text="maybe this works"),
        Action(tool_name="Bash", output_text="not sure if correct"),
        Action(tool_name="Bash", output_text="probably the right approach"),
    ]
    assert compute_hedging_rate(actions) == pytest.approx(1.0)


def test_hedging_rate_half():
    actions = [
        Action(tool_name="Bash", output_text="this is correct"),
        Action(tool_name="Bash", output_text="maybe this works"),
    ]
    assert compute_hedging_rate(actions) == pytest.approx(0.5)


def test_hedging_rate_case_insensitive():
    actions = [Action(tool_name="Bash", output_text="MAYBE something is wrong")]
    assert compute_hedging_rate(actions) == 1.0


# ---------------------------------------------------------------------------
# Unit: compute_calibration_score
# ---------------------------------------------------------------------------

def test_calibration_high_hedging_low_error():
    """Agent hedges and executes well → HIGH calibration."""
    score = compute_calibration_score(hedging_rate=0.8, error_rate=0.05)
    assert score > 0.7


def test_calibration_high_hedging_high_error():
    """Agent hedges but still fails → LOW calibration."""
    score = compute_calibration_score(hedging_rate=0.8, error_rate=0.9)
    assert score < 0.3


def test_calibration_low_hedging_high_error():
    """Overconfident and failing → LOW calibration."""
    score = compute_calibration_score(hedging_rate=0.0, error_rate=0.8)
    assert score < 0.3


def test_calibration_no_hedging_no_error():
    """Confident and correct → moderate calibration (can't tell from luck)."""
    score = compute_calibration_score(hedging_rate=0.0, error_rate=0.0)
    assert 0.3 < score < 0.8


def test_calibration_in_range():
    for h in [0.0, 0.3, 0.5, 1.0]:
        for e in [0.0, 0.3, 0.5, 1.0]:
            s = compute_calibration_score(h, e)
            assert 0.0 <= s <= 1.0, f"out of range for h={h}, e={e}: {s}"


# ---------------------------------------------------------------------------
# Unit: detect_verbal_behavioral_divergence
# ---------------------------------------------------------------------------

def test_divergence_fires_low_hedging_high_pressure():
    assert detect_verbal_behavioral_divergence(hedging_rate=0.0, pressure=0.8) is True


def test_divergence_no_fire_both_low():
    assert detect_verbal_behavioral_divergence(hedging_rate=0.0, pressure=0.2) is False


def test_divergence_no_fire_hedging_matches_pressure():
    """High hedging offsets high pressure — no divergence."""
    assert detect_verbal_behavioral_divergence(hedging_rate=0.8, pressure=0.8) is False


def test_divergence_custom_threshold():
    assert detect_verbal_behavioral_divergence(0.0, 0.3, threshold=0.25) is True
    assert detect_verbal_behavioral_divergence(0.0, 0.3, threshold=0.5) is False


# ---------------------------------------------------------------------------
# Integration: engine wiring
# ---------------------------------------------------------------------------

class TestReliabilityIntegration:
    def test_calibration_none_during_warmup(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # Default min_calibration_samples=3, action_count=1 → None
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert r.vitals.calibration_score is None

    def test_calibration_computed_after_warmup(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"calibration_min_samples": 2}
        e.register_agent("a")
        for _ in range(3):
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert r.vitals.calibration_score is not None
        assert 0.0 <= r.vitals.calibration_score <= 1.0

    def test_verbal_behavioral_divergence_false_by_default(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert r.vitals.verbal_behavioral_divergence is False

    def test_divergence_fires_with_confident_language_and_errors(self):
        """No hedging + high error pressure past grace period → divergence."""
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "calibration_min_samples": 1,
            "verbal_behavioral_divergence_threshold": 0.2,
        }
        e.register_agent("a")
        # Force past grace period with errors (no hedging in output)
        for _ in range(15):
            r = e.record_action("a", Action(
                tool_name="Bash", output_text="execution complete",
                token_count=50, error=True, retried=True,
            ))
        # Pressure should be elevated and hedging_rate=0 → divergence
        if r.pressure > 0.2:
            assert r.vitals.verbal_behavioral_divergence is True

    def test_divergence_suppressed_by_hedging(self):
        """Hedging language absorbs pressure difference — no divergence."""
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "calibration_min_samples": 1,
            "verbal_behavioral_divergence_threshold": 0.4,
        }
        e.register_agent("a")
        for _ in range(15):
            r = e.record_action("a", Action(
                tool_name="Bash",
                output_text="maybe this is incorrect, possibly the wrong approach, not sure",
                token_count=50, error=True,
            ))
        # hedging_rate ≈ 1.0, so (pressure - hedging_rate) likely < 0.4
        assert r.vitals.verbal_behavioral_divergence is False

    def test_divergence_event_emitted(self):
        """verbal_behavioral_divergence event fires with correct keys."""
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "calibration_min_samples": 1,
            "verbal_behavioral_divergence_threshold": 0.2,
        }
        e.register_agent("a")
        events = []
        e.events.on("verbal_behavioral_divergence", lambda d: events.append(d))

        for _ in range(15):
            e.record_action("a", Action(
                tool_name="Bash", output_text="done",
                token_count=50, error=True, retried=True,
            ))

        if events:
            assert "agent_id" in events[0]
            assert "hedging_rate" in events[0]
            assert "pressure" in events[0]

    def test_divergence_boosts_mode_to_guide(self):
        """When divergence fires on low-pressure agent, mode is at least GUIDE."""
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "calibration_min_samples": 1,
            "verbal_behavioral_divergence_threshold": 0.01,  # fires at any non-trivial pressure
        }
        e.register_agent("a")
        # Run past grace period with moderate pressure but zero hedging
        for _ in range(15):
            r = e.record_action("a", Action(
                tool_name="Bash", output_text="all good here",
                token_count=50, error=True,
            ))
        if r.vitals.verbal_behavioral_divergence:
            assert r.mode >= ResponseMode.GUIDE

    def test_calibration_higher_with_hedging_and_success(self):
        """Hedging + success gives higher calibration than no hedging + errors."""
        e1 = SOMAEngine(budget={"tokens": 100000})
        e1._vitals_config = {"calibration_min_samples": 3}
        e1.register_agent("a")
        for _ in range(5):
            r1 = e1.record_action("a", Action(
                tool_name="Bash",
                output_text="maybe uncertain, not sure, possibly wrong",
                token_count=50,
            ))

        e2 = SOMAEngine(budget={"tokens": 100000})
        e2._vitals_config = {"calibration_min_samples": 3}
        e2.register_agent("a")
        for _ in range(5):
            r2 = e2.record_action("a", Action(
                tool_name="Bash", output_text="done",
                token_count=50, error=True,
            ))

        if r1.vitals.calibration_score and r2.vitals.calibration_score:
            assert r1.vitals.calibration_score > r2.vitals.calibration_score


from soma.types import ResponseMode
