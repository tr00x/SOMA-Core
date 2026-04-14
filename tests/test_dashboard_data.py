"""Tests for the dashboard data layer."""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from soma.dashboard.data import get_live_agents, get_all_sessions
from soma.dashboard.types import AgentSnapshot, SessionSummary

FIXTURES = Path(__file__).parent / "fixtures" / "dashboard"


@pytest.fixture
def soma_dir(tmp_path, monkeypatch):
    """Set up a fake ~/.soma with fixture data."""
    shutil.copy(FIXTURES / "state.json", tmp_path / "state.json")
    shutil.copy(FIXTURES / "circuit_cc-1001.json", tmp_path / "circuit_cc-1001.json")
    monkeypatch.setattr("soma.dashboard.data.SOMA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def analytics_db(soma_dir):
    """Create a test analytics.db with sample session data."""
    db_path = soma_dir / "analytics.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE actions (
            timestamp REAL, agent_id TEXT, session_id TEXT, tool_name TEXT,
            pressure REAL, uncertainty REAL, drift REAL, error_rate REAL,
            context_usage REAL, token_count INTEGER, cost REAL,
            mode TEXT DEFAULT 'OBSERVE', error INTEGER DEFAULT 0
        )
    """)

    now = time.time()

    # Session 1: 5 Bash actions by cc-1001, pressures 0.2-0.4, no errors
    for i in range(5):
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now - 3600 + i * 60, "cc-1001", "sess-001", "Bash",
             0.2 + i * 0.05, 0.1, 0.05, 0.0, 0.3, 500, 0.01, "OBSERVE", 0),
        )

    # Session 2: 3 Read actions by cc-1001, pressures 0.4-0.6, 1 error
    for i in range(3):
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now - 1800 + i * 60, "cc-1001", "sess-002", "Read",
             0.4 + i * 0.1, 0.2, 0.1, 0.1, 0.4, 300, 0.005,
             "GUIDE", 1 if i == 0 else 0),
        )

    # Session 3: 2 Grep actions by cc-1002, pressure 0.1, no errors
    for i in range(2):
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now - 600 + i * 60, "cc-1002", "sess-003", "Grep",
             0.1, 0.05, 0.02, 0.0, 0.1, 200, 0.002, "OBSERVE", 0),
        )

    conn.commit()
    conn.close()
    return db_path


# ------------------------------------------------------------------
# get_live_agents tests
# ------------------------------------------------------------------


def test_get_live_agents_returns_all(soma_dir):
    agents = get_live_agents()
    assert len(agents) == 2
    assert all(isinstance(a, AgentSnapshot) for a in agents)


def test_get_live_agents_fields_correct(soma_dir):
    agents = {a.agent_id: a for a in get_live_agents()}

    a1 = agents["cc-1001"]
    assert a1.display_name == "SOMA-Core #1"
    assert a1.level == "GUIDE"
    assert a1.pressure == 0.35
    assert a1.action_count == 42
    assert a1.vitals["error_rate"] == 0.4
    assert a1.escalation_level == 1
    assert a1.dominant_signal == "error_rate"
    assert a1.throttled_tool == ""


def test_get_live_agents_without_circuit_file(soma_dir):
    agents = {a.agent_id: a for a in get_live_agents()}
    a2 = agents["cc-1002"]
    assert a2.escalation_level == 0
    assert a2.dominant_signal == ""


def test_get_live_agents_empty_state(soma_dir):
    (soma_dir / "state.json").unlink()
    assert get_live_agents() == []


# ------------------------------------------------------------------
# get_all_sessions tests
# ------------------------------------------------------------------


def test_get_all_sessions_returns_all(analytics_db):
    sessions = get_all_sessions()
    assert len(sessions) == 3
    assert all(isinstance(s, SessionSummary) for s in sessions)


def test_get_all_sessions_fields_correct(analytics_db):
    sessions = {s.session_id: s for s in get_all_sessions()}

    s1 = sessions["sess-001"]
    assert s1.action_count == 5
    assert s1.error_count == 0
    assert s1.total_tokens == 2500  # 5 * 500
    assert s1.agent_id == "cc-1001"
    assert s1.start_time < s1.end_time

    s2 = sessions["sess-002"]
    assert s2.action_count == 3
    assert s2.error_count == 1
    assert s2.total_tokens == 900  # 3 * 300

    s3 = sessions["sess-003"]
    assert s3.action_count == 2
    assert s3.error_count == 0
    assert s3.total_tokens == 400  # 2 * 200


def test_get_all_sessions_no_db(soma_dir):
    """Without analytics.db, returns empty list."""
    assert get_all_sessions() == []
