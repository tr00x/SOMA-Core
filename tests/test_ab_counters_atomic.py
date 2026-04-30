"""
Regression for v2026.6.2 fix #2 — _save_persisted must be atomic
(tmp + fsync + os.replace) so concurrent hooks racing on
ab_counters.json can never produce a torn-JSON file that
_load_persisted then silently resets.

v2026.6.x fix #6: reset_counters() must also purge orphaned
.tmp.<pid>.<tid> files left by killed processes.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch


def test_save_persisted_uses_replace(tmp_path: Path) -> None:
    """The write path must use os.replace (atomic) — not write_text
    on the destination directly."""
    target = tmp_path / "ab_counters.json"
    with patch("soma.ab_control._COUNTERS_PATH", target):
        from soma import ab_control as ab
        with patch("os.replace", side_effect=os.replace) as mock_replace:
            ab._save_persisted({"foo|cc": [1, 2]}, {"fid-1": "treatment"})
        assert mock_replace.called, (
            "_save_persisted did not call os.replace — write is not atomic"
        )
    # Sanity — content landed correctly
    data = json.loads(target.read_text())
    assert data["_counters"] == {"foo|cc": [1, 2]}
    assert data["_firings"] == {"fid-1": "treatment"}


def test_save_persisted_no_partial_file_on_concurrent_writes(tmp_path: Path) -> None:
    """Hammer _save_persisted from N threads. The file must always
    parse as valid JSON when read at any moment between writes."""
    target = tmp_path / "ab_counters.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with patch("soma.ab_control._COUNTERS_PATH", target):
        from soma import ab_control as ab
        # Plant an initial valid file so the reader has something to read
        ab._save_persisted({"init": [0, 0]}, {})

        torn = []

        def reader_loop() -> None:
            for _ in range(200):
                try:
                    if target.exists():
                        json.loads(target.read_text())
                except json.JSONDecodeError:
                    torn.append("torn")
                    return

        def writer_loop(n: int) -> None:
            for i in range(50):
                ab._save_persisted(
                    {f"p{n}|cc": [i, i]}, {f"fid-{n}-{i}": "control"}
                )

        threads = [threading.Thread(target=reader_loop) for _ in range(2)]
        threads += [threading.Thread(target=writer_loop, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not torn, (
            f"reader observed {len(torn)} torn-JSON snapshots — "
            f"_save_persisted is not atomic"
        )


def test_reset_counters_purges_orphaned_tmp_files(tmp_path: Path) -> None:
    """reset_counters() must purge ab_counters.json.tmp.<pid>.<tid> files
    left behind by processes that crashed between fsync and os.replace.
    Otherwise ~/.soma/ accumulates cruft from killed hooks."""
    target = tmp_path / "ab_counters.json"
    target.write_text('{"_counters":{},"_firings":{}}')
    # Plant three orphaned tmp files matching the v2026.6.2 naming.
    orphans = [
        tmp_path / f"ab_counters.json.tmp.99{i}.5{i}" for i in range(3)
    ]
    for o in orphans:
        o.write_text("partial-write")
    with patch("soma.ab_control._COUNTERS_PATH", target):
        from soma import ab_control as ab
        ab.reset_counters()
    # Main file gone, tmp orphans gone too.
    assert not target.exists()
    for o in orphans:
        assert not o.exists(), f"orphaned tmp file not purged: {o.name}"


def test_reset_counters_doesnt_touch_unrelated_files(tmp_path: Path) -> None:
    """The glob must be tight — sibling files like ab_counters.json.lock
    or unrelated *.json must survive reset."""
    target = tmp_path / "ab_counters.json"
    target.write_text('{}')
    keep = [
        tmp_path / "ab_counters.json.lock",
        tmp_path / "ab_counters.json.bak",
        tmp_path / "other.json",
    ]
    for k in keep:
        k.write_text("preserve me")
    with patch("soma.ab_control._COUNTERS_PATH", target):
        from soma import ab_control as ab
        ab.reset_counters()
    for k in keep:
        assert k.exists(), f"reset_counters removed unrelated file: {k.name}"
