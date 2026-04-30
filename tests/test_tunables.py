"""
Regression for v2026.6.x fix #21 — soma.tunables is the single
source of truth for behavioral thresholds. Re-exporting modules
must hold the same value as the canonical location, so a
maintainer changing tunables sees the change everywhere.
"""
from __future__ import annotations

from soma import tunables


def test_ab_control_reexports_match_tunables() -> None:
    from soma import ab_control
    assert ab_control.DEFAULT_MIN_PAIRS == tunables.DEFAULT_MIN_PAIRS
    assert ab_control.INCONCLUSIVE_AT == tunables.INCONCLUSIVE_AT
    assert ab_control.ALPHA == tunables.ALPHA
    assert ab_control.EFFECT_SIZE_THRESHOLD == tunables.EFFECT_SIZE_THRESHOLD
    assert ab_control.DELTA_DIFFERENCE_THRESHOLD == tunables.DELTA_DIFFERENCE_THRESHOLD


def test_calibration_reexports_match_tunables() -> None:
    from soma import calibration
    assert calibration.WARMUP_EXIT_ACTIONS == tunables.WARMUP_EXIT_ACTIONS
    assert calibration.SILENCE_MIN_FIRES == tunables.SILENCE_MIN_FIRES
    assert calibration.REFUTED_REFRESH_INTERVAL == tunables.REFUTED_REFRESH_INTERVAL


def test_post_tool_use_aliases_match_tunables() -> None:
    from soma.hooks import post_tool_use as ptu
    assert ptu._AB_MEASUREMENT_HORIZON == tunables.AB_MEASUREMENT_HORIZON
    assert ptu._AB_RECOVERED_DELTA == tunables.AB_RECOVERED_DELTA


def test_tunable_values_documented() -> None:
    """Every tunable has a sane positive value — pinned so a future
    edit accidentally setting a constant to 0 or negative blows up here
    instead of silently producing a degenerate verdict pipeline."""
    assert tunables.DEFAULT_MIN_PAIRS > 0
    assert tunables.INCONCLUSIVE_AT >= tunables.DEFAULT_MIN_PAIRS, (
        "INCONCLUSIVE_AT must be ≥ DEFAULT_MIN_PAIRS or we'd give up "
        "before reaching the min-pairs gate"
    )
    assert 0 < tunables.ALPHA < 1
    assert tunables.EFFECT_SIZE_THRESHOLD > 0
    assert tunables.DELTA_DIFFERENCE_THRESHOLD > 0
    assert tunables.AB_MEASUREMENT_HORIZON >= 1
    assert 0 < tunables.AB_RECOVERED_DELTA < 1
    assert tunables.WARMUP_EXIT_ACTIONS > 0
    assert tunables.SILENCE_MIN_FIRES > 0
    assert tunables.REFUTED_REFRESH_INTERVAL > 0
