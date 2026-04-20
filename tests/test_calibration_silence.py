"""Day 4: analytics-driven auto-silence loop for the adaptive phase."""

from __future__ import annotations

from soma.analytics import AnalyticsStore
from soma.calibration import (
    CALIBRATED_EXIT_ACTIONS,
    WARMUP_EXIT_ACTIONS,
    CalibrationProfile,
    SILENCE_MIN_FIRES,
    SILENCE_REFRESH_INTERVAL,
    maybe_refresh_silence,
)


# ── get_pattern_stats on AnalyticsStore ──────────────────────────────

def _seed_outcomes(store: AnalyticsStore, pattern: str, helped_count: int, total: int):
    for i in range(total):
        store.record_guidance_outcome(
            agent_id=f"cc-{i}", session_id=f"cc-{i}",
            pattern_key=pattern,
            helped=i < helped_count,
            pressure_at_injection=0.5, pressure_after=0.5,
        )


def test_pattern_stats_counts_helped_vs_fired(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    _seed_outcomes(store, "blind_edit", helped_count=3, total=25)
    stats = store.get_pattern_stats("cc", "blind_edit")
    assert stats == {"fires": 25, "helped": 3}


def test_pattern_stats_family_prefix_and_exact_match(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    # Exact family-id record (no numeric tail).
    store.record_guidance_outcome(
        agent_id="cc", session_id="cc", pattern_key="blind_edit",
        helped=True, pressure_at_injection=0.4, pressure_after=0.2,
    )
    # Session-id variants.
    store.record_guidance_outcome(
        agent_id="cc-7", session_id="cc-7", pattern_key="blind_edit",
        helped=False, pressure_at_injection=0.4, pressure_after=0.4,
    )
    # Foreign family ignored.
    store.record_guidance_outcome(
        agent_id="swe-1", session_id="swe-1", pattern_key="blind_edit",
        helped=True, pressure_at_injection=0.4, pressure_after=0.1,
    )
    stats = store.get_pattern_stats("cc", "blind_edit")
    assert stats["fires"] == 2
    assert stats["helped"] == 1


def test_pattern_stats_respects_last_n(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    _seed_outcomes(store, "blind_edit", helped_count=0, total=60)
    stats = store.get_pattern_stats("cc", "blind_edit", last_n=10)
    assert stats["fires"] == 10


def test_pattern_stats_empty_for_unseen_pattern(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    _seed_outcomes(store, "blind_edit", helped_count=0, total=10)
    # Query a different pattern than what was seeded.
    stats = store.get_pattern_stats("cc", "entropy_drop")
    assert stats == {"fires": 0, "helped": 0}


# ── maybe_refresh_silence ───────────────────────────────────────────

def test_refresh_noop_outside_adaptive(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    _seed_outcomes(store, "blind_edit", helped_count=0, total=30)
    # Explicitly inside the calibrated band — one step above warmup, not adaptive.
    p = CalibrationProfile(family="cc", action_count=WARMUP_EXIT_ACTIONS + 1)
    assert p.is_calibrated()
    assert maybe_refresh_silence(p, analytics_store=store) is False
    assert p.silenced_patterns == []


def test_refresh_runs_when_interval_met(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    # 30 fires, 2 helped → ~7% → below the 20% silence gate.
    _seed_outcomes(store, "blind_edit", helped_count=2, total=30)
    p = CalibrationProfile(
        family="cc", action_count=CALIBRATED_EXIT_ACTIONS + SILENCE_REFRESH_INTERVAL,
        last_silence_check_action=CALIBRATED_EXIT_ACTIONS,
    )
    assert p.is_adaptive()
    assert maybe_refresh_silence(p, analytics_store=store) is True
    assert "blind_edit" in p.silenced_patterns
    assert p.last_silence_check_action == p.action_count


def test_refresh_skips_when_interval_not_elapsed(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    _seed_outcomes(store, "blind_edit", helped_count=0, total=30)
    p = CalibrationProfile(
        family="cc", action_count=CALIBRATED_EXIT_ACTIONS + 10,
        last_silence_check_action=CALIBRATED_EXIT_ACTIONS,
    )
    assert maybe_refresh_silence(p, analytics_store=store) is False
    assert p.silenced_patterns == []


def test_refresh_lifts_silence_when_precision_recovers(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    # 20 fires, 12 helped → 60% → above the 40% re-enable gate.
    _seed_outcomes(store, "blind_edit", helped_count=12, total=20)
    p = CalibrationProfile(
        family="cc",
        action_count=CALIBRATED_EXIT_ACTIONS + SILENCE_REFRESH_INTERVAL,
        last_silence_check_action=CALIBRATED_EXIT_ACTIONS,
        silenced_patterns=["blind_edit"],
    )
    assert maybe_refresh_silence(p, analytics_store=store) is True
    assert "blind_edit" not in p.silenced_patterns


def test_refresh_ignores_low_volume(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    _seed_outcomes(store, "blind_edit", helped_count=0, total=SILENCE_MIN_FIRES - 1)
    p = CalibrationProfile(
        family="cc",
        action_count=CALIBRATED_EXIT_ACTIONS + SILENCE_REFRESH_INTERVAL,
        last_silence_check_action=CALIBRATED_EXIT_ACTIONS,
    )
    assert maybe_refresh_silence(p, analytics_store=store) is True
    # Not enough fires yet → no silence decision.
    assert p.silenced_patterns == []
