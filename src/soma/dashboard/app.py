"""SOMA Dashboard — FastAPI backend serving agent monitoring data."""

from __future__ import annotations

import json
import time
import tomllib
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="SOMA Dashboard", version="0.2.0")

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
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _read_jsonl_tail(path: Path, n: int) -> list[dict]:
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


def _fmt_ts(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return time.strftime("%H:%M:%S", time.localtime(ts))
    except Exception:
        return None


def _agent_session_path(agent_id: str) -> Path:
    return SESSIONS_DIR / agent_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/agents")
async def list_agents() -> JSONResponse:
    """List all agents with live state from state.json + engine_state.json."""
    state = _read_json(SOMA_DIR / "state.json")
    engine = _read_json(SOMA_DIR / "engine_state.json")

    # state.json format: {"agents": {"cc-123": {level, pressure, vitals, action_count}}, "budget": ...}
    live_agents = {}
    if isinstance(state, dict):
        for aid, adata in state.get("agents", {}).items():
            live_agents[aid] = {
                "agent_id": aid,
                "level": adata.get("level", "OBSERVE"),
                "pressure": adata.get("pressure", 0.0),
                "vitals": adata.get("vitals", {}),
                "action_count": adata.get("action_count", 0),
            }

    # Enrich with engine_state data (baselines, known_tools, etc.)
    if isinstance(engine, dict):
        for aid, edata in engine.get("agents", {}).items():
            if aid not in live_agents:
                live_agents[aid] = {
                    "agent_id": aid,
                    "level": edata.get("level", "OBSERVE"),
                    "pressure": 0.0,
                    "vitals": {},
                    "action_count": edata.get("action_count", 0),
                }
            agent = live_agents[aid]
            agent["known_tools"] = edata.get("known_tools", [])
            agent["last_active"] = edata.get("last_active")
            agent["last_active_fmt"] = _fmt_ts(edata.get("last_active"))

    # Add quality grade from session files
    for aid, agent in live_agents.items():
        quality = _read_json(_agent_session_path(aid) / "quality.json")
        if quality and "events" in quality:
            events = quality["events"]
            total = len(events)
            if total > 0:
                errors = sum(1 for e in events if not e[1])
                score = 1.0 - (errors / total)
                if score >= 0.9:
                    grade = "A"
                elif score >= 0.8:
                    grade = "B"
                elif score >= 0.7:
                    grade = "C"
                elif score >= 0.5:
                    grade = "D"
                else:
                    grade = "F"
                agent["quality_grade"] = grade
                agent["quality_score"] = round(score, 2)

    # Add task phase from task_tracker
    for aid, agent in live_agents.items():
        tracker = _read_json(_agent_session_path(aid) / "task_tracker.json")
        if tracker:
            agent["phase"] = tracker.get("phase", "unknown")
            agent["scope_drift"] = tracker.get("scope_drift", 0.0)

    return JSONResponse(list(live_agents.values()))


@app.get("/api/agent/{agent_id}")
async def get_agent(agent_id: str) -> JSONResponse:
    """Detailed agent info."""
    state = _read_json(SOMA_DIR / "state.json")
    engine = _read_json(SOMA_DIR / "engine_state.json")

    agent_data: dict = {"agent_id": agent_id}

    if isinstance(state, dict):
        live = state.get("agents", {}).get(agent_id, {})
        agent_data.update(live)

    if isinstance(engine, dict):
        eng = engine.get("agents", {}).get(agent_id, {})
        agent_data["known_tools"] = eng.get("known_tools", [])
        agent_data["baseline"] = eng.get("baseline", {})
        agent_data["last_active"] = eng.get("last_active")

    if len(agent_data) <= 1:
        return JSONResponse({"error": "agent not found"}, status_code=404)

    return JSONResponse(agent_data)


@app.get("/api/agent/{agent_id}/trajectory")
async def get_trajectory(agent_id: str) -> JSONResponse:
    """Pressure trajectory for an agent."""
    data = _read_json(_agent_session_path(agent_id) / "trajectory.json", default=[])
    return JSONResponse(data)


@app.get("/api/agent/{agent_id}/actions")
async def get_actions(agent_id: str) -> JSONResponse:
    """Recent actions for an agent — enriched."""
    data = _read_json(_agent_session_path(agent_id) / "action_log.json", default=[])
    # Enrich with readable timestamps
    for entry in data:
        if "ts" in entry:
            entry["time_fmt"] = _fmt_ts(entry["ts"])
            entry["ago"] = _relative_time(entry["ts"])
    return JSONResponse(data)


@app.get("/api/agent/{agent_id}/quality")
async def get_quality(agent_id: str) -> JSONResponse:
    """Quality report for an agent."""
    quality = _read_json(_agent_session_path(agent_id) / "quality.json")
    if quality and "events" in quality:
        events = quality["events"]
        total = len(events)
        writes = sum(1 for e in events if e[0] == "write")
        bashes = sum(1 for e in events if e[0] == "bash")
        write_ok = sum(1 for e in events if e[0] == "write" and e[1])
        bash_ok = sum(1 for e in events if e[0] == "bash" and e[1])
        syntax_errors = sum(1 for e in events if e[0] == "write" and isinstance(e[2], dict) and e[2].get("syntax"))
        lint_issues = sum(1 for e in events if e[0] == "write" and isinstance(e[2], dict) and e[2].get("lint"))

        score = 1.0
        if writes + bashes > 0:
            w_score = write_ok / writes if writes else 1.0
            b_score = bash_ok / bashes if bashes else 1.0
            w_frac = writes / (writes + bashes)
            b_frac = bashes / (writes + bashes)
            score = w_frac * w_score + b_frac * b_score
            penalty = max(0.5, 1.0 - syntax_errors * 0.15)
            score = max(0, min(1, score * penalty))

        grade = "A" if score >= 0.9 else "B" if score >= 0.8 else "C" if score >= 0.7 else "D" if score >= 0.5 else "F"

        return JSONResponse({
            "grade": grade,
            "score": round(score, 3),
            "total_events": total,
            "writes": writes,
            "write_ok": write_ok,
            "bashes": bashes,
            "bash_ok": bash_ok,
            "syntax_errors": syntax_errors,
            "lint_issues": lint_issues,
        })
    return JSONResponse({"grade": "—", "score": 0, "total_events": 0})


@app.get("/api/predictions")
async def get_predictions() -> JSONResponse:
    """Predictor state across all agents."""
    results: dict[str, Any] = {}
    if SESSIONS_DIR.is_dir():
        for session_dir in SESSIONS_DIR.iterdir():
            if session_dir.is_dir() and session_dir.name.startswith("cc-"):
                pred = _read_json(session_dir / "predictor.json")
                if pred:
                    results[session_dir.name] = pred
    return JSONResponse(results)


@app.get("/api/findings")
async def get_findings() -> JSONResponse:
    """Current findings."""
    findings = _read_json(SOMA_DIR / "findings.json", default=[])
    if not findings:
        state = _read_json(SOMA_DIR / "state.json")
        if isinstance(state, dict):
            findings = state.get("findings", [])
    return JSONResponse(findings)


@app.get("/api/audit")
async def get_audit() -> JSONResponse:
    """Last 200 audit log entries — enriched."""
    entries = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 200)
    for e in entries:
        if "timestamp" in e:
            e["time_fmt"] = _fmt_ts(e["timestamp"])
    return JSONResponse(entries)


@app.get("/api/sessions")
async def get_sessions() -> JSONResponse:
    """Session history (last 50 entries) — enriched."""
    entries = _read_jsonl_tail(SOMA_DIR / "sessions" / "history.jsonl", 50)
    for e in entries:
        if "started" in e and "ended" in e:
            duration = e["ended"] - e["started"]
            mins = int(duration // 60)
            secs = int(duration % 60)
            e["duration_fmt"] = f"{mins}m {secs}s"
            e["started_fmt"] = _fmt_ts(e["started"])
        if "max_pressure" in e:
            e["max_pressure_pct"] = round(e["max_pressure"] * 100, 1)
    return JSONResponse(entries)


@app.get("/api/fingerprints")
async def get_fingerprints() -> JSONResponse:
    data = _read_json(SOMA_DIR / "fingerprint.json")
    return JSONResponse(data)


@app.get("/api/patterns")
async def get_patterns() -> JSONResponse:
    """Mirror pattern database."""
    data = _read_json(SOMA_DIR / "patterns.json")
    return JSONResponse(data)


@app.get("/api/config")
async def get_config() -> JSONResponse:
    for candidate in [Path("soma.toml"), Path.home() / "soma.toml"]:
        try:
            with candidate.open("rb") as f:
                return JSONResponse(tomllib.load(f))
        except Exception:
            continue
    return JSONResponse({})


@app.get("/api/engine")
async def get_engine() -> JSONResponse:
    data = _read_json(SOMA_DIR / "engine_state.json")
    # Summarize for dashboard (full engine state is huge)
    summary: dict[str, Any] = {}
    if isinstance(data, dict):
        agents = data.get("agents", {})
        summary["agent_count"] = len(agents)
        summary["agents"] = {}
        for aid, adata in agents.items():
            summary["agents"][aid] = {
                "action_count": adata.get("action_count", 0),
                "known_tools_count": len(adata.get("known_tools", [])),
                "level": adata.get("level", "OBSERVE"),
            }
        summary["budget"] = data.get("budget", {})
        summary["graph"] = {"node_count": len(data.get("graph", {}).get("nodes", {}))}
    return JSONResponse(summary)


@app.get("/api/overview")
async def get_overview() -> JSONResponse:
    """Single endpoint with everything the dashboard needs — reduces round trips."""
    state = _read_json(SOMA_DIR / "state.json")
    agents_raw = state.get("agents", {}) if isinstance(state, dict) else {}

    # Build agents list
    agents = []
    for aid, adata in agents_raw.items():
        agent = {
            "agent_id": aid,
            "level": adata.get("level", "OBSERVE"),
            "pressure": adata.get("pressure", 0.0),
            "pressure_pct": round(adata.get("pressure", 0.0) * 100, 1),
            "vitals": adata.get("vitals", {}),
            "action_count": adata.get("action_count", 0),
        }
        # Quality
        quality = _read_json(_agent_session_path(aid) / "quality.json")
        if quality and "events" in quality:
            events = quality["events"]
            total = len(events)
            if total > 0:
                errors = sum(1 for e in events if not e[1])
                score = 1.0 - (errors / total)
                grade = "A" if score >= 0.9 else "B" if score >= 0.8 else "C" if score >= 0.7 else "D" if score >= 0.5 else "F"
                agent["quality_grade"] = grade
            else:
                agent["quality_grade"] = "—"
        else:
            agent["quality_grade"] = "—"
        agents.append(agent)

    # Audit (last 50)
    audit = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 50)
    for e in audit:
        if "timestamp" in e:
            e["time_fmt"] = _fmt_ts(e["timestamp"])

    # Sessions (last 20)
    sessions = _read_jsonl_tail(SOMA_DIR / "sessions" / "history.jsonl", 20)
    for e in sessions:
        if "started" in e and "ended" in e:
            d = e["ended"] - e["started"]
            e["duration_fmt"] = f"{int(d//60)}m {int(d%60)}s"
        if "max_pressure" in e:
            e["max_pressure_pct"] = round(e["max_pressure"] * 100, 1)

    return JSONResponse({
        "agents": agents,
        "audit": audit,
        "sessions": sessions,
        "budget": state.get("budget", {}) if isinstance(state, dict) else {},
    })


# ---------------------------------------------------------------------------
# Helpers (continued)
# ---------------------------------------------------------------------------

def _relative_time(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60:
        return f"{int(diff)}s ago"
    elif diff < 3600:
        return f"{int(diff // 60)}m ago"
    elif diff < 86400:
        return f"{int(diff // 3600)}h ago"
    else:
        return f"{int(diff // 86400)}d ago"


# ---------------------------------------------------------------------------
# Static files (frontend) — mounted last so API routes take priority
# ---------------------------------------------------------------------------

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
