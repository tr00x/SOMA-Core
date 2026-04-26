"""A/B control for contextual-guidance pattern validation.

SOMA's contextual-guidance patterns report "helped %" via a
followthrough heuristic (pressure drop ≥15% within 2 actions). That
number is a **prediction proxy**, not a causal claim — it can't tell
whether pressure dropped *because* the agent read the message or
because the agent would have course-corrected anyway.

This module adds the missing counterfactual: every Nth firing of a
pattern is routed to the **control** arm, where we compute the
guidance message, record ``pressure_before`` / ``pressure_after``, but
deliberately **do not** surface the message to the agent. After
enough pairs (default: 30 per arm) we compare mean Δpressure between
treatment and control with Welch's t-test.

- ``status == "validated"`` → p<0.05 AND Cohen's d > 0.2 AND raw Δp
  difference > 0.1: the pattern causes a real pressure drop beyond
  baseline recovery.
- ``status == "refuted"`` → p<0.05 AND effect goes the wrong way:
  injecting the message made things worse (or did nothing while
  control recovered).
- ``status == "inconclusive"`` → sample size met (≥100 pairs) but
  p≥0.05: no measurable effect, even with enough data.
- ``status == "collecting"`` → fewer than ``min_pairs`` in at least
  one arm.

Arm assignment uses **block randomization** keyed on persistent
per-``(family, pattern)`` counters in ``~/.soma/ab_counters.json``:
when ``|T − C| ≥ BALANCE_THRESHOLD`` we force the minority arm,
otherwise a cryptographic coin flip. This guarantees tight balance
even inside a short burst of firings within a single session — the
prior MD5 scheme could cluster 40+ consecutive firings into one arm
because neighbouring ``action_number`` values don't mix well.

Trade-off: we lose replay determinism (``hash(family|pattern|N)``
would give the same arm on replay). Reviewing 90 rows of biased data
convinced the user that bias is a worse failure mode than losing
replay; no existing tooling relied on replay reproducibility.

Users who want their guidance always live can set
``SOMA_DISABLE_CONTROL_ARM=1``; assignment falls through to
``treatment`` for every firing. The legacy ``SOMA_DISABLE_AB=1`` is
honoured as a deprecated alias.
"""

from __future__ import annotations

import json
import math
import os
import secrets
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    import fcntl

    _HAS_FLOCK = True
except ImportError:
    _HAS_FLOCK = False

Arm = Literal["treatment", "control"]
Status = Literal["collecting", "validated", "refuted", "inconclusive"]


# Minimum pairs (per arm) before we'll even consider validating.
DEFAULT_MIN_PAIRS = 30
# After this many pairs with p>=0.05 we stop waiting and call it inconclusive.
INCONCLUSIVE_AT = 100
# Cohen's d threshold for "validated".
EFFECT_SIZE_THRESHOLD = 0.2
# Minimum absolute difference in mean Δpressure.
DELTA_DIFFERENCE_THRESHOLD = 0.1
# Two-sided alpha.
ALPHA = 0.05

# Block-randomization: when |T−C| ≥ this many, the next firing is forced
# into the minority arm. 2 keeps bursts within ±1 pair of each other
# while still allowing a fair coin flip most of the time.
BALANCE_THRESHOLD = 2

# Persistent counter file. Counts are cumulative per (family, pattern)
# and are what guarantee long-run balance across sessions.
_COUNTERS_PATH = Path.home() / ".soma" / "ab_counters.json"

# Bounded LRU-ish cache of firing_id → arm. Caps memory of the dedup
# layer (post 2026-04-25 idempotency fix) so a long-lived install
# doesn't grow ab_counters.json unbounded. Trim is FIFO — oldest
# firings drop first, which matches "the firing already landed and the
# row is already written, so no caller will ask about it again."
_FIRINGS_DEDUP_MAX = 200


@dataclass(frozen=True)
class AbDecision:
    """Single arm assignment — what the hook pipeline acts on."""

    pattern: str
    agent_family: str
    arm: Arm


@dataclass(frozen=True)
class ValidationResult:
    """Summary of an A/B validation for one pattern/family.

    ``p_value`` / ``effect_size`` are ``None`` while ``status == "collecting"``
    — we haven't run the test yet.
    """

    pattern: str
    agent_family: str | None
    fires_treatment: int
    fires_control: int
    mean_treatment_delta: float
    mean_control_delta: float
    delta_difference: float
    p_value: float | None
    effect_size: float | None
    status: Status


# ── Arm assignment ──────────────────────────────────────────────────

def should_inject(
    pattern: str,
    agent_family: str,
    action_number: int,
    firing_id: str = "",
) -> Arm:
    """Return the arm this firing is assigned to.

    Uses block randomization against persistent per-(family, pattern)
    counters: if one arm is ahead by ``BALANCE_THRESHOLD`` or more, the
    next firing is forced into the other arm; otherwise ``secrets``
    decides with a fair coin flip.

    ``firing_id`` (added 2026-04-25 after ultra-review): a caller-
    supplied deterministic key — typically
    ``f"{agent_id}|{pattern}|{action_number}"`` — that lets the same
    firing be safely re-asked about. Re-entry from a hook retry,
    pre/post both consulting, or any duplicate call returns the
    *same* arm without bumping the counter, eliminating the silent
    A/B bias the prior code introduced. ``firing_id=""`` falls back
    to the legacy non-idempotent path (every call increments) and is
    only retained for backward compat.

    ``action_number`` retained for signature stability; ignored when
    ``firing_id`` is provided.

    ``SOMA_DISABLE_CONTROL_ARM=1`` (or the deprecated alias
    ``SOMA_DISABLE_AB=1``) short-circuits to always-treatment for
    users who opt out of the counterfactual arm entirely.
    """
    if _ab_disabled():
        return "treatment"
    return _assign_arm(pattern, agent_family, action_number, firing_id)


def _ab_disabled() -> bool:
    """True if the user opted out of the control arm via env var."""
    return (
        os.environ.get("SOMA_DISABLE_CONTROL_ARM") == "1"
        or os.environ.get("SOMA_DISABLE_AB") == "1"
    )


def _assign_arm(
    pattern: str,
    agent_family: str,
    action_number: int,
    firing_id: str = "",
) -> Arm:
    """Block-randomized assignment backed by the persistent counter.

    Called under an exclusive file lock so concurrent processes on the
    same machine can't both read the same counter and collide. If the
    counter file is missing or corrupt we start fresh at ``(0, 0)`` —
    the next ``BALANCE_THRESHOLD`` firings will still land near 50/50.

    Idempotency (2026-04-25): if ``firing_id`` is provided AND that
    firing has already been assigned, return the cached arm without
    bumping the counter. Re-entry no longer silently rebiases.
    """
    del action_number  # retained for signature stability; ignored.
    key = f"{agent_family}|{pattern}"
    with _counter_lock():
        counters, firings = _load_persisted()

        # Idempotency: a firing already assigned returns its arm
        # without touching the counter. Without this, every retry,
        # pre/post double-consult, or replay re-rolls and re-bumps.
        if firing_id and firing_id in firings:
            cached_arm = firings[firing_id]
            if cached_arm in ("treatment", "control"):
                return cached_arm  # type: ignore[return-value]

        t_count, c_count = counters.get(key, [0, 0])

        if t_count - c_count >= BALANCE_THRESHOLD:
            arm: Arm = "control"
        elif c_count - t_count >= BALANCE_THRESHOLD:
            arm = "treatment"
        else:
            arm = "treatment" if secrets.randbits(1) == 1 else "control"

        if arm == "treatment":
            counters[key] = [t_count + 1, c_count]
        else:
            counters[key] = [t_count, c_count + 1]

        if firing_id:
            firings[firing_id] = arm
            # FIFO trim — drop oldest insertions once over cap. Python
            # 3.7+ dicts preserve insertion order, so popitem(last=False
            # equivalent) via iteration works.
            if len(firings) > _FIRINGS_DEDUP_MAX:
                excess = len(firings) - _FIRINGS_DEDUP_MAX
                for old_key in list(firings.keys())[:excess]:
                    del firings[old_key]

        _save_persisted(counters, firings)
    return arm


def _load_persisted() -> tuple[dict[str, list[int]], dict[str, str]]:
    """Read counters AND firings dedup map.

    Two on-disk schemas, both supported:
    - Legacy (pre 2026-04-25): flat dict ``{family|pattern: [t, c]}``.
      No firings dedup → returns empty firings dict.
    - Current: ``{"_counters": {...}, "_firings": {...}}``.

    Missing or corrupt file → empty pair.
    """
    try:
        raw = _COUNTERS_PATH.read_text()
    except (FileNotFoundError, OSError):
        return {}, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}

    # Current schema if either sentinel is present.
    if "_counters" in data or "_firings" in data:
        raw_counters = data.get("_counters", {})
        raw_firings = data.get("_firings", {})
    else:
        raw_counters = data
        raw_firings = {}

    counters: dict[str, list[int]] = {}
    if isinstance(raw_counters, dict):
        for k, v in raw_counters.items():
            if (
                isinstance(v, list) and len(v) == 2
                and all(isinstance(x, int) and x >= 0 for x in v)
            ):
                counters[k] = [v[0], v[1]]

    firings: dict[str, str] = {}
    if isinstance(raw_firings, dict):
        for k, v in raw_firings.items():
            if isinstance(v, str) and v in ("treatment", "control"):
                firings[k] = v
    return counters, firings


def _save_persisted(
    counters: dict[str, list[int]], firings: dict[str, str],
) -> None:
    """Best-effort write of both maps. Failure here must not break guidance."""
    try:
        _COUNTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Counters keys sorted for diff-friendliness; firings preserved
        # in insertion order so the FIFO trim contract holds across writes.
        _COUNTERS_PATH.write_text(json.dumps({
            "_counters": dict(sorted(counters.items())),
            "_firings": firings,
        }))
    except OSError:
        pass


# Legacy aliases — kept for tests and any external caller. Internal
# call sites should use the _persisted variants directly.
def _load_counters() -> dict[str, list[int]]:
    return _load_persisted()[0]


def _save_counters(counters: dict[str, list[int]]) -> None:
    _, firings = _load_persisted()
    _save_persisted(counters, firings)


class _counter_lock:
    """Exclusive fcntl lock around the counter file.

    Degrades to a no-op context manager when fcntl isn't available
    (non-POSIX). In that case the counters are still correct for a
    single-process setup; only cross-process races are unprotected.
    """

    def __enter__(self) -> "_counter_lock":
        if not _HAS_FLOCK:
            self._fh = None
            return self
        lock_path = _COUNTERS_PATH.with_suffix(".lock")
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(lock_path, "w")
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            self._fh = None
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._fh is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self._fh.close()


def reset_counters() -> None:
    """Wipe the counter file. Used by v2026.5.5 migration and tests."""
    with _counter_lock():
        try:
            _COUNTERS_PATH.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


# ── Validation ──────────────────────────────────────────────────────

_VALID_HORIZONS: frozenset[int] = frozenset({1, 2, 5, 10})


def validate(
    outcomes: list[dict],
    *,
    pattern: str,
    agent_family: str | None = None,
    min_pairs: int = DEFAULT_MIN_PAIRS,
    horizon: int = 2,
) -> ValidationResult:
    """Run the Welch's t-test on ``outcomes`` and classify the pattern.

    ``outcomes`` must be a list of rows like those returned by
    :meth:`AnalyticsStore.get_ab_outcomes` — each with ``arm``,
    ``pressure_before``, and a ``pressure_after`` column for the
    requested horizon.

    ``horizon`` selects which post-firing sample to use for the delta:

    - 2 (default): reads ``pressure_after`` — the canonical h=2 sample
      that maps to all pre-v2026.6.0 verdicts.
    - 1, 5, 10: reads ``pressure_after_h{horizon}`` — populated by
      the multi-horizon recording flow shipped in 2026.6.0. Rows
      missing the requested column are skipped (legacy rows / late
      sample never landed).

    Skipping is intentional: zero-filling missing horizons would
    bias short-recovery patterns toward "no effect" and tilt the
    pressure-delta math.
    """
    if horizon not in _VALID_HORIZONS:
        raise ValueError(
            f"horizon must be one of {sorted(_VALID_HORIZONS)}, got {horizon!r}"
        )
    column = "pressure_after" if horizon == 2 else f"pressure_after_h{horizon}"

    treatment_deltas: list[float] = []
    control_deltas: list[float] = []
    for row in outcomes:
        before = row.get("pressure_before")
        after = row.get(column)
        if before is None or after is None:
            continue
        delta = float(before) - float(after)  # positive = pressure dropped
        if row.get("arm") == "treatment":
            treatment_deltas.append(delta)
        elif row.get("arm") == "control":
            control_deltas.append(delta)

    fires_t = len(treatment_deltas)
    fires_c = len(control_deltas)
    mean_t = statistics.fmean(treatment_deltas) if treatment_deltas else 0.0
    mean_c = statistics.fmean(control_deltas) if control_deltas else 0.0
    diff = mean_t - mean_c

    if fires_t < min_pairs or fires_c < min_pairs:
        # Not enough data yet.
        return ValidationResult(
            pattern=pattern,
            agent_family=agent_family,
            fires_treatment=fires_t,
            fires_control=fires_c,
            mean_treatment_delta=mean_t,
            mean_control_delta=mean_c,
            delta_difference=diff,
            p_value=None,
            effect_size=None,
            status="collecting",
        )

    p_value = _welch_t_test_p_value(treatment_deltas, control_deltas)
    effect_size = _cohens_d(treatment_deltas, control_deltas)

    status = _classify(
        fires_t=fires_t, fires_c=fires_c,
        diff=diff, effect_size=effect_size, p_value=p_value,
    )

    return ValidationResult(
        pattern=pattern,
        agent_family=agent_family,
        fires_treatment=fires_t,
        fires_control=fires_c,
        mean_treatment_delta=mean_t,
        mean_control_delta=mean_c,
        delta_difference=diff,
        p_value=p_value,
        effect_size=effect_size,
        status=status,
    )


def _classify(
    *,
    fires_t: int,
    fires_c: int,
    diff: float,
    effect_size: float,
    p_value: float,
) -> Status:
    """Map (p, d, Δ) → validated / refuted / inconclusive."""
    # Significant AND large enough effect in the right direction → validated.
    if (
        p_value < ALPHA
        and effect_size > EFFECT_SIZE_THRESHOLD
        and diff > DELTA_DIFFERENCE_THRESHOLD
    ):
        return "validated"
    # Significant BUT effect goes the wrong way or is negative.
    if p_value < ALPHA and (diff < 0 or effect_size < 0):
        return "refuted"
    # Enough data, no significant effect.
    if fires_t >= INCONCLUSIVE_AT and fires_c >= INCONCLUSIVE_AT:
        return "inconclusive"
    return "collecting"


# ── Stats primitives (stdlib only; no scipy/numpy dep) ─────────────

def _welch_t_test_p_value(a: list[float], b: list[float]) -> float:
    """Two-sided Welch's t-test returning p-value.

    Welch's t doesn't assume equal variances, which matters because
    treatment and control Δp often have different spread (intervention
    can collapse variance while control variance stays wide). Returns
    1.0 for degenerate inputs (< 2 samples per arm or zero variance in
    both arms).
    """
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 1.0

    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    var_a = statistics.variance(a)
    var_b = statistics.variance(b)

    # Zero variance in both arms: the means are point-masses.
    if var_a == 0.0 and var_b == 0.0:
        return 1.0 if mean_a == mean_b else 0.0

    se_sq = (var_a / n_a) + (var_b / n_b)
    if se_sq <= 0:
        return 1.0

    t_stat = (mean_a - mean_b) / math.sqrt(se_sq)

    # Welch–Satterthwaite degrees of freedom.
    numerator = se_sq ** 2
    denom = (
        ((var_a / n_a) ** 2) / (n_a - 1)
        + ((var_b / n_b) ** 2) / (n_b - 1)
    )
    if denom <= 0:
        return 1.0
    df = numerator / denom

    return _two_sided_p(t_stat, df)


def _two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value for Student's t distribution.

    Uses the regularized incomplete beta relation::

        P(|T| > t) = I_x(df/2, 1/2)  where x = df / (df + t^2)

    ``math.lgamma`` plus a continued-fraction expansion keeps this
    pure-stdlib. Accurate to ~1e-6 for df in [1, 1e6], plenty for a
    p-value used as a gate.
    """
    if df <= 0:
        return 1.0
    t_abs = abs(t)
    x = df / (df + t_abs * t_abs)
    # Return I_x(df/2, 1/2); that equals P(|T| > t) for a t-distribution.
    return _regularized_incomplete_beta(x, df / 2.0, 0.5)


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """I_x(a, b) via Lentz's continued-fraction algorithm.

    Direct port of Numerical Recipes' ``betai`` — chosen because it
    sidesteps numpy/scipy and converges in ~20 iterations for the
    t-distribution parameters we care about. On non-convergence
    (``_beta_cf`` returns NaN) we degrade gracefully to a p-value of
    1.0 so the validator reports "collecting" instead of crashing
    the hook pipeline on a malformed t-stat.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # ln of the front factor.
    lbeta = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    front = math.exp(lbeta)

    # Symmetry: the continued fraction converges faster when x is on
    # the "right side" of (a+1)/(a+b+2). Swap if we're past it.
    if x < (a + 1.0) / (a + b + 2.0):
        cf = _beta_cf(x, a, b)
        if not math.isfinite(cf):
            return 1.0
        return front * cf / a
    cf = _beta_cf(1.0 - x, b, a)
    if not math.isfinite(cf):
        return 1.0
    return 1.0 - front * cf / b


def _beta_cf(x: float, a: float, b: float, max_iter: int = 200, eps: float = 3e-7) -> float:
    """Lentz's algorithm for the continued fraction of I_x(a, b).

    Returns ``math.nan`` on non-convergence rather than a silent value
    so callers can fall back to a safe default. For df ∈ [2, 1e6] and
    typical two-sample t-stats this converges in under 50 iterations.
    """
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        # Even step.
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        # Odd step.
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if not math.isfinite(h):
            return math.nan
        if abs(delta - 1.0) < eps:
            return h
    # Exhausted iterations without convergence — signal to caller.
    return math.nan


def _cohens_d(a: list[float], b: list[float]) -> float:
    """Pooled-variance Cohen's d for two independent samples."""
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 0.0
    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    var_a = statistics.variance(a)
    var_b = statistics.variance(b)
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    if pooled_var <= 0:
        return 0.0
    return (mean_a - mean_b) / math.sqrt(pooled_var)
