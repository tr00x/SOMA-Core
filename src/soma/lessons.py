"""Cross-session lesson memory — SOMA remembers error→fix patterns."""

from __future__ import annotations

import json
import time
from pathlib import Path


def _trigrams(text: str) -> set[str]:
    """Extract character trigrams from text."""
    if len(text) < 3:
        return {text} if text else set()
    return {text[i:i+3] for i in range(len(text) - 2)}


def _trigram_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity over trigram sets. 0-1 scale."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


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
        from soma.errors import log_silent_failure
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._lessons, f, indent=2)
                os.replace(tmp, str(self._path))
            except Exception as e:
                log_silent_failure("lessons._save (write)", e)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        except Exception as e:
            log_silent_failure("lessons._save (outer)", e)

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
        """Find lessons matching an error. Trigram similarity + keyword overlap."""
        error_lower = error_text.lower()
        error_words = set(error_lower.split())
        error_trigrams = _trigrams(error_lower)
        scored: list[tuple[float, dict]] = []
        for lesson in self._lessons:
            lesson_lower = lesson["error"].lower()
            lesson_words = set(lesson_lower.split())

            # Trigram similarity (0-1 scale)
            tri_sim = _trigram_similarity(error_trigrams, _trigrams(lesson_lower))

            # Keyword overlap bonus
            overlap = len(error_words & lesson_words)

            # Combined score: trigram similarity is primary, overlap is bonus
            score = tri_sim + overlap * 0.1

            # Tool match bonus
            if tool and lesson.get("tool") == tool:
                score += 0.15

            if score >= 0.3:
                scored.append((score, lesson))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:max_results]]
