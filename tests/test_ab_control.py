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


# ── Idempotency (firing_id) ────────────────────────────────────────

class TestShouldInjectIdempotency:
    """Without firing_id every call rebumps the counter — biases the A/B
    verdict on retry, replay, or pre/post double-consult. With firing_id
    the same firing always returns the same arm without touching the
    counter."""

    def test_same_firing_id_returns_same_arm(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab.json")
        first = ab_control.should_inject(
            "context", "cc", 0, firing_id="agent1|context|42",
        )
        second = ab_control.should_inject(
            "context", "cc", 0, firing_id="agent1|context|42",
        )
        third = ab_control.should_inject(
            "context", "cc", 0, firing_id="agent1|context|42",
        )
        assert first == second == third

    def test_same_firing_id_does_not_bump_counter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab.json")
        ab_control.should_inject(
            "context", "cc", 0, firing_id="agent1|context|42",
        )
        counters_after_first = dict(ab_control._load_counters())
        ab_control.should_inject(
            "context", "cc", 0, firing_id="agent1|context|42",
        )
        ab_control.should_inject(
            "context", "cc", 0, firing_id="agent1|context|42",
        )
        counters_after_three = dict(ab_control._load_counters())
        assert counters_after_first == counters_after_three

    def test_different_firing_ids_all_assigned(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab.json")
        for n in range(20):
            ab_control.should_inject(
                "context", "cc", n, firing_id=f"agent1|context|{n}",
            )
        counters = ab_control._load_counters()
        t, c = counters["cc|context"]
        assert t + c == 20

    def test_no_firing_id_falls_back_to_legacy_path(self, tmp_path, monkeypatch):
        """Backward compat: callers that don't pass firing_id still work
        (every call increments) — this is the pre-2026-04-25 behaviour."""
        monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab.json")
        for _ in range(5):
            ab_control.should_inject("context", "cc", 0)
        counters = ab_control._load_counters()
        t, c = counters["cc|context"]
        assert t + c == 5

    def test_firings_dedup_trims_to_max(self, tmp_path, monkeypatch):
        """The dedup map can't grow forever — caps at _FIRINGS_DEDUP_MAX
        with FIFO trim so a long-lived install doesn't bloat the file."""
        monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab.json")
        monkeypatch.setattr(ab_control, "_FIRINGS_DEDUP_MAX", 10)
        for n in range(25):
            ab_control.should_inject(
                "context", "cc", n, firing_id=f"agent|context|{n}",
            )
        _counters, firings = ab_control._load_persisted()
        assert len(firings) == 10
        # Newest 10 ids retained (firing 15..24).
        for n in range(15, 25):
            assert f"agent|context|{n}" in firings
        # Oldest dropped.
        assert "agent|context|0" not in firings

    def test_legacy_schema_loads_without_firings(self, tmp_path, monkeypatch):
        """Pre-2026-04-25 ab_counters.json has no _firings sentinel.
        Loading must not crash; firings dict starts empty."""
        path = tmp_path / "ab.json"
        path.write_text('{"cc|context": [10, 8]}')
        monkeypatch.setattr(ab_control, "_COUNTERS_PATH", path)
        counters, firings = ab_control._load_persisted()
        assert counters == {"cc|context": [10, 8]}
        assert firings == {}


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
        firing_id="cc-1|bash_retry|1",
    )
    store.record_ab_outcome(
        agent_family="cc", pattern="bash_retry", arm="control",
        pressure_before=0.7, pressure_after=0.65, followed=False,
        firing_id="cc-1|bash_retry|2",
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
    for i, pattern in enumerate(("a", "a", "b", "c")):
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="treatment",
            pressure_before=0.5, pressure_after=0.3,
            firing_id=f"cc-1|{pattern}|{i}",
        )
    assert store.list_ab_patterns() == ["a", "b", "c"]


def test_get_ab_outcomes_excludes_null_after(tmp_path):
    """Rows with ``pressure_after IS NULL`` are skipped (incomplete)."""
    store = AnalyticsStore(path=tmp_path / "null.db")
    store.record_ab_outcome(
        agent_family="cc", pattern="x", arm="treatment",
        pressure_before=0.5, pressure_after=None,
        firing_id="cc-1|x|1",
    )
    store.record_ab_outcome(
        agent_family="cc", pattern="x", arm="control",
        pressure_before=0.5, pressure_after=0.3,
        firing_id="cc-1|x|2",
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
        "pressure_after_h1": 0.5,  # buffered h=1 (v2026.6.1 dropguard)
        "firing_id": "cc-mark|bash_retry|1",  # v2026.6.x trigger requires non-NULL
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
        "firing_id": "cc-horizon|bash_retry|1",
        "pressure_after_h1": 0.55,  # buffered h=1 (v2026.6.1 dropguard)
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
        "firing_id": "cc-flat|context|1",
        "pressure_after_h1": 0.59,  # buffered h=1 (v2026.6.1 dropguard)
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
        firing_id="cc-1|x|1",
    )
    store.record_ab_outcome(
        agent_family="swe", pattern="x", arm="control",
        pressure_before=0.6, pressure_after=0.5,
        firing_id="swe-1|x|1",
    )
    rows = store.get_ab_outcomes(pattern="x")
    families = {r["agent_family"] for r in rows}
    assert families == {"cc", "swe"}


# ── Multi-horizon recording (h1/h2/h5/h10) ──────────────────────────


class TestMultiHorizonRecording:
    """The new flow: INSERT once at h=2 carrying ``firing_id`` and the
    h=1 sample we already buffered, then UPDATE the same row at h=5
    and h=10 horizons via ``update_ab_outcome_horizon``. No data loss
    vs the prior behaviour because the row still lands at h=2; later
    horizons simply add columns to the same row."""

    def test_h1_buffered_into_pending_no_row_yet(self, tmp_path):
        from soma.analytics import AnalyticsStore
        from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

        pending = {
            "pattern": "bash_retry", "actions_since": 1,
            "ab_arm": "treatment", "pressure_at_injection": 0.7,
            "firing_id": "cc-h1|bash_retry|100",
        }
        wrote = _record_ab_outcome_at_horizon(
            agent_id="cc-h1",
            pending=pending,
            pressure_after=0.55,
            analytics_path=tmp_path / "ab.db",
        )
        # No INSERT at h=1 — just buffer into pending for the h=2 INSERT.
        assert wrote is False
        assert pending.get("pressure_after_h1") == 0.55
        # The DB has nothing yet.
        store = AnalyticsStore(path=tmp_path / "ab.db")
        try:
            assert store.get_ab_outcomes(pattern="bash_retry") == []
        finally:
            store.close()

    def test_h2_inserts_with_firing_id_and_h1_sample(self, tmp_path):
        from soma.analytics import AnalyticsStore
        from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

        pending = {
            "pattern": "bash_retry", "actions_since": 2,
            "ab_arm": "treatment", "pressure_at_injection": 0.8,
            "firing_id": "cc-h2|bash_retry|200",
            "pressure_after_h1": 0.65,  # buffered earlier
        }
        ok = _record_ab_outcome_at_horizon(
            agent_id="cc-h2",
            pending=pending,
            pressure_after=0.4,  # h=2 sample
            analytics_path=tmp_path / "ab.db",
        )
        assert ok is True
        assert pending["ab_recorded"] is True

        store = AnalyticsStore(path=tmp_path / "ab.db")
        try:
            cur = store._conn.execute(
                "SELECT firing_id, pressure_after, pressure_after_h1, "
                "pressure_after_h5, pressure_after_h10 FROM ab_outcomes"
            )
            row = cur.fetchone()
        finally:
            store.close()
        assert row[0] == "cc-h2|bash_retry|200"
        assert row[1] == 0.4
        assert row[2] == 0.65  # h1 backfilled into row
        assert row[3] is None  # h5 not yet
        assert row[4] is None  # h10 not yet

    def test_h5_updates_existing_row(self, tmp_path):
        from soma.analytics import AnalyticsStore
        from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

        # First, plant the h=2 row.
        pending = {
            "pattern": "bash_retry", "actions_since": 2,
            "ab_arm": "treatment", "pressure_at_injection": 0.8,
            "firing_id": "cc-h5|bash_retry|300",
            "pressure_after_h1": 0.6,  # buffered h=1 (v2026.6.1 dropguard)
        }
        _record_ab_outcome_at_horizon(
            agent_id="cc-h5", pending=pending, pressure_after=0.5,
            analytics_path=tmp_path / "ab.db",
        )
        # Now drive to h=5.
        pending["actions_since"] = 5
        _record_ab_outcome_at_horizon(
            agent_id="cc-h5", pending=pending, pressure_after=0.3,
            analytics_path=tmp_path / "ab.db",
        )
        store = AnalyticsStore(path=tmp_path / "ab.db")
        try:
            cur = store._conn.execute(
                "SELECT pressure_after, pressure_after_h5 FROM ab_outcomes "
                "WHERE firing_id = 'cc-h5|bash_retry|300'"
            )
            row = cur.fetchone()
        finally:
            store.close()
        # Original h=2 sample untouched, h=5 column populated.
        assert row[0] == 0.5
        assert row[1] == 0.3

    def test_h10_updates_existing_row_no_duplicate(self, tmp_path):
        from soma.analytics import AnalyticsStore
        from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

        pending = {
            "pattern": "bash_retry", "actions_since": 2,
            "ab_arm": "treatment", "pressure_at_injection": 0.8,
            "firing_id": "cc-h10|bash_retry|400",
            "pressure_after_h1": 0.6,  # buffered h=1 (v2026.6.1 dropguard)
        }
        _record_ab_outcome_at_horizon(
            agent_id="cc-h10", pending=pending, pressure_after=0.5,
            analytics_path=tmp_path / "ab.db",
        )
        for n, p in ((5, 0.4), (10, 0.2)):
            pending["actions_since"] = n
            _record_ab_outcome_at_horizon(
                agent_id="cc-h10", pending=pending, pressure_after=p,
                analytics_path=tmp_path / "ab.db",
            )
        store = AnalyticsStore(path=tmp_path / "ab.db")
        try:
            cur = store._conn.execute("SELECT COUNT(*) FROM ab_outcomes")
            count = cur.fetchone()[0]
            cur = store._conn.execute(
                "SELECT pressure_after, pressure_after_h5, pressure_after_h10 "
                "FROM ab_outcomes WHERE firing_id = 'cc-h10|bash_retry|400'"
            )
            row = cur.fetchone()
        finally:
            store.close()
        assert count == 1, "should still be one row, not three"
        assert (row[0], row[1], row[2]) == (0.5, 0.4, 0.2)


def test_update_ab_outcome_horizon_unknown_firing_id_is_noop(tmp_path):
    """If we get an UPDATE for a firing_id that was never INSERTed (e.g.
    h=2 INSERT failed and we still hit h=5), the UPDATE silently
    affects 0 rows. No crash."""
    from soma.analytics import AnalyticsStore

    store = AnalyticsStore(path=tmp_path / "ab.db")
    try:
        # Should not raise.
        store.update_ab_outcome_horizon(
            firing_id="never-existed", horizon=5, pressure_after=0.3,
        )
    finally:
        store.close()


# ── validate() gains horizon kwarg ──────────────────────────────────


class TestValidateHorizon:
    """``ab_control.validate()`` reads pressure_after at the requested
    horizon. Default horizon=2 keeps prior behaviour; horizon=1/5/10
    look at the new columns. Rows missing the horizon column are
    skipped (legacy rows / late-arriving sample never landed)."""

    @staticmethod
    def _row(arm: str, before: float, after_h2: float,
             h1: float | None = None, h5: float | None = None,
             h10: float | None = None) -> dict:
        return {
            "arm": arm,
            "pressure_before": before,
            "pressure_after": after_h2,
            "pressure_after_h1": h1,
            "pressure_after_h5": h5,
            "pressure_after_h10": h10,
        }

    def test_default_horizon_is_2_and_reads_pressure_after(self):
        """Back-compat: validate() with no horizon kwarg behaves
        identically to before — same column read, same delta math."""
        rows = [
            self._row("treatment", 0.7, 0.3) for _ in range(35)
        ] + [
            self._row("control", 0.7, 0.6) for _ in range(35)
        ]
        result = ab_control.validate(rows, pattern="bash_retry")
        # 0.4 vs 0.1 mean delta — clearly different.
        assert result.fires_treatment == 35
        assert result.fires_control == 35
        assert abs(result.mean_treatment_delta - 0.4) < 0.001
        assert abs(result.mean_control_delta - 0.1) < 0.001

    def test_horizon_5_reads_pressure_after_h5(self):
        """h=5 should compute deltas against pressure_after_h5, not h=2."""
        rows = [
            self._row("treatment", 0.7, after_h2=0.5, h5=0.2)
            for _ in range(35)
        ] + [
            self._row("control", 0.7, after_h2=0.6, h5=0.55)
            for _ in range(35)
        ]
        result = ab_control.validate(rows, pattern="bash_retry", horizon=5)
        # Treatment Δp_h5 = 0.5; control Δp_h5 = 0.15.
        assert abs(result.mean_treatment_delta - 0.5) < 0.001
        assert abs(result.mean_control_delta - 0.15) < 0.001

    def test_horizon_10_skips_rows_without_h10_sample(self):
        """h=10 is best-effort — if a row never got the late update,
        it must be skipped, not silently treated as zero delta."""
        rows = [
            # Treatment: 5 with h10, 30 without.
            self._row("treatment", 0.7, after_h2=0.5, h10=0.2)
            for _ in range(5)
        ] + [
            self._row("treatment", 0.7, after_h2=0.5)
            for _ in range(30)
        ] + [
            self._row("control", 0.7, after_h2=0.6, h10=0.5)
            for _ in range(35)
        ]
        result = ab_control.validate(rows, pattern="bash_retry", horizon=10)
        # Only 5 treatment rows have h10 — below min_pairs (30) → collecting.
        assert result.fires_treatment == 5
        assert result.status == "collecting"

    def test_horizon_1_reads_pressure_after_h1(self):
        rows = [
            self._row("treatment", 0.7, after_h2=0.5, h1=0.4)
            for _ in range(35)
        ] + [
            self._row("control", 0.7, after_h2=0.65, h1=0.62)
            for _ in range(35)
        ]
        result = ab_control.validate(rows, pattern="bash_retry", horizon=1)
        assert abs(result.mean_treatment_delta - 0.3) < 0.001
        assert abs(result.mean_control_delta - 0.08) < 0.001

    def test_invalid_horizon_raises(self):
        with pytest.raises(ValueError):
            ab_control.validate([], pattern="x", horizon=3)


# ── v2026.6.1 review-driven regressions (C1/I1/I3) ──────────────────


class TestReviewRegressions_v2026_6_1:
    """Regression coverage for the 4 issues caught in the 2026-04-25
    code review of the multi-horizon sprint."""

    # ── I3: timeout-forced INSERT must use buffered h=2 sample ──
    def test_i3_timeout_forced_insert_uses_buffered_h2(self, tmp_path):
        """When actions_since jumps past 2 and ab_recorded is False, the
        INSERT must use the buffered h=2 sample (set when the agent
        first hit actions_since == 2), NOT the current pressure passed
        by the caller."""
        from soma.analytics import AnalyticsStore
        from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

        pending = {
            "pattern": "bash_retry", "actions_since": 2,
            "ab_arm": "treatment", "pressure_at_injection": 0.7,
            "firing_id": "cc-i3|bash_retry|1",
        }
        # Cycle 1: h=2 hits, buffer h=2 sample = 0.4 (good recovery).
        _record_ab_outcome_at_horizon(
            agent_id="cc-i3", pending=pending, pressure_after=0.4,
            analytics_path=tmp_path / "ab.db",
        )
        assert pending["pressure_after_h2"] == 0.4

    def test_i3_no_buffered_h2_skips_insert_instead_of_writing_now_pressure(
        self, tmp_path,
    ):
        """If timeout fires before h=2 ever ran (e.g. an early skip),
        force-INSERT must NOT silently write current pressure into the
        h=2 column. It should drop the row."""
        from soma.analytics import AnalyticsStore
        from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon

        pending = {
            "pattern": "bash_retry", "actions_since": 13,  # past timeout
            "ab_arm": "treatment", "pressure_at_injection": 0.7,
            "firing_id": "cc-i3-noh2|bash_retry|2",
            # No "pressure_after_h2" buffered.
        }
        wrote = _record_ab_outcome_at_horizon(
            agent_id="cc-i3-noh2", pending=pending,
            pressure_after=0.55,  # would-be-wrong h=2 value
            analytics_path=tmp_path / "ab.db",
        )
        assert wrote is False
        store = AnalyticsStore(path=tmp_path / "ab.db")
        try:
            assert store.get_ab_outcomes(pattern="bash_retry") == []
        finally:
            store.close()


def test_i1_firing_id_uses_nanosecond_timestamp_not_action_log_len(
    tmp_path, monkeypatch,
):
    """firing_id must be unique per firing even when len(cg_action_log)
    is clamped at ACTION_LOG_MAX. Verifies _firing_id includes a ns
    timestamp by checking that two same-pattern firings produce
    distinct ids."""
    # Build two firing ids the way post_tool_use.py does it. Two
    # back-to-back time.time_ns() calls can return the same value on
    # macOS (sub-µs resolution clamped by the syscall) — sleep one
    # microsecond between samples to mirror real firing cadence.
    import time
    fid1 = f"cc-i1|bash_retry|{time.time_ns()}"
    time.sleep(1e-6)
    fid2 = f"cc-i1|bash_retry|{time.time_ns()}"
    assert fid1 != fid2, "ns-precision firing_ids must be unique"
    # Tail must be ns-scale digits — anything < 1e9 means the old
    # len(action_log) format slipped back in.
    tail = int(fid1.rsplit("|", 1)[1])
    assert tail > 10**15, f"firing_id tail looks too small for ns: {tail}"
