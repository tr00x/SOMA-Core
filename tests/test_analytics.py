"""Tests for SOMA AnalyticsStore (SQLite-backed historical analytics)."""

from __future__ import annotations

from pathlib import Path

from soma.analytics import AnalyticsStore


# ---------------------------------------------------------------------------
# DB creation
# ---------------------------------------------------------------------------

def test_creates_db(tmp_path: Path):
    db_path = tmp_path / "analytics.db"
    store = AnalyticsStore(path=db_path)
    assert db_path.exists()
    store.close()


# ---------------------------------------------------------------------------
# Record and query
# ---------------------------------------------------------------------------

def test_record_and_query(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.record("agent-1", "sess-1", "Bash", pressure=0.3, token_count=100)
    store.record("agent-1", "sess-1", "Read", pressure=0.5, token_count=200)
    store.record("agent-1", "sess-1", "Write", pressure=0.2, token_count=150)

    trends = store.get_agent_trends("agent-1")
    assert len(trends) == 1
    assert trends[0]["total_actions"] == 3
    assert trends[0]["session_id"] == "sess-1"
    store.close()


def test_tool_stats(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.record("agent-1", "sess-1", "Bash", pressure=0.1)
    store.record("agent-1", "sess-1", "Bash", pressure=0.2)
    store.record("agent-1", "sess-1", "Read", pressure=0.1)

    stats = store.get_tool_stats("agent-1")
    assert stats["Bash"] == 2
    assert stats["Read"] == 1
    store.close()


def test_empty_trends(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    trends = store.get_agent_trends("nonexistent")
    assert trends == []
    store.close()


def test_empty_tool_stats(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    stats = store.get_tool_stats("nonexistent")
    assert stats == {}
    store.close()


def test_multiple_sessions(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.record("agent-1", "sess-1", "Bash", pressure=0.3)
    store.record("agent-1", "sess-2", "Read", pressure=0.5)

    trends = store.get_agent_trends("agent-1")
    assert len(trends) == 2
    store.close()


def test_wal_mode(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    cursor = store._conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode == "wal"
    store.close()


def test_close_does_not_raise(tmp_path: Path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.close()  # Should not raise
