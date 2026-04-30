"""
Regression for v2026.6.2 fix #1 — SQLite must set busy_timeout and
synchronous=NORMAL so concurrent hook subprocesses don't hit instant
SQLITE_BUSY (which the outer except: pass swallows, silently dropping
analytics rows).
"""
from __future__ import annotations

from pathlib import Path

from soma.analytics import AnalyticsStore


def test_busy_timeout_set(tmp_path: Path) -> None:
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        # PRAGMA busy_timeout returns ms as integer
        result = store._conn.execute("PRAGMA busy_timeout").fetchone()
        assert result[0] >= 2000, (
            f"busy_timeout not set or too low: {result[0]}ms — concurrent "
            f"hooks will SQLITE_BUSY and lose data"
        )
    finally:
        store.close()


def test_synchronous_normal(tmp_path: Path) -> None:
    """synchronous=NORMAL (1) is safe under WAL and ~10x faster than FULL (2)."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        result = store._conn.execute("PRAGMA synchronous").fetchone()
        # 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA. Want 1 (NORMAL).
        assert result[0] == 1, (
            f"synchronous={result[0]} — should be 1 (NORMAL) under WAL"
        )
    finally:
        store.close()


def test_journal_mode_wal_unchanged(tmp_path: Path) -> None:
    """Sanity — pre-existing WAL mode must not regress."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        result = store._conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"
    finally:
        store.close()
