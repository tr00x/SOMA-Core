"""SOMA Dashboard — FastAPI backend serving agent monitoring data."""

from __future__ import annotations

import json
import tomllib
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="SOMA Dashboard", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SOMA_DIR = Path.home() / ".soma"
SESSIONS_DIR = SOMA_DIR / "sessions"
STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON file, returning *default* on any failure."""
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _read_jsonl_tail(path: Path, n: int) -> list[dict]:
    """Return the last *n* objects from a JSONL file."""
    try:
        lines: deque[str] = deque(maxlen=n)
        with path.open() as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
        return [json.loads(line) for line in lines]
    except Exception:
        return []


def _agent_session_path(agent_id: str) -> Path:
    return SESSIONS_DIR / agent_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/agents")
async def list_agents() -> JSONResponse:
    """List all agents with current state."""
    state = _read_json(SOMA_DIR / "state.json")
    engine = _read_json(SOMA_DIR / "engine_state.json")

    agents: list[dict] = []

    # Try engine state first — it has per-agent detail
    if isinstance(engine, dict):
        agent_states = engine.get("agents", {})
        for aid, adata in agent_states.items():
            agents.append({"agent_id": aid, **adata})

    # Fallback: if state.json has agent info and engine didn't
    if not agents and isinstance(state, dict):
        for key, val in state.items():
            if isinstance(val, dict) and "agent_id" in val:
                agents.append(val)

    return JSONResponse(agents)


@app.get("/api/agent/{agent_id}")
async def get_agent(agent_id: str) -> JSONResponse:
    """Detailed agent info including vitals, pressure, mode."""
    engine = _read_json(SOMA_DIR / "engine_state.json")

    agent_data: dict = {}
    if isinstance(engine, dict):
        agent_data = engine.get("agents", {}).get(agent_id, {})

    if not agent_data:
        # Try session directory
        session_dir = _agent_session_path(agent_id)
        agent_data = _read_json(session_dir / "state.json")

    if not agent_data:
        return JSONResponse({"error": "agent not found", "agent_id": agent_id}, status_code=404)

    return JSONResponse({"agent_id": agent_id, **agent_data})


@app.get("/api/agent/{agent_id}/trajectory")
async def get_trajectory(agent_id: str) -> JSONResponse:
    """Pressure trajectory for an agent."""
    path = _agent_session_path(agent_id) / "trajectory.json"
    data = _read_json(path, default=[])
    return JSONResponse(data)


@app.get("/api/agent/{agent_id}/actions")
async def get_actions(agent_id: str) -> JSONResponse:
    """Recent actions for an agent."""
    path = _agent_session_path(agent_id) / "action_log.json"
    data = _read_json(path, default=[])
    return JSONResponse(data)


@app.get("/api/agent/{agent_id}/quality")
async def get_quality(agent_id: str) -> JSONResponse:
    """Quality report for an agent."""
    path = _agent_session_path(agent_id) / "quality.json"
    data = _read_json(path)
    return JSONResponse(data)


@app.get("/api/predictions")
async def get_predictions() -> JSONResponse:
    """Predictor state across all agents."""
    results: dict[str, Any] = {}
    if SESSIONS_DIR.is_dir():
        for session_dir in SESSIONS_DIR.iterdir():
            if session_dir.is_dir():
                pred = _read_json(session_dir / "predictor.json")
                if pred:
                    results[session_dir.name] = pred
    return JSONResponse(results)


@app.get("/api/findings")
async def get_findings() -> JSONResponse:
    """Current findings."""
    # Try reading cached findings first
    findings = _read_json(SOMA_DIR / "findings.json", default=[])
    if not findings:
        # Try state.json findings key
        state = _read_json(SOMA_DIR / "state.json")
        if isinstance(state, dict):
            findings = state.get("findings", [])
    return JSONResponse(findings)


@app.get("/api/audit")
async def get_audit() -> JSONResponse:
    """Last 100 audit log entries."""
    entries = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 100)
    return JSONResponse(entries)


@app.get("/api/sessions")
async def get_sessions() -> JSONResponse:
    """Session history (last 50 entries)."""
    entries = _read_jsonl_tail(SOMA_DIR / "sessions" / "history.jsonl", 50)
    return JSONResponse(entries)


@app.get("/api/fingerprints")
async def get_fingerprints() -> JSONResponse:
    """Behavioral fingerprints."""
    data = _read_json(SOMA_DIR / "fingerprint.json")
    return JSONResponse(data)


@app.get("/api/config")
async def get_config() -> JSONResponse:
    """Current soma.toml config."""
    # Look in cwd first, then home
    for candidate in [Path("soma.toml"), Path.home() / "soma.toml"]:
        try:
            with candidate.open("rb") as f:
                return JSONResponse(tomllib.load(f))
        except Exception:
            continue
    return JSONResponse({})


@app.get("/api/engine")
async def get_engine() -> JSONResponse:
    """Engine state summary."""
    data = _read_json(SOMA_DIR / "engine_state.json")
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# Static files (frontend) — mounted last so API routes take priority
# ---------------------------------------------------------------------------

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
