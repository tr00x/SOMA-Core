"""SQLite-backed historical analytics for SOMA sessions."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


# Pattern keys that originate from the test suite (``test_mirror_learning``
# and ``test_roi``). When a developer ran those tests against their real
# ``~/.soma/analytics.db`` the rows leaked into production and polluted
# the guidance ROI view — 672 rows / ~45 % of the table at the time of
# the v2026.5.5 migration. Rejecting them on write stops the bleeding;
# the 20260424_purge_guidance_test_pollution migration cleans up rows
# that got in before the guard existed.
_KNOWN_TEST_PATTERN_KEYS = frozenset({"mixed", "bad_pattern", "maybe_bad"})

# Agent ids used exclusively by the test suite. The hook layer already
# rejects these for real-session writes via _is_real_production_agent,
# but direct callers of record_* (tests, mirror.py, replay tooling)
# bypass that gate and have historically polluted production analytics
# — 570 retry_loop rows under agent_id='test' as of 2026-04-24. This
# mirrors the pattern-key guard: writes are silently dropped unless
# the caller opts in with source='test'.
_KNOWN_TEST_AGENT_IDS = frozenset({"test", "agent-a", "nonexistent-agent", "claude-code"})


def _is_test_agent_id(agent_id: str) -> bool:
    return (
        not agent_id
        or agent_id in _KNOWN_TEST_AGENT_IDS
        or agent_id.startswith("test-")
    )


class AnalyticsStore:
    """SQLite-backed historical analytics for SOMA sessions."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path.home() / ".soma" / "analytics.db"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                timestamp REAL NOT NULL,
                agent_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                pressure REAL,
                uncertainty REAL,
                drift REAL,
                error_rate REAL,
                context_usage REAL,
                token_count INTEGER,
                cost REAL,
                mode TEXT,
                error INTEGER,
                source TEXT DEFAULT 'unknown',
                soma_version TEXT DEFAULT ''
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_agent_session "
            "ON actions(agent_id, session_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_timestamp "
            "ON actions(timestamp)"
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS guidance_outcomes (
                timestamp REAL NOT NULL,
                agent_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                helped INTEGER NOT NULL,
                pressure_at_injection REAL,
                pressure_after REAL,
                source TEXT DEFAULT 'hook'
            )
        """)
        # A/B-controlled outcomes — v2026.5.3. Each firing is assigned to
        # 'treatment' or 'control'; for control we suppress the guidance
        # message but still record pressure_before/after so we can later
        # run a paired-sample test against treatment deltas.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_outcomes (
                timestamp REAL NOT NULL,
                agent_family TEXT NOT NULL,
                pattern TEXT NOT NULL,
                arm TEXT NOT NULL CHECK(arm IN ('treatment', 'control')),
                pressure_before REAL,
                pressure_after REAL,
                followed INTEGER DEFAULT 0
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ab_outcomes_pat_fam "
            "ON ab_outcomes(pattern, agent_family, timestamp)"
        )
        # Migrate existing DBs: add source/soma_version columns if missing
        try:
            self._conn.execute("SELECT source FROM actions LIMIT 0")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE actions ADD COLUMN source TEXT DEFAULT 'unknown'")
            self._conn.execute("ALTER TABLE actions ADD COLUMN soma_version TEXT DEFAULT ''")
        # guidance_outcomes.source was added in v2026.5.5 alongside the
        # test-pollution guard; older DBs need the column backfilled.
        try:
            self._conn.execute("SELECT source FROM guidance_outcomes LIMIT 0")
        except sqlite3.OperationalError:
            self._conn.execute(
                "ALTER TABLE guidance_outcomes ADD COLUMN source TEXT DEFAULT 'hook'"
            )
        self._conn.commit()
        self._run_migrations()

    # ── Migrations ─────────────────────────────────────────────────

    def _run_migrations(self) -> None:
        """Apply any pending schema_migrations rows.

        Each migration is idempotent and keyed by a string ID. The ID
        is inserted only after the migration's SQL commits so a crash
        mid-run means the migration reruns next startup — at which
        point the DELETE is a no-op because the offending rows are
        already gone.
        """
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id TEXT PRIMARY KEY,
                applied_at REAL NOT NULL
            )
        """)
        self._conn.commit()
        self._apply_migration(
            "20260424_purge_guidance_test_pollution",
            self._purge_test_pattern_pollution,
        )
        self._apply_migration(
            "20260424_archive_biased_ab_outcomes",
            self._archive_biased_ab_outcomes,
        )
        self._apply_migration(
            "20260424_drop_retired_pattern_rows",
            self._drop_retired_pattern_rows,
        )
        self._apply_migration(
            "20260424_clear_stale_silence_cache",
            self._clear_stale_silence_cache_post_ab_reset,
        )
        self._apply_migration(
            "20260424_purge_test_agent_pollution",
            self._purge_test_agent_pollution,
        )
        self._apply_migration(
            "20260425_reclear_silence_after_fix_window",
            self._clear_stale_silence_cache_post_ab_reset,
        )

    def _apply_migration(self, migration_id: str, fn: Any) -> None:
        """Run ``fn`` once; record ``migration_id`` on success."""
        row = self._conn.execute(
            "SELECT 1 FROM schema_migrations WHERE id = ?", (migration_id,)
        ).fetchone()
        if row is not None:
            return
        fn()
        self._conn.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (migration_id, time.time()),
        )
        self._conn.commit()

    def _purge_test_pattern_pollution(self) -> int:
        """Drop guidance_outcomes rows from known test fixtures.

        Matches ``pattern_key`` against the hardcoded test-key set and
        the ``test_%`` prefix convention. Returns the deleted count so
        a release note can quote how many rows were cleaned.
        """
        placeholders = ",".join("?" for _ in _KNOWN_TEST_PATTERN_KEYS)
        cursor = self._conn.execute(
            f"DELETE FROM guidance_outcomes "
            f"WHERE pattern_key IN ({placeholders}) OR pattern_key LIKE 'test_%'",
            tuple(_KNOWN_TEST_PATTERN_KEYS),
        )
        return cursor.rowcount

    def _drop_retired_pattern_rows(self) -> int:
        """Delete guidance_outcomes rows whose pattern is retired.

        `_stats` and `drift` stopped emitting guidance in earlier
        releases but their historic rows (265 + 9 in Timur's DB at the
        time of the migration) still bloat the table and would confuse
        anyone looking at raw SQL. Dashboard ROI already filters them
        via allowlist; this migration cleans the storage itself so
        direct SQL queries also see an honest table.
        """
        from soma.contextual_guidance import RETIRED_PATTERN_KEYS
        if not RETIRED_PATTERN_KEYS:
            return 0
        placeholders = ",".join("?" for _ in RETIRED_PATTERN_KEYS)
        cursor = self._conn.execute(
            f"DELETE FROM guidance_outcomes WHERE pattern_key IN ({placeholders})",
            tuple(RETIRED_PATTERN_KEYS),
        )
        return cursor.rowcount

    def _purge_test_agent_pollution(self) -> int:
        """Delete guidance_outcomes rows written under a test agent id.

        Catches the leak the pattern-key guard missed: tests calling
        :meth:`record_guidance_outcome` (directly or via mirror.py) with
        real pattern keys but test agent ids (``test``, ``agent-a``,
        starts with ``test-``). Production analytics had 570+ such rows
        by 2026-04-24. Rows with ``source='test'`` are preserved — the
        ROI / mirror test suites deliberately write them.
        """
        exact = ",".join("?" for _ in _KNOWN_TEST_AGENT_IDS)
        cursor = self._conn.execute(
            f"DELETE FROM guidance_outcomes "
            f"WHERE (source IS NULL OR source != 'test') AND ("
            f"agent_id IN ({exact}) OR agent_id LIKE 'test-%' OR agent_id = '')",
            tuple(_KNOWN_TEST_AGENT_IDS),
        )
        return cursor.rowcount

    def _clear_stale_silence_cache_post_ab_reset(self) -> int:
        """Follow-on to ``_archive_biased_ab_outcomes``.

        The A/B reset truncated the outcomes table, but per-agent
        calibration profiles kept a ``silenced_patterns`` list computed
        from pre-reset (biased) data. With that cache intact, patterns
        like blind_edit/context/entropy_drop/budget stayed silenced
        forever — cg.evaluate() returned None, ab_outcomes stayed empty,
        and the P2.2 coverage gate became unreachable. This migration
        zeros the silence triad on every ``calibration_*.json`` file in
        SOMA_DIR so the post-reset distribution can rebuild itself from
        clean guidance_outcomes.

        Re-applied as ``20260425_reclear_silence_after_fix_window``: the
        original 08578c5 → d916d42 ship sequence left a 5-minute window
        where the silence refresher was already running but still used
        the unfiltered (all-time) precision query. Hooks that fired in
        that window repopulated the silence triad from biased data; the
        later since_ts filter then kept it stuck because fires=0
        post-reset is a no-op in ``update_silence``. Idempotent —
        re-running on a clean profile is a no-op.
        """
        try:
            from soma.calibration import clear_stale_silence_cache
            return clear_stale_silence_cache()
        except Exception:
            return 0

    def _archive_biased_ab_outcomes(self) -> int:
        """Move pre-v2026.5.5 A/B rows into an archive table, then truncate.

        The MD5-based arm assignment in v2026.5.4 and earlier clustered
        bursts of firings into a single arm — per-pattern splits like
        entropy_drop 44T/3C and budget 3T/30C are provably biased and
        can't be de-biased post-hoc. Mixing them with the clean,
        block-randomized stream would contaminate every Welch's t-test
        until the bad rows rolled out.

        This migration copies every existing row into
        ``ab_outcomes_biased_pre_v2026_5_5`` (so the data isn't lost —
        a future analyst can still look) and then truncates the live
        table. Also resets the per-(family, pattern) counter file so
        the new block randomizer starts balanced from scratch.
        """
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_outcomes_biased_pre_v2026_5_5 (
                timestamp REAL NOT NULL,
                agent_family TEXT NOT NULL,
                pattern TEXT NOT NULL,
                arm TEXT NOT NULL,
                pressure_before REAL,
                pressure_after REAL,
                followed INTEGER,
                archived_at REAL NOT NULL
            )
        """)
        now = time.time()
        self._conn.execute(
            "INSERT INTO ab_outcomes_biased_pre_v2026_5_5 "
            "(timestamp, agent_family, pattern, arm, pressure_before, "
            "pressure_after, followed, archived_at) "
            "SELECT timestamp, agent_family, pattern, arm, pressure_before, "
            f"pressure_after, followed, {now} FROM ab_outcomes"
        )
        cursor = self._conn.execute("DELETE FROM ab_outcomes")
        # Wipe the block-randomizer counters so the new window starts at (0,0).
        try:
            from soma.ab_control import reset_counters
            reset_counters()
        except Exception:
            pass
        # Log reset timestamp so the dashboard can surface a "data reset
        # on <date>" banner explaining why validation cards are still in
        # 'collecting'. Best-effort: failure to log must not fail the
        # migration.
        try:
            import json
            reset_log = self._path.parent / "ab_reset.log"
            reset_log.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": now,
                "archived_rows": cursor.rowcount,
                "reason": "v2026.5.5 block-randomized A/B — MD5 bias purged",
                "soma_version": self._version(),
            }
            with reset_log.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
        return cursor.rowcount

    def record(
        self,
        agent_id: str,
        session_id: str,
        tool_name: str,
        pressure: float = 0.0,
        uncertainty: float = 0.0,
        drift: float = 0.0,
        error_rate: float = 0.0,
        context_usage: float = 0.0,
        token_count: int = 0,
        cost: float = 0.0,
        mode: str = "OBSERVE",
        error: bool = False,
        source: str = "unknown",
    ) -> None:
        """Record a single action snapshot to the analytics DB."""
        self._conn.execute(
            "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), agent_id, session_id, tool_name,
             pressure, uncertainty, drift, error_rate, context_usage,
             token_count, cost, mode, int(error), source, self._version()),
        )
        self._conn.commit()

    @staticmethod
    def _version() -> str:
        """Return SOMA version string."""
        try:
            from importlib.metadata import version
            return version("soma-ai")
        except Exception:
            return ""

    def purge_before(self, timestamp: float) -> int:
        """Delete actions before timestamp. Returns count deleted."""
        cursor = self._conn.execute(
            "DELETE FROM actions WHERE timestamp < ?", (timestamp,)
        )
        self._conn.commit()
        return cursor.rowcount

    def get_agent_trends(self, agent_id: str, last_n_sessions: int = 10) -> list[dict[str, Any]]:
        """Return per-session aggregates for an agent."""
        cursor = self._conn.execute(
            """
            SELECT session_id,
                   COUNT(*) as total_actions,
                   AVG(pressure) as avg_pressure,
                   MAX(pressure) as max_pressure,
                   SUM(token_count) as total_tokens,
                   SUM(cost) as total_cost,
                   SUM(error) as error_count,
                   MIN(timestamp) as started,
                   MAX(timestamp) as ended
            FROM actions
            WHERE agent_id = ?
            GROUP BY session_id
            ORDER BY MIN(timestamp) DESC
            LIMIT ?
            """,
            (agent_id, last_n_sessions),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def record_guidance_outcome(
        self,
        agent_id: str,
        session_id: str,
        pattern_key: str,
        helped: bool,
        pressure_at_injection: float,
        pressure_after: float,
        source: str = "hook",
    ) -> None:
        """Record whether a guidance injection improved agent behavior.

        Writes are rejected when ``pattern_key`` matches a known test
        fixture (see ``_KNOWN_TEST_PATTERN_KEYS`` or the ``test_``
        prefix) unless ``source='test'`` — this stops the v2026.5.x
        pollution pattern where test runs against the user's real DB
        silently injected 672 rows of junk into the ROI view.
        """
        if source != "test" and (
            pattern_key in _KNOWN_TEST_PATTERN_KEYS
            or pattern_key.startswith("test_")
            or _is_test_agent_id(agent_id)
        ):
            return
        self._conn.execute(
            "INSERT INTO guidance_outcomes "
            "(timestamp, agent_id, session_id, pattern_key, helped, "
            "pressure_at_injection, pressure_after, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), agent_id, session_id, pattern_key,
             int(helped), pressure_at_injection, pressure_after, source),
        )
        self._conn.commit()

    def get_guidance_effectiveness(self, session_id: str | None = None) -> dict[str, Any]:
        """Return guidance effectiveness stats, optionally filtered by session."""
        where = "WHERE session_id = ?" if session_id else ""
        params = (session_id,) if session_id else ()
        cursor = self._conn.execute(
            f"SELECT COUNT(*) as total, SUM(helped) as helped FROM guidance_outcomes {where}",
            params,
        )
        row = cursor.fetchone()
        total = row[0] or 0
        helped = row[1] or 0
        return {
            "total": total,
            "helped": helped,
            "effectiveness_rate": helped / total if total > 0 else 0.0,
        }

    def get_ab_reset_ts(self) -> float:
        """Return the v2026.5.5 archive-migration timestamp, or 0.0.

        Used by the silence refresher so pre-reset (biased) guidance
        outcomes don't keep patterns silenced after the archive migration
        truncated ab_outcomes.

        Source of truth is ``schema_migrations.applied_at`` for the
        archive migration id — guaranteed to be set whenever the
        migration ran. Falls back to the ab_reset.log file (for forward
        compat with installs that don't have the migration row yet).
        """
        try:
            row = self._conn.execute(
                "SELECT applied_at FROM schema_migrations WHERE id = ?",
                ("20260424_archive_biased_ab_outcomes",),
            ).fetchone()
            if row is not None and isinstance(row[0], (int, float)):
                return float(row[0])
        except sqlite3.Error:
            pass
        log = self._path.parent / "ab_reset.log"
        if not log.exists():
            return 0.0
        latest = 0.0
        try:
            with log.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = entry.get("ts")
                    if isinstance(ts, (int, float)) and ts > latest:
                        latest = float(ts)
        except OSError:
            return 0.0
        return latest

    def get_pattern_stats(
        self, agent_family: str, pattern: str, last_n: int = 50,
        since_ts: float = 0.0,
    ) -> dict[str, int]:
        """Return (fires, helped) for the last N outcomes of ``pattern``.

        Matches agent_ids by family prefix (``agent_id LIKE 'cc-%'`` or
        exact ``cc`` match) so short-lived session ids contribute to the
        same user's precision cache.

        ``since_ts`` filters out rows older than that epoch — callers
        use it to exclude pre-v2026.5.5 biased outcomes from silence
        decisions. Default 0 preserves legacy "all-time" semantics.
        """
        cursor = self._conn.execute(
            """
            SELECT helped FROM guidance_outcomes
            WHERE pattern_key = ?
              AND (agent_id = ? OR agent_id LIKE ?)
              AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT ?
            """,
            (pattern, agent_family, f"{agent_family}-%", since_ts, last_n),
        )
        rows = cursor.fetchall()
        fires = len(rows)
        helped = sum(1 for r in rows if r[0])
        return {"fires": fires, "helped": helped}

    def record_ab_outcome(
        self,
        *,
        agent_family: str,
        pattern: str,
        arm: str,
        pressure_before: float,
        pressure_after: float | None,
        followed: bool = False,
    ) -> None:
        """Insert a row into ``ab_outcomes``.

        ``pressure_after`` is nullable because the hook records
        ``pressure_before`` at firing time and updates the row later when
        the next action's pressure is known. In practice we insert both
        at once with the pressure at the time of the *next* tool-use
        event; this method is the single write-path used by the A/B
        controller.
        """
        if arm not in ("treatment", "control"):
            raise ValueError(f"arm must be 'treatment' or 'control', got {arm!r}")
        self._conn.execute(
            "INSERT INTO ab_outcomes "
            "(timestamp, agent_family, pattern, arm, pressure_before, pressure_after, followed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), agent_family, pattern, arm,
             pressure_before, pressure_after, int(followed)),
        )
        self._conn.commit()

    def get_ab_outcomes(
        self, pattern: str, agent_family: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch A/B outcomes for a pattern, newest first.

        ``agent_family=None`` aggregates across families — used by the
        ``soma validate-patterns`` CLI in global mode. Rows with
        ``pressure_after IS NULL`` are excluded; they're incomplete
        recordings (next action never arrived, e.g. session ended).
        """
        if agent_family is None:
            cursor = self._conn.execute(
                "SELECT timestamp, agent_family, pattern, arm, "
                "pressure_before, pressure_after, followed "
                "FROM ab_outcomes WHERE pattern = ? "
                "AND pressure_after IS NOT NULL "
                "ORDER BY timestamp DESC",
                (pattern,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT timestamp, agent_family, pattern, arm, "
                "pressure_before, pressure_after, followed "
                "FROM ab_outcomes WHERE pattern = ? AND agent_family = ? "
                "AND pressure_after IS NOT NULL "
                "ORDER BY timestamp DESC",
                (pattern, agent_family),
            )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_ab_patterns(self, agent_family: str | None = None) -> list[str]:
        """Return unique patterns with at least one ab_outcomes row.

        Used by ``soma validate-patterns`` to auto-enumerate which
        patterns have enough data to try validation.
        """
        if agent_family is None:
            cursor = self._conn.execute(
                "SELECT DISTINCT pattern FROM ab_outcomes "
                "WHERE pressure_after IS NOT NULL ORDER BY pattern"
            )
        else:
            cursor = self._conn.execute(
                "SELECT DISTINCT pattern FROM ab_outcomes "
                "WHERE agent_family = ? AND pressure_after IS NOT NULL "
                "ORDER BY pattern",
                (agent_family,),
            )
        return [row[0] for row in cursor.fetchall()]

    def get_tool_stats(self, agent_id: str) -> dict[str, int]:
        """Return tool usage counts for an agent across all sessions."""
        cursor = self._conn.execute(
            "SELECT tool_name, COUNT(*) as count FROM actions "
            "WHERE agent_id = ? GROUP BY tool_name ORDER BY count DESC",
            (agent_id,),
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
