"""Tests for SOMA AnalyticsStore (SQLite-backed historical analytics)."""

from __future__ import annotations

import json
import sqlite3
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


# ---------------------------------------------------------------------------
# Source tagging
# ---------------------------------------------------------------------------

def test_record_with_source(tmp_path: Path):
    """Analytics records should include source field."""
    store = AnalyticsStore(path=tmp_path / "test.db")
    store.record(
        agent_id="test", session_id="test", tool_name="Bash",
        pressure=0.1, uncertainty=0.0, drift=0.0, error_rate=0.0,
        context_usage=0.0, token_count=100, cost=0.0, mode="OBSERVE",
        error=False, source="hook",
    )
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    row = conn.execute("SELECT source FROM actions LIMIT 1").fetchone()
    assert row[0] == "hook"
    conn.close()
    store.close()


def test_purge_before(tmp_path: Path):
    """purge_before() deletes actions before a timestamp."""
    import time
    store = AnalyticsStore(path=tmp_path / "test.db")
    store.record("a", "s", "Bash", pressure=0.1)
    cutoff = time.time() + 1
    store.record("a", "s", "Read", pressure=0.2)
    # Both records exist
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    assert conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 2
    # Purge before cutoff — first record should be deleted
    deleted = store.purge_before(cutoff)
    assert deleted >= 1
    remaining = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    assert remaining <= 1
    conn.close()


# ---------------------------------------------------------------------------
# v2026.5.5 — test-pollution guard + purge migration
# ---------------------------------------------------------------------------

def test_record_guidance_outcome_blocks_known_test_keys(tmp_path: Path):
    """``mixed``, ``bad_pattern``, ``maybe_bad`` are test fixtures that
    leaked into production DBs before v2026.5.5; writes must be
    silently dropped when ``source != 'test'``."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    for key in ("mixed", "bad_pattern", "maybe_bad"):
        store.record_guidance_outcome(
            agent_id="cc", session_id="s", pattern_key=key,
            helped=True, pressure_at_injection=0.5, pressure_after=0.3,
        )
    # Also the 'test_' prefix convention used elsewhere.
    store.record_guidance_outcome(
        agent_id="cc", session_id="s", pattern_key="test_something",
        helped=False, pressure_at_injection=0.5, pressure_after=0.5,
    )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes"
    ).fetchone()[0]
    assert count == 0
    store.close()


def test_record_guidance_outcome_allows_test_keys_with_source_test(tmp_path: Path):
    """Tests that deliberately exercise the fixture keys can still
    write by passing ``source='test'`` — required for the roi and
    mirror learning test suites to remain self-contained."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.record_guidance_outcome(
        agent_id="cc", session_id="s", pattern_key="mixed",
        helped=True, pressure_at_injection=0.5, pressure_after=0.3,
        source="test",
    )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes"
    ).fetchone()[0]
    assert count == 1
    store.close()


def test_record_guidance_outcome_blocks_test_agent_ids(tmp_path: Path):
    """Test-agent writes (test, agent-a, test-*) are silently dropped.

    Pairs with the pattern-key guard: without this the mirror.py call
    path bypasses _is_real_production_agent when tests instantiate
    AnalyticsStore() without a path, polluting production analytics
    with real pattern keys under fake agent ids.
    """
    store = AnalyticsStore(path=tmp_path / "a.db")
    for aid in ("test", "agent-a", "nonexistent-agent", "claude-code",
                "test-123", "test-cc-45", ""):
        store.record_guidance_outcome(
            agent_id=aid, session_id="s", pattern_key="bash_retry",
            helped=True, pressure_at_injection=0.5, pressure_after=0.3,
        )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes"
    ).fetchone()[0]
    assert count == 0
    store.close()


def test_record_guidance_outcome_test_agent_with_source_test_allowed(tmp_path: Path):
    """Deliberate test writes (source='test') still succeed for self-contained suites."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.record_guidance_outcome(
        agent_id="test", session_id="s", pattern_key="bash_retry",
        helped=True, pressure_at_injection=0.5, pressure_after=0.3,
        source="test",
    )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes"
    ).fetchone()[0]
    assert count == 1
    store.close()


def test_purge_test_agent_migration_drops_existing_leaks(tmp_path: Path):
    """Re-opening a DB with leaked test-agent rows must clean them up."""
    import sqlite3
    db = tmp_path / "polluted.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE guidance_outcomes (
            timestamp REAL, agent_id TEXT, session_id TEXT,
            pattern_key TEXT, helped INTEGER,
            pressure_at_injection REAL, pressure_after REAL,
            source TEXT DEFAULT 'hook'
        )
    """)
    # Seeded rows: 3 real, 3 test-agent polluters, 1 deliberate test write.
    for aid in ("cc", "cc-123", "swe-bench"):
        conn.execute(
            "INSERT INTO guidance_outcomes VALUES (?, ?, 's', 'bash_retry', 0, 0, 0, 'hook')",
            (1.0, aid),
        )
    for aid in ("test", "agent-a", "test-99"):
        conn.execute(
            "INSERT INTO guidance_outcomes VALUES (?, ?, 's', 'retry_loop', 0, 0, 0, 'hook')",
            (1.0, aid),
        )
    conn.execute(
        "INSERT INTO guidance_outcomes VALUES (?, 'test', 's', 'bash_retry', 0, 0, 0, 'test')",
        (1.0,),
    )
    conn.commit()
    conn.close()

    store = AnalyticsStore(path=db)
    rows = store._conn.execute(
        "SELECT agent_id, source FROM guidance_outcomes ORDER BY agent_id"
    ).fetchall()
    agent_ids = {r[0] for r in rows}
    assert agent_ids == {"cc", "cc-123", "swe-bench", "test"}
    # The deliberate test row with source='test' survives.
    surviving_test = [r for r in rows if r[0] == "test"]
    assert len(surviving_test) == 1
    assert surviving_test[0][1] == "test"
    store.close()


def test_record_guidance_outcome_real_patterns_unaffected(tmp_path: Path):
    """Guard must not touch legitimate pattern keys."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.record_guidance_outcome(
        agent_id="cc", session_id="s", pattern_key="bash_retry",
        helped=True, pressure_at_injection=0.6, pressure_after=0.2,
    )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM guidance_outcomes WHERE pattern_key = 'bash_retry'"
    ).fetchone()[0]
    assert count == 1
    store.close()


def test_purge_migration_drops_existing_pollution(tmp_path: Path):
    """A DB opened for the first time post-migration should have any
    pre-existing pollution rows removed. We simulate the legacy state
    by inserting rows with the raw INSERT (bypassing the write-guard),
    closing, and re-opening — the migration should run during
    re-open because schema_migrations is empty."""
    import sqlite3
    db_path = tmp_path / "legacy.db"

    # Build a legacy-style DB: raw schema without the guard, pre-seeded
    # with test-fixture rows and a real bash_retry row.
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE guidance_outcomes (
            timestamp REAL NOT NULL,
            agent_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            helped INTEGER NOT NULL,
            pressure_at_injection REAL,
            pressure_after REAL
        )
    """)
    for key in ("mixed", "bad_pattern", "maybe_bad", "test_xyz", "bash_retry"):
        conn.execute(
            "INSERT INTO guidance_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1.0, "cc", "s", key, 0, 0.5, 0.5),
        )
    conn.commit()
    conn.close()

    # Opening via AnalyticsStore triggers the migration.
    store = AnalyticsStore(path=db_path)
    remaining = store._conn.execute(
        "SELECT pattern_key FROM guidance_outcomes"
    ).fetchall()
    keys = {r[0] for r in remaining}
    assert keys == {"bash_retry"}
    store.close()


def test_purge_migration_is_idempotent(tmp_path: Path):
    """Opening the store twice must not rerun the DELETE (the
    migration marker short-circuits subsequent opens)."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    store.close()
    store2 = AnalyticsStore(path=tmp_path / "a.db")
    migrations = store2._conn.execute(
        "SELECT id FROM schema_migrations"
    ).fetchall()
    assert any(
        row[0] == "20260424_purge_guidance_test_pollution"
        for row in migrations
    )
    store2.close()


def test_archive_migration_moves_biased_rows_to_archive_table(tmp_path: Path, monkeypatch):
    """Legacy ab_outcomes rows written under MD5 assignment must be
    archived and the live table truncated. The archive table preserves
    the data so a future analyst can audit it."""
    # Isolate the counter file so the migration's reset doesn't touch
    # the user's real ~/.soma.
    from soma import ab_control
    monkeypatch.setattr(
        ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json"
    )

    import sqlite3
    db_path = tmp_path / "legacy_ab.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE ab_outcomes (
            timestamp REAL NOT NULL,
            agent_family TEXT NOT NULL,
            pattern TEXT NOT NULL,
            arm TEXT NOT NULL CHECK(arm IN ('treatment', 'control')),
            pressure_before REAL,
            pressure_after REAL,
            followed INTEGER DEFAULT 0
        )
    """)
    for i in range(10):
        conn.execute(
            "INSERT INTO ab_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1000.0 + i, "cc", "entropy_drop", "treatment",
             0.6, 0.55, 0),
        )
    conn.commit()
    conn.close()

    # Re-open via AnalyticsStore — archive migration should fire.
    store = AnalyticsStore(path=db_path)
    live = store._conn.execute("SELECT COUNT(*) FROM ab_outcomes").fetchone()[0]
    archived = store._conn.execute(
        "SELECT COUNT(*) FROM ab_outcomes_biased_pre_v2026_5_5"
    ).fetchone()[0]
    assert live == 0
    assert archived == 10
    # archived_at is populated.
    ts = store._conn.execute(
        "SELECT archived_at FROM ab_outcomes_biased_pre_v2026_5_5 LIMIT 1"
    ).fetchone()[0]
    assert ts > 0
    store.close()


def test_retired_pattern_rows_dropped(tmp_path: Path):
    """Legacy `_stats` / `drift` rows must be removed — the patterns
    no longer emit so their history only confuses direct-SQL audits.
    The dashboard filter was a belt; this migration is the braces."""
    import sqlite3
    db_path = tmp_path / "retired.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE guidance_outcomes (
            timestamp REAL, agent_id TEXT, session_id TEXT,
            pattern_key TEXT, helped INTEGER,
            pressure_at_injection REAL, pressure_after REAL
        )
    """)
    for key in ("_stats", "drift", "bash_retry", "error_cascade"):
        conn.execute(
            "INSERT INTO guidance_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1.0, "cc", "s", key, 0, 0.5, 0.5),
        )
    conn.commit()
    conn.close()

    store = AnalyticsStore(path=db_path)
    keys = {
        row[0] for row in store._conn.execute(
            "SELECT pattern_key FROM guidance_outcomes"
        ).fetchall()
    }
    assert keys == {"bash_retry", "error_cascade"}
    store.close()


def test_get_ab_reset_ts_reads_schema_migrations(tmp_path: Path, monkeypatch):
    """Primary source of truth is schema_migrations.applied_at.

    The migration flag is guaranteed to exist once the archive has run —
    unlike ab_reset.log, which the best-effort writer may have failed
    to create on older installs.
    """
    from soma import ab_control
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    store = AnalyticsStore(path=tmp_path / "a.db")
    ts = store.get_ab_reset_ts()
    # Opened just now, so the migration applied_at is within the last
    # minute.
    import time as _t
    assert 0 < ts < _t.time() + 1
    assert ts > _t.time() - 60
    store.close()


def test_get_ab_reset_ts_falls_back_to_log(tmp_path: Path, monkeypatch):
    """If schema_migrations row is absent (forward-compat), read the log."""
    from soma import ab_control
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    store = AnalyticsStore(path=tmp_path / "b.db")
    # Simulate an install where the migration row is gone but the log
    # survives.
    store._conn.execute("DELETE FROM schema_migrations")
    store._conn.commit()
    log = tmp_path / "ab_reset.log"
    log.write_text(
        json.dumps({"ts": 100.0}) + "\n"
        + "not-json\n"
        + json.dumps({"ts": 500.0}) + "\n"
        + json.dumps({"ts": 200.0}) + "\n"
    )
    assert store.get_ab_reset_ts() == 500.0
    store.close()


def test_get_ab_reset_ts_missing_everything_returns_zero(tmp_path: Path, monkeypatch):
    from soma import ab_control
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    store = AnalyticsStore(path=tmp_path / "c.db")
    store._conn.execute("DELETE FROM schema_migrations")
    store._conn.commit()
    log = tmp_path / "ab_reset.log"
    if log.exists():
        log.unlink()
    assert store.get_ab_reset_ts() == 0.0
    store.close()


def test_get_pattern_stats_since_ts_excludes_old_rows(tmp_path: Path, monkeypatch):
    """Pre-reset (biased) rows must not poison post-reset precision."""
    from soma import ab_control
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    store = AnalyticsStore(path=tmp_path / "c.db")
    # Named-column INSERT so additive migrations don't break this test.
    insert_sql = (
        "INSERT INTO guidance_outcomes "
        "(timestamp, agent_id, session_id, pattern_key, helped, "
        " pressure_at_injection, pressure_after, source) "
        "VALUES (?, 'cc', 's', 'blind_edit', ?, 0, 0, 'hook')"
    )
    # 30 pre-reset fires with helped=0 (biased).
    for i in range(30):
        store._conn.execute(insert_sql, (100.0 + i, 0))
    # 5 post-reset fires with helped=1 (clean).
    for i in range(5):
        store._conn.execute(insert_sql, (2000.0 + i, 1))
    store._conn.commit()

    # Legacy call (since_ts=0) sees the biased window — 30 fires, 5 helped.
    stats = store.get_pattern_stats("cc", "blind_edit", last_n=50)
    assert stats["fires"] == 35
    assert stats["helped"] == 5
    # Post-reset call (since_ts=1500) sees only the clean fires.
    stats = store.get_pattern_stats("cc", "blind_edit", last_n=50, since_ts=1500.0)
    assert stats["fires"] == 5
    assert stats["helped"] == 5
    store.close()


def test_clear_stale_silence_cache_migration_runs_on_open(tmp_path: Path, monkeypatch):
    """The silence triad must be zeroed when the AnalyticsStore opens.

    Without this migration the v2026.5.5 A/B reset leaves half the
    patterns silenced forever, which is what made the post-reset
    ab_outcomes table stay empty in production.
    """
    from soma import ab_control, calibration
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    monkeypatch.setattr(calibration, "SOMA_DIR", tmp_path)

    profile = tmp_path / "calibration_cc.json"
    profile.write_text(json.dumps({
        "family": "cc", "action_count": 4000, "phase": "adaptive",
        "drift_p25": 0.0, "drift_p75": 0.0,
        "entropy_p25": 0.0, "entropy_p75": 0.0,
        "typical_error_burst": 0, "typical_retry_burst": 0,
        "typical_success_rate": 0.0,
        "silenced_patterns": ["blind_edit", "context"],
        "last_silence_check_action": 3500,
        "pattern_precision_cache": {"blind_edit": 0.05},
        "refuted_patterns": [], "last_refuted_check_action": 0,
        "validated_patterns": [],
        "created_at": 1.0, "updated_at": 1.0, "schema_version": 1,
    }))

    store = AnalyticsStore(path=tmp_path / "a.db")
    store.close()

    data = json.loads(profile.read_text())
    assert data["silenced_patterns"] == []
    assert data["pattern_precision_cache"] == {}
    assert data["last_silence_check_action"] == 0


def test_clear_stale_silence_cache_migration_idempotent(tmp_path: Path, monkeypatch):
    """Second AnalyticsStore open on the same DB must not re-clear.

    We prove idempotency by writing fresh silenced_patterns *after* the
    first open and verifying the second open leaves them untouched —
    the migration flag in schema_migrations short-circuits the sweep.
    """
    from soma import ab_control, calibration
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    monkeypatch.setattr(calibration, "SOMA_DIR", tmp_path)

    profile = tmp_path / "calibration_cc.json"
    profile.write_text(json.dumps({
        "family": "cc", "action_count": 4000, "phase": "adaptive",
        "drift_p25": 0.0, "drift_p75": 0.0,
        "entropy_p25": 0.0, "entropy_p75": 0.0,
        "typical_error_burst": 0, "typical_retry_burst": 0,
        "typical_success_rate": 0.0,
        "silenced_patterns": ["blind_edit"],
        "last_silence_check_action": 0,
        "pattern_precision_cache": {},
        "refuted_patterns": [], "last_refuted_check_action": 0,
        "validated_patterns": [],
        "created_at": 1.0, "updated_at": 1.0, "schema_version": 1,
    }))
    store = AnalyticsStore(path=tmp_path / "b.db")
    store.close()

    # Simulate post-reset silence being legitimately set again.
    data = json.loads(profile.read_text())
    data["silenced_patterns"] = ["new_silence"]
    profile.write_text(json.dumps(data))

    store = AnalyticsStore(path=tmp_path / "b.db")
    store.close()
    data = json.loads(profile.read_text())
    # Migration is one-shot — the fresh silence survives.
    assert data["silenced_patterns"] == ["new_silence"]


def test_reclear_silence_after_fix_window_migration(tmp_path: Path, monkeypatch):
    """Catch the 08578c5 → d916d42 race-window stickiness.

    Scenario: original clear migration ran (id present in
    schema_migrations), but a hook in the fix window repopulated the
    silence triad. The since_ts filter then turned ``update_silence``
    into a no-op, leaving the triad stuck. The follow-on
    ``20260425_reclear_silence_after_fix_window`` migration must run
    once on next open and zero the cache.
    """
    from soma import ab_control, calibration
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json")
    monkeypatch.setattr(calibration, "SOMA_DIR", tmp_path)

    profile = tmp_path / "calibration_cc.json"
    profile.write_text(json.dumps({
        "family": "cc", "action_count": 6024, "phase": "adaptive",
        "drift_p25": 0.0, "drift_p75": 0.0,
        "entropy_p25": 0.0, "entropy_p75": 0.0,
        "typical_error_burst": 0, "typical_retry_burst": 0,
        "typical_success_rate": 1.0,
        "silenced_patterns": ["entropy_drop", "blind_edit", "context"],
        "last_silence_check_action": 6024,
        "pattern_precision_cache": {"entropy_drop": 0.2, "blind_edit": 0.03},
        "refuted_patterns": [], "last_refuted_check_action": 0,
        "validated_patterns": [],
        "created_at": 1.0, "updated_at": 1.0, "schema_version": 1,
    }))

    db = tmp_path / "race.db"
    # First open writes both silence-clear migration ids.
    store = AnalyticsStore(path=db)
    store.close()
    rows = {
        r[0] for r in
        sqlite3.connect(db).execute("SELECT id FROM schema_migrations").fetchall()
    }
    assert "20260424_clear_stale_silence_cache" in rows
    assert "20260425_reclear_silence_after_fix_window" in rows

    data = json.loads(profile.read_text())
    assert data["silenced_patterns"] == []
    assert data["pattern_precision_cache"] == {}
    assert data["last_silence_check_action"] == 0


class TestRecordAbOutcomeWriteGuard:
    """Mirror of the record_guidance_outcome guard (c1467df, 2026-04-24).

    Without this guard, mirror.py / replay tooling could leak rows into
    production ab_outcomes the same way 722 rows leaked into
    guidance_outcomes before the guidance-side guard shipped.
    """

    def test_test_agent_family_dropped_by_default(self, tmp_path: Path):
        store = AnalyticsStore(path=tmp_path / "guard.db")
        try:
            store.record_ab_outcome(
                agent_family="test", pattern="entropy_drop", arm="treatment",
                pressure_before=0.5, pressure_after=0.4,
            )
            assert store.get_ab_outcomes("entropy_drop") == []
        finally:
            store.close()

    def test_test_pattern_dropped_by_default(self, tmp_path: Path):
        store = AnalyticsStore(path=tmp_path / "guard.db")
        try:
            store.record_ab_outcome(
                agent_family="cc", pattern="test_synthetic", arm="treatment",
                pressure_before=0.5, pressure_after=0.4,
            )
            assert store.get_ab_outcomes("test_synthetic") == []
        finally:
            store.close()

    def test_known_test_pattern_dropped_by_default(self, tmp_path: Path):
        store = AnalyticsStore(path=tmp_path / "guard.db")
        try:
            store.record_ab_outcome(
                agent_family="cc", pattern="mixed", arm="treatment",
                pressure_before=0.5, pressure_after=0.4,
            )
            assert store.get_ab_outcomes("mixed") == []
        finally:
            store.close()

    def test_test_source_opt_in_writes(self, tmp_path: Path):
        """source='test' lets the test suite write its own ab_outcomes
        rows for end-to-end coverage."""
        store = AnalyticsStore(path=tmp_path / "guard.db")
        try:
            store.record_ab_outcome(
                agent_family="test", pattern="entropy_drop", arm="treatment",
                pressure_before=0.5, pressure_after=0.4, source="test",
            )
            rows = store.get_ab_outcomes("entropy_drop")
            assert len(rows) == 1
            assert rows[0]["agent_family"] == "test"
        finally:
            store.close()

    def test_real_agent_real_pattern_writes(self, tmp_path: Path):
        store = AnalyticsStore(path=tmp_path / "guard.db")
        try:
            store.record_ab_outcome(
                agent_family="cc", pattern="entropy_drop", arm="treatment",
                pressure_before=0.5, pressure_after=0.4,
            )
            assert len(store.get_ab_outcomes("entropy_drop")) == 1
        finally:
            store.close()


def test_archive_migration_resets_block_randomizer_counters(tmp_path: Path, monkeypatch):
    """After archiving biased rows the counter file from the old
    regime must be wiped so the new block randomizer starts balanced.
    Otherwise stale counts could force an imbalance in the fresh
    window."""
    from soma import ab_control
    counter_path = tmp_path / "ab_counters.json"
    monkeypatch.setattr(ab_control, "_COUNTERS_PATH", counter_path)
    # Prime counters with stale imbalance.
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text('{"cc|entropy_drop": [40, 3]}')

    store = AnalyticsStore(path=tmp_path / "reset.db")
    assert not counter_path.exists(), "archive migration must delete counters"
    store.close()


# ---------------------------------------------------------------------------
# Multi-horizon ab_outcomes columns (20260426 migration)
# ---------------------------------------------------------------------------


def test_multi_horizon_columns_added(tmp_path: Path):
    """ab_outcomes must have pressure_after_h1/_h5/_h10 + firing_id columns
    after the 20260426 migration runs. firing_id is the UPDATE key for
    landing later horizons against an existing row inserted at h=2."""
    store = AnalyticsStore(path=tmp_path / "test.db")
    try:
        cursor = store._conn.execute("PRAGMA table_info(ab_outcomes)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "pressure_after_h1" in cols
        assert "pressure_after_h5" in cols
        assert "pressure_after_h10" in cols
        assert "firing_id" in cols
        # Existing pressure_after stays — semantically equals h=2.
        assert "pressure_after" in cols
    finally:
        store.close()


def test_multi_horizon_migration_idempotent(tmp_path: Path):
    """Re-opening the DB must not re-add the columns (would fail with
    'duplicate column' SQL error if not guarded by PRAGMA table_info)."""
    db = tmp_path / "test.db"
    AnalyticsStore(path=db).close()
    AnalyticsStore(path=db).close()
    AnalyticsStore(path=db).close()
    # Survived three opens — migration is idempotent.


# ---------------------------------------------------------------------------
# Multi-definition guidance_outcomes columns (20260426 migration)
# ---------------------------------------------------------------------------


def test_multi_definition_columns_added(tmp_path: Path):
    """guidance_outcomes must gain helped_pressure_drop, _tool_switch,
    _error_resolved INTEGER columns after the 20260426 migration. The
    legacy ``helped`` column stays as the canonical pattern-specific
    rule for the dashboard."""
    store = AnalyticsStore(path=tmp_path / "test.db")
    try:
        cursor = store._conn.execute("PRAGMA table_info(guidance_outcomes)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "helped_pressure_drop" in cols
        assert "helped_tool_switch" in cols
        assert "helped_error_resolved" in cols
        # Legacy column stays untouched.
        assert "helped" in cols
    finally:
        store.close()


def test_multi_definition_migration_idempotent(tmp_path: Path):
    db = tmp_path / "test.db"
    AnalyticsStore(path=db).close()
    AnalyticsStore(path=db).close()
    AnalyticsStore(path=db).close()


def test_record_guidance_outcome_persists_multi_definition(tmp_path: Path):
    """Round-trip: caller passes the three booleans, they land in the
    new columns. NULLs are preserved when caller omits them (back-compat
    for legacy code paths that don't compute multi-helped yet)."""
    store = AnalyticsStore(path=tmp_path / "g.db")
    try:
        store.record_guidance_outcome(
            agent_id="cc-multi", session_id="s",
            pattern_key="bash_retry", helped=True,
            pressure_at_injection=0.7, pressure_after=0.4,
            helped_pressure_drop=True,
            helped_tool_switch=False,
            helped_error_resolved=True,
        )
        # Legacy caller — three columns must remain NULL.
        store.record_guidance_outcome(
            agent_id="cc-multi", session_id="s",
            pattern_key="bash_retry", helped=False,
            pressure_at_injection=0.6, pressure_after=0.55,
        )
        rows = store._conn.execute(
            "SELECT helped, helped_pressure_drop, helped_tool_switch, "
            "helped_error_resolved FROM guidance_outcomes "
            "WHERE pattern_key = 'bash_retry' ORDER BY timestamp"
        ).fetchall()
        assert rows[0] == (1, 1, 0, 1)
        assert rows[1] == (0, None, None, None)
    finally:
        store.close()
