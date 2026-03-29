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

    def __init__(self) -> None:
        self._syntax_errors: int = 0
        self._lint_issues: int = 0
        self._bash_failures: int = 0
        self._bash_total: int = 0
        self._write_total: int = 0
        self._write_clean: int = 0  # Writes with no syntax/lint issues

    def record_write(self, had_syntax_error: bool = False, had_lint_issue: bool = False) -> None:
        """Record a Write/Edit action and its validation result."""
        self._write_total += 1
        if had_syntax_error:
            self._syntax_errors += 1
        if had_lint_issue:
            self._lint_issues += 1
        if not had_syntax_error and not had_lint_issue:
            self._write_clean += 1

    def record_bash(self, error: bool = False) -> None:
        """Record a Bash action and whether it failed."""
        self._bash_total += 1
        if error:
            self._bash_failures += 1

    def get_report(self) -> QualityReport:
        """Generate quality report for current session."""
        # Compute component scores
        write_score = self._write_clean / self._write_total if self._write_total > 0 else 1.0
        bash_score = 1.0 - (self._bash_failures / self._bash_total) if self._bash_total > 0 else 1.0

        # Weighted average: writes matter more than bash
        if self._write_total + self._bash_total == 0:
            score = 1.0
        else:
            w_write = self._write_total / (self._write_total + self._bash_total)
            w_bash = self._bash_total / (self._write_total + self._bash_total)
            score = w_write * write_score + w_bash * bash_score

        # Penalty for syntax errors (these are bad)
        if self._syntax_errors > 0:
            score *= max(0.5, 1.0 - self._syntax_errors * 0.15)

        score = max(0.0, min(1.0, score))

        # Grade
        grade = _score_to_grade(score)

        # Issues
        issues = []
        if self._syntax_errors > 0:
            issues.append(f"{self._syntax_errors} syntax error{'s' if self._syntax_errors > 1 else ''}")
        if self._lint_issues > 0:
            issues.append(f"{self._lint_issues} lint issue{'s' if self._lint_issues > 1 else ''}")
        if self._bash_total > 0 and self._bash_failures / self._bash_total > 0.3:
            issues.append(f"{self._bash_failures}/{self._bash_total} bash commands failed")

        return QualityReport(
            score=score,
            grade=grade,
            syntax_errors=self._syntax_errors,
            lint_issues=self._lint_issues,
            bash_failures=self._bash_failures,
            total_writes=self._write_total,
            total_bashes=self._bash_total,
            issues=issues,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "syntax_errors": self._syntax_errors,
            "lint_issues": self._lint_issues,
            "bash_failures": self._bash_failures,
            "bash_total": self._bash_total,
            "write_total": self._write_total,
            "write_clean": self._write_clean,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityTracker":
        obj = cls()
        obj._syntax_errors = data.get("syntax_errors", 0)
        obj._lint_issues = data.get("lint_issues", 0)
        obj._bash_failures = data.get("bash_failures", 0)
        obj._bash_total = data.get("bash_total", 0)
        obj._write_total = data.get("write_total", 0)
        obj._write_clean = data.get("write_clean", 0)
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
