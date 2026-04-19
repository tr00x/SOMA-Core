"""Self-calibration profile for per-user adaptive SOMA guidance.

Three-phase lifecycle:

    warmup (0-99 actions)     → guidance silent, learn personal distribution
    calibrated (100-499)      → personal thresholds replace hardcoded constants
    adaptive (500+)           → per-pattern auto-silence based on precision

Profiles persist at ``~/.soma/calibration_{family}.json`` with atomic
writes. Profile "family" collapses the numeric tail of an agent id so
short-lived ``cc-92331`` → ``cc-47512`` sessions share one learning state
and don't warm-up forever.
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
WARMUP_EXIT_ACTIONS = 100
CALIBRATED_EXIT_ACTIONS = 500

# Auto-silence gate (adaptive phase).
SILENCE_MIN_FIRES = 20
SILENCE_HELPED_RATE = 0.20
UNSILENCE_HELPED_RATE = 0.40

# Legacy fallback values — personal thresholds clamp to these floors so
# a user with extremely quiet sessions can't accidentally disable signals
# entirely. These mirror the hardcoded constants used pre-calibration.
LEGACY_FLOORS: dict[str, float | int] = {
    "drift_threshold": 0.3,
    "entropy_threshold": 0.5,
    "retry_storm_streak": 2,
    "error_cascade_streak": 3,
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
        if rate < SILENCE_HELPED_RATE:
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
    """Load the calibration profile for the agent's family; empty new one on miss."""
    family = calibration_family(agent_id)
    path = _profile_path(family)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return CalibrationProfile.from_dict(data)
        except (json.JSONDecodeError, OSError):
            # Corrupt profile → start fresh rather than crash the hook.
            pass
    return CalibrationProfile(family=family)


def save_profile(profile: CalibrationProfile) -> None:
    """Persist profile atomically: tmp file → fsync → rename."""
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
) -> dict[str, float | int]:
    """Derive personal distribution stats from recent action history.

    Inputs are parallel lists in chronological order — one entry per
    recorded action. Missing data for any signal yields the legacy floor.
    Returns a dict shaped like the fields a profile consumes.
    """
    drifts = [p.get("drift", 0.0) for p in signal_pressures_history if isinstance(p, dict)]

    result: dict[str, float | int] = {
        "drift_p25": _percentile(drifts, 25),
        "drift_p75": _percentile(drifts, 75),
        "entropy_p25": _percentile(entropy_history, 25),
        "entropy_p75": _percentile(entropy_history, 75),
        "typical_error_burst": _typical_burst(errors_history, truthy=True),
        "typical_retry_burst": _typical_burst(errors_history, truthy=True),
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
