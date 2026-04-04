"""SOMA Dashboard SSE — Server-Sent Events hub for real-time updates.

Reads SOMA state files on a configurable interval and pushes typed events
to connected clients. Falls back gracefully when state files are missing.

Event types:
  agents  — full agent list with vitals (every tick)
  budget  — budget health, spent, limits (every tick)
  alert   — mode changes, escalations (on change detection)
  reflex  — reflex trigger events (on change detection)
  finding — new findings detected (on change detection)
  rca     — new RCA diagnosis (on change detection)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import StreamingResponse


SOMA_DIR = Path.home() / ".soma"
SESSIONS_DIR = SOMA_DIR / "sessions"

DEFAULT_INTERVAL = 2.0  # seconds


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


def _agent_session_path(agent_id: str) -> Path:
    return SESSIONS_DIR / agent_id


def _compute_quality_grade(events: list) -> dict[str, Any]:
    """Compute quality grade and score from quality events list."""
    total = len(events)
    if total == 0:
        return {"grade": "-", "score": 0.0}
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
    return {"grade": grade, "score": round(score, 3)}


def _build_agents_payload(state: dict) -> list[dict]:
    """Build agents payload from state.json data."""
    agents_raw = state.get("agents", {}) if isinstance(state, dict) else {}
    agents = []
    for aid, adata in agents_raw.items():
        agent: dict[str, Any] = {
            "agent_id": aid,
            "level": adata.get("level", "OBSERVE"),
            "pressure": adata.get("pressure", 0.0),
            "pressure_pct": round(adata.get("pressure", 0.0) * 100, 1),
            "vitals": adata.get("vitals", {}),
            "action_count": adata.get("action_count", 0),
        }
        # Quality grade
        quality = _read_json(_agent_session_path(aid) / "quality.json")
        if quality and "events" in quality:
            q = _compute_quality_grade(quality["events"])
            agent["quality_grade"] = q["grade"]
        else:
            agent["quality_grade"] = "-"

        # Task phase (compute from raw tools — not persisted by task_tracker)
        tracker = _read_json(_agent_session_path(aid) / "task_tracker.json")
        if tracker:
            phase = tracker.get("phase") or "unknown"
            if phase in ("unknown", "?", None):
                tools = tracker.get("all_tools", [])[-10:]
                if tools:
                    pm = {"research": {"Read","Grep","Glob","WebSearch","WebFetch"}, "implement": {"Write","Edit","NotebookEdit"}, "test": {"Bash"}}
                    sc = {p: sum(1 for t in tools if t in ts) for p, ts in pm.items()}
                    errs = tracker.get("all_errors", [])[-10:]
                    if len(errs) >= 3 and sum(1 for e in errs if e) / len(errs) > 0.3:
                        phase = "debug"
                    elif any(sc.values()):
                        phase = max(sc, key=sc.get)
            agent["phase"] = phase

        agents.append(agent)
    return agents


def _build_budget_payload(state: dict) -> dict[str, Any]:
    """Build budget payload from state.json data."""
    budget = state.get("budget", {}) if isinstance(state, dict) else {}
    if not budget:
        return {}
    limits = budget.get("limits", {})
    spent = budget.get("spent", {})
    return {
        "health": budget.get("health", 1.0),
        "health_pct": round(budget.get("health", 1.0) * 100, 1),
        "limits": limits,
        "spent": spent,
        "remaining": {k: limits.get(k, 0) - spent.get(k, 0) for k in limits},
    }


def _format_sse(event: str, data: Any) -> str:
    """Format a single SSE message."""
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

async def event_stream(
    request: Request,
    interval: float = DEFAULT_INTERVAL,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events at *interval* seconds.

    Tracks previous state to detect changes and emit alert/reflex/finding/rca
    events only when something new appears.
    """
    prev_modes: dict[str, str] = {}
    prev_findings_count = 0
    prev_reflex_log_size = 0
    prev_rca: dict[str, str] = {}  # agent_id -> last diagnosis text

    while True:
        # Check for client disconnect
        if await request.is_disconnected():
            break

        state = _read_json(SOMA_DIR / "state.json")

        # -- agents event (every tick) --
        agents = _build_agents_payload(state)
        yield _format_sse("agents", agents)

        # -- budget event (every tick) --
        budget = _build_budget_payload(state)
        if budget:
            yield _format_sse("budget", budget)

        # -- alert event (mode changes) --
        for agent in agents:
            aid = agent["agent_id"]
            current_mode = agent["level"]
            if aid in prev_modes and prev_modes[aid] != current_mode:
                yield _format_sse("alert", {
                    "type": "mode_change",
                    "agent_id": aid,
                    "from": prev_modes[aid],
                    "to": current_mode,
                    "pressure": agent["pressure"],
                    "timestamp": time.time(),
                })
            prev_modes[aid] = current_mode

        # -- findings event (full list, replaces client state) --
        findings = _read_json(SOMA_DIR / "findings.json", default=[])
        if not findings and isinstance(state, dict):
            findings = state.get("findings", [])
        if isinstance(findings, list) and findings:
            yield _format_sse("findings", findings)

        # -- rca event (check per-agent RCA) --
        agents_raw = state.get("agents", {}) if isinstance(state, dict) else {}
        for aid in agents_raw:
            try:
                from soma.rca import diagnose
                agent_state = agents_raw[aid]
                action_log = _read_json(
                    _agent_session_path(aid) / "action_log.json", default=[]
                )
                vitals = agent_state.get("vitals", {})
                pressure = agent_state.get("pressure", 0.0)
                level = agent_state.get("level", "OBSERVE")
                action_count = agent_state.get("action_count", 0)
                diag = diagnose(action_log, vitals, pressure, level, action_count)
                if diag and diag != prev_rca.get(aid):
                    prev_rca[aid] = diag
                    yield _format_sse("rca", {
                        "agent_id": aid,
                        "diagnosis": diag,
                        "timestamp": time.time(),
                    })
            except Exception:
                pass

        # -- reflex event (check reflex log growth) --
        reflex_log = _read_json(SOMA_DIR / "reflex_log.json", default=[])
        if isinstance(reflex_log, list) and len(reflex_log) > prev_reflex_log_size:
            new_reflexes = reflex_log[prev_reflex_log_size:]
            for r in new_reflexes:
                yield _format_sse("reflex", r)
            prev_reflex_log_size = len(reflex_log)

        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# SSE endpoint handler
# ---------------------------------------------------------------------------

async def sse_endpoint(request: Request) -> StreamingResponse:
    """FastAPI/Starlette endpoint handler for GET /api/stream."""
    return StreamingResponse(
        event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
