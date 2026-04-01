"""SOMA Session Store — append-only JSON Lines session history.

Stores completed session summaries at ~/.soma/sessions/history.jsonl.
Each line is a JSON object representing one SessionRecord. File rotates
when exceeding max_bytes (default 10MB), following the audit.py pattern.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Summary of a completed monitoring session."""

    session_id: str
    agent_id: str
    started: float
    ended: float
    action_count: int
    final_pressure: float
    max_pressure: float
    avg_pressure: float
    error_count: int
    retry_count: int
    total_tokens: int
    mode_transitions: list  # [{from, to, at_action, pressure}]
    pressure_trajectory: list  # float per action
    tool_distribution: dict  # {tool_name: count}
    phase_sequence: list  # ["research", "implement", ...]
    fingerprint_divergence: float


def _history_path(base_dir: Path | None = None) -> Path:
    """Return path to history.jsonl under base_dir/sessions/."""
    base = base_dir or (Path.home() / ".soma")
    return base / "sessions" / "history.jsonl"


def _maybe_rotate(path: Path, max_bytes: int) -> None:
    """Rotate if current file exceeds max_bytes."""
    try:
        if path.exists() and path.stat().st_size > max_bytes:
            rotated = path.with_suffix(f".{int(time.time())}.jsonl")
            path.rename(rotated)
    except OSError:
        pass


def append_session(
    record: SessionRecord,
    base_dir: Path | None = None,
    max_bytes: int = 10_000_000,
) -> None:
    """Append a session record as a JSON line to history.jsonl.

    Creates parent directories if needed. Rotates at max_bytes.
    Never raises -- catches OSError silently.
    """
    path = _history_path(base_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _maybe_rotate(path, max_bytes)
        with open(path, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
    except OSError:
        pass  # Never crash for session store failures


def load_sessions(
    base_dir: Path | None = None,
    max_sessions: int = 100,
) -> list[SessionRecord]:
    """Load the last max_sessions records from history.jsonl.

    Returns [] if file is missing or empty. Skips malformed lines.
    """
    path = _history_path(base_dir)
    if not path.exists():
        return []

    try:
        lines = path.read_text().strip().splitlines()
    except OSError:
        return []

    if not lines:
        return []

    # Take last max_sessions lines
    lines = lines[-max_sessions:]

    records: list[SessionRecord] = []
    for line in lines:
        try:
            data = json.loads(line)
            records.append(SessionRecord(**data))
        except (json.JSONDecodeError, TypeError, KeyError):
            continue  # Skip malformed lines

    return records
