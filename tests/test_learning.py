"""Tests for soma.learning.LearningEngine."""

from __future__ import annotations

import pytest

from soma.learning import LearningEngine, _Record
from soma.types import InterventionOutcome, Level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(**kwargs) -> LearningEngine:
    defaults = dict(
        evaluation_window=5,
        threshold_adj_step=0.02,
        weight_adj_step=0.05,
        min_weight=0.2,
        max_threshold_shift=0.10,
        min_interventions=3,
    )
    defaults.update(kwargs)
    return LearningEngine(**defaults)


SIGNALS = {"error_rate": 0.8, "uncertainty": 0.6}


def _record_and_drain(
    engine: LearningEngine,
    agent_id: str,
    old: Level,
    new: Level,
    pressure_at: float,
    signals: dict,
    current_pressure: float,
    actions: int = 10,
) -> InterventionOutcome:
    """Helper: record an intervention and immediately evaluate it."""
    engine.record_intervention(agent_id, old, new, pressure_at, signals)
    return engine.evaluate(agent_id, current_pressure, actions)


# ---------------------------------------------------------------------------
# Basic record / pending
# ---------------------------------------------------------------------------

def test_record_creates_pending_entry():
    engine = make_engine()
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    pending = engine.pending("a1")
    assert len(pending) == 1
    r = pending[0]
    assert r.agent_id == "a1"
    assert r.old_level is Level.HEALTHY
    assert r.new_level is Level.CAUTION
    assert r.pressure == pytest.approx(0.30)
    assert r.actions_elapsed == 0


def test_pending_returns_empty_for_unknown_agent():
    engine = make_engine()
    assert engine.pending("nobody") == []


# ---------------------------------------------------------------------------
# Too early — window not reached
# ---------------------------------------------------------------------------

def test_evaluate_pending_when_window_not_reached():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    # Only 3 actions — below window of 5
    result = engine.evaluate("a1", current_pressure=0.10, actions_since=3)
    assert result is InterventionOutcome.PENDING
    # Record should still be in pending
    assert len(engine.pending("a1")) == 1


def test_evaluate_pending_with_no_record():
    engine = make_engine()
    result = engine.evaluate("nobody", current_pressure=0.10, actions_since=10)
    assert result is InterventionOutcome.PENDING


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_evaluate_success_when_pressure_drops():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.CAUTION, Level.DEGRADE, 0.60, SIGNALS)
    result = engine.evaluate("a1", current_pressure=0.30, actions_since=10)
    assert result is InterventionOutcome.SUCCESS


def test_success_clears_pending():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.CAUTION, Level.DEGRADE, 0.60, SIGNALS)
    engine.evaluate("a1", current_pressure=0.30, actions_since=10)
    assert engine.pending("a1") == []


def test_success_does_not_adjust_threshold():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.CAUTION, Level.DEGRADE, 0.60, SIGNALS)
    engine.evaluate("a1", current_pressure=0.30, actions_since=10)
    assert engine.get_threshold_adjustment(Level.CAUTION, Level.DEGRADE) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------

def test_evaluate_failure_when_pressure_stays():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.CAUTION, Level.DEGRADE, 0.60, SIGNALS)
    result = engine.evaluate("a1", current_pressure=0.65, actions_since=10)
    assert result is InterventionOutcome.FAILURE


def test_failure_clears_pending():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.CAUTION, Level.DEGRADE, 0.60, SIGNALS)
    engine.evaluate("a1", current_pressure=0.65, actions_since=10)
    assert engine.pending("a1") == []


# ---------------------------------------------------------------------------
# Threshold rises after min_interventions failures
# ---------------------------------------------------------------------------

def test_threshold_not_raised_before_min_interventions():
    """2 failures with min_interventions=3 should produce no threshold change."""
    engine = make_engine(evaluation_window=5, min_interventions=3, threshold_adj_step=0.02)
    for _ in range(2):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=10)

    assert engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION) == pytest.approx(0.0)


def test_threshold_rises_after_min_interventions():
    """3 failures (== min_interventions) should trigger the first adjustment."""
    engine = make_engine(evaluation_window=5, min_interventions=3, threshold_adj_step=0.02)
    for _ in range(3):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=10)

    assert engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION) == pytest.approx(0.02)


def test_threshold_rises_after_four_failures():
    """4 failures should apply two steps (failures 3 and 4 each trigger a step)."""
    engine = make_engine(evaluation_window=5, min_interventions=3, threshold_adj_step=0.02)
    for _ in range(4):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=10)

    assert engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION) == pytest.approx(0.04)


# ---------------------------------------------------------------------------
# Threshold capped at max_threshold_shift
# ---------------------------------------------------------------------------

def test_threshold_bounded_at_max_shift():
    """Many failures must not push adjustment beyond max_threshold_shift."""
    engine = make_engine(
        evaluation_window=5,
        min_interventions=3,
        threshold_adj_step=0.02,
        max_threshold_shift=0.10,
    )
    for _ in range(20):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=10)

    adj = engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION)
    assert adj <= 0.10 + 1e-9  # must not exceed max


def test_threshold_bounded_does_not_exceed_max_exactly():
    engine = make_engine(
        evaluation_window=1,
        min_interventions=1,
        threshold_adj_step=0.03,
        max_threshold_shift=0.10,
    )
    # 5 failures × 0.03 step would = 0.15 without cap
    for _ in range(5):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=5)

    adj = engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION)
    assert adj == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Weight adjustments
# ---------------------------------------------------------------------------

def test_weight_lowered_after_min_interventions():
    engine = make_engine(
        evaluation_window=5, min_interventions=3, weight_adj_step=0.05
    )
    for _ in range(3):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=10)

    # One step of -0.05 applied
    assert engine.get_weight_adjustment("error_rate") == pytest.approx(-0.05)
    assert engine.get_weight_adjustment("uncertainty") == pytest.approx(-0.05)


def test_weight_bounded_by_min_weight():
    """With original weight 2.0 and min_weight 0.2, the max negative adj is -1.8."""
    engine = make_engine(
        evaluation_window=1,
        min_interventions=1,
        weight_adj_step=0.05,
        min_weight=0.2,
    )
    # Drive many failures; each failure produces a -0.05 step.
    # The spec says adjustment >= -1.8 for original weight 2.0 with min 0.2.
    # The engine tracks raw cumulative adjustments; callers apply the floor.
    # We verify here that even with 100 failures the engine itself records
    # the steps (floor enforcement is at the consumer level), OR that the
    # engine respects the floor. Per spec the test verifies adj >= -1.8.
    for _ in range(100):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, {"sig": 2.0})
        engine.evaluate("a1", current_pressure=0.40, actions_since=5)

    # The effective adjustment must not push the weight below min_weight (0.2).
    # original weight = 2.0 → max down-shift = 2.0 - 0.2 = 1.8
    adj = engine.get_weight_adjustment("sig")
    # adj is negative; must not exceed -1.8 in magnitude
    assert adj >= -1.8 - 1e-9


def test_weight_not_changed_before_min_interventions():
    engine = make_engine(evaluation_window=5, min_interventions=3)
    for _ in range(2):
        engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
        engine.evaluate("a1", current_pressure=0.40, actions_since=10)

    assert engine.get_weight_adjustment("error_rate") == pytest.approx(0.0)


def test_unknown_signal_weight_adjustment_is_zero():
    engine = make_engine()
    assert engine.get_weight_adjustment("nonexistent_signal") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def test_reset_clears_pending():
    engine = make_engine()
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    engine.reset()
    assert engine.pending("a1") == []


def test_reset_clears_adjustments():
    engine = make_engine(evaluation_window=1, min_interventions=1, threshold_adj_step=0.02)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    engine.evaluate("a1", current_pressure=0.40, actions_since=5)
    engine.reset()
    assert engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION) == pytest.approx(0.0)
    assert engine.get_weight_adjustment("error_rate") == pytest.approx(0.0)


def test_reset_clears_history():
    engine = make_engine(evaluation_window=1, min_interventions=1)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    engine.evaluate("a1", current_pressure=0.40, actions_since=5)
    engine.reset()
    # After reset, further failures should not fire (failure_counts cleared)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    engine.evaluate("a1", current_pressure=0.40, actions_since=5)
    # Only 1 failure post-reset with min_interventions=1 → threshold should be raised
    # (verifies failure_counts were reset, not preserved)
    adj = engine.get_threshold_adjustment(Level.HEALTHY, Level.CAUTION)
    assert adj == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_to_dict_contains_config_keys():
    engine = make_engine()
    d = engine.to_dict()
    for key in (
        "evaluation_window",
        "threshold_adj_step",
        "weight_adj_step",
        "min_weight",
        "max_threshold_shift",
        "min_interventions",
    ):
        assert key in d


def test_to_dict_contains_state_keys():
    engine = make_engine()
    d = engine.to_dict()
    for key in ("threshold_adjustments", "weight_adjustments", "pending", "history"):
        assert key in d


def test_to_dict_reflects_adjustments():
    engine = make_engine(evaluation_window=1, min_interventions=1, threshold_adj_step=0.02)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, {"sig": 1.0})
    engine.evaluate("a1", current_pressure=0.40, actions_since=5)

    d = engine.to_dict()
    assert "HEALTHY->CAUTION" in d["threshold_adjustments"]
    assert d["threshold_adjustments"]["HEALTHY->CAUTION"] == pytest.approx(0.02)
    assert "sig" in d["weight_adjustments"]


def test_to_dict_pending_included():
    engine = make_engine(evaluation_window=10)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    d = engine.to_dict()
    assert "a1" in d["pending"]
    assert len(d["pending"]["a1"]) == 1
    assert d["pending"]["a1"][0]["old_level"] == "HEALTHY"
    assert d["pending"]["a1"][0]["new_level"] == "CAUTION"


def test_to_dict_history_included_after_resolution():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.CAUTION, Level.DEGRADE, 0.60, SIGNALS)
    engine.evaluate("a1", current_pressure=0.30, actions_since=10)
    d = engine.to_dict()
    assert "a1" in d["history"]
    assert len(d["history"]["a1"]) == 1


# ---------------------------------------------------------------------------
# Multi-agent isolation
# ---------------------------------------------------------------------------

def test_different_agents_are_independent():
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)
    engine.record_intervention("a2", Level.HEALTHY, Level.DEGRADE, 0.50, SIGNALS)

    assert len(engine.pending("a1")) == 1
    assert len(engine.pending("a2")) == 1

    # Resolve a1 with success
    outcome_a1 = engine.evaluate("a1", current_pressure=0.10, actions_since=10)
    assert outcome_a1 is InterventionOutcome.SUCCESS
    # a2 still pending
    assert len(engine.pending("a2")) == 1


# ---------------------------------------------------------------------------
# Window accumulation across multiple evaluate calls
# ---------------------------------------------------------------------------

def test_window_accumulates_across_calls():
    """actions_since is cumulative — two calls of 3 each reach window=5."""
    engine = make_engine(evaluation_window=5)
    engine.record_intervention("a1", Level.HEALTHY, Level.CAUTION, 0.30, SIGNALS)

    result1 = engine.evaluate("a1", current_pressure=0.10, actions_since=3)
    assert result1 is InterventionOutcome.PENDING

    result2 = engine.evaluate("a1", current_pressure=0.10, actions_since=3)
    assert result2 is InterventionOutcome.SUCCESS
