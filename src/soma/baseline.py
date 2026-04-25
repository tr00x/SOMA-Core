"""EMA baseline with cold-start blending for SOMA Core."""

from __future__ import annotations

import math
from typing import Any

DEFAULTS: dict[str, float] = {
    "uncertainty": 0.05,
    "drift": 0.05,
    "token_usage": 0.01,
    "cost": 0.01,
    "error_rate": 0.01,
}


class Baseline:
    """Exponential moving average baseline with cold-start blending.

    During cold start (fewer than ``min_samples`` observations), the computed
    EMA is blended toward the signal's default value so that early readings
    don't over-react to a handful of observations.
    """

    def __init__(self, alpha: float = 0.08, min_samples: int = 5) -> None:
        self.alpha = alpha
        self.min_samples = min_samples

        # Per-signal state
        self._value: dict[str, float] = {}
        self._variance: dict[str, float] = {}
        self._count: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def update(self, signal: str, value: float) -> None:
        """Apply one EMA step for *signal*."""
        if signal not in self._value:
            # First observation: initialise directly from the value.
            self._value[signal] = value
            self._variance[signal] = 0.0
            self._count[signal] = 1
            return

        old = self._value[signal]
        old_var = self._variance[signal]

        new_value = self.alpha * value + (1.0 - self.alpha) * old
        new_variance = self.alpha * (value - old) ** 2 + (1.0 - self.alpha) * old_var

        self._value[signal] = new_value
        self._variance[signal] = new_variance
        self._count[signal] = self._count[signal] + 1

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, signal: str) -> float:
        """Return the blended baseline for *signal*.

        During cold start the computed EMA is blended toward the default.
        Once ``min_samples`` observations have been collected the EMA value
        is returned as-is.
        """
        if signal not in self._value:
            return DEFAULTS.get(signal, 0.0)

        n = self._count[signal]
        blend = min(n / self.min_samples, 1.0)
        default = DEFAULTS.get(signal, 0.0)
        computed = self._value[signal]
        return blend * computed + (1.0 - blend) * default

    def get_std(self, signal: str) -> float:
        """Return the standard deviation of the EMA variance estimate."""
        if signal not in self._variance:
            return 0.1
        return max(math.sqrt(self._variance[signal]), 1e-9)

    def get_count(self, signal: str) -> int:
        """Return the number of observations recorded for *signal*."""
        return self._count.get(signal, 0)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "min_samples": self.min_samples,
            "value": dict(self._value),
            "variance": dict(self._variance),
            "count": dict(self._count),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Baseline":
        # Defaults must mirror __init__ (alpha=0.08, min_samples=5).
        # Older from_dict had alpha=0.15 / min_samples=10 — a partial /
        # legacy state file rehydrated with different EMA dynamics than
        # the running engine, producing a silent behavioural shift on
        # restart. Caught by ultra-review code audit 2026-04-25.
        obj = cls(
            alpha=data.get("alpha", 0.08),
            min_samples=data.get("min_samples", 5),
        )
        obj._value = dict(data.get("value", {}))
        obj._variance = dict(data.get("variance", {}))
        obj._count = dict(data.get("count", {}))
        return obj
