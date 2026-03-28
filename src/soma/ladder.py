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

    def evaluate_with_adjustments(
        self,
        pressure: float,
        budget_health: float,
        threshold_adjustments: dict[str, float] | None = None,
        custom_thresholds: dict | None = None,
    ) -> Level:
        """Like evaluate(), but applies learned threshold adjustments before checking.

        *threshold_adjustments* maps a transition key string such as
        ``"HEALTHY->CAUTION"`` to a float shift that is **added** to the
        escalation threshold for that step.  This lets the learning engine raise
        thresholds for transitions that have historically been false alarms.

        *custom_thresholds* maps level names (lowercase, e.g. ``"caution"``) to
        absolute escalation threshold values read from soma.toml.  When provided,
        these replace the built-in THRESHOLDS defaults before learning shifts are
        applied.
        """
        if not threshold_adjustments and not custom_thresholds:
            return self.evaluate(pressure, budget_health)

        # Build an adjusted copy of THRESHOLDS keyed by level index.
        # Start from custom_thresholds if provided, otherwise use built-in defaults.
        if custom_thresholds:
            _level_name_map = {lv.name.lower(): i for i, lv in enumerate(_ESCALATION_LEVELS)}
            adjusted_thresholds = list(THRESHOLDS)
            for level_name, esc_val in custom_thresholds.items():
                idx = _level_name_map.get(level_name.lower())
                if idx is not None and idx > 0:
                    _, de = adjusted_thresholds[idx]
                    # de-escalation threshold: keep proportional gap (default gap is 0.05)
                    default_esc, default_de = THRESHOLDS[idx]
                    gap = default_esc - default_de
                    adjusted_thresholds[idx] = (float(esc_val), float(esc_val) - gap)
        else:
            adjusted_thresholds = list(THRESHOLDS)

        # Threshold adjustment keys are "<OLD_LEVEL_NAME>-><NEW_LEVEL_NAME>".
        for i, level in enumerate(_ESCALATION_LEVELS):
            if i == 0:
                continue  # HEALTHY has no escalation transition into it
            prev_level = _ESCALATION_LEVELS[i - 1]
            key = f"{prev_level.name}->{level.name}"
            shift = threshold_adjustments.get(key, 0.0)
            if shift:
                esc, de = adjusted_thresholds[i]
                adjusted_thresholds[i] = (esc + shift, de + shift)

        # Temporarily swap THRESHOLDS, evaluate, then restore.
        # We do this by reimplementing the core logic inline to avoid mutation.
        # --- safe-mode (delegate to normal evaluate so state is managed) ---
        if budget_health <= 0.0:
            self._in_safe_mode = True

        if self._in_safe_mode:
            if budget_health > SAFE_MODE_EXIT:
                self._in_safe_mode = False
                self._current = Level.HEALTHY
            else:
                self._current = Level.SAFE_MODE
                return self._current

        if self._forced is not None:
            self._current = self._forced
            return self._current

        target_index = 0
        for i, (esc_thresh, _) in enumerate(adjusted_thresholds):
            if pressure >= esc_thresh:
                target_index = i

        target = _ESCALATION_LEVELS[target_index]
        current_index = (
            _ESCALATION_LEVELS.index(self._current)
            if self._current in _ESCALATION_LEVELS
            else 0
        )

        if target > self._current:
            self._current = target
        elif target < self._current:
            _, de_thresh = adjusted_thresholds[current_index]
            if pressure < de_thresh:
                self._current = _ESCALATION_LEVELS[current_index - 1]

        return self._current

    def force_level(self, level: Level | None) -> None:
        """Manually override the current level. Pass None to clear."""
        self._forced = level
        if level is not None:
            self._current = level
