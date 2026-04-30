"""Structured audit logging -- JSON Lines per action (LOG-01).

Zero-config: enabled by default, writes to ~/.soma/audit.jsonl.
Rotatable: starts new file when current exceeds max_bytes.
Parseable: each line is valid JSON, compatible with jq/grep/etc.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


#: How many rotated audit files to keep. Older ones get deleted on
#: each rotation. 5 × 10MB = 50MB max footprint of historical audit.
DEFAULT_RETAIN_ROTATED = 5


class AuditLogger:
    """Append-only JSON Lines audit log."""

    def __init__(
        self,
        path: str | Path | None = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB default
        enabled: bool = True,
        retain_rotated: int = DEFAULT_RETAIN_ROTATED,
    ) -> None:
        self._enabled = enabled
        self._max_bytes = max_bytes
        self._retain_rotated = retain_rotated
        if path is None:
            self._path = Path.home() / ".soma" / "audit.jsonl"
        else:
            self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def append(
        self,
        agent_id: str,
        tool_name: str,
        error: bool,
        pressure: float,
        mode: str,
        **extra: Any,
    ) -> None:
        """Append one JSON line to the audit log."""
        if not self._enabled:
            return
        entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "tool_name": tool_name,
            "error": error,
            "pressure": pressure,
            "mode": mode,
            **extra,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._maybe_rotate()
            with open(self._path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # Never crash the engine for audit failures

    def _maybe_rotate(self) -> None:
        """Rotate if current file exceeds max_bytes, then prune old
        rotated files past the retention limit so ~/.soma/ doesn't
        grow forever (audit.<ts>.jsonl files would otherwise pile up
        every time the live log hits max_bytes).
        """
        try:
            if self._path.exists() and self._path.stat().st_size > self._max_bytes:
                rotated = self._path.with_suffix(f".{int(time.time())}.jsonl")
                self._path.rename(rotated)
                self._prune_rotated()
        except OSError:
            pass

    def _prune_rotated(self) -> None:
        """Delete all but the ``retain_rotated`` newest rotated logs."""
        if self._retain_rotated <= 0:
            # 0 → unlimited retention (legacy behavior, opt-in).
            return
        try:
            # Match audit.<digits>.jsonl siblings. Stem of self._path is
            # "audit"; rotated form is "audit.<ts>.jsonl" (suffix → .jsonl).
            stem = self._path.name.split(".")[0]  # "audit"
            siblings = sorted(
                (
                    p for p in self._path.parent.glob(f"{stem}.*.jsonl")
                    if p != self._path
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in siblings[self._retain_rotated:]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except OSError:
            pass
