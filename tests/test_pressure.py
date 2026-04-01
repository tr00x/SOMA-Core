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
        """Custom weights are respected; error_rate=1.0 lifts aggregate via floor."""
        signals = {"error_rate": 1.0, "cost": 0.0}
        custom_weights = {"error_rate": 1.0, "cost": 1.0}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE, weights=custom_weights)
        # Smooth floor: er_p=1.0 → 0.10 + 0.60 = 0.70
        assert result >= 0.65, f"Expected ≥ 0.65, got {result:.3f}"

    def test_error_rate_floor_at_50_pct(self):
        """error_rate signal ≥ 0.50 lifts aggregate smoothly."""
        signals = {"error_rate": 0.50, "uncertainty": 0.01, "drift": 0.01,
                   "cost": 0.01, "token_usage": 0.01}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        # Smooth floor: er_p=0.50 → 0.10 + 0.60*(0.30/0.80) ≈ 0.325
        assert result >= 0.30, f"Expected ≥ 0.30, got {result:.3f}"

    def test_error_rate_floor_at_75_pct(self):
        """error_rate signal ≥ 0.75 lifts aggregate to GUIDE+."""
        signals = {"error_rate": 0.75, "uncertainty": 0.01, "drift": 0.01,
                   "cost": 0.01, "token_usage": 0.01}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        # Smooth floor: er_p=0.75 → 0.10 + 0.60*(0.55/0.80) ≈ 0.51
        assert result >= 0.45, f"Expected ≥ 0.45 (GUIDE+), got {result:.3f}"

    def test_error_rate_floor_at_100_pct(self):
        """error_rate signal = 1.0 lifts aggregate to high WARN."""
        signals = {"error_rate": 1.0, "uncertainty": 0.01, "drift": 0.01,
                   "cost": 0.01, "token_usage": 0.01}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        # Smooth floor: er_p=1.0 → 0.10 + 0.60 = 0.70
        assert result >= 0.65, f"Expected ≥ 0.65 (high WARN), got {result:.3f}"

    def test_error_rate_floor_inactive_below_20_pct(self):
        """error_rate < 0.20 — smooth floor does not activate."""
        signals = {"error_rate": 0.15, "uncertainty": 0.01, "drift": 0.01,
                   "cost": 0.01, "token_usage": 0.01}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE)
        assert result < 0.30, f"Expected < 0.30, got {result:.3f}"

    def test_error_rate_floor_skipped_when_weight_is_zero(self):
        """Floor must not fire if error_rate weight is explicitly 0."""
        signals = {"error_rate": 1.0, "uncertainty": 0.5}
        weights_no_error = {"error_rate": 0.0, "uncertainty": 1.0}
        result = compute_aggregate_pressure(signals, DriftMode.DIRECTIVE, weights=weights_no_error)
        # error_rate excluded → aggregate based on uncertainty only, < 0.80
        assert result < 0.80, f"Expected < 0.80 (floor skipped), got {result:.3f}"

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
