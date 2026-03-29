"""SOMA Quality Scoring — rate output quality, not just behavioral signals.

Tracks quality signals per session:
- Syntax errors caught by post-write validation
- Lint issues caught by ruff
- Bash command failures (agent's commands don't work)
- Edit success rate (edits that don't break things)

Produces a quality score [0, 1] that feeds into the SOMA notification
as a human-readable quality grade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QualityReport:
    """Session quality summary."""
    score: float  # 0-1 overall quality
    grade: str  # A, B, C, D, F
    syntax_errors: int
    lint_issues: int
    bash_failures: int
    total_writes: int
    total_bashes: int
    issues: list[str] = field(default_factory=list)  # Human-readable issues


class QualityTracker:
    """Tracks code quality signals during a session.

    Fed by post_tool_use validation results. Produces a rolling
    quality score that tells you "is this agent writing good code?"
    """

    def __init__(self, window: int = 30) -> None:
        self._window = window
        # Rolling window: list of (type, ok, flags) tuples
        # flags: {"syntax": bool, "lint": bool} for writes, empty for bash
        self._events: list[tuple[str, bool, dict]] = []

    def record_write(self, had_syntax_error: bool = False, had_lint_issue: bool = False) -> None:
        """Record a Write/Edit action and its validation result."""
        ok = not had_syntax_error and not had_lint_issue
        self._events.append(("write", ok, {"syntax": had_syntax_error, "lint": had_lint_issue}))
        self._trim()

    def record_bash(self, error: bool = False) -> None:
        """Record a Bash action and whether it failed."""
        self._events.append(("bash", not error, {}))
        self._trim()

    def _trim(self) -> None:
        """Keep only last N events."""
        if len(self._events) > self._window:
            self._events = self._events[-self._window:]

    def get_report(self) -> QualityReport:
        """Generate quality report from rolling window."""
        writes = [(t, ok, f) for t, ok, f in self._events if t == "write"]
        bashes = [(t, ok, f) for t, ok, f in self._events if t == "bash"]

        write_total = len(writes)
        write_clean = sum(1 for _, ok, _ in writes if ok)
        bash_total = len(bashes)
        bash_failures = sum(1 for _, ok, _ in bashes if not ok)

        # Count errors from the rolling window, not a monotonic accumulator
        syntax_errors = sum(1 for _, _, f in writes if f.get("syntax"))
        lint_issues = sum(1 for _, _, f in writes if f.get("lint"))

        write_score = write_clean / write_total if write_total > 0 else 1.0
        bash_score = 1.0 - (bash_failures / bash_total) if bash_total > 0 else 1.0

        total = write_total + bash_total
        if total == 0:
            score = 1.0
        else:
            w_write = write_total / total
            w_bash = bash_total / total
            score = w_write * write_score + w_bash * bash_score

        # Penalty for syntax errors
        if syntax_errors > 0:
            score *= max(0.5, 1.0 - syntax_errors * 0.15)

        score = max(0.0, min(1.0, score))
        grade = _score_to_grade(score)

        issues = []
        if syntax_errors > 0:
            issues.append(f"{syntax_errors} syntax error{'s' if syntax_errors > 1 else ''}")
        if lint_issues > 0:
            issues.append(f"{lint_issues} lint issue{'s' if lint_issues > 1 else ''}")
        if bash_total > 0 and bash_failures / bash_total > 0.3:
            issues.append(f"{bash_failures}/{bash_total} bash commands failed")

        return QualityReport(
            score=score,
            grade=grade,
            syntax_errors=syntax_errors,
            lint_issues=lint_issues,
            bash_failures=bash_failures,
            total_writes=write_total,
            total_bashes=bash_total,
            issues=issues,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": self._events,
            "window": self._window,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityTracker":
        window = data.get("window", 30)
        obj = cls(window=window)
        raw_events = data.get("events", [])
        # Migrate old format: (type, ok) → (type, ok, {})
        migrated = []
        for ev in raw_events:
            if len(ev) == 2:
                migrated.append((ev[0], ev[1], {}))
            else:
                migrated.append((ev[0], ev[1], ev[2] if ev[2] else {}))
        obj._events = migrated
        return obj


def _score_to_grade(score: float) -> str:
    if score >= 0.9:
        return "A"
    if score >= 0.8:
        return "B"
    if score >= 0.7:
        return "C"
    if score >= 0.5:
        return "D"
    return "F"
