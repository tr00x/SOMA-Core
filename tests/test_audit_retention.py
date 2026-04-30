"""
Regression for v2026.6.x fix #27 — audit.jsonl rotated siblings must
be pruned to keep ~/.soma/ from growing forever.

Existing rotation already moves audit.jsonl → audit.<ts>.jsonl when
the live file exceeds max_bytes, but old rotated files never got
deleted. After enough rotations the directory accumulates an
unbounded number of historical audit logs.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from soma.audit import AuditLogger


def _force_rotate(logger: AuditLogger, ts_offset: int = 0) -> Path:
    """Plant a fake rotated file at audit.<ts>.jsonl with a back-dated mtime."""
    rotated = logger._path.with_suffix(f".{int(time.time()) - 1000 + ts_offset}.jsonl")
    rotated.write_text("{}\n")
    # Older mtime so the prune sort sees it as old.
    age = time.time() - 1000 + ts_offset
    os.utime(rotated, (age, age))
    return rotated


def test_old_rotated_files_pruned(tmp_path: Path) -> None:
    """8 historical rotated files + retain=5 → keep 5 newest, drop 3 oldest."""
    audit = tmp_path / "audit.jsonl"
    audit.write_text("{}\n")
    logger = AuditLogger(path=audit, max_bytes=10, retain_rotated=5)
    rotated_paths = []
    for i in range(8):
        # Newer mtime per i (i=0 oldest, i=7 newest).
        rotated_paths.append(_force_rotate(logger, ts_offset=i))

    # Trigger prune by writing one more entry that crosses max_bytes.
    logger.append("a", "Bash", False, 0.0, "OBSERVE")  # appends + may rotate
    logger._prune_rotated()

    surviving = sorted(
        p for p in tmp_path.glob("audit.*.jsonl")
        if p != audit
    )
    # Keep newest 5 by mtime.
    assert len(surviving) == 5, (
        f"expected 5 rotated files after prune, got {len(surviving)}: "
        f"{[p.name for p in surviving]}"
    )
    # Oldest 3 must be gone.
    for p in rotated_paths[:3]:
        assert not p.exists(), f"oldest rotated file not pruned: {p.name}"


def test_retain_zero_means_unbounded(tmp_path: Path) -> None:
    """Opt-out: retain_rotated=0 keeps all (legacy behavior)."""
    audit = tmp_path / "audit.jsonl"
    audit.write_text("{}\n")
    logger = AuditLogger(path=audit, retain_rotated=0)
    paths = [_force_rotate(logger, ts_offset=i) for i in range(10)]
    logger._prune_rotated()
    for p in paths:
        assert p.exists(), f"retain=0 should keep all, lost: {p.name}"


def test_prune_handles_missing_dir(tmp_path: Path) -> None:
    """If ~/.soma/ disappears mid-rotation, prune must not crash."""
    nonexistent = tmp_path / "missing" / "audit.jsonl"
    logger = AuditLogger(path=nonexistent)
    logger._prune_rotated()  # must not raise
