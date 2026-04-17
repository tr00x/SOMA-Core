"""SQLite-backed historical analytics for SOMA sessions."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


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
                pressure_after REAL
            )
        """)
        # Migrate existing DBs: add source/soma_version columns if missing
        try:
            self._conn.execute("SELECT source FROM actions LIMIT 0")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE actions ADD COLUMN source TEXT DEFAULT 'unknown'")
            self._conn.execute("ALTER TABLE actions ADD COLUMN soma_version TEXT DEFAULT ''")
        self._conn.commit()

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
    ) -> None:
        """Record whether a guidance injection improved agent behavior."""
        self._conn.execute(
            "INSERT INTO guidance_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), agent_id, session_id, pattern_key,
             int(helped), pressure_at_injection, pressure_after),
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
