"""Tests for soma.pressure — signal and aggregate pressure computation."""

from __future__ import annotations

import math

import pytest

from soma.pressure import DEFAULT_WEIGHTS, compute_aggregate_pressure, compute_signal_pressure
from soma.types import DriftMode


# ---------------------------------------------------------------------------
# compute_signal_pressure
# ---------------------------------------------------------------------------

class TestComputeSignalPressure:
    def test_at_baseline_returns_near_zero(self):
        """current == baseline → z=0 → sigmoid_clamp clamps to 0.0."""
        result = compute_signal_pressure(current=0.5, baseline=0.5, std=0.1)
        assert result == pytest.approx(0.0)

    def test_one_std_above_baseline(self):
        """current = baseline + 1*std → z=1 → sigmoid_clamp(1) ≈ 0.119."""
        result = compute_signal_pressure(current=0.6, baseline=0.5, std=0.1)
        # sigmoid_clamp(1) = 1/(1+exp(2)) ≈ 0.11920292
        assert result == pytest.approx(1.0 / (1.0 + math.exp(2.0)), abs=1e-6)
        assert result == pytest.approx(0.119, abs=0.001)

    def test_three_std_above_baseline(self):
        """current = baseline + 3*std → z=3 → sigmoid_clamp(3) = 0.5."""
        result = compute_signal_pressure(current=0.8, baseline=0.5, std=0.1)
        # sigmoid_clamp(3) = 1/(1+exp(0)) = 0.5
        assert result == pytest.approx(0.5, abs=1e-6)

    def test_below_baseline_returns_zero(self):
        """current < baseline → negative z → sigmoid_clamp clamps to 0.0."""
        result = compute_signal_pressure(current=0.3, baseline=0.5, std=0.1)
        assert result == pytest.approx(0.0)

    def test_std_zero_uses_min_std(self):
        """std=0 → min_std=0.05 prevents extreme z-scores."""
        result = compute_signal_pressure(current=0.2, baseline=0.05, std=0.0)
        # z = (0.2-0.05)/0.05 = 3.0, sigmoid_clamp(3) ≈ 0.5
        assert 0.3 < result < 0.8

    def test_well_above_baseline_saturates(self):
        """z > 6 → sigmoid_clamp returns 1.0."""
        result = compute_signal_pressure(current=7.0, baseline=0.0, std=1.0)
        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_aggregate_pressure
# ---------------------------------------------------------------------------

class TestComputeAggregatePressure:
    def test_all_zero_signals_returns_zero(self):
        """All pressures zero → aggregate is 0.0."""
        signals = {
            "uncertainty": 0.0,
            "drift": 0.0,
            "error_rate": 0.0,
            "cost": 0.0,
            "token_usage": 0.0,
        }
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        assert result == pytest.approx(0.0)

    def test_one_critical_uncertainty(self):
        """High uncertainty alone → aggregate between 0.2 and 0.6."""
        signals = {
            "uncertainty": 0.9,
            "drift": 0.0,
            "error_rate": 0.0,
            "cost": 0.0,
            "token_usage": 0.0,
        }
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        assert 0.2 < result < 0.6

    def test_drift_weight_zeroed_in_informational_mode(self):
        """In INFORMATIONAL mode, drift signal is excluded from aggregate."""
        signals = {
            "uncertainty": 0.5,
            "drift": 1.0,
            "error_rate": 0.0,
            "cost": 0.0,
            "token_usage": 0.0,
        }
        result_informational = compute_aggregate_pressure(signals, DriftMode.INFORMATIONAL)
        result_directive = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        # INFORMATIONAL should be lower than DIRECTIVE because drift is excluded
        assert result_informational < result_directive

    def test_all_max_signals_above_0_9(self):
        """All signals at 1.0 → aggregate should exceed 0.9."""
        signals = {k: 1.0 for k in DEFAULT_WEIGHTS}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        assert result > 0.9

    def test_custom_weights(self):
        """Custom weights are respected in weighted mean calculation."""
        signals = {"error_rate": 1.0, "cost": 0.0}
        # With equal weights, mean = 0.5, max = 1.0 → 0.7*0.5 + 0.3*1.0 = 0.65
        custom_weights = {"error_rate": 1.0, "cost": 1.0}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE, weights=custom_weights)
        assert result == pytest.approx(0.65, abs=1e-6)

    def test_empty_signals_returns_zero(self):
        """Empty signal dict → 0.0."""
        result = compute_aggregate_pressure({}, DriftMode.DIRECTIVE)
        assert result == pytest.approx(0.0)

    def test_unknown_signal_keys_ignored(self):
        """Signals not in weights dict are ignored (weight defaults to 0)."""
        signals = {"nonexistent_signal": 0.9}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        assert result == pytest.approx(0.0)

    def test_informational_drift_only_returns_zero(self):
        """In INFORMATIONAL mode with only drift signal → 0.0 (drift zeroed)."""
        signals = {"drift": 1.0}
        result = compute_aggregate_pressure(signals, DriftMode.INFORMATIONAL)
        assert result == pytest.approx(0.0)

    def test_directive_drift_only_returns_positive(self):
        """In DIRECTIVE mode with only drift signal → positive value."""
        signals = {"drift": 1.0}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        assert result > 0.0
