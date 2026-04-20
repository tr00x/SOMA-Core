"""Tests for the A/B control module.

Coverage:
- Deterministic 50/50 assignment by hash(family|pattern|action).
- ``SOMA_DISABLE_AB=1`` short-circuit to treatment.
- Welch's t-test numerics on stdlib implementation.
- Classification thresholds (validated / refuted / inconclusive /
  collecting) match the plan's definition.
- SQLite round-trip via ``AnalyticsStore.record_ab_outcome`` →
  ``get_ab_outcomes``.
"""

from __future__ import annotations

import random

import pytest

from soma import ab_control
from soma.analytics import AnalyticsStore


# ── Arm assignment ──────────────────────────────────────────────────

def test_assignment_is_deterministic():
    a = ab_control.should_inject("error_cascade", "cc", 42)
    b = ab_control.should_inject("error_cascade", "cc", 42)
    c = ab_control.should_inject("error_cascade", "cc", 42)
    assert a == b == c


def test_assignment_splits_roughly_evenly():
    """Over 2000 action numbers the split should be ~50/50."""
    counts = {"treatment": 0, "control": 0}
    for n in range(2000):
        arm = ab_control.should_inject("bash_retry", "cc", n)
        counts[arm] += 1
    # Allow ±5% slack for MD5's empirical distribution.
    assert 900 <= counts["treatment"] <= 1100
    assert 900 <= counts["control"] <= 1100


def test_disable_env_forces_treatment(monkeypatch):
    monkeypatch.setenv("SOMA_DISABLE_AB", "1")
    for n in range(20):
        assert ab_control.should_inject("x", "cc", n) == "treatment"


def test_disable_env_not_set_uses_hash(monkeypatch):
    monkeypatch.delenv("SOMA_DISABLE_AB", raising=False)
    # Not all actions can be treatment — hash split is binary.
    arms = {ab_control.should_inject("x", "cc", n) for n in range(50)}
    assert arms == {"treatment", "control"}


# ── Stats primitives ────────────────────────────────────────────────

def test_welch_identical_samples_high_p():
    a = [0.1, 0.12, 0.11, 0.13, 0.15]
    p = ab_control._welch_t_test_p_value(a, a)
    assert p == pytest.approx(1.0)


def test_welch_clear_separation_low_p():
    a = [0.3 + 0.01 * i for i in range(30)]
    b = [0.05 + 0.01 * i for i in range(30)]
    p = ab_control._welch_t_test_p_value(a, b)
    assert p < 0.001


def test_welch_handles_single_sample_gracefully():
    # n_a < 2 → degenerate; must not raise.
    p = ab_control._welch_t_test_p_value([0.5], [0.1, 0.2, 0.3])
    assert p == 1.0


def test_cohens_d_positive_when_a_larger():
    d = ab_control._cohens_d(
        [0.3, 0.32, 0.28, 0.31, 0.29] * 3,
        [0.05, 0.07, 0.04, 0.06, 0.05] * 3,
    )
    assert d > 0.5  # very large effect


def test_cohens_d_zero_on_degenerate_inputs():
    assert ab_control._cohens_d([0.5] * 10, [0.5] * 10) == 0.0
    assert ab_control._cohens_d([0.5], [0.5]) == 0.0


# ── validate() — classification ────────────────────────────────────

def _rows(arm: str, n: int, mean: float, seed: int, spread: float = 0.08):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        before = 0.8
        after = before - rng.gauss(mean, spread)
        out.append({
            "arm": arm, "pressure_before": before, "pressure_after": after,
        })
    return out


def test_validate_validated_when_treatment_clearly_better():
    rows = _rows("treatment", 35, mean=0.30, seed=1) + _rows("control", 35, mean=0.05, seed=2)
    r = ab_control.validate(rows, pattern="error_cascade")
    assert r.status == "validated"
    assert r.p_value < 0.05
    assert r.effect_size > 0.2
    assert r.delta_difference > 0.1


def test_validate_refuted_when_control_outperforms():
    rows = _rows("treatment", 35, mean=0.05, seed=3) + _rows("control", 35, mean=0.30, seed=4)
    r = ab_control.validate(rows, pattern="blind_edit")
    assert r.status == "refuted"


def test_validate_collecting_when_under_min_pairs():
    rows = _rows("treatment", 5, mean=0.3, seed=5) + _rows("control", 5, mean=0.05, seed=6)
    r = ab_control.validate(rows, pattern="bash_retry")
    assert r.status == "collecting"
    assert r.p_value is None
    assert r.effect_size is None


def test_validate_inconclusive_after_hundreds_of_null_pairs():
    rng = random.Random(7)
    rows = []
    # Same distribution in both arms → no effect.
    for _ in range(110):
        rows.append({
            "arm": "treatment", "pressure_before": 0.8,
            "pressure_after": 0.8 - rng.gauss(0.1, 0.05),
        })
        rows.append({
            "arm": "control", "pressure_before": 0.8,
            "pressure_after": 0.8 - rng.gauss(0.1, 0.05),
        })
    r = ab_control.validate(rows, pattern="entropy_drop")
    assert r.status == "inconclusive"
    assert r.p_value is not None and r.p_value > 0.05


def test_validate_ignores_incomplete_rows():
    """Rows with None pressure are skipped, not crashed on."""
    rows = _rows("treatment", 35, mean=0.3, seed=8) + _rows("control", 35, mean=0.05, seed=9)
    rows.append({"arm": "treatment", "pressure_before": None, "pressure_after": None})
    rows.append({"arm": "control", "pressure_before": 0.5, "pressure_after": None})
    r = ab_control.validate(rows, pattern="cost_spiral")
    # The extra rows shouldn't alter classification.
    assert r.status == "validated"


# ── SQLite round-trip ──────────────────────────────────────────────

def test_record_and_fetch_ab_outcome(tmp_path):
    store = AnalyticsStore(path=tmp_path / "ab.db")
    store.record_ab_outcome(
        agent_family="cc", pattern="bash_retry", arm="treatment",
        pressure_before=0.7, pressure_after=0.4, followed=True,
    )
    store.record_ab_outcome(
        agent_family="cc", pattern="bash_retry", arm="control",
        pressure_before=0.7, pressure_after=0.65, followed=False,
    )
    rows = store.get_ab_outcomes(pattern="bash_retry", agent_family="cc")
    assert len(rows) == 2
    assert {r["arm"] for r in rows} == {"treatment", "control"}


def test_invalid_arm_raises(tmp_path):
    store = AnalyticsStore(path=tmp_path / "x.db")
    with pytest.raises(ValueError):
        store.record_ab_outcome(
            agent_family="cc", pattern="x", arm="placebo",
            pressure_before=0.5, pressure_after=0.4,
        )


def test_list_ab_patterns_distinct(tmp_path):
    store = AnalyticsStore(path=tmp_path / "list.db")
    for pattern in ("a", "a", "b", "c"):
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="treatment",
            pressure_before=0.5, pressure_after=0.3,
        )
    assert store.list_ab_patterns() == ["a", "b", "c"]


def test_get_ab_outcomes_excludes_null_after(tmp_path):
    """Rows with ``pressure_after IS NULL`` are skipped (incomplete)."""
    store = AnalyticsStore(path=tmp_path / "null.db")
    store.record_ab_outcome(
        agent_family="cc", pattern="x", arm="treatment",
        pressure_before=0.5, pressure_after=None,
    )
    store.record_ab_outcome(
        agent_family="cc", pattern="x", arm="control",
        pressure_before=0.5, pressure_after=0.3,
    )
    rows = store.get_ab_outcomes(pattern="x", agent_family="cc")
    assert len(rows) == 1
    assert rows[0]["arm"] == "control"


def test_get_ab_outcomes_no_family_filter(tmp_path):
    store = AnalyticsStore(path=tmp_path / "nofam.db")
    store.record_ab_outcome(
        agent_family="cc", pattern="x", arm="treatment",
        pressure_before=0.5, pressure_after=0.3,
    )
    store.record_ab_outcome(
        agent_family="swe", pattern="x", arm="control",
        pressure_before=0.6, pressure_after=0.5,
    )
    rows = store.get_ab_outcomes(pattern="x")
    families = {r["agent_family"] for r in rows}
    assert families == {"cc", "swe"}
