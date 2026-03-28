"""MultiBudget — tracks spend across multiple named dimensions."""

from __future__ import annotations

import time
from typing import Any


class MultiBudget:
    """Tracks spending across multiple named resource dimensions."""

    def __init__(self, limits: dict[str, float]) -> None:
        self._limits: dict[str, float] = dict(limits)
        self._spent: dict[str, float] = {k: 0.0 for k in limits}
        self._start_time: float = time.monotonic()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def limits(self) -> dict[str, float]:
        return dict(self._limits)

    @property
    def spent(self) -> dict[str, float]:
        return dict(self._spent)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def spend(self, **kwargs: float) -> None:
        """Add to spent amounts, clamping each dimension at its limit."""
        for dim, amount in kwargs.items():
            if dim not in self._limits:
                raise KeyError(f"Unknown dimension: {dim!r}")
            self._spent[dim] = min(self._spent[dim] + amount, self._limits[dim])

    def replenish(self, dimension: str, amount: float) -> None:
        """Reduce spent for a dimension (floor at 0)."""
        if dimension not in self._limits:
            raise KeyError(f"Unknown dimension: {dimension!r}")
        self._spent[dimension] = max(0.0, self._spent[dimension] - amount)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def remaining(self, dimension: str) -> float:
        """Remaining budget for *dimension*."""
        return self._limits[dimension] - self._spent[dimension]

    def utilization(self, dimension: str) -> float:
        """Fraction spent for *dimension* (spent / limit)."""
        limit = self._limits[dimension]
        if limit == 0.0:
            return 1.0
        return self._spent[dimension] / limit

    def health(self) -> float:
        """Minimum (remaining / limit) across all dimensions. Empty budget = 1.0."""
        if not self._limits:
            return 1.0
        healths = []
        for dim, limit in self._limits.items():
            if limit == 0.0:
                healths.append(0.0)
            else:
                healths.append(self.remaining(dim) / limit)
        return min(healths)

    def burn_rate(self, dimension: str) -> float:
        """Average spend per second since creation."""
        elapsed = time.monotonic() - self._start_time
        if elapsed <= 0.0:
            return 0.0
        return self._spent[dimension] / elapsed

    def projected_overshoot(
        self,
        dimension: str,
        estimated_total_steps: int,
        current_step: int,
    ) -> float:
        """Estimate overshoot (negative = headroom) at *estimated_total_steps*.

        Returns projected_total_spend - limit.
        """
        if current_step <= 0:
            return 0.0
        spend_per_step = self._spent[dimension] / current_step
        projected_total = spend_per_step * estimated_total_steps
        return projected_total - self._limits[dimension]

    def is_exhausted(self) -> bool:
        """True when health == 0 (at least one dimension fully spent)."""
        return self.health() <= 0.0

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "limits": dict(self._limits),
            "spent": dict(self._spent),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultiBudget":
        obj = cls(data["limits"])
        for dim, value in data["spent"].items():
            obj._spent[dim] = value
        return obj
