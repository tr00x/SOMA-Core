"""Self-calibration profile for per-user adaptive SOMA guidance.

Three-phase lifecycle:

    warmup (0-29 actions)     → guidance silent, learn personal distribution
    calibrated (30-199)       → personal thresholds replace hardcoded constants
    adaptive (200+)           → per-pattern auto-silence based on precision

Profiles persist at ``~/.soma/calibration_{family}.json`` with atomic
writes. Profile "family" collapses the numeric tail of an agent id so
short-lived ``cc-92331`` → ``cc-47512`` sessions share one learning state
and don't warm-up forever.

2026-04-19: boundaries lowered from 100/500 to 30/200 — median session is
~50 actions, so 30 is the smallest threshold that still yields stable
P25/P75 percentiles while letting >40% of sessions exit warmup.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from soma.state import SOMA_DIR

Phase = Literal["warmup", "calibrated", "adaptive"]

# Phase boundaries. Exposed as module constants so tests and dashboard
# can reference the same source of truth.
# 2026-04-27 onward: WARMUP_EXIT_ACTIONS, SILENCE_MIN_FIRES, REFUTED_REFRESH_INTERVAL
# moved to soma.tunables — re-exported below for backward compatibility.
from soma.tunables import (  # noqa: F401, E402
    REFUTED_REFRESH_INTERVAL,
    SILENCE_MIN_FIRES,
    WARMUP_EXIT_ACTIONS,
)

CALIBRATED_EXIT_ACTIONS = 200

# Auto-silence gate (adaptive phase).
SILENCE_HELPED_RATE = 0.20
UNSILENCE_HELPED_RATE = 0.40
# How often (in actions) to re-query analytics and refresh the silence
# list during the adaptive phase. Query is indexed by pattern so it's
# cheap, but we still only pay it once per N actions.
SILENCE_REFRESH_INTERVAL = 100

# Patterns we track for auto-silence. Keep in sync with _PATTERN_PRIORITY
# in contextual_guidance — hardcoded here to avoid a circular import.
# 2026-04-27 onward: dropped retired patterns (`entropy_drop`, `context`,
# retired 2026-04-25) so silence/refute decisions can't accumulate
# stats for patterns that never re-fire.
_SILENCE_TRACKED_PATTERNS = (
    "cost_spiral", "budget", "bash_retry", "bash_error_streak",
    "error_cascade", "blind_edit",
)

# Legacy fallback values — personal thresholds clamp to these floors so
# a user with extremely quiet sessions can't accidentally disable signals
# entirely. These mirror the hardcoded constants used pre-calibration.
LEGACY_FLOORS: dict[str, float | int] = {
    "drift_threshold": 0.3,
    "entropy_threshold": 0.5,
    "error_cascade_streak": 3,
    # retry_storm_streak retained for backward-compat profile roundtrip
    # even though the pattern was dropped in 2026-04-18 and no evaluator
    # reads it. Removing would break legacy calibration_*.json files.
    "retry_storm_streak": 2,
}

# Regex strips the trailing numeric part of a session-style agent id so
# the same user's next cc-* session inherits calibration.
_AGENT_FAMILY_RE = re.compile(r"^(?P<family>.+?)[-_][0-9]+$")

# 2026-04-27 onward: explicit alias map for non-session-style ids that
# conceptually belong to a known family. Without this, the CLI default
# ``agent_id="claude-code"`` writes ~/.soma/calibration_claude-code.json
# while hook sessions (``cc-12345``) write ~/.soma/calibration_cc.json
# — two profiles for the same agent.
_AGENT_FAMILY_ALIASES = {
    "claude-code": "cc",
}

SCHEMA_VERSION = 2

# Schema migration registry. Each entry maps from_version → callable
# that takes a raw dict at that version and returns a dict at
# from_version+1.
from typing import Callable as _Callable  # noqa: E402


# Patterns whose silenced/refuted state should not survive the
# 2026-04-30 resurrection. These were retired between 2026-04-18 and
# 2026-04-25 and many user profiles persisted them in
# ``silenced_patterns`` or ``refuted_patterns``. Carrying that state
# forward would silently kill the resurrection for anyone with a
# pre-existing profile.
_RESURRECTED_2026_04_30: frozenset[str] = frozenset(
    {"_stats", "drift", "entropy_drop", "context"}
)


def _migrate_v1_to_v2(d: dict) -> dict:
    """Strip resurrected pattern keys from silenced/refuted lists AND
    reset the per-pattern precision cache + last_silence_check_action.

    The resurrection (2026-04-30) reactivated four patterns that some
    pre-existing user profiles had auto-silenced or auto-refuted under
    their pre-fix behavior. Without this migration ``evaluate()`` would
    drop the resurrected candidates on load and the resurrection would
    ship dead-on-arrival.

    Resetting ``last_silence_check_action`` and the precision cache
    closes the second-order trap: even after stripping the pattern
    from ``silenced_patterns``, the next ``update_silence`` call would
    re-read the *cached* precision (computed under the old broken
    behavior) and immediately re-silence the resurrected pattern. The
    reset forces the silence loop to recompute precision from
    post-resurrection data.
    """
    d = dict(d)
    for key in ("silenced_patterns", "refuted_patterns", "validated_patterns"):
        existing = d.get(key) or []
        if existing:
            d[key] = [p for p in existing if p not in _RESURRECTED_2026_04_30]
    cache = d.get("pattern_precision_cache") or {}
    if cache:
        d["pattern_precision_cache"] = {
            k: v for k, v in cache.items()
            if k not in _RESURRECTED_2026_04_30
        }
    # Reset both action counters so the next silence/refute check
    # reads fresh post-resurrection data, not the pre-fix window.
    d["last_silence_check_action"] = 0
    d["last_refuted_check_action"] = 0
    d["schema_version"] = 2
    return d


_SCHEMA_MIGRATORS: dict[int, _Callable[[dict], dict]] = {
    1: _migrate_v1_to_v2,
}


def _apply_schema_migrators(
    data: dict, from_version: int, target_version: int
) -> dict:
    """Walk the registered migrators from ``from_version`` up to
    ``target_version``. Missing intermediate migrator → return data
    as-is (forward-compat: extra fields will be dropped by from_dict).
    """
    current = data
    v = from_version
    while v < target_version:
        migrator = _SCHEMA_MIGRATORS.get(v)
        if migrator is None:
            break
        current = migrator(current)
        v += 1
    return current


def calibration_family(agent_id: str) -> str:
    """Collapse ephemeral session ids into a stable calibration key.

    ``cc-92331`` → ``cc``; ``swe-bench-48`` → ``swe-bench``;
    ``claude-code`` → ``cc`` (explicit alias);
    ``claude-code-12345`` → ``cc`` (regex strip → alias). Falls back
    to the full id when no rule matches so user-chosen agent ids
    keep isolated profiles.

    2026-04-27 onward review fix: alias map is consulted *after* the
    numeric-tail regex too, so wrappers that send
    ``claude-code-<pid>`` collapse correctly into the same family
    as the bare literal — same bug class we already closed for the
    pure literal case.
    """
    if not agent_id:
        return "default"
    m = _AGENT_FAMILY_RE.match(agent_id)
    family = m.group("family") if m else agent_id
    return _AGENT_FAMILY_ALIASES.get(family, family)


def _profile_path(family: str) -> Path:
    return SOMA_DIR / f"calibration_{family}.json"


@dataclass
class CalibrationProfile:
    """Per-agent-family calibration state.

    Invariant: ``phase`` is derived from ``action_count`` and must stay
    consistent — use :meth:`advance` after each recorded action, never
    mutate ``phase`` directly.
    """

    family: str
    action_count: int = 0
    phase: Phase = "warmup"

    # Learned distributions (populated at phase transitions).
    drift_p25: float = 0.0
    drift_p75: float = 0.0
    entropy_p25: float = 0.0
    entropy_p75: float = 0.0
    typical_error_burst: int = 0
    typical_retry_burst: int = 0
    typical_success_rate: float = 0.0

    # Auto-silence state (adaptive phase).
    silenced_patterns: list[str] = field(default_factory=list)
    last_silence_check_action: int = 0
    pattern_precision_cache: dict[str, float] = field(default_factory=dict)

    # Auto-retire state (P1.1). Patterns whose A/B validation returned
    # ``refuted`` are silenced unconditionally — independent of phase
    # and of precision-based auto-silence. Populated by
    # :func:`maybe_refresh_refuted` and cleared if a later validation
    # flips the verdict.
    refuted_patterns: list[str] = field(default_factory=list)
    last_refuted_check_action: int = 0

    # Skeptic-mode allowlist (P2.3). Populated in the same refresh pass
    # that tracks refuted_patterns: a pattern enters this list when its
    # A/B validation returns ``validated`` and drops out when the status
    # changes. Consumed by ContextualGuidance when SOMA_SKEPTIC=1 — the
    # flag restricts guidance to patterns in this list.
    validated_patterns: list[str] = field(default_factory=list)

    # Metadata.
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        # Phase is always a function of action_count — callers setting
        # action_count directly (tests, migrations) shouldn't have to
        # remember to sync `phase`.
        self.phase = _phase_for(self.action_count)

    # ── Lifecycle ──────────────────────────────────────────────────

    def advance(self, by: int = 1) -> None:
        """Record ``by`` more actions and update phase accordingly."""
        if by <= 0:
            return
        self.action_count += by
        self.phase = _phase_for(self.action_count)
        self.updated_at = time.time()

    def is_warmup(self) -> bool:
        return self.phase == "warmup"

    def is_calibrated(self) -> bool:
        return self.phase == "calibrated"

    def is_adaptive(self) -> bool:
        return self.phase == "adaptive"

    # ── Personal thresholds ────────────────────────────────────────

    def drift_threshold(self) -> float:
        """Personal P75 of drift, never below the legacy 0.3 floor."""
        if self.phase == "warmup":
            return float(LEGACY_FLOORS["drift_threshold"])
        return max(self.drift_p75, float(LEGACY_FLOORS["drift_threshold"]))

    def entropy_threshold(self) -> float:
        """Personal P25 of entropy, never below the legacy 0.5 floor.

        Low entropy = monotool panic; P25 captures the user's own quiet
        baseline so we fire only when they're abnormally repetitive.
        """
        if self.phase == "warmup":
            return float(LEGACY_FLOORS["entropy_threshold"])
        return max(self.entropy_p25, float(LEGACY_FLOORS["entropy_threshold"]))

    def retry_storm_streak(self) -> int:
        if self.phase == "warmup":
            return int(LEGACY_FLOORS["retry_storm_streak"])
        # One more than the user's typical error burst: fire only when
        # the streak exceeds their normal noise level.
        return max(self.typical_retry_burst + 1, int(LEGACY_FLOORS["retry_storm_streak"]))

    def error_cascade_streak(self) -> int:
        if self.phase == "warmup":
            return int(LEGACY_FLOORS["error_cascade_streak"])
        return max(self.typical_error_burst + 1, int(LEGACY_FLOORS["error_cascade_streak"]))

    # ── Auto-silence gate ──────────────────────────────────────────

    def should_silence(self, pattern: str) -> bool:
        """Return True iff this pattern should not fire for this family.

        Only active in the adaptive phase — warmup silences *everything*
        and calibrated fires unconditionally.
        """
        return self.phase == "adaptive" and pattern in self.silenced_patterns

    # ── Auto-retire (P1.1) ─────────────────────────────────────────

    def is_refuted(self, pattern: str) -> bool:
        """Return True iff A/B validation has refuted this pattern.

        Unlike :meth:`should_silence`, auto-retire fires in every phase
        — if we have enough data to say the pattern is harmful, the
        warmup/calibrated/adaptive distinction doesn't matter.
        """
        return pattern in self.refuted_patterns

    def mark_refuted(self, pattern: str) -> None:
        """Record a refuted verdict from :func:`ab_control.validate`."""
        if pattern not in self.refuted_patterns:
            self.refuted_patterns.append(pattern)
            self.updated_at = time.time()

    def unmark_refuted(self, pattern: str) -> None:
        """Drop a refuted verdict; called when newer data recovers it."""
        if pattern in self.refuted_patterns:
            self.refuted_patterns.remove(pattern)
            self.updated_at = time.time()

    # ── Skeptic allowlist (P2.3) ───────────────────────────────────

    def is_validated(self, pattern: str) -> bool:
        """Return True iff A/B validation has confirmed this pattern."""
        return pattern in self.validated_patterns

    def mark_validated(self, pattern: str) -> None:
        """Record a validated verdict from :func:`ab_control.validate`."""
        if pattern not in self.validated_patterns:
            self.validated_patterns.append(pattern)
            self.updated_at = time.time()

    def unmark_validated(self, pattern: str) -> None:
        """Drop a validated verdict when the status flips away."""
        if pattern in self.validated_patterns:
            self.validated_patterns.remove(pattern)
            self.updated_at = time.time()

    def update_silence(self, pattern: str, fires: int, helped: int) -> None:
        """Apply the 20/40 hysteresis based on latest analytics snapshot.

        Silence kicks in at <20% helped over ≥20 fires; re-enable when
        helped rate climbs above 40% on a later refresh.
        """
        if fires < SILENCE_MIN_FIRES:
            return
        rate = helped / fires if fires else 0.0
        self.pattern_precision_cache[pattern] = rate
        # Inclusive boundary: exactly 20% helped triggers silence,
        # exactly 40% helped triggers re-enable. Plan wording is
        # "<20% helped" — use <= so the documented 20-fire / 4-helped
        # corner case actually silences the pattern.
        if rate <= SILENCE_HELPED_RATE:
            if pattern not in self.silenced_patterns:
                self.silenced_patterns.append(pattern)
        elif rate >= UNSILENCE_HELPED_RATE:
            if pattern in self.silenced_patterns:
                self.silenced_patterns.remove(pattern)

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CalibrationProfile:
        # 2026-04-27 onward: schema migration scaffold. Apply registered
        # upgraders for any version below SCHEMA_VERSION before
        # constructing the dataclass. Currently the registry is
        # empty (we're at v=1 from day one) — adding an entry like
        # ``_SCHEMA_MIGRATORS[1] = _migrate_v1_to_v2`` keys a future
        # bump. Profiles persisted at a HIGHER version than this
        # build understands fall back to defaults (with a debug log
        # so the maintainer notices the downgrade).
        from_version = int(data.get("schema_version", 1))
        if from_version > SCHEMA_VERSION:
            # Future-version data on an older binary — refuse to
            # corrupt it by misinterpretation. Return a fresh
            # default profile so the caller's family stays intact;
            # the original file isn't touched here.
            from soma.errors import log_silent_failure
            log_silent_failure(
                f"calibration.from_dict (schema v{from_version} > v{SCHEMA_VERSION})",
                RuntimeError(
                    f"calibration profile is at v{from_version}, this "
                    f"build only understands v{SCHEMA_VERSION} — using defaults"
                ),
            )
            return cls(family=str(data.get("family", "default")))
        elif from_version < SCHEMA_VERSION:
            data = _apply_schema_migrators(data, from_version, SCHEMA_VERSION)

        # Forward-compat: drop unknown fields silently so v2 data never
        # crashes a v1 reader (within the same major-version chain).
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in allowed}
        prof = cls(**clean)
        # Re-derive phase defensively — a hand-edited file with a stale
        # phase shouldn't outrank the action_count ground truth.
        prof.phase = _phase_for(prof.action_count)
        return prof


def _phase_for(action_count: int) -> Phase:
    if action_count < WARMUP_EXIT_ACTIONS:
        return "warmup"
    if action_count < CALIBRATED_EXIT_ACTIONS:
        return "calibrated"
    return "adaptive"


# ── Persistence ────────────────────────────────────────────────────

def load_profile(agent_id: str) -> CalibrationProfile:
    """Load the calibration profile for the agent's family; empty new one on miss.

    On corrupt JSON we rename the broken file to ``.corrupt`` before
    starting over so the user can inspect (or restore) their
    accumulated calibration rather than lose it silently.
    """
    family = calibration_family(agent_id)
    path = _profile_path(family)
    # 2026-04-27 onward: one-shot migration of pre-alias profile files.
    # Users who ran `soma reset`/`soma config` etc. before the
    # claude-code → cc alias landed have a calibration_claude-code.json
    # sitting next to (or instead of) their hook-session
    # calibration_cc.json. Rename it into place so they don't lose
    # accumulated calibration.
    #
    # Race-safe: hold profile_lock(family) around the migration so two
    # concurrent hooks can't both rename the stale file (which silently
    # succeeds on POSIX but loses the second mutation cycle).
    if not path.exists():
        with profile_lock(family):
            # Re-check under the lock — another hook may have raced
            # us to the migration.
            if not path.exists():
                for stale_id in (sid for sid, alias in _AGENT_FAMILY_ALIASES.items() if alias == family):
                    stale_path = _profile_path(stale_id)
                    if stale_path.exists():
                        try:
                            stale_path.rename(path)
                            break
                        except OSError:
                            pass
    if path.exists():
        try:
            data = json.loads(path.read_text())
            profile = CalibrationProfile.from_dict(data)
            # 2026-04-27 onward: post-migration the file holds the *legacy*
            # family value ("claude-code") in its `family` field. The
            # next save_profile would write back to
            # _profile_path("claude-code") and recreate the file we
            # just migrated away from. Coerce family to the canonical
            # alias target.
            if profile.family != family:
                profile.family = family
            return profile
        except (json.JSONDecodeError, OSError):
            try:
                backup = path.with_suffix(path.suffix + ".corrupt")
                path.rename(backup)
            except OSError:
                pass
    return CalibrationProfile(family=family)


def clear_stale_silence_cache(soma_dir: Path | None = None) -> int:
    """Zero the auto-silence cache on every calibration profile in ``soma_dir``.

    Paired with the 2026-04-23 ``_archive_biased_ab_outcomes`` migration:
    that one truncates ab_outcomes, but the per-profile silence cache
    (populated from pre-reset guidance precision) kept suppressing
    half of the tracked patterns. With the cache intact, those patterns
    never fire post-reset → ab_outcomes stays empty → the P2.2 coverage
    gate is unreachable.

    Only the silence triad is cleared — ``silenced_patterns``,
    ``pattern_precision_cache``, ``last_silence_check_action``. The
    refuted/validated lists (P1.1/P2.3) reflect post-reset A/B evidence
    and must survive.

    Idempotent: re-running on an already-clean profile is a no-op.
    Returns the number of profile files visited (including ones that
    were already empty) so callers can log the sweep size.
    """
    base = soma_dir if soma_dir is not None else SOMA_DIR
    if not base.exists():
        return 0
    visited = 0
    for path in base.glob("calibration_*.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        data["silenced_patterns"] = []
        data["pattern_precision_cache"] = {}
        data["last_silence_check_action"] = 0
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data))
            os.replace(tmp, path)
            visited += 1
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
    return visited


def save_profile(profile: CalibrationProfile) -> None:
    """Persist profile atomically: tmp file → fsync → rename.

    Concurrent hooks (parallel subagents) can race on the same family
    profile. The advance→save sequence needs a lock around the read-
    modify-write performed by callers, but save itself is best-effort
    atomic: we use a lock file so that if a caller sets up
    ``with profile_lock(family):`` around load+advance+save, the
    sequence is serialized.
    """
    path = _profile_path(profile.family)
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile guarantees unique name, same-filesystem for atomic replace.
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(profile.to_dict(), f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class profile_lock:
    """POSIX fcntl advisory lock around a family's calibration file.

    Use to serialize ``load → advance → save`` across concurrent hooks::

        with profile_lock(family):
            p = load_profile(agent_id)
            p.advance(1)
            save_profile(p)

    Non-POSIX (Windows) falls through without locking — better than
    crashing the hook, and action counters drift by at most 1 per
    simultaneous invocation.
    """

    def __init__(self, family: str):
        self.family = family
        self._fh = None

    def __enter__(self):
        try:
            import fcntl
            lock_path = SOMA_DIR / f"calibration_{self.family}.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(lock_path, "w")
            fcntl.flock(self._fh, fcntl.LOCK_EX)
        except Exception:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
        return self

    def __exit__(self, *_exc):
        if self._fh is not None:
            try:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        return False


def reset_profile(agent_id: str) -> bool:
    """Delete the profile so the next action starts a fresh warmup.

    Returns True iff a profile file was actually removed.
    """
    path = _profile_path(calibration_family(agent_id))
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


# ── Distribution learning ─────────────────────────────────────────

def compute_distributions(
    signal_pressures_history: list[dict[str, float]],
    errors_history: list[bool],
    entropy_history: list[float],
    bash_retry_history: list[bool] | None = None,
) -> dict[str, float | int]:
    """Derive personal distribution stats from recent action history.

    Inputs are parallel lists in chronological order — one entry per
    recorded action. ``bash_retry_history`` is an optional list marking
    rows where the same Bash command retried; when omitted, retry
    burst equals the generic error burst (no Bash-specific signal).
    Missing data for any signal yields the legacy floor. Returns a dict
    shaped like the fields a profile consumes.
    """
    drifts = [p.get("drift", 0.0) for p in signal_pressures_history if isinstance(p, dict)]

    error_burst = _typical_burst(errors_history, truthy=True)
    retry_burst = (
        _typical_burst(bash_retry_history, truthy=True)
        if bash_retry_history else error_burst
    )

    result: dict[str, float | int] = {
        "drift_p25": _percentile(drifts, 25),
        "drift_p75": _percentile(drifts, 75),
        "entropy_p25": _percentile(entropy_history, 25),
        "entropy_p75": _percentile(entropy_history, 75),
        "typical_error_burst": error_burst,
        "typical_retry_burst": retry_burst,
        "typical_success_rate": (
            1.0 - sum(1 for e in errors_history if e) / len(errors_history)
            if errors_history else 0.0
        ),
    }
    return result


def apply_distributions(
    profile: CalibrationProfile, dists: dict[str, float | int],
) -> None:
    """Write computed distributions into the profile in-place."""
    for k, v in dists.items():
        if hasattr(profile, k):
            setattr(profile, k, v)
    profile.updated_at = time.time()


def maybe_refresh_silence(profile: CalibrationProfile, analytics_store=None) -> bool:
    """Refresh silence list from analytics every N adaptive-phase actions.

    Returns True if analytics was actually queried (for test hooks /
    metrics). No-op outside the adaptive phase, or when the refresh
    interval hasn't elapsed since the last check.
    """
    if not profile.is_adaptive():
        return False
    delta = profile.action_count - profile.last_silence_check_action
    if delta < SILENCE_REFRESH_INTERVAL:
        return False

    # Lazy-import to keep analytics optional. We own the connection
    # only when we opened it ourselves, so we must close it — otherwise
    # each hook invocation leaks a SQLite FD.
    owned_store = False
    store = analytics_store
    if store is None:
        try:
            from soma.analytics import AnalyticsStore
            store = AnalyticsStore()
            owned_store = True
        except Exception:
            return False

    try:
        # Skip pre-2026-04-23 outcomes: they were generated under MD5
        # A/B assignment whose per-pattern bias skewed helped-rate
        # readings, and keeping them in the precision window kept
        # half the patterns silenced forever after the archive
        # migration truncated ab_outcomes.
        try:
            reset_ts = store.get_ab_reset_ts()
        except Exception:
            reset_ts = 0.0
        for pattern in _SILENCE_TRACKED_PATTERNS:
            stats = store.get_pattern_stats(
                profile.family, pattern, last_n=50, since_ts=reset_ts,
            )
            profile.update_silence(pattern, stats["fires"], stats["helped"])
    except Exception:
        return False
    finally:
        if owned_store:
            try:
                store.close()
            except Exception:
                pass

    profile.last_silence_check_action = profile.action_count
    profile.updated_at = time.time()
    return True


def maybe_refresh_refuted(
    profile: CalibrationProfile, analytics_store=None,
) -> bool:
    """Refresh the refuted- and validated-pattern lists from A/B outcomes.

    For each tracked pattern, query its outcomes and run
    :func:`ab_control.validate`. The ``refuted`` list (P1.1) and the
    ``validated`` list (P2.3) are both updated from the same verdict so
    we only pay for one t-test per pattern per refresh window.

    Returns True iff either list was potentially touched or analytics
    was actually queried. Fires in every phase — unlike silence, we want
    to retire bad patterns even for warmup users who still rely on
    defaults.
    """
    delta = profile.action_count - profile.last_refuted_check_action
    if delta < REFUTED_REFRESH_INTERVAL and profile.last_refuted_check_action > 0:
        return False

    owned_store = False
    store = analytics_store
    if store is None:
        try:
            from soma.analytics import AnalyticsStore
            store = AnalyticsStore()
            owned_store = True
        except Exception:
            return False

    try:
        from soma import ab_control
        for pattern in _SILENCE_TRACKED_PATTERNS:
            try:
                outcomes = store.get_ab_outcomes(pattern, agent_family=profile.family)
            except Exception:
                continue
            result = ab_control.validate(
                outcomes, pattern=pattern, agent_family=profile.family,
            )
            is_refuted = result.status == "refuted"
            was_refuted = pattern in profile.refuted_patterns
            if is_refuted and not was_refuted:
                profile.mark_refuted(pattern)
            elif not is_refuted and was_refuted:
                profile.unmark_refuted(pattern)

            is_validated = result.status == "validated"
            was_validated = pattern in profile.validated_patterns
            if is_validated and not was_validated:
                profile.mark_validated(pattern)
            elif not is_validated and was_validated:
                profile.unmark_validated(pattern)
    except Exception:
        return False
    finally:
        if owned_store:
            try:
                store.close()
            except Exception:
                pass

    profile.last_refuted_check_action = profile.action_count
    profile.updated_at = time.time()
    return True


def load_recent_audit(
    agent_family: str, limit: int = 500,
    audit_path: Path | None = None,
) -> list[dict]:
    """Read the last ``limit`` audit.jsonl rows for this family.

    Family matching is prefix-based so session-scoped ids (cc-47512)
    contribute to the "cc" family's distribution. Returns rows
    chronologically (oldest first). Malformed lines are skipped.
    """
    path = audit_path or (SOMA_DIR / "audit.jsonl")
    if not path.exists():
        return []
    # Tail the file — audit.jsonl can be tens of MB after a few weeks.
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return []
    rows: list[dict] = []
    # Walk backwards, keeping only this family's rows, stopping when we
    # have `limit`. Then reverse to chronological order for callers.
    for line in reversed(lines):
        if len(rows) >= limit:
            break
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        aid = row.get("agent_id", "")
        if calibration_family(aid) != agent_family:
            continue
        rows.append(row)
    rows.reverse()
    return rows


def recompute_from_audit(
    profile: CalibrationProfile, limit: int = 500,
    audit_path: Path | None = None,
) -> None:
    """Read recent audit rows for this profile and refresh distributions.

    Safe no-op when audit.jsonl is missing or empty. Callers should invoke
    this at phase transitions (action 100 / 500) rather than every hook —
    percentile math over 500 rows is cheap but not free.
    """
    rows = load_recent_audit(profile.family, limit=limit, audit_path=audit_path)
    if not rows:
        return
    signal_pressures = [r.get("signal_pressures", {}) for r in rows]
    errors = [bool(r.get("error", False)) for r in rows]
    # Entropy not currently logged per-row; leave as-is until Day 3 loop
    # runs audit enrichment. Pass empty list so entropy_p* stay defaults.
    entropy = [float(r.get("entropy", 0.0)) for r in rows if "entropy" in r]
    dists = compute_distributions(signal_pressures, errors, entropy)
    # Don't clobber entropy percentiles with zeros when we have no data.
    if not entropy:
        dists.pop("entropy_p25", None)
        dists.pop("entropy_p75", None)
    apply_distributions(profile, dists)


def _percentile(xs: list[float], q: float) -> float:
    """Nearest-rank percentile with safe handling of empty / one-element lists."""
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    # q in [0, 100]
    idx = max(0, min(len(s) - 1, int(round((q / 100.0) * (len(s) - 1)))))
    return float(s[idx])


def _typical_burst(flags: list[bool], truthy: bool) -> int:
    """Median length of consecutive ``truthy`` runs in ``flags``.

    Used to answer "what's a normal error streak for this user?" — the
    calibrated phase then fires retry_storm / error_cascade at *more*
    than that streak, not at the hardcoded 2/3.
    """
    runs: list[int] = []
    cur = 0
    for f in flags:
        if bool(f) == truthy:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    if not runs:
        return 0
    runs.sort()
    return int(runs[len(runs) // 2])  # median (lower on even count)
