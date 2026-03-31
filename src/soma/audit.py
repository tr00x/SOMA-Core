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


class AuditLogger:
    """Append-only JSON Lines audit log."""

    def __init__(
        self,
        path: str | Path | None = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB default
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._max_bytes = max_bytes
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
        """Rotate if current file exceeds max_bytes."""
        try:
            if self._path.exists() and self._path.stat().st_size > self._max_bytes:
                rotated = self._path.with_suffix(f".{int(time.time())}.jsonl")
                self._path.rename(rotated)
        except OSError:
            pass
