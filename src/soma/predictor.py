"""SOMA Predictor — predict pressure escalation before it happens.

Uses two signals:
1. Trend extrapolation: linear regression on recent pressure readings
2. Pattern boosters: known-bad sequences that historically precede escalation

The predictor runs after each action and emits a warning when predicted
pressure in N actions exceeds the next escalation threshold.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Prediction:
    """Result of a pressure prediction."""
    current_pressure: float
    predicted_pressure: float
    actions_ahead: int
    will_escalate: bool
    next_threshold: float
    dominant_reason: str  # "trend", "error_streak", "blind_writes", "thrashing"
    confidence: float  # 0-1, based on sample count and R²


# Known-bad patterns and their pressure boost
_PATTERN_BOOSTS: dict[str, float] = {
    "error_streak": 0.15,      # 3+ consecutive errors
    "blind_writes": 0.10,      # 2+ writes without read
    "thrashing": 0.08,         # same file edited 3+ times
    "retry_storm": 0.12,       # high retry rate
}


class PressurePredictor:
    """Predicts future pressure from recent history.

    Maintains a sliding window of recent pressure readings and action
    patterns. On each update, fits a simple linear trend and adds
    pattern-based boosts to estimate pressure N actions ahead.
    """

    def __init__(self, window: int = 10, horizon: int = 5) -> None:
        self.window = window
        self.horizon = horizon
        self._pressures: list[float] = []
        self._action_log: list[dict] = []

    def update(self, pressure: float, action_entry: dict | None = None) -> None:
        """Record a new pressure reading and optional action log entry."""
        self._pressures.append(pressure)
        if len(self._pressures) > self.window:
            self._pressures = self._pressures[-self.window:]

        if action_entry:
            self._action_log.append(action_entry)
            if len(self._action_log) > self.window:
                self._action_log = self._action_log[-self.window:]

    def predict(self, next_threshold: float) -> Prediction:
        """Predict pressure `horizon` actions ahead.

        Args:
            next_threshold: The pressure level that would trigger escalation.

        Returns:
            Prediction with extrapolated pressure and escalation likelihood.
        """
        current = self._pressures[-1] if self._pressures else 0.0

        # 1. Linear trend
        slope, r_squared = self._linear_trend()
        trend_prediction = current + slope * self.horizon

        # 2. Pattern boosts
        boost, dominant_pattern = self._pattern_boost()
        predicted = max(0.0, min(1.0, trend_prediction + boost))

        # 3. Confidence: based on sample count and fit quality
        n = len(self._pressures)
        sample_confidence = min(n / self.window, 1.0)
        fit_confidence = max(r_squared, 0.0) if n >= 3 else 0.0
        confidence = 0.6 * sample_confidence + 0.4 * fit_confidence

        # 4. Dominant reason — use SIGNED slope so a strongly negative
        # trend reads as "improving" instead of being lumped into
        # "stable". The boost comparison uses abs because "pattern
        # dominates trend in magnitude" is the right question regardless
        # of trend direction.
        if boost > abs(slope * self.horizon):
            reason = dominant_pattern or "pattern"
        elif slope > 0:
            reason = "trend"
        elif slope < 0:
            reason = "improving"
        else:
            reason = "stable"

        will_escalate = predicted >= next_threshold and confidence > 0.3

        return Prediction(
            current_pressure=current,
            predicted_pressure=predicted,
            actions_ahead=self.horizon,
            will_escalate=will_escalate,
            next_threshold=next_threshold,
            dominant_reason=reason,
            confidence=confidence,
        )

    def _linear_trend(self) -> tuple[float, float]:
        """Fit a simple linear regression to pressure readings.

        Returns (slope, r_squared). Slope is change per action.
        """
        n = len(self._pressures)
        if n < 2:
            return 0.0, 0.0

        # Simple OLS: y = a + b*x
        xs = list(range(n))
        ys = self._pressures

        x_mean = sum(xs) / n
        y_mean = sum(ys) / n

        ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        ss_xx = sum((x - x_mean) ** 2 for x in xs)
        ss_yy = sum((y - y_mean) ** 2 for y in ys)

        if ss_xx == 0:
            return 0.0, 0.0

        slope = ss_xy / ss_xx

        # R² (coefficient of determination)
        if ss_yy == 0:
            r_squared = 1.0 if ss_xy == 0 else 0.0
        else:
            r_squared = (ss_xy ** 2) / (ss_xx * ss_yy)

        return slope, r_squared

    def _pattern_boost(self) -> tuple[float, str]:
        """Check for known-bad patterns in recent actions.

        Returns (total_boost, dominant_pattern_name).
        """
        if not self._action_log:
            return 0.0, ""

        recent = self._action_log[-self.window:]
        boost = 0.0
        dominant = ""

        # Error streak: 3+ consecutive errors at the end
        consecutive_errors = 0
        for entry in reversed(recent):
            if entry.get("error"):
                consecutive_errors += 1
            else:
                break
        if consecutive_errors >= 3:
            b = _PATTERN_BOOSTS["error_streak"]
            boost += b
            dominant = "error_streak"

        # Blind writes: 2+ writes without a Read
        writes_since_read = 0
        for entry in reversed(recent):
            if entry.get("tool") in ("Write", "Edit", "NotebookEdit"):
                writes_since_read += 1
            elif entry.get("tool") == "Read":
                break
        if writes_since_read >= 2:
            b = _PATTERN_BOOSTS["blind_writes"]
            if b > boost:
                dominant = "blind_writes"
            boost += b

        # Thrashing: same file edited 3+ times in window
        edit_files: list[str] = []
        for entry in recent:
            if entry.get("tool") in ("Write", "Edit") and entry.get("file"):
                edit_files.append(entry["file"])
        if edit_files:
            from collections import Counter
            file_counts = Counter(edit_files)
            max_edits = max(file_counts.values())
            if max_edits >= 3:
                b = _PATTERN_BOOSTS["thrashing"]
                if b > boost:
                    dominant = "thrashing"
                boost += b

        # Retry storm: check if error rate > 40%
        if len(recent) >= 5:
            error_count = sum(1 for e in recent if e.get("error"))
            if error_count / len(recent) > 0.4:
                b = _PATTERN_BOOSTS["retry_storm"]
                if b > boost:
                    dominant = "retry_storm"
                boost += b

        return boost, dominant

    def to_dict(self) -> dict:
        return {
            "window": self.window,
            "horizon": self.horizon,
            "pressures": list(self._pressures),
            "action_log": list(self._action_log),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PressurePredictor":
        obj = cls(window=data.get("window", 10), horizon=data.get("horizon", 5))
        obj._pressures = list(data.get("pressures", []))
        obj._action_log = list(data.get("action_log", []))
        return obj
