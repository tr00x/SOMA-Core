"""SOMA Guidance Engine — the decision point.

Replaces the old Ladder-based blocking system with gradient response.
SOMA observes, suggests, warns — and only blocks truly destructive operations.

Response modes:
    OBSERVE  (p=0-25%):  Silent. Metrics only.
    GUIDE    (p=25-50%): Soft suggestions when patterns detected. Never blocks.
    WARN     (p=50-75%): Insistent warnings + alternatives. Never blocks.
    BLOCK    (p=75-100%): Blocks ONLY destructive operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from soma.types import ResponseMode


@dataclass(frozen=True, slots=True)
class GuidanceResponse:
    """Result of a guidance evaluation."""
    mode: ResponseMode
    allow: bool
    message: str | None = None
    suggestions: list[str] = field(default_factory=list)


DESTRUCTIVE_BASH_PATTERNS = [
    re.compile(r"\brm\s+.*-[rf]*r[rf]*\b"),
    re.compile(r"\brm\s+--recursive\b"),
    re.compile(r"\brm\s+--force\b.*--recursive\b"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+push\s+.*(-f|--force)\b"),
    re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"),
    re.compile(r"\bgit\s+checkout\s+\.\s*$"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bkill\s+-9\b"),
]

SENSITIVE_FILE_PATTERNS = [
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)credentials"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"(^|/)secret"),
]


def is_destructive_bash(command: str) -> bool:
    """Check if a bash command is destructive."""
    return any(p.search(command) for p in DESTRUCTIVE_BASH_PATTERNS)


def is_sensitive_file(file_path: str) -> bool:
    """Check if a file path points to sensitive content."""
    return any(p.search(file_path) for p in SENSITIVE_FILE_PATTERNS)


DEFAULT_THRESHOLDS = {"guide": 0.25, "warn": 0.50, "block": 0.75}


def pressure_to_mode(
    pressure: float,
    thresholds: dict[str, float] | None = None,
) -> ResponseMode:
    """Map pressure to response mode using configurable thresholds."""
    t = thresholds or DEFAULT_THRESHOLDS
    if pressure >= t.get("block", 0.75):
        return ResponseMode.BLOCK
    if pressure >= t.get("warn", 0.50):
        return ResponseMode.WARN
    if pressure >= t.get("guide", 0.25):
        return ResponseMode.GUIDE
    return ResponseMode.OBSERVE


def _check_destructive(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """Check if this specific tool call is destructive."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if is_destructive_bash(cmd):
            return True, f"destructive command: {cmd[:80]}"

    if tool_name in ("Write", "Edit", "NotebookEdit"):
        fp = tool_input.get("file_path", "")
        if fp and is_sensitive_file(fp):
            short = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            return True, f"sensitive file: {short}"

    return False, ""


def _build_suggestions(tool_name: str, action_log: list[dict], gsd_active: bool = False) -> list[str]:
    """Build context-aware suggestions based on action patterns."""
    suggestions: list[str] = []
    if not action_log:
        return suggestions

    recent = action_log[-10:]

    # File thrashing
    if tool_name in ("Write", "Edit"):
        edit_files = [e["file"] for e in recent if e["tool"] in ("Write", "Edit") and e.get("file")]
        if edit_files:
            from collections import Counter
            counts = Counter(edit_files)
            for fname, count in counts.most_common(1):
                if count >= 3:
                    short = fname.rsplit("/", 1)[-1] if "/" in fname else fname
                    suggestions.append(f"you've edited {short} {count}x — consider collecting all changes first")

    # Consecutive bash failures
    consecutive_failures = 0
    for entry in reversed(recent):
        if entry["tool"] == "Bash" and entry.get("error"):
            consecutive_failures += 1
        elif entry["tool"] == "Bash":
            break
    if consecutive_failures >= 2:
        suggestions.append(f"{consecutive_failures} bash failures in a row — check assumptions before retrying")

    # Many agents — skip if GSD active (agent spawning is normal in workflows)
    if not gsd_active:
        agent_calls = sum(1 for e in recent if e["tool"] == "Agent")
        if agent_calls >= 3:
            suggestions.append(f"{agent_calls} agents spawned recently — check for file conflicts")

    return suggestions


def evaluate(
    pressure: float,
    tool_name: str,
    tool_input: dict,
    action_log: list[dict],
    gsd_active: bool = False,
    thresholds: dict[str, float] | None = None,
) -> GuidanceResponse:
    """Central guidance decision."""
    mode = pressure_to_mode(pressure, thresholds)

    if mode == ResponseMode.OBSERVE:
        return GuidanceResponse(mode=mode, allow=True)

    if mode == ResponseMode.BLOCK:
        is_destructive, reason = _check_destructive(tool_name, tool_input)
        if is_destructive:
            return GuidanceResponse(
                mode=mode,
                allow=False,
                message=f"SOMA blocked: {reason} (p={pressure:.0%})",
                suggestions=["pressure is very high — focus on safe, reversible actions"],
            )
        suggestions = _build_suggestions(tool_name, action_log, gsd_active)
        return GuidanceResponse(
            mode=mode,
            allow=True,
            message=f"SOMA warning: pressure at {pressure:.0%} — only destructive ops blocked",
            suggestions=suggestions,
        )

    if mode == ResponseMode.WARN:
        suggestions = _build_suggestions(tool_name, action_log, gsd_active)
        msg = None
        if suggestions:
            msg = f"SOMA warning (p={pressure:.0%}): {suggestions[0]}"
        else:
            msg = f"SOMA warning: pressure at {pressure:.0%} — slow down and verify"
        return GuidanceResponse(mode=mode, allow=True, message=msg, suggestions=suggestions)

    # GUIDE
    suggestions = _build_suggestions(tool_name, action_log, gsd_active)
    msg = None
    if suggestions:
        msg = f"SOMA suggestion: {suggestions[0]}"
    return GuidanceResponse(mode=mode, allow=True, message=msg, suggestions=suggestions)
