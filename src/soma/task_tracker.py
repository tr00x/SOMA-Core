"""SOMA Task Tracker — understand WHAT the agent is doing, not just HOW.

Infers the current task from tool usage patterns and file paths:
- File clustering: which files are being touched together
- Task phase detection: research → implement → test → debug
- Goal drift: when the agent starts touching unrelated files

This gives SOMA the ability to say "agent drifted from auth module to
unrelated config files" instead of just "drift=0.40".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskContext:
    """Inferred context about what the agent is working on."""
    phase: str  # "research", "implement", "test", "debug", "unknown"
    focus_files: list[str] = field(default_factory=list)  # files being worked on
    focus_dirs: list[str] = field(default_factory=list)  # directories being worked on
    scope_drift: float = 0.0  # 0-1, how much the agent has drifted from initial focus
    drift_explanation: str = ""


# Phase detection: map tool patterns to development phases
_PHASE_TOOLS = {
    "research": {"Read", "Grep", "Glob", "WebSearch", "WebFetch"},
    "implement": {"Write", "Edit", "NotebookEdit"},
    "test": {"Bash"},  # Bash is ambiguous but often testing
    "debug": set(),  # Detected by error patterns, not tool type
}


class TaskTracker:
    """Tracks what the agent is working on and detects scope drift.

    Feed it actions as they happen. It builds up a picture of:
    - Which files/directories the agent is focused on
    - What phase of work (research, implement, test, debug)
    - Whether the agent is drifting away from its initial focus
    """

    def __init__(self, drift_window: int = 10, cwd: str = "") -> None:
        self.drift_window = drift_window
        self.cwd = cwd
        self._all_files: list[str] = []
        self._all_tools: list[str] = []
        self._all_errors: list[bool] = []
        self._initial_focus: set[str] | None = None  # Set after first N actions

    def _extract_relative_dir(self, file_path: str) -> str:
        """Extract directory relative to cwd. If outside cwd, prefix with '!'."""
        if self.cwd and file_path.startswith(self.cwd):
            rel = file_path[len(self.cwd):].lstrip("/")
            parts = rel.split("/")
            return parts[0] if len(parts) > 1 else ""
        elif self.cwd:
            # Outside project — mark as external
            return "!" + _extract_dir(file_path)
        return _extract_dir(file_path)

    def record(self, tool: str, file_path: str = "", error: bool = False) -> None:
        """Record an action."""
        self._all_tools.append(tool)
        self._all_errors.append(error)
        if file_path:
            self._all_files.append(file_path)

        # Set initial focus after 5 file-touching actions
        if self._initial_focus is None:
            files_with_dirs = [self._extract_relative_dir(f) for f in self._all_files if f]
            if len(files_with_dirs) >= 5:
                self._initial_focus = set(files_with_dirs[:5])

    def get_context(self) -> TaskContext:
        """Analyze current state and return task context."""
        phase = self._detect_phase()
        focus_files = self._get_focus_files()
        focus_dirs = self._get_focus_dirs()
        scope_drift, drift_explanation = self._compute_scope_drift()

        return TaskContext(
            phase=phase,
            focus_files=focus_files,
            focus_dirs=focus_dirs,
            scope_drift=scope_drift,
            drift_explanation=drift_explanation,
        )

    def _detect_phase(self) -> str:
        """Detect current development phase from recent tool usage."""
        if not self._all_tools:
            return "unknown"

        recent = self._all_tools[-self.drift_window:]
        recent_errors = self._all_errors[-self.drift_window:]

        # Debug: high error rate
        error_count = sum(1 for e in recent_errors if e)
        if len(recent) >= 3 and error_count / len(recent) > 0.3:
            return "debug"

        # Count tools by phase
        phase_scores: dict[str, int] = {
            "research": 0, "implement": 0, "test": 0,
        }
        for tool in recent:
            for phase, tools in _PHASE_TOOLS.items():
                if phase == "debug":
                    continue
                if tool in tools:
                    phase_scores[phase] += 1

        if not any(phase_scores.values()):
            return "unknown"

        return max(phase_scores, key=phase_scores.get)

    def _get_focus_files(self, n: int = 5) -> list[str]:
        """Get the N most recently touched files (deduplicated)."""
        seen = set()
        result = []
        for f in reversed(self._all_files):
            short = f.rsplit("/", 1)[-1]
            if short not in seen:
                seen.add(short)
                result.append(short)
                if len(result) >= n:
                    break
        return result

    def _get_focus_dirs(self, n: int = 3) -> list[str]:
        """Get the N most common directories from recent files."""
        if not self._all_files:
            return []

        recent_files = self._all_files[-self.drift_window:]
        dir_counts: dict[str, int] = {}
        for f in recent_files:
            d = self._extract_relative_dir(f)
            if d:
                dir_counts[d] = dir_counts.get(d, 0) + 1

        sorted_dirs = sorted(dir_counts.items(), key=lambda x: -x[1])
        return [d for d, _ in sorted_dirs[:n]]

    def _compute_scope_drift(self) -> tuple[float, str]:
        """Compute how much the agent has drifted from its initial focus.

        Returns (drift_score, explanation).
        When cwd is set, moving between directories within the project is
        penalized much less than leaving the project entirely.
        """
        if self._initial_focus is None or len(self._all_files) < 20:
            return 0.0, ""

        recent_dirs = set(
            self._extract_relative_dir(f) for f in self._all_files[-self.drift_window:] if f
        )

        if not recent_dirs:
            return 0.0, ""

        overlap = recent_dirs & self._initial_focus
        new_dirs = recent_dirs - self._initial_focus

        if not new_dirs:
            return 0.0, ""

        # When cwd is set, distinguish in-project dirs from external dirs
        if self.cwd:
            external = {d for d in new_dirs if d.startswith("!")}
            internal = new_dirs - external

            # External dirs get full drift, internal dirs get 0.2x weight
            external_drift = len(external) / len(recent_dirs)
            internal_drift = len(internal) / len(recent_dirs) * 0.2
            drift = external_drift + internal_drift
        else:
            drift = 1.0 - len(overlap) / len(recent_dirs)

        if drift < 0.5:
            return drift, ""

        if new_dirs:
            display_dirs = sorted(d.lstrip("!") for d in new_dirs)
            return drift, f"scope expanded to {', '.join(display_dirs[:3])}"

        return drift, "working in different area than initial focus"

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_window": self.drift_window,
            "cwd": self.cwd,
            "all_files": self._all_files[-50:],  # Keep last 50
            "all_tools": self._all_tools[-50:],
            "all_errors": self._all_errors[-50:],
            "initial_focus": list(self._initial_focus) if self._initial_focus else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskTracker":
        obj = cls(drift_window=data.get("drift_window", 10), cwd=data.get("cwd", ""))
        obj._all_files = data.get("all_files", [])
        obj._all_tools = data.get("all_tools", [])
        obj._all_errors = data.get("all_errors", [])
        focus = data.get("initial_focus")
        obj._initial_focus = set(focus) if focus else None
        return obj


def _extract_dir(file_path: str) -> str:
    """Extract the parent directory from a file path."""
    if "/" not in file_path:
        return ""
    parts = file_path.rsplit("/", 1)
    return parts[0].rsplit("/", 1)[-1] if "/" in parts[0] else parts[0]
