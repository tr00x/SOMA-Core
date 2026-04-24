"""Tests for the A/B control module.

Coverage:
- Block-randomized 50/50 assignment with persistent per-(family,
  pattern) counters.
- Opt-out via ``SOMA_DISABLE_CONTROL_ARM`` (and the deprecated
  ``SOMA_DISABLE_AB`` alias).
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

@pytest.fixture(autouse=True)
def _isolated_counters(tmp_path, monkeypatch):
    """Redirect the counter file to a tmp path so tests never touch
    the user's real ``~/.soma/ab_counters.json`` and don't leak state
    between cases."""
    monkeypatch.setattr(
        ab_control,
        "_COUNTERS_PATH",
        tmp_path / "ab_counters.json",
    )
    yield


def test_assignment_stays_balanced_in_burst():
    """A burst of 20 firings on one (family, pattern) must land within
    ±1 pair of perfect balance — the whole point of block-randomizing
    instead of hashing ``action_number``, which clustered 40 firings
    into a single arm in v2026.5.4 production data."""
    counts = {"treatment": 0, "control": 0}
    for n in range(20):
        counts[ab_control.should_inject("entropy_drop", "cc", n)] += 1
    diff = abs(counts["treatment"] - counts["control"])
    assert diff <= ab_control.BALANCE_THRESHOLD


def test_assignment_splits_roughly_evenly_over_many_firings():
    """Over 2000 firings the split should be very close to 50/50.
    Block randomization makes this guarantee tighter than the old MD5
    scheme: no streaks ≥ BALANCE_THRESHOLD are possible."""
    counts = {"treatment": 0, "control": 0}
    for n in range(2000):
        arm = ab_control.should_inject("bash_retry", "cc", n)
        counts[arm] += 1
    # Block randomization bounds |T−C| ≤ BALANCE_THRESHOLD regardless of
    # the coin flips, so we can assert much tighter than ±5%.
    assert abs(counts["treatment"] - counts["control"]) <= ab_control.BALANCE_THRESHOLD


def test_balance_invariant_holds_after_every_firing():
    """The core guarantee: ``|T − C| ≤ BALANCE_THRESHOLD`` after every
    single firing. This is what prevents the v2026.5.4 bug where 40+
    consecutive firings all went to the same arm — impossible here
    because the next firing past the threshold is forced into the
    minority arm."""
    t = c = 0
    for n in range(200):
        arm = ab_control.should_inject("budget", "cc", n)
        if arm == "treatment":
            t += 1
        else:
            c += 1
        assert abs(t - c) <= ab_control.BALANCE_THRESHOLD, (
            f"balance invariant broken at firing {n}: T={t}, C={c}"
        )


def test_counters_are_isolated_per_pattern_and_family():
    """One pattern's imbalance must not push another pattern's next
    firing. Each (family, pattern) maintains its own counter."""
    # Drive pattern A five times.
    for n in range(5):
        ab_control.should_inject("pattern_a", "cc", n)
    # pattern_b starts fresh.
    arms = [ab_control.should_inject("pattern_b", "cc", n) for n in range(2)]
    # First two pattern_b firings are both coin flips (neither arm is
    # ≥ BALANCE_THRESHOLD ahead on a zero counter), so they may be any
    # combination; but the counter file must contain pattern_b entries
    # and pattern_a entries separately.
    counters = ab_control._load_counters()
    assert "cc|pattern_a" in counters
    assert "cc|pattern_b" in counters
    assert sum(counters["cc|pattern_a"]) == 5
    assert sum(counters["cc|pattern_b"]) == 2
    assert arms  # Silence unused variable warning.


def test_corrupt_counter_file_falls_back_empty(tmp_path, monkeypatch):
    bad = tmp_path / "ab_counters.json"
    bad.write_text("{not valid json")
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", bad)
    # Must not raise, must produce a valid arm.
    arm = ab_control.should_inject("bash_retry", "cc", 0)
    assert arm in ("treatment", "control")


def test_disable_control_arm_env_forces_treatment(monkeypatch):
    monkeypatch.setenv("SOMA_DISABLE_CONTROL_ARM", "1")
    for n in range(20):
        assert ab_control.should_inject("x", "cc", n) == "treatment"


def test_legacy_disable_ab_env_still_honoured(monkeypatch):
    """The old ``SOMA_DISABLE_AB`` flag stays wired as a deprecated
    alias so existing user configs don't silently re-enable the
    control arm after upgrading."""
    monkeypatch.delenv("SOMA_DISABLE_CONTROL_ARM", raising=False)
    monkeypatch.setenv("SOMA_DISABLE_AB", "1")
    for n in range(20):
        assert ab_control.should_inject("x", "cc", n) == "treatment"


def test_disable_env_not_set_uses_block_randomizer(monkeypatch):
    monkeypatch.delenv("SOMA_DISABLE_CONTROL_ARM", raising=False)
    monkeypatch.delenv("SOMA_DISABLE_AB", raising=False)
    arms = {ab_control.should_inject("x", "cc", n) for n in range(50)}
    assert arms == {"treatment", "control"}


def test_reset_counters_wipes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    ab_control.should_inject("bash_retry", "cc", 0)
    assert (tmp_path / "ab_counters.json").exists()
    ab_control.reset_counters()
    assert not (tmp_path / "ab_counters.json").exists()


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


def test_non_convergence_returns_safe_p_value():
    """_beta_cf returning NaN must degrade to p=1.0 (no false 'validated').

    We force non-convergence by pushing ``max_iter`` to 1 and then call
    _two_sided_p — if the degradation path isn't wired, this would
    either crash or emit a bogus tiny p-value and pass through as
    ``validated``. Both are unacceptable.
    """
    import math
    from soma.ab_control import _beta_cf, _two_sided_p

    # Direct probe: non-convergence must surface as NaN.
    nan = _beta_cf(0.5, 10.0, 10.0, max_iter=1, eps=0.0)
    assert math.isnan(nan)

    # _two_sided_p / _regularized_incomplete_beta should swallow NaN
    # and return a safe p-value. With plausible real inputs it converges
    # easily, so we can only verify the guard by patching _beta_cf to
    # always fail:
    import soma.ab_control as abm
    original = abm._beta_cf
    try:
        abm._beta_cf = lambda *a, **k: float("nan")
        p = _two_sided_p(1.5, df=10)
        # Safe default is 1.0 (pattern reported as "no effect detected").
        assert p == 1.0
    finally:
        abm._beta_cf = original


def test_ab_horizon_constant_matches_plan():
    """A/B pressure_after measurement horizon must be a small fixed
    number — if this drifts the treatment/control windows fall out of
    sync and the proof layer becomes biased again.
    """
    from soma.hooks.post_tool_use import _AB_MEASUREMENT_HORIZON
    assert _AB_MEASUREMENT_HORIZON == 2


def test_guidance_outcome_skips_control_arm(tmp_path):
    """Control arm never saw the guidance → ``guidance_outcomes`` row
    would be meaningless. The A/B table captures the control-arm
    data; the dashboard ROI view stays uncontaminated.
    """
    from soma.analytics import AnalyticsStore
    from soma.hooks.post_tool_use import _record_guidance_outcome

    db = tmp_path / "a.db"
    pending = {
        "pattern": "bash_retry", "ab_arm": "control",
        "pressure_at_injection": 0.6,
    }
    _record_guidance_outcome(
        agent_id="cc-ctl", pending=pending,
        followed=False, pressure_after=0.55,
        analytics_path=db,
    )
    rows = AnalyticsStore(path=db)._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes WHERE agent_id = 'cc-ctl'"
    ).fetchone()
    assert rows[0] == 0

    # Treatment arm still writes.
    pending["ab_arm"] = "treatment"
    _record_guidance_outcome(
        agent_id="cc-ctl", pending=pending,
        followed=True, pressure_after=0.2,
        analytics_path=db,
    )
    rows = AnalyticsStore(path=db)._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes WHERE agent_id = 'cc-ctl'"
    ).fetchone()
    assert rows[0] == 1


def test_record_ab_outcome_self_marks_pending(tmp_path):
    """After a successful write, ``pending`` must carry ab_recorded=True
    so the next call in the same hook can short-circuit without hitting
    SQLite again. Round-2 fix: the function now self-marks instead of
    relying on the caller to remember."""
    from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

    pending = {
        "pattern": "bash_retry", "actions_since": 2,
        "ab_arm": "treatment", "pressure_at_injection": 0.7,
    }
    ok = _record_ab_outcome_at_horizon(
        agent_id="cc-mark",
        pending=pending,
        pressure_after=0.3,
        analytics_path=tmp_path / "ab.db",
    )
    assert ok is True
    assert pending["ab_recorded"] is True

    # Second call on the same pending is a no-op even though the
    # conditions are otherwise satisfied.
    again = _record_ab_outcome_at_horizon(
        agent_id="cc-mark",
        pending=pending,
        pressure_after=0.2,
        analytics_path=tmp_path / "ab.db",
    )
    assert again is False


def test_record_ab_outcome_skips_if_already_recorded(tmp_path):
    """The horizon recorder must be idempotent — reading the same
    pending twice must not write two rows."""
    from soma.analytics import AnalyticsStore
    from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

    pending = {
        "pattern": "bash_retry", "actions_since": 2,
        "ab_arm": "treatment", "pressure_at_injection": 0.7,
        "ab_recorded": True,
    }
    wrote = _record_ab_outcome_at_horizon(
        agent_id="cc-idem",
        pending=pending,
        pressure_after=0.3,
        analytics_path=tmp_path / "a.db",
    )
    assert wrote is False


def test_record_ab_outcome_waits_until_horizon(tmp_path):
    """Below the horizon the recorder is a no-op — treatment and
    control must land at the same ``actions_since``."""
    from soma.analytics import AnalyticsStore
    from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

    pending = {
        "pattern": "bash_retry", "actions_since": 1,
        "ab_arm": "treatment", "pressure_at_injection": 0.7,
    }
    wrote = _record_ab_outcome_at_horizon(
        agent_id="cc-early",
        pending=pending,
        pressure_after=0.3,
        analytics_path=tmp_path / "a.db",
    )
    assert wrote is False
    store = AnalyticsStore(path=tmp_path / "a.db")
    assert store.list_ab_patterns() == []


def test_record_ab_outcome_at_horizon_writes_once(tmp_path):
    """At horizon the row is written with ``followed`` from pressure delta."""
    from soma.analytics import AnalyticsStore
    from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

    pending = {
        "pattern": "bash_retry", "actions_since": 2,
        "ab_arm": "treatment", "pressure_at_injection": 0.7,
    }
    ok = _record_ab_outcome_at_horizon(
        agent_id="cc-horizon",
        pending=pending,
        pressure_after=0.4,  # delta 0.3 ≥ 0.15
        analytics_path=tmp_path / "ab.db",
    )
    assert ok is True
    rows = AnalyticsStore(path=tmp_path / "ab.db").get_ab_outcomes(
        pattern="bash_retry",
    )
    assert len(rows) == 1
    assert rows[0]["followed"] == 1
    assert rows[0]["pressure_before"] == 0.7
    assert rows[0]["pressure_after"] == 0.4


def test_record_ab_outcome_at_horizon_marks_not_followed_when_pressure_flat(tmp_path):
    from soma.analytics import AnalyticsStore
    from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

    pending = {
        "pattern": "context", "actions_since": 2,
        "ab_arm": "control", "pressure_at_injection": 0.6,
    }
    _record_ab_outcome_at_horizon(
        agent_id="cc-flat",
        pending=pending,
        pressure_after=0.58,  # delta 0.02 < 0.15
        analytics_path=tmp_path / "ab.db",
    )
    rows = AnalyticsStore(path=tmp_path / "ab.db").get_ab_outcomes(pattern="context")
    assert rows[0]["followed"] == 0


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
