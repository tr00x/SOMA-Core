"""Self-calibration profile tests (v2026.5.0 Day 1).

Covers: family resolution, phase transitions, threshold derivation,
auto-silence hysteresis, distribution math, and atomic persistence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma import calibration as cal
from soma.calibration import (
    CALIBRATED_EXIT_ACTIONS,
    CalibrationProfile,
    LEGACY_FLOORS,
    SILENCE_MIN_FIRES,
    WARMUP_EXIT_ACTIONS,
    _percentile,
    _phase_for,
    _typical_burst,
    apply_distributions,
    calibration_family,
    compute_distributions,
    load_profile,
    reset_profile,
    save_profile,
)


@pytest.fixture(autouse=True)
def _isolated_soma_dir(tmp_path, monkeypatch):
    """Redirect all calibration I/O into a temp dir per test."""
    monkeypatch.setattr(cal, "SOMA_DIR", tmp_path)
    yield tmp_path


# ── Family resolution ────────────────────────────────────────────────

def test_family_strips_numeric_tail():
    assert calibration_family("cc-92331") == "cc"
    assert calibration_family("cc_47512") == "cc"
    assert calibration_family("swe-bench-48") == "swe-bench"


def test_family_preserves_non_numeric_ids():
    assert calibration_family("my-agent") == "my-agent"
    assert calibration_family("worker") == "worker"


def test_family_handles_empty_id():
    assert calibration_family("") == "default"


# ── Phase math ───────────────────────────────────────────────────────

def test_phase_for_boundaries():
    assert _phase_for(0) == "warmup"
    assert _phase_for(WARMUP_EXIT_ACTIONS - 1) == "warmup"
    assert _phase_for(WARMUP_EXIT_ACTIONS) == "calibrated"
    assert _phase_for(CALIBRATED_EXIT_ACTIONS - 1) == "calibrated"
    assert _phase_for(CALIBRATED_EXIT_ACTIONS) == "adaptive"
    assert _phase_for(10_000) == "adaptive"


def test_advance_updates_phase_and_counter():
    p = CalibrationProfile(family="cc")
    # Stay inside warmup.
    p.advance(WARMUP_EXIT_ACTIONS - 5)
    assert p.action_count == WARMUP_EXIT_ACTIONS - 5
    assert p.phase == "warmup"
    # Cross into calibrated.
    p.advance(10)
    assert p.phase == "calibrated"
    # Cross into adaptive.
    p.advance(CALIBRATED_EXIT_ACTIONS)
    assert p.phase == "adaptive"


def test_advance_ignores_non_positive():
    p = CalibrationProfile(family="cc", action_count=10)
    p.advance(0)
    p.advance(-5)
    assert p.action_count == 10


def test_phase_predicates():
    p = CalibrationProfile(family="cc")
    assert p.is_warmup()
    p.advance(WARMUP_EXIT_ACTIONS)
    assert p.is_calibrated()
    p.advance(CALIBRATED_EXIT_ACTIONS)
    assert p.is_adaptive()


# ── Personal thresholds ──────────────────────────────────────────────

def test_warmup_thresholds_use_legacy_floors():
    p = CalibrationProfile(family="cc")
    assert p.drift_threshold() == LEGACY_FLOORS["drift_threshold"]
    assert p.entropy_threshold() == LEGACY_FLOORS["entropy_threshold"]
    assert p.retry_storm_streak() == LEGACY_FLOORS["retry_storm_streak"]
    assert p.error_cascade_streak() == LEGACY_FLOORS["error_cascade_streak"]


def test_calibrated_thresholds_prefer_personal_when_higher():
    p = CalibrationProfile(
        family="cc", action_count=200,
        drift_p75=0.55, entropy_p25=0.7,
        typical_error_burst=3, typical_retry_burst=4,
    )
    assert p.drift_threshold() == pytest.approx(0.55)
    assert p.entropy_threshold() == pytest.approx(0.7)
    # error streak = typical_burst + 1, floored at legacy
    assert p.error_cascade_streak() == 4
    assert p.retry_storm_streak() == 5


def test_calibrated_thresholds_clamp_to_legacy_floor():
    """Extremely quiet user can't disable signals by sending 0 drift forever."""
    p = CalibrationProfile(
        family="cc", action_count=200,
        drift_p75=0.05, entropy_p25=0.1,
        typical_error_burst=0,
    )
    assert p.drift_threshold() == LEGACY_FLOORS["drift_threshold"]
    assert p.entropy_threshold() == LEGACY_FLOORS["entropy_threshold"]
    assert p.error_cascade_streak() == LEGACY_FLOORS["error_cascade_streak"]


# ── Auto-silence hysteresis ──────────────────────────────────────────

def test_silence_requires_minimum_fires():
    p = CalibrationProfile(family="cc", action_count=600)
    p.update_silence("drift", fires=SILENCE_MIN_FIRES - 1, helped=0)
    assert "drift" not in p.silenced_patterns


def test_silence_triggers_below_20_percent():
    p = CalibrationProfile(family="cc", action_count=600)
    p.update_silence("drift", fires=30, helped=3)  # 10% helped
    assert "drift" in p.silenced_patterns


def test_silence_lifts_above_40_percent():
    p = CalibrationProfile(family="cc", action_count=600, silenced_patterns=["drift"])
    p.update_silence("drift", fires=30, helped=15)  # 50% helped
    assert "drift" not in p.silenced_patterns


def test_silence_hysteresis_gap_keeps_state():
    """Between 20% and 40% — neither silence nor re-enable triggers."""
    p = CalibrationProfile(family="cc", action_count=600, silenced_patterns=["drift"])
    p.update_silence("drift", fires=30, helped=9)  # 30% — inside the gap
    assert "drift" in p.silenced_patterns  # stays silenced

    q = CalibrationProfile(family="cc", action_count=600)
    q.update_silence("drift", fires=30, helped=9)
    assert "drift" not in q.silenced_patterns  # stays un-silenced


def test_should_silence_only_in_adaptive_phase():
    p = CalibrationProfile(family="cc", action_count=50, silenced_patterns=["drift"])
    assert not p.should_silence("drift")  # warmup ignores silence list
    p.action_count = 200
    p.phase = "calibrated"
    assert not p.should_silence("drift")
    p.action_count = 600
    p.phase = "adaptive"
    assert p.should_silence("drift")


# ── Distribution math ────────────────────────────────────────────────

def test_percentile_empty_is_zero():
    assert _percentile([], 50) == 0.0


def test_percentile_single_returns_value():
    assert _percentile([0.42], 75) == pytest.approx(0.42)


def test_percentile_basic():
    xs = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    assert _percentile(xs, 25) == pytest.approx(0.3)
    assert _percentile(xs, 75) == pytest.approx(0.8)


def test_typical_burst_handles_all_false():
    assert _typical_burst([False, False, False], truthy=True) == 0


def test_typical_burst_counts_runs():
    # runs of True: [1, 3, 2] → median 2
    flags = [True, False, True, True, True, False, True, True]
    assert _typical_burst(flags, truthy=True) == 2


def test_compute_distributions_populates_expected_keys():
    drifts = [{"drift": v} for v in [0.1, 0.2, 0.3, 0.4, 0.5]]
    errors = [False, True, True, False, False, True]
    entropy = [0.2, 0.5, 0.7, 0.9, 1.0]
    result = compute_distributions(drifts, errors, entropy)
    assert set(result.keys()) == {
        "drift_p25", "drift_p75", "entropy_p25", "entropy_p75",
        "typical_error_burst", "typical_retry_burst", "typical_success_rate",
    }
    assert 0.0 <= result["typical_success_rate"] <= 1.0
    assert result["drift_p75"] >= result["drift_p25"]


def test_apply_distributions_writes_to_profile():
    p = CalibrationProfile(family="cc")
    apply_distributions(p, {
        "drift_p25": 0.1, "drift_p75": 0.6,
        "entropy_p25": 0.4, "entropy_p75": 0.9,
        "typical_error_burst": 3, "typical_retry_burst": 4,
        "typical_success_rate": 0.82,
    })
    assert p.drift_p75 == 0.6
    assert p.typical_success_rate == pytest.approx(0.82)


# ── Persistence ──────────────────────────────────────────────────────

def test_load_missing_returns_fresh_profile(tmp_path):
    p = load_profile("cc-12345")
    assert p.family == "cc"
    assert p.action_count == 0
    assert p.phase == "warmup"


def test_save_then_load_roundtrip(tmp_path):
    action_count = (WARMUP_EXIT_ACTIONS + CALIBRATED_EXIT_ACTIONS) // 2
    p = CalibrationProfile(family="cc", action_count=action_count, drift_p75=0.41)
    p.phase = _phase_for(p.action_count)
    save_profile(p)

    reloaded = load_profile("cc-99999")
    assert reloaded.family == "cc"
    assert reloaded.action_count == action_count
    assert reloaded.phase == "calibrated"
    assert reloaded.drift_p75 == pytest.approx(0.41)


def test_save_is_atomic_no_partial_files(tmp_path):
    """After a save, only the final file should exist (no .tmp siblings)."""
    p = CalibrationProfile(family="cc", action_count=10)
    save_profile(p)
    tmps = list(tmp_path.glob("calibration_cc.json.*.tmp"))
    assert tmps == []
    assert (tmp_path / "calibration_cc.json").exists()


def test_load_corrupt_returns_fresh(tmp_path):
    (tmp_path / "calibration_cc.json").write_text("{not json")
    p = load_profile("cc-1")
    assert p.action_count == 0
    assert p.phase == "warmup"


def test_load_ignores_unknown_fields_for_forward_compat(tmp_path):
    path = tmp_path / "calibration_cc.json"
    action_count = (WARMUP_EXIT_ACTIONS + CALIBRATED_EXIT_ACTIONS) // 2
    path.write_text(json.dumps({
        "family": "cc", "action_count": action_count,
        "future_field_v2": "hello",
    }))
    p = load_profile("cc-1")
    assert p.action_count == action_count
    assert p.phase == "calibrated"


def test_load_rederives_phase_from_action_count(tmp_path):
    """Hand-edited stale phase must not outrank the action counter."""
    path = tmp_path / "calibration_cc.json"
    path.write_text(json.dumps({
        "family": "cc", "action_count": 600, "phase": "warmup",
    }))
    p = load_profile("cc-1")
    assert p.phase == "adaptive"


def test_reset_profile_removes_file(tmp_path):
    save_profile(CalibrationProfile(family="cc", action_count=5))
    assert (tmp_path / "calibration_cc.json").exists()
    assert reset_profile("cc-17") is True
    assert not (tmp_path / "calibration_cc.json").exists()


def test_reset_profile_missing_returns_false(tmp_path):
    assert reset_profile("cc-17") is False
