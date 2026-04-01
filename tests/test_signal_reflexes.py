"""Tests for SOMA signal reflexes — pure function evaluators."""

from __future__ import annotations

from soma.reflexes import ReflexResult
from soma.signal_reflexes import (
    evaluate_predictor_checkpoint,
    evaluate_drift_guardian,
    evaluate_handoff,
    evaluate_rca_injection,
    evaluate_commit_gate,
    evaluate_all_signals,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_prediction(
    confidence: float = 0.5,
    actions_ahead: int = 5,
    will_escalate: bool = True,
    dominant_reason: str = "trend",
) -> dict:
    """Build a prediction-like dict for testing."""
    return {
        "confidence": confidence,
        "actions_ahead": actions_ahead,
        "will_escalate": will_escalate,
        "dominant_reason": dominant_reason,
    }


class _FakePrediction:
    """Mimics Prediction dataclass for signal reflex evaluators."""

    def __init__(self, confidence: float, actions_ahead: int, will_escalate: bool = True, dominant_reason: str = "trend"):
        self.confidence = confidence
        self.actions_ahead = actions_ahead
        self.will_escalate = will_escalate
        self.dominant_reason = dominant_reason


# ── TestPredictorCheckpoint ──────────────────────────────────────────


class TestPredictorCheckpoint:
    def test_fires_in_reflex_mode(self):
        pred = _FakePrediction(confidence=0.8, actions_ahead=2)
        result = evaluate_predictor_checkpoint(pred, mode="reflex")
        assert result.allow is True
        assert result.reflex_kind == "predictor_checkpoint"
        assert result.inject_message is not None
        assert "predicted_escalation" in result.inject_message or "confidence=" in result.inject_message

    def test_fires_in_guide_mode(self):
        pred = _FakePrediction(confidence=0.8, actions_ahead=2)
        result = evaluate_predictor_checkpoint(pred, mode="guide")
        assert result.allow is True
        assert result.reflex_kind == "predictor_warning"
        assert result.inject_message is not None

    def test_below_confidence_threshold(self):
        pred = _FakePrediction(confidence=0.5, actions_ahead=5)
        result = evaluate_predictor_checkpoint(pred, mode="reflex")
        assert result.allow is True
        assert result.reflex_kind == ""

    def test_too_far_away(self):
        pred = _FakePrediction(confidence=0.8, actions_ahead=5)
        result = evaluate_predictor_checkpoint(pred, mode="reflex")
        assert result.allow is True
        assert result.reflex_kind == ""

    def test_none_prediction(self):
        result = evaluate_predictor_checkpoint(None, mode="reflex")
        assert result.allow is True
        assert result.reflex_kind == ""


# ── TestDriftGuardian ────────────────────────────────────────────────


class TestDriftGuardian:
    def test_fires_above_threshold(self):
        result = evaluate_drift_guardian(
            drift=0.5, original_task="Build auth", current_activity="refactoring CSS"
        )
        assert result.allow is True
        assert result.reflex_kind == "drift_guardian"
        assert "Build auth" in result.inject_message
        assert "drift=" in result.inject_message

    def test_below_threshold(self):
        result = evaluate_drift_guardian(drift=0.3, original_task="Build auth")
        assert result.allow is True
        assert result.reflex_kind == ""

    def test_no_original_task_graceful(self):
        result = evaluate_drift_guardian(drift=0.5, original_task="")
        assert result.allow is True
        assert result.reflex_kind == ""
        assert result.inject_message is None

    def test_none_original_task_graceful(self):
        result = evaluate_drift_guardian(drift=0.5, original_task=None)
        assert result.allow is True
        assert result.reflex_kind == ""
        assert result.inject_message is None


# ── TestHandoffSuggestion ────────────────────────────────────────────


class TestHandoffSuggestion:
    def test_fires_below_threshold(self):
        result = evaluate_handoff(
            success_rate=0.35,
            handoff_text="Agent 'main' half-life boundary passed",
            agent_id="main",
        )
        assert result.allow is True
        assert result.reflex_kind == "handoff_suggestion"
        assert result.inject_message is not None
        assert "half-life" in result.inject_message.lower() or "handoff" in result.inject_message.lower() or "Agent" in result.inject_message

    def test_above_threshold(self):
        result = evaluate_handoff(success_rate=0.5, handoff_text="irrelevant", agent_id="main")
        assert result.allow is True
        assert result.reflex_kind == ""

    def test_detail_contains_trust_reduction(self):
        result = evaluate_handoff(
            success_rate=0.35,
            handoff_text="Agent 'main' half-life boundary passed",
            agent_id="main",
        )
        assert "success_rate" in result.detail.lower() or "agent" in result.detail.lower()


# ── TestRCAInjection ─────────────────────────────────────────────────


class TestRCAInjection:
    def test_fires_above_threshold(self):
        result = evaluate_rca_injection(error_rate=0.35, rca_text="stuck in Edit loop")
        assert result.allow is True
        assert result.reflex_kind == "rca_injection"
        assert result.inject_message is not None
        assert "error_rate=" in result.inject_message
        assert "stuck in Edit loop" in result.inject_message

    def test_below_threshold(self):
        result = evaluate_rca_injection(error_rate=0.25, rca_text="something")
        assert result.allow is True
        assert result.reflex_kind == ""

    def test_no_rca_text(self):
        result = evaluate_rca_injection(error_rate=0.35, rca_text=None)
        assert result.allow is True
        assert result.reflex_kind == ""
        assert result.inject_message is None


# ── TestCommitGate ───────────────────────────────────────────────────


class TestCommitGate:
    def test_blocks_grade_d(self):
        result = evaluate_commit_gate(grade="D", tool_name="Bash", tool_input={"command": "git commit -m 'test'"})
        assert result.allow is False
        assert result.reflex_kind == "commit_gate"
        assert result.block_message is not None

    def test_blocks_grade_f(self):
        result = evaluate_commit_gate(grade="F", tool_name="Bash", tool_input={"command": "  git  commit -am 'wip'"})
        assert result.allow is False
        assert result.reflex_kind == "commit_gate"

    def test_warns_grade_c(self):
        result = evaluate_commit_gate(grade="C", tool_name="Bash", tool_input={"command": "git commit -m 'fix'"})
        assert result.allow is True
        assert result.inject_message is not None

    def test_allows_grade_b(self):
        result = evaluate_commit_gate(grade="B", tool_name="Bash", tool_input={"command": "git commit -m 'feat'"})
        assert result.allow is True
        assert result.inject_message is None

    def test_allows_grade_a(self):
        result = evaluate_commit_gate(grade="A", tool_name="Bash", tool_input={"command": "git commit -m 'feat'"})
        assert result.allow is True
        assert result.inject_message is None

    def test_non_commit_tool_passes(self):
        result = evaluate_commit_gate(grade="F", tool_name="Edit", tool_input={"file_path": "foo.py"})
        assert result.allow is True
        assert result.reflex_kind == ""

    def test_non_commit_bash_passes(self):
        result = evaluate_commit_gate(grade="F", tool_name="Bash", tool_input={"command": "git status"})
        assert result.allow is True
        assert result.reflex_kind == ""


# ── TestEvaluateAllSignals ───────────────────────────────────────────


class TestEvaluateAllSignals:
    def test_caps_to_max_2(self):
        """Multiple elevated signals should cap to max 2 results."""
        results = evaluate_all_signals(
            prediction=_FakePrediction(confidence=0.9, actions_ahead=1),
            soma_mode="reflex",
            drift=0.6,
            original_task="Build auth",
            current_activity="refactoring CSS",
            error_rate=0.5,
            rca_text="error cascade",
            success_rate=0.2,
            handoff_text="Agent approaching half-life",
            agent_id="main",
        )
        assert len(results) <= 2

    def test_priority_order(self):
        """RCA should take priority over drift/handoff/checkpoint."""
        results = evaluate_all_signals(
            prediction=_FakePrediction(confidence=0.9, actions_ahead=1),
            soma_mode="reflex",
            drift=0.6,
            original_task="Build auth",
            current_activity="refactoring CSS",
            error_rate=0.5,
            rca_text="error cascade",
            success_rate=0.2,
            handoff_text="Agent approaching half-life",
            agent_id="main",
        )
        kinds = [r.reflex_kind for r in results]
        assert kinds[0] == "rca_injection"

    def test_empty_when_nothing_fires(self):
        results = evaluate_all_signals(
            prediction=None,
            soma_mode="reflex",
            drift=0.1,
            original_task="",
            current_activity="",
            error_rate=0.1,
            rca_text=None,
            success_rate=0.8,
            handoff_text="",
            agent_id="main",
        )
        assert len(results) == 0
