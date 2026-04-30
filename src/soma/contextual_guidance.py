"""SOMA Contextual Guidance — pattern-based actionable messages.

Replaces abstract pressure-based guidance with specific, evidence-cited
messages that tell the agent what happened, why it matters, and what to do.

Every message contains:
1. What happened — cites specific actions/errors from action_log
2. Why it matters — the concrete risk
3. What to do next — a specific actionable suggestion
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuidanceMessage:
    """A contextual guidance message with evidence."""

    pattern: str  # See REAL_PATTERN_KEYS for the live set.
    severity: str  # "info", "warn", "critical"
    message: str  # Full contextual message for the agent
    evidence: tuple[str, ...] = ()  # Specific actions/errors that triggered this
    suggestion: str = ""  # The actionable next step


# Severity ordering for comparison
_SEVERITY_ORDER = {"info": 0, "warn": 1, "critical": 2}

# Pattern priority within same severity (higher = wins ties)
_PATTERN_PRIORITY = {
    "cost_spiral": 10,
    "bash_error_streak": 6,
    "budget": 5,
    "bash_retry": 4,
    "error_cascade": 2,
    "context": 1,
    "blind_edit": 1,
    "entropy_drop": 1,
    "drift": 0,
}

# Canonical list of pattern keys that real production guidance paths emit.
# Dashboard ROI whitelisting and any future analytics filter should import
# this tuple rather than re-declare the set — single source of truth.
#
# Resurrected 2026-04-30:
#   - `entropy_drop` — was retired 2026-04-25 because the panic-velocity
#                escalator used a hardcoded ``avg_gap < 3.0`` cutoff that
#                fired on healthy fast Read/Glob loops. The escalator is
#                gone; severity is now driven by entropy alone (relative
#                to the user's calibrated ``entropy_p25`` floor).
#   - `context`     — was retired 2026-04-25 because the followthrough
#                check required literal "next.md"/"git commit" tokens, so
#                helped% was structurally pinned at 0%. Followthrough is
#                rewritten to detect actual compaction behavior (``/compact``
#                Bash, git commit, summary writes, or pressure drop).
#   - `drift`       — was retired 2026-04-18 after a 9-firing/0%-helped
#                window. Detector body restored from commit a673e67~1
#                with no behavior change. Sample was statistically too
#                small for a verdict — re-collecting from zero.
#   - `_stats`      — was retired 2026-04-19 as the "largest fatigue
#                source" at 242 firings/31% helped. Restored in
#                ``mirror.py`` behind a cooldown so the fallback emits at
#                most once per N actions per agent — addresses the
#                fatigue cause without losing the 31% lift signal.
#
# Reaching ``collecting`` status under the A/B harness; any "helped %"
# claim waits until MIN_PAIRS. Empty set today, but kept as a typed
# constant so downstream code (gate, dashboard) doesn't need to special-
# case "no retired patterns" vs "set missing."
RETIRED_PATTERN_KEYS: frozenset[str] = frozenset()
REAL_PATTERN_KEYS: tuple[str, ...] = tuple(_PATTERN_PRIORITY.keys())


def _forced_patterns() -> frozenset[str]:
    """Parse ``SOMA_FORCE_PATTERN`` into a set of pattern names.

    Accepts comma-separated names (``bash_retry,drift``). The sentinel
    values ``all`` / ``ALL`` / ``*`` force every known pattern back on,
    which is useful for debugging why guidance stopped firing after an
    auto-retire. Returns an empty set when the env var is unset/empty
    so the common path short-circuits with no string work.
    """
    raw = os.environ.get("SOMA_FORCE_PATTERN", "").strip()
    if not raw:
        return frozenset()
    if raw.lower() in ("all", "*"):
        return frozenset(REAL_PATTERN_KEYS)
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    return frozenset(parts)


def _skeptic_mode() -> bool:
    """Whether SOMA_SKEPTIC restricts guidance to A/B-validated patterns.

    ``1``, ``true``, ``yes``, ``on`` (case-insensitive) enable it;
    ``0``, ``false``, ``no``, ``off``, or any unset/empty value disable.
    """
    raw = os.environ.get("SOMA_SKEPTIC", "").strip().lower()
    return raw in ("1", "true", "yes", "on")

# Error message → suggestion mapping for retry storms
_ERROR_SUGGESTIONS: list[tuple[list[str], str]] = [
    (["permission denied", "access denied"], "check file permissions or run with appropriate access"),
    (["not found", "no such file", "no such directory"], "verify the path exists"),
    (["syntax error", "syntaxerror"], "read the file first to see current state"),
    (["test failed", "assertion", "assert", "expected", "actual"], "read the test output carefully — compare expected vs actual values"),
    (["import error", "modulenotfounderror", "no module named"], "check the import path and installed packages"),
    (["timeout", "timed out"], "the command is too slow — simplify or break it up"),
]


def _compute_tool_entropy(action_log: list[dict], window: int = 10) -> float:
    """Shannon entropy of tool distribution in recent actions. 0 = monotool, 2+ = diverse."""
    import math
    from collections import Counter
    recent = action_log[-window:]
    if len(recent) < 8:
        return 2.0  # Not enough data, assume healthy
    tools = [e.get("tool", "?") for e in recent]
    counts = Counter(tools)
    total = len(tools)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


# Data-backed healing transitions from production actions. Used as a
# fallback when no per-user calibration data is available. These defaults
# are re-derived from Timur's April 2026 analytics run (measure_transitions
# results at the time of 2026-04-19).
_HEALING_TRANSITIONS: dict[str, tuple[str, str]] = {
    "Bash": ("Read", "Bash→Read reduces pressure by 7%"),
    "Edit": ("Read", "Edit→Read reduces pressure by 5%"),
    "Write": ("Grep", "Write→Grep reduces pressure by 5%"),
}


# Cache for per-user healing transitions measured off analytics.db. Keyed
# by the failing tool; value is ``(heal_tool, evidence_text)``. Populated
# lazily on first call and refreshed every HEALING_CACHE_TTL_SECONDS
# (default 1h) so long-lived processes (dashboard) pick up new analytics
# instead of serving stale transitions forever.
_HEALING_CACHE: dict[str, tuple[str, str]] | None = None
_HEALING_CACHE_TS: float = 0.0
HEALING_CACHE_TTL_SECONDS: float = 3600.0  # 1 hour


def _load_healing_from_analytics() -> dict[str, tuple[str, str]]:
    """Derive the best healing tool for each failing tool from analytics.

    Returns ``{failing_tool: (heal_tool, evidence_sentence)}``. Uses
    :func:`soma.healing_validation.measure_transitions` with the default
    ``min_n=20`` threshold. Falls back to the hardcoded defaults when the
    DB is empty or the measurement raises.
    """
    try:
        from soma.healing_validation import measure_transitions
        rows = measure_transitions()
    except Exception:
        return dict(_HEALING_TRANSITIONS)

    # For each failing_tool, pick the transition with the most negative
    # delta (strongest healing). Skip positive-delta pairs.
    best: dict[str, tuple[str, float, int]] = {}
    for r in rows:
        if r.delta >= 0:
            continue
        if "→" not in r.transition:
            continue
        prev_tool, next_tool = r.transition.split("→", 1)
        cur = best.get(prev_tool)
        if cur is None or r.delta < cur[1]:
            best[prev_tool] = (next_tool, r.delta, r.n)

    if not best:
        return dict(_HEALING_TRANSITIONS)

    result: dict[str, tuple[str, str]] = {}
    for prev_tool, (next_tool, delta, n) in best.items():
        # Convert "-0.033" to "3.3%" for the agent-facing message.
        pct = abs(delta) * 100.0
        evidence = f"{prev_tool}→{next_tool} reduces pressure by {pct:.1f}% (n={n})"
        result[prev_tool] = (next_tool, evidence)
    # Keep hardcoded defaults for any tools we haven't measured yet.
    for k, v in _HEALING_TRANSITIONS.items():
        result.setdefault(k, v)
    return result


def _healing_table(use_analytics: bool = True) -> dict[str, tuple[str, str]]:
    """Return the active healing-transition table.

    Caches the result for HEALING_CACHE_TTL_SECONDS; set
    ``use_analytics=False`` (tests, offline runs) to short-circuit
    the DB read entirely.
    """
    global _HEALING_CACHE, _HEALING_CACHE_TS
    if not use_analytics:
        return dict(_HEALING_TRANSITIONS)
    import time as _time
    # Monotonic so NTP corrections / clock jumps can't freeze the cache.
    now = _time.monotonic()
    if _HEALING_CACHE is None or (now - _HEALING_CACHE_TS) >= HEALING_CACHE_TTL_SECONDS:
        _HEALING_CACHE = _load_healing_from_analytics()
        _HEALING_CACHE_TS = now
    return _HEALING_CACHE


def _reset_healing_cache() -> None:
    """Test hook: force the healing table to re-read analytics on next call."""
    global _HEALING_CACHE, _HEALING_CACHE_TS
    _HEALING_CACHE = None
    _HEALING_CACHE_TS = 0.0


def _healing_suggestion(failing_tool: str, use_analytics: bool = True) -> str:
    """Suggest a healing tool transition, preferring measured per-user data."""
    table = _healing_table(use_analytics=use_analytics)
    if failing_tool in table:
        heal_tool, evidence = table[failing_tool]
        return f"{heal_tool} next ({evidence})"
    return "Read the relevant files to re-establish context"


def _suggest_for_error(error_text: str) -> str:
    """Pick a suggestion based on error content."""
    lower = error_text.lower()
    for keywords, suggestion in _ERROR_SUGGESTIONS:
        if any(kw in lower for kw in keywords):
            return suggestion
    return "read the error output and try a fundamentally different approach"


_SENSITIVE_PATTERNS = {".env", "credentials", "secret", "private_key", ".pem", ".key", ".ssh", "token"}


def _read_file_snippet(file_path: str, max_lines: int = 20) -> str:
    """Read a snippet of a file for context enrichment. Never raises."""
    try:
        from pathlib import Path
        p = Path(file_path).resolve()
        if not p.exists() or not p.is_file() or p.is_symlink():
            return ""
        # Don't inject sensitive files into agent context
        lower_name = p.name.lower()
        if any(pat in lower_name for pat in _SENSITIVE_PATTERNS):
            return ""
        if p.stat().st_size > 100_000:  # Skip files >100KB
            return ""
        lines = p.read_text(errors="replace").splitlines()
        if len(lines) <= max_lines:
            snippet = "\n".join(f"  {i+1}: {ln}" for i, ln in enumerate(lines))
        else:
            # Show first 10 + last 10
            top = "\n".join(f"  {i+1}: {ln}" for i, ln in enumerate(lines[:10]))
            bot = "\n".join(f"  {i+1}: {ln}" for i, ln in enumerate(lines[-10:], len(lines)-10))
            snippet = f"{top}\n  ...\n{bot}"
        return snippet
    except Exception:
        return ""


def _recent_reads(action_log: list[dict], n: int = 5) -> list[str]:
    """Extract recently read file names from action log."""
    files: list[str] = []
    for entry in reversed(action_log):
        if entry.get("tool") in ("Read", "Grep", "Glob"):
            f = entry.get("file", "")
            if f:
                short = f.rsplit("/", 1)[-1] if "/" in f else f
                if short not in files:
                    files.append(short)
        if len(files) >= n:
            break
    return files


def _last_error_line(action_log: list[dict]) -> str:
    """Get the last error preview from action log."""
    for entry in reversed(action_log):
        if entry.get("error"):
            # action_log entries may have an "output" field from the extended log
            out = entry.get("output", "")
            if out:
                # Take last non-empty line as the most relevant error
                lines = [ln.strip() for ln in str(out).split("\n") if ln.strip()]
                return lines[-1][:120] if lines else ""
            return entry.get("tool", "unknown") + " failed"
    return ""


_PRESSURE_DROP_HELPED = 0.15  # pressure drop ≥ 15% counts as "guidance worked"
_PRESSURE_FALSE_ACTIONS = 2    # after this many actions with no drop, count as ignored


def _resolve_via_pressure(pressure_delta: float | None, actions_since: int) -> bool | None:
    """Fallback outcome resolver for patterns without explicit followthrough.

    Returns True if pressure dropped ≥15% (guidance worked),
    False if pressure did not drop after 2+ actions (guidance ignored),
    None if still inconclusive.
    """
    if pressure_delta is None:
        return None
    if pressure_delta >= _PRESSURE_DROP_HELPED:
        return True
    if actions_since >= _PRESSURE_FALSE_ACTIONS and pressure_delta <= 0:
        return False
    return None


def _pressure_dropped(pressure_delta: float | None) -> bool:
    """Strict pressure-drop check used by stricter followthrough.

    2026-04-19: instead of resolving purely on Δp, ``helped`` now
    requires BOTH a real drop AND an expected recovery action. This
    helper isolates the Δp half so each pattern branch can compose it
    with its own recovery test.
    """
    if pressure_delta is None:
        return False
    return pressure_delta >= _PRESSURE_DROP_HELPED


# Tool families used by ``compute_multi_helped`` to detect a tool-class
# switch after a guidance firing. The grouping is deliberately coarse —
# a switch from Bash to Read/Grep/Glob is what we mean by "stopped
# bashing the same wall"; switches inside the same family (Edit→Write)
# are noise. ``_tool_family("Anything else")`` returns ``other``.
_TOOL_FAMILIES: dict[str, str] = {
    "Bash": "bash",
    "Read": "read",
    "Grep": "read",
    "Glob": "read",
    "Write": "edit",
    "Edit": "edit",
    "NotebookEdit": "edit",
    "MultiEdit": "edit",
}


def _tool_family(tool_name: str) -> str:
    """Map a tool name to its coarse family for ``compute_multi_helped``.

    Returns one of: ``bash``, ``read``, ``edit``, ``other``. Empty /
    unknown tool names map to ``other``. The mapping is intentionally
    minimal so it stays cheap to extend; if a new tool ships and isn't
    in this dict, the worst case is one false negative for the
    tool-switch helped definition — never a crash.
    """
    if not tool_name:
        return "other"
    return _TOOL_FAMILIES.get(tool_name, "other")


# Multi-definition helped pressure-drop threshold. Generic, pattern-
# agnostic — just "did the load come down?". Looser than the strict
# 0.15 used in ``_PRESSURE_DROP_HELPED`` because the multi-definition
# stat is meant to surface *any* recovery, including small ones the
# pattern-specific rule would miss.
_MULTI_HELPED_PRESSURE_DROP = 0.10


def compute_multi_helped(
    pending: dict,
    pressure_after: float,
    next_actions: list[dict],
) -> dict[str, bool]:
    """Compute three orthogonal helped definitions for one firing.

    Inputs:

    - ``pending``: the followthrough dict — must carry
      ``pressure_at_injection`` and (for tool_switch) the failing tool
      under one of the keys we already use today (``tool`` /
      ``failing_tool`` / ``file`` is unused here).
    - ``pressure_after``: pressure sample at the resolution point.
    - ``next_actions``: action_log slice of the *N* actions that
      happened after the firing. Caller supplies the slice so this
      helper stays pure / testable. Three is enough — beyond that
      any "recovery" is statistically indistinguishable from drift.

    Returns a dict with three booleans:

    - ``helped_pressure_drop``: pressure_after dropped > 10pp from
      injection. Generic, pattern-agnostic.
    - ``helped_tool_switch``: any of next_actions[0:3] uses a tool
      from a family different from the failing tool's family. Useful
      for retry-storm / bash_retry where the fix is "stop hitting
      the same tool".
    - ``helped_error_resolved``: none of next_actions[0:3] errored.
      Useful for error_cascade / blind_edit.

    Edge cases:

    - Empty ``next_actions`` → tool_switch False, error_resolved True
      (vacuous: no errors observed).
    - Missing ``failing_tool`` → tool_switch False (no anchor to
      switch from).
    """
    pressure_at_injection = float(pending.get("pressure_at_injection", 0.0))
    failing_tool = (
        pending.get("failing_tool")
        or pending.get("tool")
        or ""
    )
    failing_family = _tool_family(failing_tool) if failing_tool else None
    sample = next_actions[:3]

    if failing_family is None:
        tool_switch = False
    else:
        tool_switch = any(
            _tool_family(a.get("tool", "")) != failing_family
            for a in sample
        )
    error_resolved = all(not a.get("error", False) for a in sample)
    pressure_drop = (
        float(pressure_after) < pressure_at_injection - _MULTI_HELPED_PRESSURE_DROP
    )
    return {
        "helped_pressure_drop": bool(pressure_drop),
        "helped_tool_switch": bool(tool_switch),
        "helped_error_resolved": bool(error_resolved),
    }


def check_followthrough(
    pending: dict,
    tool_name: str,
    tool_input: dict,
    file_path: str,
    error: bool,
    pressure_after: float | None = None,
    recent_actions: list[dict] | None = None,
) -> bool | None:
    """Check if the agent followed contextual guidance.

    Returns True if followed, False if ignored, None if inconclusive
    (keep waiting).

    2026-04-19 tightened the semantics: each pattern has a list of
    *strong* recovery signals (e.g. Read of the exact suggested file
    for ``blind_edit``, explicit git-commit / handoff-file write for
    ``context``, Read/Grep for ``bash_retry``, ≥3 distinct tools in a
    3-action window for ``entropy_drop``) that count as "helped" on
    their own — these are explicit behavioral markers that the agent
    clearly acted on the message. *Weak* signals (tool switch alone,
    related-but-different Read, Bash-succeeds-on-same-tool) only count
    when pressure actually drops ≥15%, so passive recovery can't
    credit SOMA. The old rule ("pressure drop alone = helped") over-
    credited natural recovery; this design separates "the agent did
    the thing" from "pressure went down."

    Note: this is the *dashboard-facing* semantic. The A/B proof
    layer (2026-04-19+) uses a simpler pressure-only rule because
    control-arm agents never saw the message and so can never perform
    the strong recovery signal by definition — the strict semantic
    would systematically under-count the control arm's "recoveries."

    ``recent_actions`` is the chronological action log (oldest→newest)
    used for tool-diversity checks; when omitted we fall back to the
    single-action view for backward compatibility.
    """
    pattern = pending.get("pattern", "")
    actions_since = pending.get("actions_since", 0) + 1

    # Truly-retired patterns short-circuit to None so legacy circuit_*.json
    # entries don't pollute helped/not-helped accounting. As of 2026-04-30
    # the set is empty (entropy_drop / context / drift / _stats were
    # resurrected). Keep the guard — it's the contract for any future
    # retirement.
    if pattern in RETIRED_PATTERN_KEYS:
        return None

    if actions_since > 5:
        return False  # Gave up waiting

    # Pressure-delta signal shared by patterns without explicit detection.
    pressure_at = pending.get("pressure_at_injection")
    pressure_delta: float | None = None
    if pressure_after is not None and pressure_at is not None:
        try:
            pressure_delta = float(pressure_at) - float(pressure_after)
        except (TypeError, ValueError):
            pressure_delta = None

    if pattern == "blind_edit":
        suggested_file = pending.get("file", "")
        # Recovery action = Read (preferably of the same file).
        if tool_name in ("Read", "Grep", "Glob"):
            if not suggested_file or file_path == suggested_file:
                return True
            # Related Read (e.g. Grep without exact path match) only
            # counts when pressure actually dropped — otherwise it may
            # just be unrelated exploration.
            return True if _pressure_dropped(pressure_delta) else None
        # A second edit without an intervening Read = ignored.
        if tool_name in ("Edit", "Write", "NotebookEdit"):
            return False
        return None

    if pattern == "error_cascade":
        # Strict: "helped" requires a tool *switch* (not the failing tool)
        # AND a real pressure drop. Success on the same tool without a
        # pressure drop is just noise.
        failing_tools = set(pending.get("failing_tools") or [])
        if not failing_tools:
            # Hooks written before 2026-04-19 don't set failing_tools.
            # Fallback to Bash-heavy cascade heuristic so we never skip
            # evaluation — but this path won't produce a "True" unless
            # pressure drops.
            failing_tools = {"Bash"}
        if tool_name not in failing_tools and not error:
            if _pressure_dropped(pressure_delta):
                return True
            # Tool switched but pressure flat: inconclusive.
            return None
        # Same tool or still error: if pressure dropped it's a
        # coincidence, not a followthrough.
        if actions_since >= _PRESSURE_FALSE_ACTIONS and not _pressure_dropped(pressure_delta):
            return False
        return None

    if pattern == "context":
        # Resurrected 2026-04-30. The pre-retire rule required literal
        # ``next.md`` / ``handoff`` / ``git commit`` tokens, so any agent
        # that wrapped up via different mechanics was scored as "did not
        # help." New rule: any *real* compaction signal counts —
        #   1. ``/compact`` Bash invocation (user-driven compaction);
        #   2. ``git commit`` / ``git add`` (preserve work before window);
        #   3. Write/Edit of a markdown summary handoff (NEXT.md, HANDOFF
        #      .md, summary.md, or any file with "summary" in the path);
        #   4. A meaningful pressure drop after the message (passive
        #      recovery — credited only via the pressure rule, not on its
        #      own behavior).
        if tool_name == "Bash" and isinstance(tool_input, dict):
            cmd = (tool_input.get("command", "") or "").lower()
            if "/compact" in cmd or "git commit" in cmd or "git add" in cmd:
                return True
        if tool_name in ("Write", "Edit", "NotebookEdit"):
            lower_path = (file_path or "").lower()
            if any(
                marker in lower_path
                for marker in ("next.md", "handoff", "summary")
            ):
                return True
        # Fall through to the pressure-only rule for everything else.
        return _resolve_via_pressure(pressure_delta, actions_since)

    if pattern == "budget":
        # Did they commit/wrap up?
        if tool_name == "Bash" and isinstance(tool_input, dict):
            cmd = tool_input.get("command", "")
            if "git commit" in cmd or "git add" in cmd:
                return True
        return _resolve_via_pressure(pressure_delta, actions_since)

    if pattern == "cost_spiral":
        return _resolve_via_pressure(pressure_delta, actions_since)

    if pattern == "entropy_drop":
        # Resurrected 2026-04-30. Tunnel-vision recovery wants a real
        # diversification signal: ≥3 distinct tools in the last 5
        # actions. The wider window (5 vs the original 3) lets
        # realistic recoveries like Read→Edit→Read→Grep→Bash count
        # as diversification — a strict 3-of-3 rule biases helped%
        # downward in the same way the old `context` literal-token
        # rule did. When ``recent_actions`` is absent (legacy callers)
        # we credit Read/Grep/Glob as a diversifying explore. Otherwise
        # fall through to the pressure rule.
        if recent_actions:
            window = recent_actions[-5:]
            distinct = {a.get("tool", "?") for a in window}
            if len(distinct) >= 3:
                return True
        elif tool_name in ("Read", "Grep", "Glob"):
            return True
        return _resolve_via_pressure(pressure_delta, actions_since)

    if pattern == "drift":
        # Resurrected 2026-04-30. Drift = "started with X, drifted to
        # Y." Followthrough = the agent re-anchored on the original
        # task: a Read of the task spec, a Grep for the keyword, or a
        # tool family change away from the drifted-to tool. Without
        # those signals we resolve via pressure.
        if tool_name in ("Read", "Grep", "Glob"):
            return True
        return _resolve_via_pressure(pressure_delta, actions_since)

    if pattern == "bash_retry":
        # Required recovery = Read OR a different command family (not
        # another Bash retry).
        if tool_name == "Read" or tool_name == "Grep":
            return True
        if tool_name != "Bash":
            return True if _pressure_dropped(pressure_delta) else None
        # Same tool (Bash).
        if not error:
            # Bash succeeded but same tool — credit only if pressure
            # actually dropped (avoids counting natural successes).
            return True if _pressure_dropped(pressure_delta) else None
        return False  # Still retrying Bash with another error.

    return None


class ContextualGuidance:
    """Pattern-based guidance that produces actionable messages.

    Returns at most ONE message per evaluation (highest severity wins).
    Tracks cooldowns per pattern to avoid spamming.
    """

    def __init__(
        self,
        cooldown_actions: int = 5,
        lesson_store=None,
        baseline=None,
        profile=None,
    ):
        self._cooldown_actions = cooldown_actions
        # pattern → last action_number when this pattern fired
        self._last_fired: dict[str, int] = {}
        self._lesson_store = lesson_store
        self._baseline = baseline
        # Optional CalibrationProfile — gates guidance in warmup, filters
        # auto-silenced patterns in adaptive. None = behave like the
        # legacy always-armed evaluator (used by test fixtures and the
        # soma.wrap SDK path that hasn't opted into calibration yet).
        self._profile = profile

    def evaluate(
        self,
        action_log: list[dict],
        current_tool: str,
        current_input: dict,
        vitals: dict,
        budget_health: float = 1.0,
        action_number: int = 0,
    ) -> GuidanceMessage | None:
        """Check all patterns, return highest-severity message or None."""
        # Warmup gate — no guidance fires until personal distribution
        # has accumulated. The engine still records the action; we just
        # withhold injection so a fresh install doesn't bombard the user
        # with globally-calibrated noise.
        if self._profile is not None and self._profile.is_warmup():
            return None

        candidates: list[GuidanceMessage] = []

        # Check each pattern (cost_spiral first — subsumes error_cascade/bash_retry)
        msg = self._check_cost_spiral(action_log, vitals, budget_health)
        if msg:
            candidates.append(msg)

        msg = self._check_blind_edit(action_log, current_tool, current_input)
        if msg:
            candidates.append(msg)

        msg = self._check_bash_error_streak(action_log, current_tool)
        if msg:
            candidates.append(msg)

        msg = self._check_bash_retry(action_log, current_tool)
        if msg:
            candidates.append(msg)

        msg = self._check_error_cascade(action_log)
        if msg:
            candidates.append(msg)

        msg = self._check_budget(budget_health)
        if msg:
            candidates.append(msg)

        # context + entropy_drop resurrected 2026-04-30. Both ship as
        # ``collecting`` — A/B harness runs from zero and the public
        # README does not credit them with verdicts until pairs cross
        # MIN_PAIRS. Resurrection rationale documented in CHANGELOG.
        msg = self._check_context_window(vitals)
        if msg:
            candidates.append(msg)

        msg = self._check_entropy_drop(action_log)
        if msg:
            candidates.append(msg)

        # drift resurrected 2026-04-30 — restored detector body from the
        # pre-retire history (commit a673e67~1) with the original
        # signal/threshold and tool-shift heuristic. Status: collecting.
        msg = self._check_drift(action_log, vitals)
        if msg:
            candidates.append(msg)

        if not candidates:
            return None

        # Filter by cooldown
        active = [
            c for c in candidates
            if not self._in_cooldown(c.pattern, action_number)
        ]
        # Adaptive-phase auto-silence — patterns with <20% helped over
        # their last 20+ fires drop out for this family until precision
        # climbs back above 40%.
        if self._profile is not None:
            forced = _forced_patterns()
            active = [
                c for c in active
                if c.pattern in forced or not self._profile.should_silence(c.pattern)
            ]
            # Auto-retire (P1.1): a pattern refuted by A/B validation
            # stays silenced in every phase unless SOMA_FORCE_PATTERN
            # opts it back in for debugging/override.
            active = [
                c for c in active
                if c.pattern in forced or not self._profile.is_refuted(c.pattern)
            ]
            # Skeptic mode (P2.3): SOMA_SKEPTIC=1 narrows guidance to
            # patterns A/B validation has confirmed. Everything else —
            # including untested and inconclusive patterns — is silenced
            # unless SOMA_FORCE_PATTERN overrides.
            if _skeptic_mode():
                active = [
                    c for c in active
                    if c.pattern in forced or self._profile.is_validated(c.pattern)
                ]
        if not active:
            return None

        # Pick highest severity, break ties by pattern priority
        best = max(active, key=lambda m: (_SEVERITY_ORDER.get(m.severity, 0), _PATTERN_PRIORITY.get(m.pattern, 0)))

        # Record cooldown
        self._last_fired[best.pattern] = action_number

        return best

    def _in_cooldown(self, pattern: str, action_number: int) -> bool:
        last = self._last_fired.get(pattern)
        if last is None:
            return False
        return (action_number - last) < self._cooldown_actions

    # ── Pattern 1: Blind Edit ──

    def _check_blind_edit(
        self, action_log: list[dict], current_tool: str, current_input: dict,
    ) -> GuidanceMessage | None:
        # 2026-04-19 — narrowed to Write / NotebookEdit only. Claude Code
        # already forces a Read before Edit, so firing on Edit produced
        # a stream of 0%-helped duplicates (47% "helped" in analytics
        # was almost entirely noise from the built-in guard). Write +
        # NotebookEdit are the tools that actually *can* run blindly.
        if current_tool not in ("Write", "NotebookEdit"):
            return None

        file_path = ""
        if isinstance(current_input, dict):
            file_path = current_input.get("file_path", "") or current_input.get("path", "")
        if not file_path:
            return None

        # Write to a non-existing file is a create, not a blind edit — skip.
        # Audit data shows 0% helped on these because there is nothing to read.
        if current_tool == "Write":
            try:
                import os as _os
                if not _os.path.exists(file_path):
                    return None
            except Exception:
                pass

        # Check if this file was read recently
        read_files: set[str] = set()
        for entry in action_log[-20:]:
            if entry.get("tool") in ("Read", "Grep", "Glob"):
                f = entry.get("file", "")
                if f:
                    read_files.add(f)

        if file_path in read_files:
            return None

        short = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
        reads = _recent_reads(action_log)
        reads_str = ", ".join(reads[:3]) if reads else "none"

        snippet = _read_file_snippet(file_path)
        if snippet:
            message = (
                f"[SOMA] You're editing {short} without reading it first. "
                f"Here's the current content:\n{snippet}\n"
                f"Review before editing."
            )
        else:
            message = (
                f"[SOMA] You're editing {short} without reading it first. "
                f"Last read files: {reads_str}. Consider reading {short} to check current state."
            )

        return GuidanceMessage(
            pattern="blind_edit",
            severity="warn",
            message=message,
            evidence=(f"Edit to {short} with no prior Read",),
            suggestion=f"Read {short} before editing",
        )

    # ── Pattern 2: Retry Storm ──

    # ── Pattern 3: Error Cascade ──

    def _check_error_cascade(
        self, action_log: list[dict],
    ) -> GuidanceMessage | None:
        if len(action_log) < 3:
            return None

        # Count consecutive errors from the end
        consecutive = 0
        error_tools: list[str] = []
        for entry in reversed(action_log[-10:]):
            if entry.get("error"):
                consecutive += 1
                error_tools.append(entry.get("tool", "?"))
            else:
                break

        # Personal streak threshold if a calibrated profile is attached;
        # legacy hardcode otherwise. Profile returns max(typical+1, 3).
        streak_floor = (
            self._profile.error_cascade_streak()
            if (self._profile is not None and not self._profile.is_warmup())
            else 3
        )
        if consecutive < streak_floor:
            return None

        # If we have a baseline and this error rate is within normal range, suppress
        if self._baseline and self._baseline.get_count("error_rate") >= 3:
            recent_len = len(action_log[-10:])
            error_rate = consecutive / recent_len if recent_len else 0
            baseline_er = self._baseline.get("error_rate")
            baseline_std = self._baseline.get_std("error_rate")
            # Only fire if current error rate is >1.5 std above baseline
            if error_rate < baseline_er + 1.5 * baseline_std:
                return None

        last_error = _last_error_line(action_log)
        error_preview = last_error[:100] if last_error else "multiple tool failures"

        # Summarize error pattern
        from collections import Counter
        tool_counts = Counter(error_tools)
        pattern_parts = [f"{t}×{c}" for t, c in tool_counts.most_common(3)]
        pattern_summary = ", ".join(pattern_parts)

        dominant_tool = tool_counts.most_common(1)[0][0] if tool_counts else "Bash"
        heal = _healing_suggestion(dominant_tool)
        # 2026-04-19 — data-driven suggestion. The healing evidence is
        # already baked into `_healing_suggestion`'s string, so the
        # rendered tip now carries the agent's own analytics numbers
        # when available.
        suggestion = f"step back and try {heal}"
        if tool_counts.get("Bash", 0) >= 2:
            suggestion = f"stop running Bash — {heal}"
        elif tool_counts.get("Edit", 0) >= 2:
            suggestion = f"read the files you're editing — {heal}"

        return GuidanceMessage(
            pattern="error_cascade",
            severity="critical" if consecutive >= 5 else "warn",
            message=(
                f"[SOMA] {consecutive} consecutive errors on {pattern_summary}. "
                f'Last error: "{error_preview}". '
                f"Historical data says {heal} — "
                f"write a minimal reproduction or read the relevant file before retrying."
            ),
            evidence=tuple(
                f"{t} error" for t in error_tools[:3]
            ),
            suggestion=suggestion,
        )

    # ── Pattern 4: Budget Warning ──

    def _check_budget(self, budget_health: float) -> GuidanceMessage | None:
        if budget_health >= 0.2:
            return None

        pct = int(budget_health * 100)
        severity = "critical" if budget_health < 0.05 else "warn"

        return GuidanceMessage(
            pattern="budget",
            severity=severity,
            message=(
                f"[SOMA] {pct}% of token budget remaining. "
                f"Consider wrapping up current task and committing progress."
            ),
            evidence=(f"Budget at {pct}%",),
            suggestion="wrap up current task, commit progress",
        )

    # ── Pattern 5: Context Window Warning ──

    def _check_context_window(self, vitals: dict) -> GuidanceMessage | None:
        token_usage = vitals.get("token_usage", 0) or vitals.get("context_usage", 0)
        # 2026-04-19 — fire at 60% instead of 80%. Firing at 80% in the
        # old measurement left no time to wrap up coherently; the
        # dataset showed pressure *rising* after the message, which
        # means it arrived too late for anyone to act on. 60% gives
        # ~20% of the window to land a summary + commit.
        if token_usage < 0.6:
            return None

        pct = int(token_usage * 100)
        # Critical only after we're actually near the wall. Between
        # 60-80% stays "warn".
        severity = "critical" if token_usage > 0.9 else "warn"

        return GuidanceMessage(
            pattern="context",
            severity=severity,
            message=(
                f"[SOMA] Long session detected ({pct}% context used). Wrap up now: "
                "commit progress, write a 2-sentence summary in NEXT.md for the next "
                "session to pick up, and avoid starting new refactors. "
                "The /compact command is user-initiated — you can't run it, but you "
                "can make the handoff clean."
            ),
            evidence=(f"Context at {pct}%",),
            suggestion="commit progress, write NEXT.md handoff summary, finish current task",
        )

    # ── Pattern 6: Drift Detection ──

    # ── Pattern 7: Cost Spiral ──

    def _check_cost_spiral(
        self, action_log: list[dict], vitals: dict, budget_health: float,
    ) -> GuidanceMessage | None:
        if len(action_log) < 5:
            return None

        # Need: 5+ errors in last 8 actions AND (high token usage OR low budget)
        recent = action_log[-8:]
        error_count = sum(1 for e in recent if e.get("error"))
        if error_count < 5:
            return None

        token_usage = vitals.get("token_usage", 0) or vitals.get("context_usage", 0)
        if token_usage < 0.5 and budget_health > 0.4:
            return None  # Not expensive enough to warn

        pct_budget = int(budget_health * 100)
        pct_context = int(token_usage * 100)

        return GuidanceMessage(
            pattern="cost_spiral",
            severity="critical",
            message=(
                f"[SOMA] {error_count} errors in last {len(recent)} actions while "
                f"using {pct_context}% context and {pct_budget}% budget remaining. "
                f"You're burning tokens on a retry loop. "
                f"Consider: use a cheaper model (Haiku) for debugging this issue, "
                f"then switch back once you understand the problem."
            ),
            evidence=(f"{error_count} errors, {pct_context}% context, {pct_budget}% budget",),
            suggestion="switch to cheaper model for debug phase",
        )

    # ── Pattern 8: Entropy Drop ──

    def _check_entropy_drop(
        self, action_log: list[dict],
    ) -> GuidanceMessage | None:
        if len(action_log) < 8:
            return None

        entropy = _compute_tool_entropy(action_log)
        # Personal floor: the pattern should only fire when entropy drops
        # *below this user's normal low* — we use the user's P25 (their
        # own baseline of low-diversity behavior) clamped into [0.5, 1.0].
        # Clamp upper bound to the legacy 1.0 so diverse users can't make
        # the pattern more aggressive; clamp lower bound to 0.5 so users
        # with extremely focused workflows never silence it entirely.
        if (self._profile is not None and not self._profile.is_warmup()
                and self._profile.entropy_p25 > 0):
            entropy_ceiling = max(0.5, min(self._profile.entropy_p25, 1.0))
        else:
            entropy_ceiling = 1.0
        if entropy >= entropy_ceiling:
            return None  # Healthy diversity for this user

        # Identify the dominant tool
        from collections import Counter
        recent = action_log[-10:]
        tools = Counter(e.get("tool", "?") for e in recent)
        dominant = tools.most_common(1)[0][0]
        pct = tools[dominant] * 100 // len(recent)

        severity = "critical" if entropy < 0.5 else "warn"
        # NOTE: previous implementation escalated to "critical" when
        # ``avg_gap < 3.0`` seconds — a hardcoded threshold that fired on
        # healthy fast Read/Glob exploration loops, which was the false-
        # positive that triggered the 2026-04-25 retirement. Velocity
        # escalation removed; severity is now driven by entropy alone.

        return GuidanceMessage(
            pattern="entropy_drop",
            severity=severity,
            message=(
                f"[SOMA] Tool tunnel vision: {pct}% of last {len(recent)} actions used {dominant}. "
                f"Diverse tool usage correlates with success. "
                f"Consider: Read files for context, Grep to search, or rethink your approach."
            ),
            evidence=(f"Tool entropy {entropy:.2f}, {dominant} at {pct}%",),
            suggestion=f"diversify — use Read or Grep before continuing with {dominant}",
        )

    # ── Pattern 9: Drift (resurrected 2026-04-30) ──

    def _check_drift(
        self, action_log: list[dict], vitals: dict,
    ) -> GuidanceMessage | None:
        """Tool-shift drift detector.

        Restored 2026-04-30 from commit ``a673e67~1`` with no behavior
        change. The 9-firing / 0%-helped window that drove the original
        retirement was statistically too small for a verdict, and the
        underlying ``drift`` signal still feeds the pressure aggregator
        — emitting guidance again gives us A/B data to make a real call.

        Fires when ``vitals.drift > 0.5`` and the dominant tool in the
        first 5 actions differs from the dominant tool in the last 5.
        Drift signal is high but tools haven't shifted → silent (we'd be
        emitting vague advice we can't action on).
        """
        drift_threshold = 0.5
        if (
            self._profile is not None
            and not self._profile.is_warmup()
        ):
            drift_threshold = self._profile.drift_threshold()
        drift = vitals.get("drift", 0)
        if drift < drift_threshold:
            return None

        if len(action_log) < 10:
            return None

        early = action_log[:5]
        recent = action_log[-5:]

        from collections import Counter
        early_tools = Counter(e.get("tool", "?") for e in early)
        recent_tools = Counter(e.get("tool", "?") for e in recent)

        initial = early_tools.most_common(1)[0][0] if early_tools else "?"
        current = recent_tools.most_common(1)[0][0] if recent_tools else "?"

        if initial == current:
            # Drift signal is high but the dominant tool hasn't shifted
            # — the source is *within-tool* behavior change (args, file
            # paths, operation type). There's no actionable advice we
            # can prescribe here, so stay silent rather than emitting
            # vague "use a different tool" copy. This early-return is
            # the original 2026-04-18 semantics and is the reason the
            # mode-blind ``most_common(1)`` view is acceptable.
            return None

        return GuidanceMessage(
            pattern="drift",
            severity="warn",
            message=(
                f"[SOMA] You started with mostly {initial} but shifted to {current}. "
                f"Re-read the original task spec or grep for the main keyword to refocus."
            ),
            evidence=(f"Tool shift: {initial} → {current}",),
            suggestion="Read or Grep the original task spec",
        )

    # ── Pattern 10: Bash Retry Intercept ──

    def _check_bash_error_streak(
        self, action_log: list[dict], current_tool: str,
    ) -> GuidanceMessage | None:
        """P2.1: intercept a 3rd Bash when the last two Bash calls both errored.

        Grounded in 1,566 production cases where the Bash→Bash→Bash
        sequence failed 100% of the time. Shipped at severity=warn
        (OBSERVE mode) until its own 30/30 A/B pairs validate the
        effect — then promoted to strict-block via _STRICT_BLOCK_PATTERNS.
        """
        if current_tool != "Bash":
            return None
        if len(action_log) < 2:
            return None
        last = action_log[-1]
        prev = action_log[-2]
        if last.get("tool") != "Bash" or not last.get("error"):
            return None
        if prev.get("tool") != "Bash" or not prev.get("error"):
            return None

        # Yield to error_cascade once the streak crosses into runaway
        # territory — that pattern has its own escalation copy.
        consecutive_any = 0
        for entry in reversed(action_log):
            if entry.get("error"):
                consecutive_any += 1
            else:
                break
        if consecutive_any >= 3:
            return None

        return GuidanceMessage(
            pattern="bash_error_streak",
            severity="warn",
            message=(
                "[SOMA] 2 consecutive Bash failures. Production data shows "
                "a 3rd Bash fails 100% of the time (n=1566). Read the error "
                "or inspect the failing file before retrying."
            ),
            evidence=(
                "prev-2 tool=Bash error=True",
                "prev-1 tool=Bash error=True",
                "historical fail rate 100% over 1566 cases",
            ),
            suggestion="Read the file that's failing, or check error output line-by-line",
        )

    def _check_bash_retry(
        self, action_log: list[dict], current_tool: str,
    ) -> GuidanceMessage | None:
        if current_tool != "Bash":
            return None
        if not action_log:
            return None

        # Check if last action was a failed Bash
        last = action_log[-1]
        if last.get("tool") != "Bash" or not last.get("error"):
            return None

        # Don't fire if already in error_cascade territory (3+ consecutive errors)
        consecutive_any = 0
        for entry in reversed(action_log):
            if entry.get("error"):
                consecutive_any += 1
            else:
                break
        if consecutive_any >= 3:
            return None  # Let error_cascade handle this

        error_text = last.get("output", "") or "command failed"
        error_preview = str(error_text)[:80]
        heal = _healing_suggestion("Bash")

        return GuidanceMessage(
            pattern="bash_retry",
            severity="warn",
            message=(
                f'[SOMA] Bash just failed: "{error_preview}". '
                f"Running another Bash without reading the error rarely helps. "
                f"Your analytics: {heal} — prefer writing a minimal reproduction "
                "or reading the failing file over re-running the same command."
            ),
            evidence=("Bash error, next action = Bash retry",),
            suggestion=heal,
        )
