"""SOMA Cross-Session Predictor — trajectory-based pressure prediction.

Extends PressurePredictor by matching current pressure trajectory against
past sessions. When a similar historical trajectory is found (cosine > 0.8),
blends the historical continuation into the prediction for earlier warnings.
"""

from __future__ import annotations

import math

from soma.predictor import Prediction, PressurePredictor
from soma.session_store import load_sessions


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 for zero-length."""
    if len(a) == 0 or len(b) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class CrossSessionPredictor(PressurePredictor):
    """Pressure predictor enhanced with cross-session pattern matching.

    Loads session history and finds past trajectories similar to the current
    one. When a match is found (cosine > 0.8), blends the historical
    continuation (60% base + 40% cross-session) for better prediction.
    """

    def __init__(self, window: int = 10, horizon: int = 5) -> None:
        super().__init__(window=window, horizon=horizon)
        self._session_patterns: list[list[float]] = []

    def load_history(self, base_dir=None) -> None:
        """Load past session trajectories from session store.

        Only keeps trajectories with 5+ data points (minimum for matching).
        """
        records = load_sessions(base_dir=base_dir)
        for r in records:
            if len(r.pressure_trajectory) >= 5:
                self._session_patterns.append(r.pressure_trajectory)

    def predict(self, next_threshold: float) -> Prediction:
        """Predict pressure with cross-session trajectory blending.

        Falls back to base PressurePredictor when:
        - Fewer than 3 session patterns loaded
        - Fewer than 3 current pressure readings
        - No similar trajectory found (cosine < 0.8)
        """
        base = super().predict(next_threshold)

        if len(self._session_patterns) < 3 or len(self._pressures) < 3:
            return base

        # Current trajectory window
        current = list(self._pressures)[-min(len(self._pressures), self.window):]

        best_score = 0.0
        best_cont: list[float] | None = None

        for past in self._session_patterns:
            # Slide current pattern over past trajectory to find best match
            max_start = len(past) - len(current) - self.horizon
            for start in range(max(0, max_start + 1)):
                segment = past[start : start + len(current)]
                if len(segment) != len(current):
                    continue
                sim = _cosine_similarity(current, segment)
                if sim > best_score and sim > 0.8:
                    cont_start = start + len(current)
                    cont_end = cont_start + self.horizon
                    continuation = past[cont_start:cont_end]
                    if continuation:
                        best_score = sim
                        best_cont = continuation

        if best_cont:
            cross_pred = max(best_cont)
            blended = 0.6 * base.predicted_pressure + 0.4 * cross_pred
            confidence = base.confidence * 0.6 + best_score * 0.4

            return Prediction(
                current_pressure=base.current_pressure,
                predicted_pressure=min(1.0, max(0.0, blended)),
                actions_ahead=base.actions_ahead,
                will_escalate=blended >= next_threshold and confidence > 0.3,
                next_threshold=next_threshold,
                dominant_reason=(
                    "cross_session"
                    if cross_pred > base.predicted_pressure
                    else base.dominant_reason
                ),
                confidence=confidence,
            )

        return base

    def to_dict(self) -> dict:
        """Serialize including session patterns."""
        d = super().to_dict()
        d["session_patterns"] = self._session_patterns
        return d

    @classmethod
    def from_dict(cls, data: dict) -> CrossSessionPredictor:
        """Restore from serialized dict."""
        obj = cls(window=data.get("window", 10), horizon=data.get("horizon", 5))
        # Restore base state
        for p in data.get("pressures", []):
            obj._pressures.append(p)
        for a in data.get("action_log", []):
            obj._action_log.append(a)
        obj._session_patterns = data.get("session_patterns", [])
        return obj
