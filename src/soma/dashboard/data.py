"""SOMA Dashboard data layer — single source of truth for all dashboard data."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from soma.dashboard.types import (
    AgentSnapshot,
    SessionDetail,
    SessionSummary,
)

SOMA_DIR = Path.home() / ".soma"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_db_connection() -> sqlite3.Connection | None:
    """Open analytics.db, returning None if it doesn't exist."""
    db_path = SOMA_DIR / "analytics.db"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _get_name_registry() -> dict[str, str]:
    """Read agent_names.json for display name lookup."""
    names_path = SOMA_DIR / "agent_names.json"
    if not names_path.exists():
        return {}
    try:
        return json.loads(names_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_live_agents() -> list[AgentSnapshot]:
    """Return all currently active agents from state.json + circuit files."""
    state_path = SOMA_DIR / "state.json"
    if not state_path.exists():
        return []

    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    agents_data = state.get("agents", {})
    result = []

    for agent_id, data in agents_data.items():
        esc_level = 0
        dominant = ""
        throttled = ""
        cb_block = 0
        cb_open = False

        circuit_path = SOMA_DIR / f"circuit_{agent_id}.json"
        if circuit_path.exists():
            try:
                circuit = json.loads(circuit_path.read_text())
                gs = circuit.get("guidance_state", {})
                esc_level = gs.get("escalation_level", 0)
                dominant = gs.get("dominant_signal", "")
                throttled = gs.get("throttled_tool", "")
                cb_block = circuit.get("consecutive_block", 0)
                cb_open = circuit.get("is_open", False)
            except (json.JSONDecodeError, OSError):
                pass

        result.append(AgentSnapshot(
            agent_id=agent_id,
            display_name=data.get("display_name", agent_id),
            level=data.get("level", "OBSERVE"),
            pressure=data.get("pressure", 0.0),
            action_count=data.get("action_count", 0),
            vitals=data.get("vitals", {}),
            escalation_level=esc_level,
            dominant_signal=dominant,
            throttled_tool=throttled,
            consecutive_block=cb_block,
            is_open=cb_open,
        ))

    return result


# ------------------------------------------------------------------
# Session queries
# ------------------------------------------------------------------


def get_all_sessions() -> list[SessionSummary]:
    """Return all sessions from analytics.db, grouped by session_id."""
    conn = _get_db_connection()
    if conn is None:
        return []

    try:
        names = _get_name_registry()
        rows = conn.execute("""
            SELECT
                session_id,
                agent_id,
                COUNT(*) as action_count,
                AVG(pressure) as avg_pressure,
                MAX(pressure) as max_pressure,
                SUM(token_count) as total_tokens,
                SUM(cost) as total_cost,
                SUM(error) as error_count,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                MAX(mode) as mode
            FROM actions
            GROUP BY session_id
            ORDER BY start_time DESC
        """).fetchall()

        sessions = []
        for r in rows:
            agent_id = r["agent_id"]
            sessions.append(SessionSummary(
                session_id=r["session_id"],
                agent_id=agent_id,
                display_name=names.get(agent_id, agent_id),
                action_count=r["action_count"],
                avg_pressure=round(r["avg_pressure"], 4),
                max_pressure=round(r["max_pressure"], 4),
                total_tokens=r["total_tokens"] or 0,
                total_cost=round(r["total_cost"] or 0.0, 6),
                error_count=int(r["error_count"] or 0),
                start_time=r["start_time"],
                end_time=r["end_time"],
                mode=r["mode"] or "OBSERVE",
            ))
        return sessions
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def get_session_detail(session_id: str) -> SessionDetail | None:
    """Return full detail for a single session, or None if not found."""
    conn = _get_db_connection()
    if conn is None:
        return None

    try:
        names = _get_name_registry()
        rows = conn.execute(
            "SELECT * FROM actions WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()

        if not rows:
            return None

        actions = []
        tool_counts: dict[str, int] = {}
        total_tokens = 0
        total_cost = 0.0
        error_count = 0
        pressures = []

        for r in rows:
            actions.append(dict(r))
            tool = r["tool_name"]
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            total_tokens += r["token_count"] or 0
            total_cost += r["cost"] or 0.0
            error_count += r["error"] or 0
            pressures.append(r["pressure"] or 0.0)

        agent_id = rows[0]["agent_id"]
        avg_p = sum(pressures) / len(pressures) if pressures else 0.0
        max_p = max(pressures) if pressures else 0.0

        return SessionDetail(
            session_id=session_id,
            agent_id=agent_id,
            display_name=names.get(agent_id, agent_id),
            action_count=len(actions),
            avg_pressure=round(avg_p, 4),
            max_pressure=round(max_p, 4),
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            error_count=error_count,
            start_time=rows[0]["timestamp"],
            end_time=rows[-1]["timestamp"],
            mode=rows[-1]["mode"] or "OBSERVE",
            actions=actions,
            tool_stats=tool_counts,
        )
    except sqlite3.Error:
        return None
    finally:
        conn.close()
