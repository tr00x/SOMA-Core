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


# ── Auto-retire (P1.1) ───────────────────────────────────────────────

def test_refuted_defaults_empty():
    p = CalibrationProfile(family="cc")
    assert p.refuted_patterns == []
    assert not p.is_refuted("bash_retry")


def test_mark_refuted_adds_pattern():
    p = CalibrationProfile(family="cc")
    p.mark_refuted("bash_retry")
    assert "bash_retry" in p.refuted_patterns
    assert p.is_refuted("bash_retry")


def test_mark_refuted_is_idempotent():
    p = CalibrationProfile(family="cc")
    p.mark_refuted("bash_retry")
    p.mark_refuted("bash_retry")
    assert p.refuted_patterns.count("bash_retry") == 1


def test_unmark_refuted_removes_pattern():
    p = CalibrationProfile(family="cc", refuted_patterns=["bash_retry"])
    p.unmark_refuted("bash_retry")
    assert "bash_retry" not in p.refuted_patterns
    assert not p.is_refuted("bash_retry")


def test_unmark_refuted_missing_is_noop():
    p = CalibrationProfile(family="cc")
    p.unmark_refuted("bash_retry")  # does not raise
    assert p.refuted_patterns == []


def test_is_refuted_ignores_phase():
    """Refuted is strictly stronger than silence; fires in every phase."""
    p = CalibrationProfile(
        family="cc", action_count=5, refuted_patterns=["bash_retry"],
    )
    assert p.is_refuted("bash_retry")  # warmup
    p.action_count = 100
    p.phase = "calibrated"
    assert p.is_refuted("bash_retry")
    p.action_count = 600
    p.phase = "adaptive"
    assert p.is_refuted("bash_retry")


def test_refuted_roundtrips_through_save_load(tmp_path):
    p = CalibrationProfile(family="cc", action_count=50)
    p.mark_refuted("bash_retry")
    p.mark_refuted("budget")
    save_profile(p)
    q = load_profile("cc-1")
    assert set(q.refuted_patterns) == {"bash_retry", "budget"}


def test_maybe_refresh_refuted_marks_refuted_from_validate(monkeypatch):
    """Validate returns refuted → profile records it."""
    p = CalibrationProfile(family="cc", action_count=600)

    class FakeStore:
        def get_ab_outcomes(self, pattern, agent_family=None):
            return []
        def close(self):
            pass

    def fake_validate(outcomes, *, pattern, agent_family=None, min_pairs=30):
        from soma.ab_control import ValidationResult
        status = "refuted" if pattern == "bash_retry" else "validated"
        return ValidationResult(
            pattern=pattern, agent_family=agent_family,
            fires_treatment=30, fires_control=30,
            mean_treatment_delta=0.0, mean_control_delta=0.0,
            delta_difference=0.0, p_value=0.01, effect_size=0.3,
            status=status,
        )

    import soma.ab_control as ab
    monkeypatch.setattr(ab, "validate", fake_validate)

    changed = cal.maybe_refresh_refuted(p, analytics_store=FakeStore())
    assert changed is True
    assert "bash_retry" in p.refuted_patterns
    assert "cost_spiral" not in p.refuted_patterns


def test_maybe_refresh_refuted_unmarks_on_recovery(monkeypatch):
    """A previously refuted pattern whose status flips back drops off the list."""
    p = CalibrationProfile(
        family="cc", action_count=600, refuted_patterns=["bash_retry"],
    )

    class FakeStore:
        def get_ab_outcomes(self, pattern, agent_family=None):
            return []
        def close(self):
            pass

    def fake_validate(outcomes, *, pattern, agent_family=None, min_pairs=30):
        from soma.ab_control import ValidationResult
        return ValidationResult(
            pattern=pattern, agent_family=agent_family,
            fires_treatment=30, fires_control=30,
            mean_treatment_delta=0.0, mean_control_delta=0.0,
            delta_difference=0.0, p_value=0.01, effect_size=0.3,
            status="validated",
        )

    import soma.ab_control as ab
    monkeypatch.setattr(ab, "validate", fake_validate)

    changed = cal.maybe_refresh_refuted(p, analytics_store=FakeStore())
    assert changed is True
    assert "bash_retry" not in p.refuted_patterns


def test_maybe_refresh_refuted_respects_interval(monkeypatch):
    """Second call within REFRESH_INTERVAL is a no-op."""
    p = CalibrationProfile(family="cc", action_count=600)
    p.last_refuted_check_action = 600

    called = {"n": 0}

    class FakeStore:
        def get_ab_outcomes(self, pattern, agent_family=None):
            called["n"] += 1
            return []
        def close(self):
            pass

    changed = cal.maybe_refresh_refuted(p, analytics_store=FakeStore())
    assert changed is False
    assert called["n"] == 0


# ── P2.3: validated-pattern tracking ────────────────────────────────


def test_mark_validated_adds_to_list():
    p = CalibrationProfile(family="cc")
    assert not p.is_validated("bash_retry")
    p.mark_validated("bash_retry")
    assert p.is_validated("bash_retry")
    # Idempotent.
    p.mark_validated("bash_retry")
    assert p.validated_patterns == ["bash_retry"]


def test_unmark_validated_drops_from_list():
    p = CalibrationProfile(family="cc", validated_patterns=["bash_retry"])
    p.unmark_validated("bash_retry")
    assert not p.is_validated("bash_retry")
    # Idempotent: removing again is a no-op.
    p.unmark_validated("bash_retry")
    assert p.validated_patterns == []


def test_validated_roundtrips_through_save_load(tmp_path):
    p = CalibrationProfile(family="cc", action_count=50)
    p.mark_validated("bash_retry")
    p.mark_validated("cost_spiral")
    save_profile(p)
    q = load_profile("cc-1")
    assert set(q.validated_patterns) == {"bash_retry", "cost_spiral"}


def test_maybe_refresh_refuted_also_marks_validated(monkeypatch):
    """Same refresh pass also records validated verdicts (P2.3)."""
    p = CalibrationProfile(family="cc", action_count=600)

    class FakeStore:
        def get_ab_outcomes(self, pattern, agent_family=None):
            return []
        def close(self):
            pass

    def fake_validate(outcomes, *, pattern, agent_family=None, min_pairs=30):
        from soma.ab_control import ValidationResult
        if pattern == "bash_retry":
            status = "validated"
        elif pattern == "cost_spiral":
            status = "refuted"
        else:
            status = "collecting"
        return ValidationResult(
            pattern=pattern, agent_family=agent_family,
            fires_treatment=30, fires_control=30,
            mean_treatment_delta=0.0, mean_control_delta=0.0,
            delta_difference=0.0, p_value=0.01, effect_size=0.3,
            status=status,
        )

    import soma.ab_control as ab
    monkeypatch.setattr(ab, "validate", fake_validate)

    changed = cal.maybe_refresh_refuted(p, analytics_store=FakeStore())
    assert changed is True
    assert "bash_retry" in p.validated_patterns
    assert "cost_spiral" not in p.validated_patterns
    assert "cost_spiral" in p.refuted_patterns


# ── Stale-silence cache clear (v2026.5.5 migration fix) ────────────


def _write_profile(soma_dir: Path, family: str, **fields) -> Path:
    base = {
        "family": family, "action_count": 4000, "phase": "adaptive",
        "drift_p25": 0.0, "drift_p75": 0.0,
        "entropy_p25": 0.0, "entropy_p75": 0.0,
        "typical_error_burst": 0, "typical_retry_burst": 0,
        "typical_success_rate": 0.0,
        "silenced_patterns": [], "last_silence_check_action": 0,
        "pattern_precision_cache": {},
        "refuted_patterns": [], "last_refuted_check_action": 0,
        "validated_patterns": [],
        "created_at": 1.0, "updated_at": 1.0, "schema_version": 1,
    }
    base.update(fields)
    path = soma_dir / f"calibration_{family}.json"
    path.write_text(json.dumps(base))
    return path


def test_clear_stale_silence_cache_zeros_silence_fields(tmp_path):
    _write_profile(
        tmp_path, "cc",
        silenced_patterns=["blind_edit", "context"],
        pattern_precision_cache={"blind_edit": 0.05, "context": 0.1},
        last_silence_check_action=3500,
        refuted_patterns=["drift"],
        validated_patterns=["bash_retry"],
    )
    n = cal.clear_stale_silence_cache(soma_dir=tmp_path)
    assert n == 1
    data = json.loads((tmp_path / "calibration_cc.json").read_text())
    assert data["silenced_patterns"] == []
    assert data["pattern_precision_cache"] == {}
    assert data["last_silence_check_action"] == 0
    # Auto-retire and skeptic allowlists must survive — they reflect
    # post-reset A/B evidence, not the biased silence cache.
    assert data["refuted_patterns"] == ["drift"]
    assert data["validated_patterns"] == ["bash_retry"]
    # Non-silence state must not be touched.
    assert data["action_count"] == 4000
    assert data["phase"] == "adaptive"


def test_clear_stale_silence_cache_handles_multiple_profiles(tmp_path):
    _write_profile(tmp_path, "cc", silenced_patterns=["a", "b"])
    _write_profile(tmp_path, "claude-code", silenced_patterns=["c"])
    _write_profile(tmp_path, "empty", silenced_patterns=[])
    n = cal.clear_stale_silence_cache(soma_dir=tmp_path)
    assert n == 3
    for family in ("cc", "claude-code", "empty"):
        data = json.loads((tmp_path / f"calibration_{family}.json").read_text())
        assert data["silenced_patterns"] == []


def test_clear_stale_silence_cache_missing_dir_returns_zero(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert cal.clear_stale_silence_cache(soma_dir=missing) == 0


def test_clear_stale_silence_cache_skips_malformed_json(tmp_path):
    (tmp_path / "calibration_broken.json").write_text("{not json")
    _write_profile(tmp_path, "cc", silenced_patterns=["a"])
    # Malformed file must not halt the sweep — other profiles still clear.
    n = cal.clear_stale_silence_cache(soma_dir=tmp_path)
    assert n == 1
    data = json.loads((tmp_path / "calibration_cc.json").read_text())
    assert data["silenced_patterns"] == []


def test_clear_stale_silence_cache_idempotent(tmp_path):
    _write_profile(tmp_path, "cc", silenced_patterns=["a"])
    assert cal.clear_stale_silence_cache(soma_dir=tmp_path) == 1
    # Second run is a no-op in effect — silenced already empty.
    cal.clear_stale_silence_cache(soma_dir=tmp_path)
    data = json.loads((tmp_path / "calibration_cc.json").read_text())
    assert data["silenced_patterns"] == []


def test_maybe_refresh_refuted_unmarks_validated_on_regression(monkeypatch):
    """Pattern that drops out of validated (e.g. flips to collecting) is cleared."""
    p = CalibrationProfile(
        family="cc", action_count=600, validated_patterns=["bash_retry"],
    )

    class FakeStore:
        def get_ab_outcomes(self, pattern, agent_family=None):
            return []
        def close(self):
            pass

    def fake_validate(outcomes, *, pattern, agent_family=None, min_pairs=30):
        from soma.ab_control import ValidationResult
        return ValidationResult(
            pattern=pattern, agent_family=agent_family,
            fires_treatment=10, fires_control=10,
            mean_treatment_delta=0.0, mean_control_delta=0.0,
            delta_difference=0.0, p_value=None, effect_size=None,
            status="collecting",
        )

    import soma.ab_control as ab
    monkeypatch.setattr(ab, "validate", fake_validate)

    cal.maybe_refresh_refuted(p, analytics_store=FakeStore())
    assert "bash_retry" not in p.validated_patterns
