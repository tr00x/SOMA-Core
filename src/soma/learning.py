"""Learning Engine — adjusts thresholds and signal weights based on intervention outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from soma.types import InterventionOutcome, ResponseMode


@dataclass
class _Record:
    """A single recorded intervention."""
    agent_id: str
    old_level: ResponseMode
    new_level: ResponseMode
    pressure: float
    trigger_signals: dict[str, float]
    actions_elapsed: int = 0


def _transition_key(old: ResponseMode, new: ResponseMode) -> tuple[ResponseMode, ResponseMode]:
    return (old, new)


def _record_to_dict(r: _Record) -> dict[str, Any]:
    return {
        "agent_id": r.agent_id,
        "old_level": r.old_level.name,
        "new_level": r.new_level.name,
        "pressure": r.pressure,
        "trigger_signals": dict(r.trigger_signals),
        "actions_elapsed": r.actions_elapsed,
    }


class LearningEngine:
    """Tracks interventions and adapts thresholds / signal weights over time.

    Parameters
    ----------
    evaluation_window:
        Minimum number of actions that must elapse before an intervention
        outcome can be evaluated.
    threshold_adj_step:
        How much to raise a threshold on each confirmed failure batch.
    weight_adj_step:
        How much to lower a signal weight on each confirmed failure batch.
    min_weight:
        Floor below which a signal weight will not be pushed.
    max_threshold_shift:
        Ceiling for the cumulative threshold adjustment for any transition key.
    min_interventions:
        Minimum number of same-type failures required before adjustments fire.
    """

    def __init__(
        self,
        evaluation_window: int = 5,
        threshold_adj_step: float = 0.02,
        weight_adj_step: float = 0.05,
        min_weight: float = 0.2,
        max_threshold_shift: float = 0.10,
        min_interventions: int = 3,
    ) -> None:
        self.evaluation_window = evaluation_window
        self.threshold_adj_step = threshold_adj_step
        self.weight_adj_step = weight_adj_step
        self.min_weight = min_weight
        self.max_threshold_shift = max_threshold_shift
        self.min_interventions = min_interventions

        # agent_id → list of pending _Records awaiting evaluation
        self._pending: dict[str, list[_Record]] = {}

        # agent_id → list of resolved _Records
        self._history: dict[str, list[_Record]] = {}

        # (old_level, new_level) → count of resolved failures for that transition
        self._failure_counts: dict[tuple[ResponseMode, ResponseMode], int] = {}

        # (old_level, new_level) → count of resolved successes for that transition
        self._success_counts: dict[tuple[ResponseMode, ResponseMode], int] = {}

        # (old_level, new_level) → cumulative threshold shift applied so far
        self._threshold_adjustments: dict[tuple[ResponseMode, ResponseMode], float] = {}

        # signal_name → cumulative weight adjustment applied so far (negative = lower)
        self._weight_adjustments: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_intervention(
        self,
        agent_id: str,
        old: ResponseMode,
        new: ResponseMode,
        pressure: float,
        signals: dict[str, float],
    ) -> None:
        """Record that an intervention occurred for *agent_id*."""
        record = _Record(
            agent_id=agent_id,
            old_level=old,
            new_level=new,
            pressure=pressure,
            trigger_signals=dict(signals),
        )
        self._pending.setdefault(agent_id, []).append(record)

    def pending(self, agent_id: str) -> list[_Record]:
        """Return a snapshot of pending (unresolved) records for *agent_id*."""
        return list(self._pending.get(agent_id, []))

    def evaluate(
        self,
        agent_id: str,
        current_pressure: float,
        actions_since: int,
    ) -> InterventionOutcome:
        """Evaluate the oldest pending intervention for *agent_id*.

        Returns
        -------
        InterventionOutcome.PENDING
            If there is no pending record, or the evaluation window has not
            been reached yet.
        InterventionOutcome.SUCCESS
            If pressure has dropped since the intervention.
        InterventionOutcome.FAILURE
            If pressure has not dropped; triggers :meth:`_on_failure`.
        """
        pending_list = self._pending.get(agent_id, [])
        if not pending_list:
            return InterventionOutcome.PENDING

        record = pending_list[0]
        record.actions_elapsed += actions_since

        if record.actions_elapsed < self.evaluation_window:
            return InterventionOutcome.PENDING

        # Window reached — resolve.
        delta = record.pressure - current_pressure
        key = _transition_key(record.old_level, record.new_level)
        if delta > 0:
            outcome = InterventionOutcome.SUCCESS
            self._success_counts[key] = self._success_counts.get(key, 0) + 1
            self._on_success(key, record.trigger_signals)
        else:
            outcome = InterventionOutcome.FAILURE
            # Increment failure count before calling _on_failure so it sees
            # the current failure included in the total.
            self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
            self._on_failure(key, record.trigger_signals)

        # Move to history.
        self._history.setdefault(agent_id, []).append(record)
        pending_list.pop(0)

        return outcome

    def get_threshold_adjustment(self, old: ResponseMode, new: ResponseMode) -> float:
        """Return the current cumulative threshold adjustment for this transition."""
        return self._threshold_adjustments.get(_transition_key(old, new), 0.0)

    def get_weight_adjustment(self, signal: str) -> float:
        """Return the current cumulative weight adjustment for *signal*."""
        return self._weight_adjustments.get(signal, 0.0)

    def reset(self) -> None:
        """Clear all state."""
        self._pending.clear()
        self._history.clear()
        self._failure_counts.clear()
        self._success_counts.clear()
        self._threshold_adjustments.clear()
        self._weight_adjustments.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialise engine state to a plain dictionary."""
        return {
            "evaluation_window": self.evaluation_window,
            "threshold_adj_step": self.threshold_adj_step,
            "weight_adj_step": self.weight_adj_step,
            "min_weight": self.min_weight,
            "max_threshold_shift": self.max_threshold_shift,
            "min_interventions": self.min_interventions,
            "threshold_adjustments": {
                f"{k[0].name}->{k[1].name}": v
                for k, v in self._threshold_adjustments.items()
            },
            "weight_adjustments": dict(self._weight_adjustments),
            "failure_counts": {
                f"{k[0].name}->{k[1].name}": v
                for k, v in self._failure_counts.items()
            },
            "success_counts": {
                f"{k[0].name}->{k[1].name}": v
                for k, v in self._success_counts.items()
            },
            "pending": {
                agent_id: [_record_to_dict(r) for r in records]
                for agent_id, records in self._pending.items()
            },
            "history": {
                agent_id: [_record_to_dict(r) for r in records]
                for agent_id, records in self._history.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningEngine":
        obj = cls(
            evaluation_window=data.get("evaluation_window", 5),
            threshold_adj_step=data.get("threshold_adj_step", 0.02),
            weight_adj_step=data.get("weight_adj_step", 0.05),
            min_weight=data.get("min_weight", 0.2),
            max_threshold_shift=data.get("max_threshold_shift", 0.10),
            min_interventions=data.get("min_interventions", 3),
        )
        for key_str, v in data.get("threshold_adjustments", {}).items():
            old_name, new_name = key_str.split("->")
            obj._threshold_adjustments[
                (ResponseMode[old_name], ResponseMode[new_name])
            ] = v
        obj._weight_adjustments = dict(data.get("weight_adjustments", {}))
        for key_str, v in data.get("failure_counts", {}).items():
            old_name, new_name = key_str.split("->")
            obj._failure_counts[
                (ResponseMode[old_name], ResponseMode[new_name])
            ] = v
        for key_str, v in data.get("success_counts", {}).items():
            old_name, new_name = key_str.split("->")
            obj._success_counts[
                (ResponseMode[old_name], ResponseMode[new_name])
            ] = v
        return obj

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _adaptive_step(self, key: tuple[ResponseMode, ResponseMode], is_failure: bool) -> float:
        """Compute adaptive step size based on consecutive same-type outcomes.

        More consecutive same-type outcomes → larger step (up to 3x base).
        This makes the system converge faster on clear patterns.
        """
        failures = self._failure_counts.get(key, 0)
        successes = self._success_counts.get(key, 0)
        total = failures + successes
        if total == 0:
            return self.threshold_adj_step

        if is_failure:
            ratio = failures / total
        else:
            ratio = successes / total

        # Scale: 1x at 50/50, up to 3x at 100% same type
        multiplier = 1.0 + 2.0 * max(0, ratio - 0.5)
        return self.threshold_adj_step * multiplier

    def _on_success(
        self,
        key: tuple[ResponseMode, ResponseMode],
        signals: dict[str, float],
    ) -> None:
        """React to a confirmed success for transition *key*.

        On success: slightly lower the threshold (the escalation was warranted,
        so we can be a bit more sensitive) and recover signal weights.
        """
        success_count = self._success_counts.get(key, 0)
        if success_count < self.min_interventions:
            return

        step = self._adaptive_step(key, is_failure=False)

        # Lower threshold slightly (make escalation easier since it worked)
        current_shift = self._threshold_adjustments.get(key, 0.0)
        # Don't go below -max_threshold_shift (don't make system too sensitive)
        new_shift = max(current_shift - step * 0.5, -self.max_threshold_shift)
        self._threshold_adjustments[key] = new_shift

        # Recover signal weights toward zero (restore original sensitivity)
        for signal in signals:
            current_adj = self._weight_adjustments.get(signal, 0.0)
            if current_adj < 0:
                # Recover at half speed of decay
                recovery = min(self.weight_adj_step * 0.5, abs(current_adj))
                self._weight_adjustments[signal] = current_adj + recovery

    def _on_failure(
        self,
        key: tuple[ResponseMode, ResponseMode],
        signals: dict[str, float],
    ) -> None:
        """React to a confirmed failure for transition *key*.

        The failure count for *key* has already been incremented by the caller.
        If the total count is below *min_interventions*, skip adjustments.
        Otherwise raise the threshold (adaptive step) and lower signal weights.
        """
        failure_count = self._failure_counts.get(key, 0)
        if failure_count < self.min_interventions:
            return

        step = self._adaptive_step(key, is_failure=True)

        # Raise threshold (capped at max_threshold_shift).
        current_shift = self._threshold_adjustments.get(key, 0.0)
        new_shift = min(current_shift + step, self.max_threshold_shift)
        self._threshold_adjustments[key] = new_shift

        # Lower each triggering signal weight, floored so the effective weight
        # never drops below min_weight.
        for signal, original_weight in signals.items():
            current_adj = self._weight_adjustments.get(signal, 0.0)
            new_adj = current_adj - self.weight_adj_step
            # Floor: effective weight = original_weight + adj >= min_weight
            floor = self.min_weight - original_weight
            new_adj = max(new_adj, floor)
            self._weight_adjustments[signal] = new_adj
