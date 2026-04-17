"""Tests for the SOMA Dashboard modular API layer."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
ASGITransport = httpx.ASGITransport
AsyncClient = httpx.AsyncClient

import soma.dashboard.data as data_mod
from soma.dashboard.app import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "dashboard"


@pytest.fixture
def soma_dir(tmp_path: Path) -> Path:
    """Create a temporary .soma directory with test data."""
    # Copy fixture files
    shutil.copy(FIXTURES / "state.json", tmp_path / "state.json")
    shutil.copy(FIXTURES / "circuit_cc-1001.json", tmp_path / "circuit_cc-1001.json")

    # engine_state.json
    (tmp_path / "engine_state.json").write_text(json.dumps({
        "agents": {
            "cc-1001": {
                "baseline": {"uncertainty": 0.05, "drift": 0.03},
                "level": "GUIDE",
                "action_count": 42,
            }
        },
        "graph": {
            "edges": [{"source": "cc-1001", "target": "cc-1002", "trust": 0.9}],
        },
        "learning": {"adjustments": [{"signal": "drift", "delta": 0.1}]},
    }))

    # audit log
    entries = [
        {"action_num": 10, "type": "guidance", "signal": "error_rate"},
        {"action_num": 15, "type": "throttle", "signal": "error_rate"},
    ]
    (tmp_path / "audit_cc-1001.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries)
    )

    # analytics.db
    db_path = tmp_path / "analytics.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE actions (
        timestamp REAL, agent_id TEXT, session_id TEXT, tool_name TEXT,
        pressure REAL, uncertainty REAL, drift REAL, error_rate REAL,
        context_usage REAL, token_count INTEGER, cost REAL,
        mode TEXT DEFAULT 'OBSERVE', error INTEGER DEFAULT 0
    )""")
    for i in range(5):
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (1700000000.0 + i * 60, "cc-1001", "sess-001", "Bash",
             0.2 + i * 0.05, 0.1, 0.05, 0.0, 0.3, 500, 0.01, "OBSERVE", 0),
        )
    for i in range(3):
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (1700001000.0 + i * 60, "cc-1001", "sess-002", "Read",
             0.4 + i * 0.1, 0.2, 0.1, 0.3, 0.5, 300, 0.005,
             "GUIDE", 1 if i == 0 else 0),
        )
    conn.commit()
    conn.close()

    # Patch SOMA_DIR
    data_mod.SOMA_DIR = tmp_path
    return tmp_path


@pytest.fixture
def app(soma_dir: Path):
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ------------------------------------------------------------------
# Agent endpoints
# ------------------------------------------------------------------


async def test_list_agents(client: AsyncClient):
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert isinstance(agents, list)
    assert len(agents) == 2
    ids = {a["agent_id"] for a in agents}
    assert "cc-1001" in ids


async def test_get_agent(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001")
    assert resp.status_code == 200
    agent = resp.json()
    assert agent["agent_id"] == "cc-1001"
    assert agent["level"] == "GUIDE"
    assert agent["pressure"] == 0.35
    assert "vitals" in agent


async def test_get_agent_not_found(client: AsyncClient):
    resp = await client.get("/api/agents/nonexistent")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Session endpoints
# ------------------------------------------------------------------


async def test_list_sessions(client: AsyncClient):
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert isinstance(sessions, list)
    assert len(sessions) == 2  # sess-001, sess-002


async def test_get_session_detail(client: AsyncClient):
    resp = await client.get("/api/sessions/sess-001")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["session_id"] == "sess-001"
    assert detail["action_count"] == 5
    assert "actions" in detail
    assert "tool_stats" in detail


async def test_get_session_not_found(client: AsyncClient):
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------


async def test_overview(client: AsyncClient):
    resp = await client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_agents" in data
    assert "total_sessions" in data
    assert "total_actions" in data
    assert data["total_agents"] == 2
    assert data["total_actions"] == 8  # 5 + 3


# ------------------------------------------------------------------
# Budget
# ------------------------------------------------------------------


async def test_budget(client: AsyncClient):
    resp = await client.get("/api/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["health"] == 0.85
    assert data["tokens_limit"] == 1000000
    assert data["cost_spent"] == 7.5


# ------------------------------------------------------------------
# Analytics
# ------------------------------------------------------------------


async def test_pressure_history(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/pressure-history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 8  # 5 + 3


async def test_timeline(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 8


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


async def test_tools(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    by_name = {t["tool_name"]: t for t in data}
    assert by_name["Bash"]["count"] == 5
    assert by_name["Read"]["count"] == 3


# ------------------------------------------------------------------
# Audit / guidance
# ------------------------------------------------------------------


async def test_audit(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["type"] == "guidance"


async def test_guidance_state(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/guidance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["escalation_level"] == 1
    assert data["dominant_signal"] == "error_rate"


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------


async def test_get_config(client: AsyncClient):
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ------------------------------------------------------------------
# Export
# ------------------------------------------------------------------


async def test_export_session_json(client: AsyncClient):
    resp = await client.get("/api/sessions/sess-001/export?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")


async def test_export_session_csv(client: AsyncClient):
    resp = await client.get("/api/sessions/sess-001/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


async def test_export_not_found(client: AsyncClient):
    resp = await client.get("/api/sessions/nonexistent/export?format=json")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Graph
# ------------------------------------------------------------------


async def test_graph(client: AsyncClient):
    resp = await client.get("/api/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data


# ------------------------------------------------------------------
# Quality / fingerprint
# ------------------------------------------------------------------


async def test_quality_none(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/quality")
    assert resp.status_code == 200
    # Without real quality tracker state, returns default
    data = resp.json()
    assert isinstance(data, dict)


async def test_fingerprint(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/fingerprint")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ------------------------------------------------------------------
# Baselines
# ------------------------------------------------------------------


async def test_baselines(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/baselines")
    assert resp.status_code == 200
    data = resp.json()
    assert data["uncertainty"] == 0.05
    assert data["drift"] == 0.03


# ------------------------------------------------------------------
# Learning
# ------------------------------------------------------------------


async def test_learning(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/learning")
    assert resp.status_code == 200
    data = resp.json()
    assert "adjustments" in data


# ------------------------------------------------------------------
# Findings
# ------------------------------------------------------------------


async def test_findings(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/findings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ------------------------------------------------------------------
# Predictions (was missing)
# ------------------------------------------------------------------


async def test_predictions(client: AsyncClient):
    resp = await client.get("/api/agents/cc-1001/predictions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ------------------------------------------------------------------
# Heatmap
# ------------------------------------------------------------------


async def test_heatmap(client: AsyncClient):
    resp = await client.get("/api/heatmap?agent_id=cc-1001")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
