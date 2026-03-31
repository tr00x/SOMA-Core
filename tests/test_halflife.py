"""Tests for half-life estimator (HLF-01, HLF-02)."""

import math
import pytest

from soma.halflife import (
    compute_half_life,
    predict_success_rate,
    predict_actions_to_threshold,
    generate_handoff_suggestion,
)
from soma.engine import SOMAEngine
from soma.types import Action


# ---------------------------------------------------------------------------
# Unit tests — compute_half_life
# ---------------------------------------------------------------------------

def test_half_life_zero_error_rate():
    """No historical errors → half_life = avg_session_length."""
    hl = compute_half_life(avg_session_length=50.0, avg_error_rate=0.0)
    assert hl == pytest.approx(50.0)


def test_half_life_high_error_rate_is_shorter():
    """High-error agents have shorter effective half-life."""
    hl_clean = compute_half_life(50.0, avg_error_rate=0.0)
    hl_error = compute_half_life(50.0, avg_error_rate=0.4)
    assert hl_error < hl_clean


def test_half_life_never_below_minimum():
    """half_life is always >= min_half_life regardless of inputs."""
    hl = compute_half_life(avg_session_length=1.0, avg_error_rate=0.99)
    assert hl >= 10.0


# ---------------------------------------------------------------------------
# Unit tests — predict_success_rate
# ---------------------------------------------------------------------------

def test_success_rate_at_zero_is_one():
    assert predict_success_rate(0, half_life=50.0) == pytest.approx(1.0)


def test_success_rate_at_half_life_is_half():
    hl = 50.0
    assert predict_success_rate(50, half_life=hl) == pytest.approx(0.5, abs=1e-9)


def test_success_rate_decays_monotonically():
    hl = 30.0
    rates = [predict_success_rate(t, hl) for t in range(0, 100, 10)]
    assert all(rates[i] > rates[i + 1] for i in range(len(rates) - 1))


def test_success_rate_in_range():
    for t in [0, 10, 50, 100, 200]:
        r = predict_success_rate(t, half_life=50.0)
        assert 0.0 <= r <= 1.0


def test_success_rate_zero_half_life_returns_zero():
    assert predict_success_rate(10, half_life=0.0) == 0.0


# ---------------------------------------------------------------------------
# Unit tests — predict_actions_to_threshold
# ---------------------------------------------------------------------------

def test_actions_to_threshold_zero_when_already_past():
    # At t=100 with hl=50, P ≈ 0.25 < 0.5
    remaining = predict_actions_to_threshold(100, half_life=50.0, threshold=0.5)
    assert remaining == 0


def test_actions_to_threshold_positive_before_crossing():
    # At t=0, P=1.0 > 0.5, should have ~50 actions to threshold
    remaining = predict_actions_to_threshold(0, half_life=50.0, threshold=0.5)
    assert remaining == pytest.approx(50, abs=2)


def test_actions_to_threshold_none_for_invalid_threshold():
    assert predict_actions_to_threshold(10, 50.0, threshold=1.0) is None
    assert predict_actions_to_threshold(10, 50.0, threshold=0.0) is None


# ---------------------------------------------------------------------------
# Unit tests — generate_handoff_suggestion
# ---------------------------------------------------------------------------

def test_handoff_suggestion_contains_agent_id():
    msg = generate_handoff_suggestion("my-agent", 60, 50.0, 0.35)
    assert "my-agent" in msg


def test_handoff_suggestion_contains_action_count():
    msg = generate_handoff_suggestion("a", 75, 50.0, 0.25)
    assert "75" in msg


def test_handoff_suggestion_not_empty():
    msg = generate_handoff_suggestion("a", 10, 50.0, 0.88)
    assert len(msg) > 20


# ---------------------------------------------------------------------------
# Integration tests — engine wiring
# ---------------------------------------------------------------------------

class TestHalfLifeIntegration:
    def test_predicted_success_none_without_fingerprint(self):
        """Without fingerprint history, predicted_success_rate is None."""
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        # No fingerprint data → None
        assert r.vitals.predicted_success_rate is None

    def test_half_life_warning_false_by_default(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert r.vitals.half_life_warning is False

    def test_handoff_suggestion_none_without_fingerprint(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert r.handoff_suggestion is None

    def test_half_life_warning_fires_with_mocked_fingerprint(self):
        """With a fingerprint showing short avg_session_length, warning fires quickly."""
        from unittest.mock import patch, MagicMock

        e = SOMAEngine(budget={"tokens": 100000})
        # very short half-life (session_length=5) and lookahead=10 → fires after ~1 action
        e._vitals_config = {
            "half_life_min_samples": 1,
            "half_life_lookahead_actions": 10,
            "half_life_success_threshold": 0.5,
        }
        e.register_agent("a")

        mock_fp = MagicMock()
        mock_fp.avg_session_length = 5.0
        mock_fp.avg_error_rate = 0.0
        mock_fp.sample_count = 3
        mock_fp_engine = MagicMock()
        mock_fp_engine.get.return_value = mock_fp

        with patch("soma.state.get_fingerprint_engine", return_value=mock_fp_engine):
            # At t=1 with hl=5, P(1+10) = P(11) = exp(-ln2*11/5) ≈ 0.21 < 0.5 → warning
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))

        assert r.vitals.half_life_warning is True
        assert r.handoff_suggestion is not None
        assert "a" in r.handoff_suggestion

    def test_half_life_no_warning_when_session_short(self):
        """With long half-life and short session, no warning fires."""
        from unittest.mock import patch, MagicMock

        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "half_life_min_samples": 1,
            "half_life_lookahead_actions": 5,
            "half_life_success_threshold": 0.5,
        }
        e.register_agent("a")

        mock_fp = MagicMock()
        mock_fp.avg_session_length = 200.0  # Very long half-life
        mock_fp.avg_error_rate = 0.0
        mock_fp.sample_count = 5
        mock_fp_engine = MagicMock()
        mock_fp_engine.get.return_value = mock_fp

        with patch("soma.state.get_fingerprint_engine", return_value=mock_fp_engine):
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))

        assert r.vitals.half_life_warning is False
        assert r.handoff_suggestion is None

    def test_half_life_event_emitted_on_warning(self):
        """half_life_warning event is emitted with correct payload."""
        from unittest.mock import patch, MagicMock

        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"half_life_min_samples": 1, "half_life_lookahead_actions": 10}
        e.register_agent("a")

        events = []
        e.events.on("half_life_warning", lambda d: events.append(d))

        mock_fp = MagicMock()
        mock_fp.avg_session_length = 3.0
        mock_fp.avg_error_rate = 0.0
        mock_fp.sample_count = 2
        mock_fp_engine = MagicMock()
        mock_fp_engine.get.return_value = mock_fp

        with patch("soma.state.get_fingerprint_engine", return_value=mock_fp_engine):
            e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))

        assert len(events) >= 1
        assert events[0]["agent_id"] == "a"
        assert "handoff_suggestion" in events[0]
        assert "half_life" in events[0]

    def test_predicted_success_rate_in_vitals(self):
        """predicted_success_rate is in [0,1] when fingerprint exists."""
        from unittest.mock import patch, MagicMock

        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"half_life_min_samples": 1}
        e.register_agent("a")

        mock_fp = MagicMock()
        mock_fp.avg_session_length = 50.0
        mock_fp.avg_error_rate = 0.1
        mock_fp.sample_count = 5
        mock_fp_engine = MagicMock()
        mock_fp_engine.get.return_value = mock_fp

        with patch("soma.state.get_fingerprint_engine", return_value=mock_fp_engine):
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))

        assert r.vitals.predicted_success_rate is not None
        assert 0.0 <= r.vitals.predicted_success_rate <= 1.0
