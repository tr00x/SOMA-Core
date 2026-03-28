"""Escalation Ladder — maps (pressure, budget_health) → Level."""

from __future__ import annotations

from soma.types import AutonomyMode, Level

# (pressure_threshold_to_escalate_to_this_level, de_escalate_threshold)
# Index corresponds to Level value order: HEALTHY, CAUTION, DEGRADE, QUARANTINE, RESTART
THRESHOLDS: list[tuple[float, float]] = [
    (0.00, 0.00),   # HEALTHY
    (0.25, 0.20),   # CAUTION
    (0.50, 0.45),   # DEGRADE
    (0.75, 0.70),   # QUARANTINE
    (0.90, 0.85),   # RESTART
]

SAFE_MODE_EXIT: float = 0.10

# Levels in escalation order (excluding SAFE_MODE which is budget-triggered)
_ESCALATION_LEVELS: list[Level] = [
    Level.HEALTHY,
    Level.CAUTION,
    Level.DEGRADE,
    Level.QUARANTINE,
    Level.RESTART,
]


class Ladder:
    """Stateful escalation ladder."""

    def __init__(self) -> None:
        self._current: Level = Level.HEALTHY
        self._forced: Level | None = None
        self._in_safe_mode: bool = False

    @property
    def current(self) -> Level:
        return self._current

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, pressure: float, budget_health: float) -> Level:
        """Compute and record the new escalation level.

        Rules (in priority order):
        1. budget_health <= 0  → SAFE_MODE (latches).
        2. While in SAFE_MODE, exit only when budget_health > SAFE_MODE_EXIT.
        3. Manual force_level override applies after safe-mode check.
        4. Escalation: highest level whose escalate-threshold <= pressure.
        5. De-escalation: if pressure < de_escalate threshold of current level,
           drop exactly one level.
        """
        # --- safe-mode ---
        if budget_health <= 0.0:
            self._in_safe_mode = True

        if self._in_safe_mode:
            if budget_health > SAFE_MODE_EXIT:
                self._in_safe_mode = False
                # Reset current to HEALTHY so normal evaluation starts fresh
                self._current = Level.HEALTHY
                # fall through to normal evaluation
            else:
                self._current = Level.SAFE_MODE
                return self._current

        # --- manual override ---
        if self._forced is not None:
            self._current = self._forced
            return self._current

        # --- normal pressure-based evaluation ---
        # Find highest escalation level whose escalate-threshold pressure satisfies
        target_index = 0
        for i, (esc_thresh, _) in enumerate(THRESHOLDS):
            if pressure >= esc_thresh:
                target_index = i

        target = _ESCALATION_LEVELS[target_index]

        # De-escalation hysteresis: only drop one level at a time
        current_index = _ESCALATION_LEVELS.index(self._current) if self._current in _ESCALATION_LEVELS else 0

        if target > self._current:
            # Escalate — allow jumping multiple levels (spike scenario)
            self._current = target
        elif target < self._current:
            # Only de-escalate one level if pressure is below the de-escalate threshold
            _, de_thresh = THRESHOLDS[current_index]
            if pressure < de_thresh:
                self._current = _ESCALATION_LEVELS[current_index - 1]
            # else: hold current (hysteresis)
        # else: target == current, no change

        return self._current

    def requires_approval(self, level: Level, autonomy: AutonomyMode) -> bool:
        """Return True if this level + autonomy combination requires human approval.

        Only HUMAN_IN_THE_LOOP blocks on QUARANTINE, RESTART, or SAFE_MODE.
        """
        if autonomy is not AutonomyMode.HUMAN_IN_THE_LOOP:
            return False
        return level in (Level.QUARANTINE, Level.RESTART, Level.SAFE_MODE)

    def force_level(self, level: Level | None) -> None:
        """Manually override the current level. Pass None to clear."""
        self._forced = level
        if level is not None:
            self._current = level
