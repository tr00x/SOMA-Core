"""Single source of truth for all SOMA behavioral thresholds.

v2026.6.x: previously these constants were scattered across
``ab_control``, ``calibration``, and ``hooks/post_tool_use``.
Centralizing them here means a maintainer wanting to tune a single
threshold edits one file, not three.

Each subsystem still re-exports the constants it cares about so
existing callers (``from soma.ab_control import DEFAULT_MIN_PAIRS``)
keep working.

Calibration philosophy: every constant has a comment explaining
the *why*. Don't change one without updating the comment.
"""
from __future__ import annotations


# ── A/B validation (Welch's t-test) ────────────────────────────────

#: Minimum pairs (per arm) before we'll even attempt to classify.
#: Welch's t-test stays valid at n=15 (standard scientific minimum
#: 10–15). Achieved power: d=0.2 → 22%, d=0.5 → 50%, d=0.8 → 85%.
#: Tradeoff is honest: faster time-to-signal vs. lower power on weak
#: effects. Was 30 pre-2026.6.x.
DEFAULT_MIN_PAIRS: int = 15

#: After this many pairs without statistical significance we stop
#: waiting and emit ``inconclusive``. ~2x of MIN_PAIRS so the ratio
#: stays consistent. Was 100 pre-2026.6.x (3.3x).
INCONCLUSIVE_AT: int = 30

#: Two-sided alpha for Welch's t-test.
ALPHA: float = 0.05

#: Cohen's d threshold for "validated" — 0.2 is "small effect" by
#: convention. Anything below is statistically detectable but
#: practically negligible.
EFFECT_SIZE_THRESHOLD: float = 0.2

#: Minimum absolute difference in mean Δpressure (treatment vs.
#: control). Belt-and-suspenders against tiny effects clearing
#: alpha by chance with large samples.
DELTA_DIFFERENCE_THRESHOLD: float = 0.1


# ── A/B measurement (recording side) ───────────────────────────────

#: Action horizon at which we INSERT the canonical ab_outcomes row.
#: Both treatment and control record pressure_after at exactly this
#: many actions after the firing — critical for unbiased comparison.
#: The h=1/h=5/h=10 columns layer on top via UPDATE.
AB_MEASUREMENT_HORIZON: int = 2

#: Δpressure threshold ≥ which we consider the firing "recovered"
#: (the boolean ``followed`` column). 15% drop is the calibrated
#: floor below which natural decay alone explains the change.
AB_RECOVERED_DELTA: float = 0.15


# ── Calibration phases ─────────────────────────────────────────────

#: Actions before the engine exits "warmup" phase and starts
#: emitting guidance. Per ~50-action observation window analysis,
#: 30 is the smallest threshold that yields stable P25/P75
#: percentiles while letting >40% of sessions exit warmup.
WARMUP_EXIT_ACTIONS: int = 30

#: Minimum fires per pattern before adaptive-phase auto-silence
#: can trigger. Below this the precision estimate is too noisy
#: to act on.
SILENCE_MIN_FIRES: int = 20

#: How often (in actions) to re-evaluate refuted/validated status
#: from analytics.db. Decoupled from silence refresh because
#: validation is heavier (Welch's t-test over all outcome rows).
REFUTED_REFRESH_INTERVAL: int = 100


# ── Persistence retention ──────────────────────────────────────────

#: Drop agents from engine_state.json whose ``last_active`` is older
#: than this. Each Claude Code PID becomes an agent_id; without
#: pruning ``cc-12345`` entries accumulate indefinitely as users
#: open and close sessions. 168 hours = 7 days, plenty for legit
#: long-lived sessions to keep their state, short enough that a
#: month of dead PIDs doesn't bloat the state file.
AGENT_RETENTION_HOURS: float = 168.0
