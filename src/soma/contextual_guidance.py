"""SOMA Contextual Guidance — pattern-based actionable messages.

Replaces abstract pressure-based guidance with specific, evidence-cited
messages that tell the agent what happened, why it matters, and what to do.

Every message contains:
1. What happened — cites specific actions/errors from action_log
2. Why it matters — the concrete risk
3. What to do next — a specific actionable suggestion
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuidanceMessage:
    """A contextual guidance message with evidence."""

    pattern: str  # "blind_edit", "retry_storm", "error_cascade", "budget", "context", "drift"
    severity: str  # "info", "warn", "critical"
    message: str  # Full contextual message for the agent
    evidence: tuple[str, ...] = ()  # Specific actions/errors that triggered this
    suggestion: str = ""  # The actionable next step


# Severity ordering for comparison
_SEVERITY_ORDER = {"info": 0, "warn": 1, "critical": 2}

# Pattern priority within same severity (higher = wins ties)
_PATTERN_PRIORITY = {"cost_spiral": 10, "budget": 5, "bash_retry": 4, "error_cascade": 2, "entropy_drop": 1, "blind_edit": 1, "context": 1}

# Canonical list of pattern keys that real production guidance paths emit.
# Dashboard ROI whitelisting and any future analytics filter should import
# this tuple rather than re-declare the set — single source of truth.
# `_stats` is the aggregate row written by the analytics recorder.
REAL_PATTERN_KEYS: tuple[str, ...] = tuple(_PATTERN_PRIORITY.keys()) + ("_stats",)

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


# Data-backed healing transitions from production actions
_HEALING_TRANSITIONS: dict[str, tuple[str, str]] = {
    "Bash": ("Read", "Bash→Read reduces pressure by 7%"),
    "Edit": ("Read", "Edit→Read reduces pressure by 5%"),
    "Write": ("Grep", "Write→Grep reduces pressure by 5%"),
}


def _healing_suggestion(failing_tool: str) -> str:
    """Suggest a healing tool transition based on production data."""
    if failing_tool in _HEALING_TRANSITIONS:
        heal_tool, evidence = _HEALING_TRANSITIONS[failing_tool]
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


def check_followthrough(
    pending: dict,
    tool_name: str,
    tool_input: dict,
    file_path: str,
    error: bool,
    pressure_after: float | None = None,
) -> bool | None:
    """Check if the agent followed contextual guidance.

    Returns True if followed, False if ignored, None if inconclusive (keep waiting).

    When `pressure_after` is provided, patterns without explicit followthrough
    semantics (drift, cost_spiral, context, budget, error_cascade) resolve via
    pressure delta: a drop of >=15% = True, a non-drop after 2 actions = False.
    """
    pattern = pending.get("pattern", "")
    actions_since = pending.get("actions_since", 0) + 1

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
        # Did they read the file?
        suggested_file = pending.get("file", "")
        if tool_name in ("Read", "Grep", "Glob"):
            if not suggested_file or file_path == suggested_file:
                return True
        if tool_name in ("Edit", "Write"):
            return False  # Edited again without reading
        return None  # Still waiting

    if pattern == "error_cascade":
        if not error:
            return True  # Next action succeeded
        return _resolve_via_pressure(pressure_delta, actions_since)

    if pattern == "context":
        # Did they compact/summarize?
        if tool_name in ("Bash",) and isinstance(tool_input, dict):
            cmd = tool_input.get("command", "")
            if "compact" in cmd.lower() or "summarize" in cmd.lower():
                return True
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
        # Did they diversify tools?
        failing_tool = pending.get("tool", "")
        if tool_name != failing_tool:
            return True  # Switched to different tool — good
        if actions_since >= 3:
            return False  # Still monotool after 3 actions — ignored
        return None

    if pattern == "bash_retry":
        # Did they stop retrying Bash?
        if tool_name != "Bash":
            return True  # Good — switched away
        if tool_name == "Bash" and not error:
            return True  # Bash succeeded
        if tool_name == "Bash" and error:
            return False  # Still retrying
        return None

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

        msg = self._check_bash_retry(action_log, current_tool)
        if msg:
            candidates.append(msg)

        msg = self._check_error_cascade(action_log)
        if msg:
            candidates.append(msg)

        msg = self._check_budget(budget_health)
        if msg:
            candidates.append(msg)

        msg = self._check_context_window(vitals)
        if msg:
            candidates.append(msg)

        msg = self._check_entropy_drop(action_log)
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
            active = [c for c in active if not self._profile.should_silence(c.pattern)]
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
        if current_tool not in ("Edit", "Write", "NotebookEdit"):
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

        if consecutive < 3:
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
        suggestion = f"step back and try {heal}"
        if tool_counts.get("Bash", 0) >= 2:
            suggestion = f"stop running commands — {heal}"
        elif tool_counts.get("Edit", 0) >= 2:
            suggestion = f"read the files you're editing — {heal}"

        return GuidanceMessage(
            pattern="error_cascade",
            severity="critical" if consecutive >= 5 else "warn",
            message=(
                f"[SOMA] {consecutive} errors in a row. "
                f'Last error: "{error_preview}". '
                f"Pattern: {pattern_summary}. Suggestion: {suggestion}."
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
        if token_usage < 0.8:
            return None

        pct = int(token_usage * 100)
        severity = "critical" if token_usage > 0.95 else "warn"

        return GuidanceMessage(
            pattern="context",
            severity=severity,
            message=(
                f"[SOMA] Context window is {pct}% full. "
                f"Consider compacting or summarizing before continuing."
            ),
            evidence=(f"Context at {pct}%",),
            suggestion="compact conversation or start a new context",
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
        if entropy >= 1.0:
            return None  # Healthy diversity

        # Identify the dominant tool
        from collections import Counter
        recent = action_log[-10:]
        tools = Counter(e.get("tool", "?") for e in recent)
        dominant = tools.most_common(1)[0][0]
        pct = tools[dominant] * 100 // len(recent)

        severity = "critical" if entropy < 0.5 else "warn"

        # Panic detection: low entropy + high velocity = critical
        recent_ts = [e.get("ts", 0) for e in recent if e.get("ts")]
        if len(recent_ts) >= 3:
            gaps = [recent_ts[i] - recent_ts[i - 1] for i in range(1, len(recent_ts)) if recent_ts[i - 1] > 0]
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                if avg_gap < 3.0:  # Less than 3 seconds between actions
                    severity = "critical"  # Panic: monotool + fast = disaster

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

    # ── Pattern 9: Bash Retry Intercept ──

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
                f"Running another Bash without reading the error won't help. "
                f"Try: {heal}."
            ),
            evidence=("Bash error, next action = Bash retry",),
            suggestion=heal,
        )
