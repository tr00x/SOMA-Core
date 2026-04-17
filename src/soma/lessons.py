"""Cross-session lesson memory — SOMA remembers error→fix patterns."""

from __future__ import annotations

import json
import time
from pathlib import Path


class LessonStore:
    """Persisted store of error→fix lessons learned across sessions."""

    def __init__(self, path: Path | None = None, max_lessons: int = 100):
        self._path = path or (Path.home() / ".soma" / "lessons.json")
        self._max_lessons = max_lessons
        self._lessons: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._lessons = json.loads(self._path.read_text())
        except Exception:
            self._lessons = []

    def _save(self) -> None:
        import os
        import tempfile
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._lessons, f, indent=2)
                os.replace(tmp, str(self._path))
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        except Exception:
            pass

    def record(self, pattern: str, error_text: str, fix_text: str, tool: str = "") -> None:
        """Record a lesson: this error was fixed by this action."""
        self._lessons.append({
            "pattern": pattern,
            "error": error_text[:200],
            "fix": fix_text[:200],
            "tool": tool,
            "ts": time.time(),
        })
        if len(self._lessons) > self._max_lessons:
            self._lessons = self._lessons[-self._max_lessons:]
        self._save()

    def query(self, error_text: str, tool: str = "", max_results: int = 3) -> list[dict]:
        """Find lessons matching an error. Simple keyword overlap."""
        error_lower = error_text.lower()
        error_words = set(error_lower.split())
        scored: list[tuple[float, dict]] = []
        for lesson in self._lessons:
            lesson_words = set(lesson["error"].lower().split())
            overlap = len(error_words & lesson_words)
            if overlap >= 2 or (overlap >= 1 and tool and lesson.get("tool") == tool):
                scored.append((overlap, lesson))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:max_results]]
