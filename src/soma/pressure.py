"""Pressure computation for SOMA Core behavioral monitoring."""

from __future__ import annotations

from soma.types import DriftMode
from soma.vitals import sigmoid_clamp

DEFAULT_WEIGHTS: dict[str, float] = {
    "uncertainty": 2.0,
    "drift": 1.8,
    "error_rate": 1.5,
    "cost": 1.0,
    "token_usage": 0.8,
    "goal_coherence": 1.5,
    "context_exhaustion": 1.5,
}


def compute_signal_pressure(current: float, baseline: float, std: float) -> float:
    """Compute pressure for a single signal via sigmoid-clamped z-score.

    Uses min_std=0.05 to prevent huge z-scores when baseline has low variance
    (e.g. first few actions where std≈0) while still producing visible
    pressure from normal behavioral variation.
    """
    z = (current - baseline) / max(std, 0.05)
    return sigmoid_clamp(z)


def compute_aggregate_pressure(
    signal_pressures: dict[str, float],
    drift_mode: DriftMode,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute aggregate pressure from individual signal pressures.

    Uses a blend of weighted mean and weighted max:
        result = 0.7 * weighted_mean + 0.3 * max_pressure

    If drift_mode is INFORMATIONAL, the drift signal weight is set to 0.
    Signals with weight <= 0 are excluded from both mean and max calculations.
    Returns 0.0 if no signals have positive weight.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Copy and potentially zero out drift weight
    effective_weights: dict[str, float] = dict(weights)
    if drift_mode is DriftMode.INFORMATIONAL:
        if "drift" in effective_weights:
            effective_weights["drift"] = 0.0

    # Collect active signals (w > 0 and signal exists)
    active: list[tuple[float, float]] = []  # (weight, pressure)
    for signal, pressure in signal_pressures.items():
        w = effective_weights.get(signal, 0.0)
        if w > 0:
            active.append((w, pressure))

    if not active:
        return 0.0

    total_weight = sum(w for w, _ in active)
    weighted_mean = sum(w * p for w, p in active) / total_weight
    max_p = max(p for _, p in active)

    result = 0.7 * weighted_mean + 0.3 * max_p

    # Error-rate aggregate floor: sustained high error rates must escalate mode
    # regardless of other signals sitting at baseline.  Without this, the
    # mean-based formula dilutes a dominant error signal when all other signals
    # are healthy — keeping aggregate < GUIDE even at 80%+ error rates.
    #
    # Floor mapping (mirrors the threshold ladder):
    #   er_p = 0.50  →  floor = 0.40  (GUIDE entry)
    #   er_p = 0.75  →  floor = 0.60  (WARN entry)
    #   er_p = 1.00  →  floor = 0.80  (BLOCK entry)
    er_p = signal_pressures.get("error_rate", 0.0)
    if er_p >= 0.50 and effective_weights.get("error_rate", 0.0) > 0:
        er_floor = 0.40 + 0.40 * (er_p - 0.50) / 0.50
        result = max(result, er_floor)

    return min(1.0, result)
