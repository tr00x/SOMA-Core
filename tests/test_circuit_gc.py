"""
Regression for v2026.6.x fix #9 — circuit_*.json files accumulate
forever (one per Claude Code PID), polluting ~/.soma/. Add an
opportunistic GC keyed on file mtime so dead session files age out.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from soma.hooks.common import gc_stale_circuit_files


def test_gc_removes_files_older_than_threshold(tmp_path: Path) -> None:
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    # Plant 3 stale files (mtime far in the past) and 2 fresh ones.
    stale = []
    fresh = []
    now = time.time()
    for i in range(3):
        f = soma_dir / f"circuit_cc-stale{i}.json"
        f.write_text("{}")
        os.utime(f, (now - 7 * 86400, now - 7 * 86400))  # 7 days old
        stale.append(f)
    for i in range(2):
        f = soma_dir / f"circuit_cc-fresh{i}.json"
        f.write_text("{}")
        fresh.append(f)
    # And a non-matching file that must not be touched.
    other = soma_dir / "engine_state.json"
    other.write_text("{}")
    os.utime(other, (now - 30 * 86400, now - 30 * 86400))

    with patch("soma.hooks.common.SOMA_DIR", soma_dir):
        removed = gc_stale_circuit_files(max_age_hours=48)
    assert removed == 3, f"expected 3 stale removed, got {removed}"
    for f in stale:
        assert not f.exists()
    for f in fresh:
        assert f.exists()
    assert other.exists(), "GC removed unrelated file engine_state.json"


def test_gc_also_purges_lock_siblings(tmp_path: Path) -> None:
    """circuit_<id>.lock files must be removed alongside their .json."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    now = time.time()
    json_f = soma_dir / "circuit_cc-stale.json"
    lock_f = soma_dir / "circuit_cc-stale.lock"
    json_f.write_text("{}")
    lock_f.write_text("")
    for f in (json_f, lock_f):
        os.utime(f, (now - 7 * 86400, now - 7 * 86400))

    with patch("soma.hooks.common.SOMA_DIR", soma_dir):
        gc_stale_circuit_files(max_age_hours=48)
    assert not json_f.exists()
    assert not lock_f.exists()


def test_gc_handles_missing_dir(tmp_path: Path) -> None:
    """Missing ~/.soma/ must not crash the hook."""
    nonexistent = tmp_path / "does_not_exist"
    with patch("soma.hooks.common.SOMA_DIR", nonexistent):
        # Must not raise.
        removed = gc_stale_circuit_files(max_age_hours=48)
    assert removed == 0
