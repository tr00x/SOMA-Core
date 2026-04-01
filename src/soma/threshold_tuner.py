"""SOMA Threshold Tuner — percentile-based threshold optimization.

Analyzes benchmark run results to find optimal guide/warn/block thresholds
that minimize false positives while maintaining detection capability.
Pure stdlib implementation — no sklearn, numpy, or external ML libraries.
"""

from __future__ import annotations

import statistics

from soma.types import ResponseMode

# Default thresholds (matching guidance.py)
DEFAULT_THRESHOLDS: dict[str, float] = {"guide": 0.25, "warn": 0.50, "block": 0.75}

# Modes that count as triggered guidance
_TRIGGERED_MODES = {"GUIDE", "WARN", "BLOCK"}


def compute_optimal_thresholds(
    run_results: list,
    target_false_positive_rate: float = 0.05,
) -> dict[str, float]:
    """Find guide/warn/block thresholds from benchmark data.

    Collects pressure at GUIDE+ events. Separates true positives
    (error in next 3 actions) from false positives. Sets guide threshold
    at percentile that achieves target FP rate.

    Returns DEFAULT_THRESHOLDS if insufficient data.

    Args:
        run_results: List of benchmark runs, each with a 'per_action' list
            of dicts containing 'pressure', 'mode', and 'error' keys.
        target_false_positive_rate: Target false positive rate (default 5%).

    Returns:
        Dict with 'guide', 'warn', 'block' threshold values.
    """
    if not run_results:
        return dict(DEFAULT_THRESHOLDS)

    true_positive_pressures: list[float] = []
    false_positive_pressures: list[float] = []

    for run in run_results:
        actions = run.get("per_action", [])
        for i, action in enumerate(actions):
            mode = action.get("mode", "OBSERVE")
            if mode not in _TRIGGERED_MODES:
                continue

            pressure = action.get("pressure", 0.0)

            # Check if any of the next 3 actions have error=True
            has_subsequent_error = False
            for j in range(i + 1, min(i + 4, len(actions))):
                if actions[j].get("error", False):
                    has_subsequent_error = True
                    break

            if has_subsequent_error:
                true_positive_pressures.append(pressure)
            else:
                false_positive_pressures.append(pressure)

    # Not enough data to tune
    if not false_positive_pressures:
        return dict(DEFAULT_THRESHOLDS)

    # Sort and find percentile threshold
    false_positive_pressures.sort()
    n = len(false_positive_pressures)

    # Index at (1 - target_FP_rate) percentile
    idx = int(n * (1.0 - target_false_positive_rate))
    idx = min(idx, n - 1)  # Clamp to valid range

    guide = false_positive_pressures[idx]

    # Safety bounds: clamp guide between 0.10 and 0.60
    guide = max(0.10, min(0.60, guide))

    warn = min(guide + 0.25, 0.90)
    block = min(guide + 0.50, 0.95)

    return {"guide": guide, "warn": warn, "block": block}
