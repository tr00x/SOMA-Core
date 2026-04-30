"""
Regression for v2026.6.x fix #11 — schema-level guard against
INSERTing NULL firing_id into ab_outcomes.

Python-level dropguards already prevent this in the live writers
(post_tool_use._record_ab_outcome_at_horizon), but a future code
path that bypasses that helper (test fixture, scripted backfill,
external tool) would silently re-introduce the B1 bias class. A
SQLite BEFORE INSERT trigger closes it structurally.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from soma.analytics import AnalyticsStore


def test_insert_with_null_firing_id_is_rejected(tmp_path: Path) -> None:
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        with pytest.raises(sqlite3.IntegrityError) as exc:
            store._conn.execute(
                "INSERT INTO ab_outcomes(timestamp, agent_family, pattern, "
                "arm, pressure_before, pressure_after, followed, firing_id) "
                "VALUES (1.0, 'cc', 'budget', 'treatment', 0, 0, 0, NULL)"
            )
        assert "firing_id" in str(exc.value).lower(), (
            f"trigger error didn't mention firing_id: {exc.value}"
        )
    finally:
        store.close()


def test_insert_with_firing_id_succeeds(tmp_path: Path) -> None:
    """Sanity — non-NULL firing_id INSERTs still work."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        store._conn.execute(
            "INSERT INTO ab_outcomes(timestamp, agent_family, pattern, arm, "
            "pressure_before, pressure_after, followed, firing_id) "
            "VALUES (1.0, 'cc', 'budget', 'treatment', 0, 0, 0, 'fid-1')"
        )
        store._conn.commit()
        rows = store._conn.execute(
            "SELECT COUNT(*) FROM ab_outcomes"
        ).fetchone()
        assert rows[0] == 1
    finally:
        store.close()


def test_archive_table_unchanged(tmp_path: Path) -> None:
    """Legacy archive tables (pre_firing_id_legacy) intentionally hold
    NULL-firing_id rows for forensics. The trigger must NOT apply to
    archives — only to the live ab_outcomes table."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        # Should not raise — archive table has no trigger.
        store._conn.execute(
            "INSERT INTO ab_outcomes_pre_firing_id_legacy("
            "timestamp, agent_family, pattern, arm, pressure_before, "
            "pressure_after, followed, archived_at) "
            "VALUES (1.0, 'cc', 'budget', 'treatment', 0, 0, 0, 1.0)"
        )
        store._conn.commit()
    finally:
        store.close()
