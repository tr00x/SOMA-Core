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

    Uses min_std=0.02 to allow sharper z-scores from real behavioral
    variation while preventing division by zero.
    """
    z = (current - baseline) / max(std, 0.02)
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

    # Continuous error-rate aggregate floor: ensures high error pressure
    # translates to proportional aggregate pressure even when other signals
    # are healthy. Uses smooth mapping starting at er_p=0.20 instead of
    # step function at 0.50 (which caused bimodal 0/0.80 pressure distribution).
    #
    # Smooth mapping:
    #   er_p = 0.20  →  floor = 0.10  (early OBSERVE)
    #   er_p = 0.40  →  floor = 0.25  (late OBSERVE)
    #   er_p = 0.60  →  floor = 0.40  (GUIDE entry)
    #   er_p = 0.80  →  floor = 0.55  (mid WARN)
    #   er_p = 1.00  →  floor = 0.70  (high WARN, not instant BLOCK)
    er_p = signal_pressures.get("error_rate", 0.0)
    if er_p >= 0.20 and effective_weights.get("error_rate", 0.0) > 0:
        er_floor = 0.10 + 0.60 * (er_p - 0.20) / 0.80  # linear 0.10→0.70
        result = max(result, er_floor)

    return min(1.0, result)
