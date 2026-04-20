"""Self-calibration profile for per-user adaptive SOMA guidance.

Three-phase lifecycle:

    warmup (0-29 actions)     → guidance silent, learn personal distribution
    calibrated (30-199)       → personal thresholds replace hardcoded constants
    adaptive (200+)           → per-pattern auto-silence based on precision

Profiles persist at ``~/.soma/calibration_{family}.json`` with atomic
writes. Profile "family" collapses the numeric tail of an agent id so
short-lived ``cc-92331`` → ``cc-47512`` sessions share one learning state
and don't warm-up forever.

v2026.5.3: boundaries lowered from 100/500 to 30/200 — median session is
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
# can reference the same source of truth. Lowered in v2026.5.3 to match
# real-world session-length distribution (median ~50 actions).
WARMUP_EXIT_ACTIONS = 30
CALIBRATED_EXIT_ACTIONS = 200

# Auto-silence gate (adaptive phase).
SILENCE_MIN_FIRES = 20
SILENCE_HELPED_RATE = 0.20
UNSILENCE_HELPED_RATE = 0.40
# How often (in actions) to re-query analytics and refresh the silence
# list during the adaptive phase. Query is indexed by pattern so it's
# cheap, but we still only pay it once per N actions.
SILENCE_REFRESH_INTERVAL = 100

# Patterns we track for auto-silence. Keep in sync with _PATTERN_PRIORITY
# in contextual_guidance — hardcoded here to avoid a circular import.
_SILENCE_TRACKED_PATTERNS = (
    "cost_spiral", "budget", "bash_retry", "error_cascade",
    "entropy_drop", "blind_edit", "context",
)

# Legacy fallback values — personal thresholds clamp to these floors so
# a user with extremely quiet sessions can't accidentally disable signals
# entirely. These mirror the hardcoded constants used pre-calibration.
LEGACY_FLOORS: dict[str, float | int] = {
    "drift_threshold": 0.3,
    "entropy_threshold": 0.5,
    "error_cascade_streak": 3,
    # retry_storm_streak retained for backward-compat profile roundtrip
    # even though the pattern was dropped in v2026.4.4 and no evaluator
    # reads it. Removing would break legacy calibration_*.json files.
    "retry_storm_streak": 2,
}

# Regex strips the trailing numeric part of a session-style agent id so
# the same user's next cc-* session inherits calibration.
_AGENT_FAMILY_RE = re.compile(r"^(?P<family>.+?)[-_][0-9]+$")

SCHEMA_VERSION = 1


def calibration_family(agent_id: str) -> str:
    """Collapse ephemeral session ids into a stable calibration key.

    ``cc-92331`` → ``cc``; ``swe-bench-48`` → ``swe-bench``. Falls back
    to the full id when no numeric tail is present so user-chosen agent
    ids keep isolated profiles.
    """
    if not agent_id:
        return "default"
    m = _AGENT_FAMILY_RE.match(agent_id)
    if m:
        return m.group("family")
    return agent_id


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
        # Forward-compat: drop unknown fields silently so v2 data never
        # crashes a v1 reader.
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
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return CalibrationProfile.from_dict(data)
        except (json.JSONDecodeError, OSError):
            try:
                backup = path.with_suffix(path.suffix + ".corrupt")
                path.rename(backup)
            except OSError:
                pass
    return CalibrationProfile(family=family)


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
        for pattern in _SILENCE_TRACKED_PATTERNS:
            stats = store.get_pattern_stats(profile.family, pattern, last_n=50)
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
