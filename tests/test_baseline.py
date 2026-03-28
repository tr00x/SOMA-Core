"""Tests for soma.baseline — EMA baseline with cold-start blending."""

from __future__ import annotations

import math

import pytest

from soma.baseline import DEFAULTS, Baseline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_baseline(**kwargs) -> Baseline:
    return Baseline(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cold_start_uses_defaults():
    """Before any observations the baseline returns the signal default."""
    b = make_baseline()
    for signal, default in DEFAULTS.items():
        assert b.get(signal) == pytest.approx(default), (
            f"Expected default {default!r} for {signal!r}"
        )


def test_update_moves_toward_observation():
    """After 20 updates of 0.5 the baseline should exceed 0.30."""
    b = make_baseline(alpha=0.15, min_samples=10)
    # Default for 'uncertainty' is 0.15; we push toward 0.5
    for _ in range(20):
        b.update("uncertainty", 0.5)
    assert b.get("uncertainty") > 0.30


def test_variance_tracks_spread():
    """Alternating values should produce non-trivial variance."""
    b = make_baseline()
    for i in range(20):
        b.update("drift", 0.0 if i % 2 == 0 else 1.0)
    assert b.get_std("drift") > 0.0


def test_cold_start_blending():
    """With only 5 samples of 0.8 the result should be between the default and 0.8."""
    b = make_baseline(alpha=0.15, min_samples=10)
    signal = "uncertainty"
    default = DEFAULTS[signal]  # 0.15
    for _ in range(5):
        b.update(signal, 0.8)
    result = b.get(signal)
    assert default < result < 0.8, (
        f"Expected blended result between {default} and 0.8, got {result}"
    )


def test_full_convergence():
    """After 20 samples of 0.8 the baseline should exceed 0.65."""
    b = make_baseline(alpha=0.15, min_samples=10)
    for _ in range(20):
        b.update("uncertainty", 0.8)
    assert b.get("uncertainty") > 0.65


def test_unknown_signal_returns_zero():
    """A signal with no default and no observations should return 0."""
    b = make_baseline()
    assert b.get("nonexistent_signal") == 0.0


def test_serialization_roundtrip():
    """to_dict / from_dict should preserve all state exactly."""
    b = make_baseline(alpha=0.20, min_samples=5)
    for v in [0.1, 0.5, 0.9, 0.3, 0.7]:
        b.update("cost", v)
    b.update("error_rate", 0.05)

    data = b.to_dict()
    b2 = Baseline.from_dict(data)

    assert b2.alpha == b.alpha
    assert b2.min_samples == b.min_samples
    assert b2.get("cost") == pytest.approx(b.get("cost"))
    assert b2.get("error_rate") == pytest.approx(b.get("error_rate"))
    assert b2.get_std("cost") == pytest.approx(b.get_std("cost"))
    assert b2.get_count("cost") == b.get_count("cost")
    assert b2.get_count("error_rate") == b.get_count("error_rate")
