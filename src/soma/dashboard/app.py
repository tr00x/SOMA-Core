"""SOMA Dashboard — FastAPI backend serving agent monitoring data.

Organized by domain:
  1. Helpers — shared file I/O, formatting, quality computation
  2. Agent endpoints — per-agent state, vitals, trajectory, quality
  3. Agent subsystem endpoints — reflexes, RCA, mirror, context, capacity, etc.
  4. Subagent endpoints — subagent matrix, cascade risk
  5. Overview & engine — combined overview, engine summary
  6. Config endpoints — read/write soma.toml, defaults
  7. Settings endpoints — granular PATCH for mode, thresholds, weights, etc.
  8. Session endpoints — session list, replay, report, record
  9. Analytics endpoints — trends, tool stats, threshold tuner
  10. Policy endpoints — rule catalog CRUD
  11. Export endpoints — CSV/JSON downloads, heatmap
  12. LLM endpoints — semantic analysis via external API
  13. Predictions, findings, fingerprints, patterns
  14. SSE — mounted from sse.py
  15. Static files — mounted last for frontend
"""

from __future__ import annotations

import csv
import io
import json
import time
import tomllib
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

app = FastAPI(title="SOMA Dashboard", version="0.3.0")

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


# ===================================================================
# 1. Helpers
# ===================================================================

def _read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON file, returning *default* on any failure."""
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _read_jsonl_tail(path: Path, n: int) -> list[dict]:
    """Read the last *n* lines from a JSONL file."""
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
    """Format a unix timestamp as HH:MM:SS."""
    if ts is None:
        return None
    try:
        return time.strftime("%H:%M:%S", time.localtime(ts))
    except Exception:
        return None


def _relative_time(ts: float) -> str:
    """Human-readable relative time string."""
    diff = time.time() - ts
    if diff < 60:
        return f"{int(diff)}s ago"
    elif diff < 3600:
        return f"{int(diff // 60)}m ago"
    elif diff < 86400:
        return f"{int(diff // 3600)}h ago"
    else:
        return f"{int(diff // 86400)}d ago"


def _agent_session_path(agent_id: str) -> Path:
    """Return the session directory for an agent."""
    return SESSIONS_DIR / agent_id


def _compute_quality(events: list) -> dict[str, Any]:
    """Compute quality grade and score from quality tracker events."""
    total = len(events)
    if total == 0:
        return {"grade": "-", "score": 0.0, "total": 0, "errors": 0}
    errors = sum(1 for e in events if not e[1])
    writes = sum(1 for e in events if e[0] == "write")
    bashes = sum(1 for e in events if e[0] == "bash")
    write_ok = sum(1 for e in events if e[0] == "write" and e[1])
    bash_ok = sum(1 for e in events if e[0] == "bash" and e[1])
    syntax_errors = sum(
        1 for e in events
        if e[0] == "write" and isinstance(e[2], dict) and e[2].get("syntax")
    )
    lint_issues = sum(
        1 for e in events
        if e[0] == "write" and isinstance(e[2], dict) and e[2].get("lint")
    )

    score = 1.0
    if writes + bashes > 0:
        w_score = write_ok / writes if writes else 1.0
        b_score = bash_ok / bashes if bashes else 1.0
        w_frac = writes / (writes + bashes)
        b_frac = bashes / (writes + bashes)
        score = w_frac * w_score + b_frac * b_score
        penalty = max(0.5, 1.0 - syntax_errors * 0.15)
        score = max(0, min(1, score * penalty))

    grade = (
        "A" if score >= 0.9 else
        "B" if score >= 0.8 else
        "C" if score >= 0.7 else
        "D" if score >= 0.5 else
        "F"
    )
    return {
        "grade": grade,
        "score": round(score, 3),
        "total": total,
        "errors": errors,
        "writes": writes,
        "write_ok": write_ok,
        "write_fail": writes - write_ok,
        "bashes": bashes,
        "bash_ok": bash_ok,
        "bash_fail": bashes - bash_ok,
        "syntax_errors": syntax_errors,
        "lint_issues": lint_issues,
    }


def _quality_grade_only(events: list) -> str:
    """Return just the letter grade from quality events."""
    total = len(events)
    if total == 0:
        return "-"
    errors = sum(1 for e in events if not e[1])
    score = 1.0 - (errors / total)
    return (
        "A" if score >= 0.9 else
        "B" if score >= 0.8 else
        "C" if score >= 0.7 else
        "D" if score >= 0.5 else
        "F"
    )


def _enrich_actions(entries: list[dict]) -> list[dict]:
    """Add time_fmt and ago fields to action log entries."""
    for entry in entries:
        if "ts" in entry:
            entry["time_fmt"] = _fmt_ts(entry["ts"])
            entry["ago"] = _relative_time(entry["ts"])
    return entries


def _read_config() -> tuple[Path, dict]:
    """Read soma.toml config from CWD or home directory."""
    for candidate in [Path("soma.toml"), Path.home() / "soma.toml"]:
        if candidate.exists():
            with candidate.open("rb") as f:
                return candidate, tomllib.load(f)
    return Path("soma.toml"), {}


def _write_config(path: Path, data: dict) -> None:
    """Write config dict as TOML to path."""
    import tomli_w
    path.write_text(tomli_w.dumps(data))


def _get_agent_state(agent_id: str) -> dict[str, Any]:
    """Load live agent state from state.json."""
    state = _read_json(SOMA_DIR / "state.json")
    if isinstance(state, dict):
        return state.get("agents", {}).get(agent_id, {})
    return {}


def _get_engine_agent(agent_id: str) -> dict[str, Any]:
    """Load agent data from engine_state.json."""
    engine = _read_json(SOMA_DIR / "engine_state.json")
    if isinstance(engine, dict):
        return engine.get("agents", {}).get(agent_id, {})
    return {}


# ===================================================================
# 2. Agent endpoints
# ===================================================================

@app.get("/api/agents")
async def list_agents() -> JSONResponse:
    """List all agents with live state from state.json + engine_state.json."""
    state = _read_json(SOMA_DIR / "state.json")
    engine = _read_json(SOMA_DIR / "engine_state.json")

    live_agents: dict[str, dict] = {}

    # Build from state.json
    if isinstance(state, dict):
        for aid, adata in state.get("agents", {}).items():
            live_agents[aid] = {
                "agent_id": aid,
                "level": adata.get("level", "OBSERVE"),
                "pressure": adata.get("pressure", 0.0),
                "vitals": adata.get("vitals", {}),
                "action_count": adata.get("action_count", 0),
            }

    # Enrich from engine_state.json
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

    # Enrich with quality + task phase from session files
    for aid, agent in live_agents.items():
        quality = _read_json(_agent_session_path(aid) / "quality.json")
        if quality and "events" in quality:
            q = _compute_quality(quality["events"])
            agent["quality_grade"] = q["grade"]
            agent["quality_score"] = q["score"]
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
            agent["scope_drift"] = tracker.get("scope_drift", 0.0)

    return JSONResponse(list(live_agents.values()))


@app.get("/api/agent/{agent_id}")
async def get_agent(agent_id: str) -> JSONResponse:
    """Detailed agent info."""
    state = _read_json(SOMA_DIR / "state.json")
    engine = _read_json(SOMA_DIR / "engine_state.json")

    agent_data: dict[str, Any] = {"agent_id": agent_id}

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

    # Enrich with calibration data from reliability module
    # Calibration from vitals (hedging not persisted, derive what we can)
    vitals = agent_data.get("vitals", {})
    err_rate = vitals.get("error_rate", 0.0)
    pressure = agent_data.get("pressure", 0.0)
    cal_score = vitals.get("calibration_score")
    if cal_score is None:
        cal_score = max(0, (1 - err_rate) * 0.75)  # approximation without hedging
    vbd = vitals.get("verbal_behavioral_divergence", pressure > 0.4 and err_rate < 0.1)
    agent_data["calibration"] = {
        "score": round(cal_score, 3),
        "hedging_rate": vitals.get("hedging_rate", 0.0),
        "error_rate": err_rate,
        "verbal_behavioral_divergence": bool(vbd),
        "uncertainty_type": vitals.get("uncertainty_type"),
    }

    # Enrich with baseline health
    try:
        baseline = agent_data.get("baseline", {})
        vitals = agent_data.get("vitals", {})
        integrity = vitals.get("baseline_integrity", True)
        warmup_count = min(baseline.get("count", {}).values()) if baseline.get("count") else 0
        min_samples = baseline.get("min_samples", 10)
        agent_data["baseline_health"] = {
            "integrity": integrity,
            "warmup_progress": min(1.0, warmup_count / max(min_samples, 1)),
            "signals": {k: {"ema": baseline.get("value", {}).get(k, 0), "current": vitals.get(k, 0)} for k in ["uncertainty", "drift", "error_rate"]},
        }
    except Exception:
        agent_data["baseline_health"] = {}

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
    _enrich_actions(data)
    return JSONResponse(data)


@app.get("/api/agent/{agent_id}/quality")
async def get_quality(agent_id: str) -> JSONResponse:
    """Quality report for an agent."""
    quality = _read_json(_agent_session_path(agent_id) / "quality.json")
    if quality and "events" in quality:
        return JSONResponse(_compute_quality(quality["events"]))
    return JSONResponse({"grade": "-", "score": 0, "total": 0})


@app.get("/api/agent/{agent_id}/vitals-history")
async def get_vitals_history(agent_id: str) -> JSONResponse:
    """Vitals over time for charting individual signals."""
    try:
        session = _agent_session_path(agent_id)
        trajectory = _read_json(session / "trajectory.json", default=[])
        points: list[dict] = []
        for idx, entry in enumerate(trajectory, 1):
            if isinstance(entry, dict):
                vitals = entry.get("vitals", entry)
                points.append({
                    "idx": idx,
                    "pressure": entry.get("pressure", vitals.get("pressure", 0.0)),
                    "uncertainty": vitals.get("uncertainty", 0.0),
                    "drift": vitals.get("drift", 0.0),
                    "error_rate": vitals.get("error_rate", 0.0),
                    "cost": vitals.get("cost", 0.0),
                    "token_usage": vitals.get("token_usage", 0.0),
                })
            elif isinstance(entry, (int, float)):
                points.append({"idx": idx, "pressure": float(entry)})

        # Append current vitals from state.json if available
        agent_state = _get_agent_state(agent_id)
        current_vitals = agent_state.get("vitals", {})
        if current_vitals and (not points or points[-1].get("pressure") != agent_state.get("pressure")):
            points.append({
                "idx": len(points) + 1,
                "pressure": agent_state.get("pressure", 0.0),
                "uncertainty": current_vitals.get("uncertainty", 0.0),
                "drift": current_vitals.get("drift", 0.0),
                "error_rate": current_vitals.get("error_rate", 0.0),
                "cost": current_vitals.get("cost", 0.0),
                "token_usage": current_vitals.get("token_usage", 0.0),
            })

        return JSONResponse({"points": points})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/agent/{agent_id}/quality-breakdown")
async def get_quality_breakdown(agent_id: str) -> JSONResponse:
    """Quality stats for charting."""
    try:
        quality = _read_json(_agent_session_path(agent_id) / "quality.json")
        if not quality or "events" not in quality:
            return JSONResponse({
                "total": 0, "writes": 0, "write_ok": 0, "write_fail": 0,
                "bashes": 0, "bash_ok": 0, "bash_fail": 0,
                "syntax_errors": 0, "lint_issues": 0, "score": 0.0, "grade": "-",
            })
        return JSONResponse(_compute_quality(quality["events"]))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/agent/{agent_id}/detail")
async def get_agent_detail(agent_id: str) -> JSONResponse:
    """Full agent detail — everything about one agent."""
    try:
        session = _agent_session_path(agent_id)
        result: dict[str, Any] = {"agent_id": agent_id}

        # Live state
        agent_state = _get_agent_state(agent_id)
        result["vitals"] = agent_state.get("vitals", {})
        result["pressure"] = agent_state.get("pressure", 0.0)
        result["level"] = agent_state.get("level", "OBSERVE")
        result["action_count"] = agent_state.get("action_count", 0)

        # Engine state
        eng = _get_engine_agent(agent_id)
        result["known_tools"] = eng.get("known_tools", [])
        result["baseline"] = eng.get("baseline", {})
        result["last_active"] = eng.get("last_active")
        result["last_active_fmt"] = _fmt_ts(eng.get("last_active"))

        # Trajectory (last 50)
        trajectory = _read_json(session / "trajectory.json", default=[])
        result["trajectory"] = trajectory[-50:]

        # Recent actions (last 20)
        action_log = _read_json(session / "action_log.json", default=[])
        result["recent_actions"] = _enrich_actions(action_log[-20:])

        # Quality
        quality = _read_json(session / "quality.json")
        if quality and "events" in quality:
            result["quality"] = _compute_quality(quality["events"])

        # Predictor
        predictor = _read_json(session / "predictor.json")
        if predictor:
            result["predictor"] = predictor

        # Task tracker
        tracker = _read_json(session / "task_tracker.json")
        if tracker:
            result["task"] = tracker

        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===================================================================
# 3. Agent subsystem endpoints (new)
# ===================================================================

@app.get("/api/agent/{agent_id}/reflexes")
async def get_agent_reflexes(agent_id: str) -> JSONResponse:
    """Reflex trigger history from audit.jsonl."""
    try:
        entries = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 500)
        reflexes = [
            {
                "timestamp": e.get("timestamp"),
                "time_fmt": _fmt_ts(e.get("timestamp")),
                "tool_name": e.get("tool_name"),
                "kind": e.get("reflex_kind"),
                "blocked": bool(e.get("blocked")),
                "action": e.get("reflex_action", "inject"),
            }
            for e in entries
            if isinstance(e, dict)
            and e.get("agent_id") == agent_id
            and e.get("reflex_kind")
        ]
        return JSONResponse(reflexes[-50:])  # last 50 reflex events
    except Exception:
        return JSONResponse([])


@app.get("/api/agent/{agent_id}/rca")
async def get_agent_rca(agent_id: str) -> JSONResponse:
    """Current + past RCA diagnoses for an agent."""
    try:
        from soma.rca import diagnose
    except ImportError:
        return JSONResponse({"current": None, "history": []})

    try:
        agent_state = _get_agent_state(agent_id)
        action_log = _read_json(
            _agent_session_path(agent_id) / "action_log.json", default=[]
        )
        vitals = agent_state.get("vitals", {})
        pressure = agent_state.get("pressure", 0.0)
        level = agent_state.get("level", "OBSERVE")
        action_count = agent_state.get("action_count", 0)

        current = diagnose(action_log, vitals, pressure, level, action_count)

        # Load RCA history if stored
        rca_history = _read_json(
            _agent_session_path(agent_id) / "rca_history.json", default=[]
        )

        return JSONResponse({
            "current": current,
            "pressure": pressure,
            "level": level,
            "history": rca_history if isinstance(rca_history, list) else [],
        })
    except Exception:
        return JSONResponse({"current": None, "history": []})


@app.get("/api/agent/{agent_id}/mirror")
async def get_agent_mirror(agent_id: str) -> JSONResponse:
    """Mirror pattern DB + effectiveness stats for an agent."""
    try:
        # Load pattern database
        patterns = _read_json(SOMA_DIR / "patterns.json")
        agent_patterns: dict[str, Any] = {}
        if isinstance(patterns, dict):
            # Filter to agent-specific patterns if keyed by agent
            if agent_id in patterns:
                agent_patterns = patterns[agent_id]
            else:
                agent_patterns = patterns

        # Load mirror stats from session
        mirror_stats = _read_json(
            _agent_session_path(agent_id) / "mirror_stats.json"
        )

        return JSONResponse({
            "patterns": agent_patterns,
            "stats": mirror_stats if mirror_stats else {},
        })
    except Exception:
        return JSONResponse({"patterns": {}, "stats": {}})


@app.get("/api/agent/{agent_id}/context")
async def get_agent_context(agent_id: str) -> JSONResponse:
    """Context control state — tools available at current mode, retention %."""
    try:
        agent_state = _get_agent_state(agent_id)
        level = agent_state.get("level", "OBSERVE")

        # Compute retention and tool availability based on mode
        retention_pct = {
            "OBSERVE": 100,
            "GUIDE": 80,
            "WARN": 50,
            "BLOCK": 0,
        }.get(level, 100)

        eng = _get_engine_agent(agent_id)
        all_tools = eng.get("known_tools", [])

        return JSONResponse({
            "level": level,
            "retention_pct": retention_pct,
            "tools_available": all_tools,
            "tools_total": len(all_tools),
        })
    except Exception:
        return JSONResponse({"level": "OBSERVE", "retention_pct": 100, "tools_available": [], "tools_total": 0})


@app.get("/api/agent/{agent_id}/session-memory")
async def get_agent_session_memory(agent_id: str) -> JSONResponse:
    """Similar session match from session memory."""
    try:
        from soma.session_memory import find_similar_session
        from soma.session_store import load_sessions
    except ImportError:
        return JSONResponse({"match": None, "similarity": 0.0})

    try:
        sessions = load_sessions()
        if not sessions:
            return JSONResponse({"match": None, "similarity": 0.0})

        # Build current tool distribution from action log
        action_log = _read_json(
            _agent_session_path(agent_id) / "action_log.json", default=[]
        )
        current_tools: dict[str, int] = {}
        for entry in action_log:
            tool = entry.get("tool", entry.get("tool_name", "unknown"))
            current_tools[tool] = current_tools.get(tool, 0) + 1

        if not current_tools:
            return JSONResponse({"match": None, "similarity": 0.0})

        match, sim = find_similar_session(current_tools, sessions)
        if match is None:
            return JSONResponse({"match": None, "similarity": 0.0})

        from dataclasses import asdict
        return JSONResponse({
            "match": asdict(match),
            "similarity": round(sim, 3),
        })
    except Exception:
        return JSONResponse({"match": None, "similarity": 0.0})


@app.get("/api/agent/{agent_id}/capacity")
async def get_agent_capacity(agent_id: str) -> JSONResponse:
    """Session capacity from planner module."""
    try:
        from soma.planner import compute_session_capacity
    except ImportError:
        return JSONResponse({})

    try:
        agent_state = _get_agent_state(agent_id)
        pressure = agent_state.get("pressure", 0.0)
        action_count = agent_state.get("action_count", 0)
        vitals = agent_state.get("vitals", {})
        error_rate = vitals.get("error_rate", 0.0)

        capacity = compute_session_capacity(
            current_pressure=pressure,
            action_count=action_count,
            avg_error_rate=error_rate,
        )
        return JSONResponse(capacity)
    except Exception:
        return JSONResponse({})


@app.get("/api/agent/{agent_id}/circuit-breaker")
async def get_agent_circuit_breaker(agent_id: str) -> JSONResponse:
    """Circuit breaker state for an agent."""
    try:
        # Circuit breaker state is stored in engine state
        engine = _read_json(SOMA_DIR / "engine_state.json")
        if isinstance(engine, dict):
            cb_states = engine.get("circuit_breakers", {})
            cb = cb_states.get(agent_id, {})
            if cb:
                return JSONResponse(cb)

        # Fallback: default closed state
        agent_state = _get_agent_state(agent_id)
        return JSONResponse({
            "agent_id": agent_id,
            "consecutive_block": 0,
            "consecutive_observe": 0,
            "is_open": False,
            "level": agent_state.get("level", "OBSERVE"),
        })
    except Exception:
        return JSONResponse({
            "agent_id": agent_id,
            "consecutive_block": 0,
            "consecutive_observe": 0,
            "is_open": False,
        })


@app.get("/api/agent/{agent_id}/scope")
async def get_agent_scope(agent_id: str) -> JSONResponse:
    """Scope drift detail from task tracker."""
    try:
        tracker = _read_json(_agent_session_path(agent_id) / "task_tracker.json")
        if not tracker:
            return JSONResponse({"drift_score": 0.0})

        # Compute phase from raw tool data (not persisted by task_tracker)
        phase = tracker.get("phase") or "unknown"
        if phase in ("unknown", "?", None):
            tools = tracker.get("all_tools", [])[-10:]
            if tools:
                phase_map = {"research": {"Read","Grep","Glob","WebSearch","WebFetch"}, "implement": {"Write","Edit","NotebookEdit"}, "test": {"Bash"}}
                scores = {p: sum(1 for t in tools if t in ts) for p, ts in phase_map.items()}
                errors = tracker.get("all_errors", [])[-10:]
                if len(errors) >= 3 and sum(1 for e in errors if e) / len(errors) > 0.3:
                    phase = "debug"
                elif any(scores.values()):
                    phase = max(scores, key=scores.get)

        return JSONResponse({
            "drift_score": tracker.get("scope_drift", 0.0),
            "drift_explanation": tracker.get("drift_explanation", ""),
            "focus_files": tracker.get("focus_files", []),
            "focus_dirs": tracker.get("focus_dirs", []),
            "initial_focus": tracker.get("initial_focus", {}),
            "current_focus": tracker.get("current_focus", {}),
            "phase": phase,
        })
    except Exception:
        return JSONResponse({"drift_score": 0.0})


# ===================================================================
# 4. Subagent endpoints (new)
# ===================================================================

@app.get("/api/subagents/{parent_id}")
async def get_subagents(parent_id: str) -> JSONResponse:
    """Subagent matrix + cascade risk for a parent agent."""
    try:
        from soma.subagent_monitor import aggregate, get_cascade_risk, get_subagent_summary
    except ImportError:
        return JSONResponse({"subagents": {}, "cascade_risk": 0.0, "summary": {}})

    try:
        vitals = aggregate(parent_id)
        risk = get_cascade_risk(parent_id)
        summary = get_subagent_summary(parent_id)

        return JSONResponse({
            "subagents": vitals,
            "cascade_risk": round(risk, 3),
            "summary": summary,
        })
    except Exception:
        return JSONResponse({"subagents": {}, "cascade_risk": 0.0, "summary": {}})


# ===================================================================
# 5. Overview & engine
# ===================================================================

@app.get("/api/overview")
async def get_overview() -> JSONResponse:
    """Single endpoint with everything the dashboard needs — reduces round trips."""
    state = _read_json(SOMA_DIR / "state.json")
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
        quality = _read_json(_agent_session_path(aid) / "quality.json")
        if quality and "events" in quality:
            agent["quality_grade"] = _quality_grade_only(quality["events"])
        else:
            agent["quality_grade"] = "-"
        agents.append(agent)

    # Audit (last 50)
    audit = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 50)
    for e in audit:
        if "timestamp" in e:
            e["time_fmt"] = _fmt_ts(e["timestamp"])

    # Sessions (last 100, deduplicated — keep latest per session_id)
    sessions_raw = _read_jsonl_tail(SOMA_DIR / "sessions" / "history.jsonl", 100)
    seen: dict[str, dict] = {}
    for e in sessions_raw:
        sid = e.get("session_id") or e.get("agent_id") or ""
        if sid:
            seen[sid] = e
    sessions = list(seen.values())[-20:]
    for e in sessions:
        if "started" in e and "ended" in e:
            d = e["ended"] - e["started"]
            e["duration_fmt"] = f"{int(d // 60)}m {int(d % 60)}s"
        if "max_pressure" in e:
            e["max_pressure_pct"] = round(e["max_pressure"] * 100, 1)

    # Findings
    findings = _read_json(SOMA_DIR / "findings.json", default=[])

    return JSONResponse({
        "agents": agents,
        "audit": audit,
        "sessions": sessions,
        "budget": state.get("budget", {}) if isinstance(state, dict) else {},
        "findings": findings,
    })


@app.get("/api/engine")
async def get_engine() -> JSONResponse:
    """Summarized engine state for the dashboard."""
    data = _read_json(SOMA_DIR / "engine_state.json")
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


@app.get("/api/budget")
async def get_budget() -> JSONResponse:
    """Budget status with computed fields."""
    state = _read_json(SOMA_DIR / "state.json")
    budget = state.get("budget", {}) if isinstance(state, dict) else {}
    if not budget:
        return JSONResponse({})

    limits = budget.get("limits", {})
    spent = budget.get("spent", {})
    return JSONResponse({
        "health": budget.get("health", 1.0),
        "health_pct": round(budget.get("health", 1.0) * 100, 1),
        "limits": limits,
        "spent": spent,
        "remaining": {k: limits.get(k, 0) - spent.get(k, 0) for k in limits},
        "used_pct": {
            k: round(spent.get(k, 0) / limits[k] * 100, 1) if limits.get(k) else 0
            for k in limits
        },
    })


# ===================================================================
# 6. Config endpoints
# ===================================================================

@app.get("/api/config")
async def get_config() -> JSONResponse:
    """Parsed soma.toml config."""
    for candidate in [Path("soma.toml"), Path.home() / "soma.toml"]:
        try:
            with candidate.open("rb") as f:
                return JSONResponse(tomllib.load(f))
        except Exception:
            continue
    return JSONResponse({})


@app.get("/api/config/raw")
async def get_config_raw() -> JSONResponse:
    """Return raw soma.toml text for editing."""
    for candidate in [Path("soma.toml"), Path.home() / "soma.toml"]:
        try:
            return JSONResponse({"path": str(candidate), "content": candidate.read_text()})
        except Exception:
            continue
    return JSONResponse({"path": "", "content": ""})


@app.put("/api/config")
async def save_config(request: Request) -> JSONResponse:
    """Save soma.toml from raw text or structured data."""
    import tomli_w
    body = await request.json()

    config_path = None
    for candidate in [Path("soma.toml"), Path.home() / "soma.toml"]:
        if candidate.exists():
            config_path = candidate
            break
    if config_path is None:
        config_path = Path("soma.toml")

    # Accept raw TOML text
    if "raw" in body:
        try:
            tomllib.loads(body["raw"])
            config_path.write_text(body["raw"])
            return JSONResponse({"ok": True, "path": str(config_path)})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    # Accept structured updates (merge into existing)
    try:
        existing: dict = {}
        if config_path.exists():
            with config_path.open("rb") as f:
                existing = tomllib.load(f)

        def deep_merge(base: dict, overlay: dict) -> dict:
            for k, v in overlay.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
            return base

        deep_merge(existing, body)
        config_path.write_text(tomli_w.dumps(existing))
        return JSONResponse({"ok": True, "path": str(config_path)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.get("/api/config/defaults")
async def get_config_defaults() -> JSONResponse:
    """Return default config values for reset-to-defaults feature."""
    return JSONResponse({
        "soma": {"mode": "reflex"},
        "thresholds": {"guide": 0.25, "warn": 0.50, "block": 0.75},
        "weights": {
            "uncertainty": 1.0, "drift": 1.0, "error_rate": 1.5,
            "cost": 0.8, "token_usage": 0.8,
        },
        "budget": {"tokens": 200000, "cost_usd": 5.0},
        "hooks": {
            "pre_tool_use": True, "post_tool_use": True,
            "stop": True, "notification": True, "validate_js": False,
        },
        "baseline": {"alpha": 0.15, "cold_start_n": 10},
    })


# ===================================================================
# 7. Settings endpoints
# ===================================================================

@app.patch("/api/settings/mode")
async def patch_mode(request: Request) -> JSONResponse:
    """Change SOMA operating mode (reflex / review / passive)."""
    try:
        body = await request.json()
        mode = body.get("mode")
        if mode not in ("reflex", "review", "passive"):
            return JSONResponse(
                {"ok": False, "error": f"Invalid mode: {mode}. Must be reflex, review, or passive."},
                status_code=400,
            )
        path, cfg = _read_config()
        cfg.setdefault("soma", {})["mode"] = mode
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "mode": mode})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/thresholds")
async def patch_thresholds(request: Request) -> JSONResponse:
    """Update pressure thresholds (guide / warn / block)."""
    try:
        body = await request.json()
        allowed = {"guide", "warn", "block"}
        invalid = set(body.keys()) - allowed
        if invalid:
            return JSONResponse(
                {"ok": False, "error": f"Invalid threshold keys: {invalid}. Allowed: {allowed}"},
                status_code=400,
            )
        for v in body.values():
            if not isinstance(v, (int, float)) or not (0.0 <= v <= 1.0):
                return JSONResponse(
                    {"ok": False, "error": "Threshold values must be numbers between 0.0 and 1.0"},
                    status_code=400,
                )
        path, cfg = _read_config()
        cfg.setdefault("thresholds", {}).update(body)
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "thresholds": cfg["thresholds"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/weights")
async def patch_weights(request: Request) -> JSONResponse:
    """Update signal weights."""
    try:
        body = await request.json()
        for v in body.values():
            if not isinstance(v, (int, float)):
                return JSONResponse(
                    {"ok": False, "error": "Weight values must be numbers"},
                    status_code=400,
                )
        path, cfg = _read_config()
        cfg.setdefault("weights", {}).update(body)
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "weights": cfg["weights"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/hooks")
async def patch_hooks(request: Request) -> JSONResponse:
    """Toggle hook features on/off."""
    try:
        body = await request.json()
        for v in body.values():
            if not isinstance(v, bool):
                return JSONResponse(
                    {"ok": False, "error": "Hook values must be booleans"},
                    status_code=400,
                )
        path, cfg = _read_config()
        cfg.setdefault("hooks", {}).update(body)
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "hooks": cfg["hooks"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/agent/{agent_id}")
async def patch_agent_settings(agent_id: str, request: Request) -> JSONResponse:
    """Update per-agent settings."""
    try:
        body = await request.json()
        path, cfg = _read_config()
        cfg.setdefault("agents", {}).setdefault(agent_id, {}).update(body)
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "agent": cfg["agents"][agent_id]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/refresh")
async def patch_refresh(request: Request) -> JSONResponse:
    """Store dashboard refresh interval preference."""
    try:
        body = await request.json()
        interval = body.get("interval_ms")
        if not isinstance(interval, (int, float)) or interval < 500:
            return JSONResponse(
                {"ok": False, "error": "interval_ms must be a number >= 500"},
                status_code=400,
            )
        prefs_path = SOMA_DIR / "dashboard_prefs.json"
        prefs: dict = _read_json(prefs_path)
        prefs["refresh_interval_ms"] = int(interval)
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text(json.dumps(prefs))
        return JSONResponse({"ok": True, "interval_ms": int(interval)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/budget")
async def patch_budget(request: Request) -> JSONResponse:
    """Update budget limits (tokens, cost_usd)."""
    try:
        body = await request.json()
        path, cfg = _read_config()
        budget = cfg.setdefault("budget", {})
        for key in ("tokens", "cost_usd"):
            if key in body:
                val = body[key]
                if not isinstance(val, (int, float)) or val < 0:
                    return JSONResponse(
                        {"ok": False, "error": f"{key} must be a non-negative number"},
                        status_code=400,
                    )
                budget[key] = val
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "budget": budget})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/graph")
async def patch_graph(request: Request) -> JSONResponse:
    """Update graph settings (damping, trust_decay_rate, trust_recovery_rate)."""
    try:
        body = await request.json()
        allowed = {"damping", "trust_decay_rate", "trust_recovery_rate"}
        invalid = set(body.keys()) - allowed
        if invalid:
            return JSONResponse(
                {"ok": False, "error": f"Invalid keys: {invalid}. Allowed: {allowed}"},
                status_code=400,
            )
        for v in body.values():
            if not isinstance(v, (int, float)):
                return JSONResponse(
                    {"ok": False, "error": "Values must be numbers"},
                    status_code=400,
                )
        path, cfg = _read_config()
        cfg.setdefault("graph", {}).update(body)
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "graph": cfg["graph"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/vitals")
async def patch_vitals(request: Request) -> JSONResponse:
    """Update vitals settings (goal_coherence_threshold, warmup, error_ratio, min_samples)."""
    try:
        body = await request.json()
        allowed = {"goal_coherence_threshold", "warmup", "error_ratio", "min_samples"}
        invalid = set(body.keys()) - allowed
        if invalid:
            return JSONResponse(
                {"ok": False, "error": f"Invalid keys: {invalid}. Allowed: {allowed}"},
                status_code=400,
            )
        path, cfg = _read_config()
        cfg.setdefault("vitals", {}).update(body)
        _write_config(path, cfg)
        return JSONResponse({"ok": True, "vitals": cfg["vitals"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.patch("/api/settings/raw-toml")
async def patch_raw_toml(request: Request) -> JSONResponse:
    """Save raw TOML text content to soma.toml."""
    try:
        body = await request.json()
        content = body.get("content", "")
        if not content:
            return JSONResponse(
                {"ok": False, "error": "content is required"},
                status_code=400,
            )
        # Validate it parses
        try:
            tomllib.loads(content)
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": f"Invalid TOML: {e}"},
                status_code=400,
            )
        path, _ = _read_config()
        path.write_text(content)
        return JSONResponse({"ok": True, "path": str(path)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


# ===================================================================
# 8. Session endpoints
# ===================================================================

@app.get("/api/sessions")
async def get_sessions() -> JSONResponse:
    """Session history (deduplicated, last 50) — enriched."""
    raw = _read_jsonl_tail(SOMA_DIR / "sessions" / "history.jsonl", 200)
    seen: dict[str, dict] = {}
    for e in raw:
        sid = e.get("session_id") or e.get("agent_id") or ""
        if sid:
            seen[sid] = e
    entries = list(seen.values())[-50:]
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


@app.get("/api/sessions/{session_id}/replay")
async def get_session_replay(session_id: str) -> JSONResponse:
    """Full session replay — trajectory, actions, quality, predictor."""
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.is_dir():
        return JSONResponse({"error": f"Session {session_id} not found"}, status_code=404)

    trajectory = _read_json(session_dir / "trajectory.json", default=[])
    action_log = _read_json(session_dir / "action_log.json", default=[])
    quality = _read_json(session_dir / "quality.json")
    predictor = _read_json(session_dir / "predictor.json")

    _enrich_actions(action_log)

    result: dict[str, Any] = {
        "session_id": session_id,
        "trajectory": trajectory,
        "action_log": action_log,
    }
    if quality:
        result["quality"] = quality
    if predictor:
        result["predictor"] = predictor

    return JSONResponse(result)


@app.get("/api/sessions/{session_id}/report")
async def get_session_report(session_id: str) -> JSONResponse:
    """Rendered session report from report module."""
    try:
        from soma.report import generate_session_report
        from soma.persistence import load_engine_state
    except ImportError:
        return JSONResponse({"error": "report module not available"}, status_code=501)

    try:
        engine = load_engine_state()
        if engine is None:
            return JSONResponse({"report": f"# Session Report\n\nNo engine state available for session `{session_id}`."})
        report_md = generate_session_report(engine, agent_id=session_id)
        return JSONResponse({"report": report_md, "session_id": session_id})
    except Exception as e:
        return JSONResponse({"report": f"# Session Report\n\nError generating report: {e}"})


@app.get("/api/sessions/{session_id}/record")
async def get_session_record(session_id: str) -> JSONResponse:
    """Full SessionRecord from session store."""
    try:
        from soma.session_store import load_sessions
    except ImportError:
        return JSONResponse({"error": "session_store module not available"}, status_code=501)

    try:
        sessions = load_sessions()
        for s in sessions:
            if s.session_id == session_id or s.agent_id == session_id:
                from dataclasses import asdict
                return JSONResponse(asdict(s))
        return JSONResponse({"error": f"Session {session_id} not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===================================================================
# 9. Analytics endpoints (new)
# ===================================================================

@app.get("/api/analytics/trends/{agent_id}")
async def get_analytics_trends(agent_id: str) -> JSONResponse:
    """Cross-session trends from analytics store."""
    try:
        from soma.analytics import AnalyticsStore
    except ImportError:
        return JSONResponse([])

    try:
        store = AnalyticsStore()
        trends = store.get_agent_trends(agent_id)
        store.close()
        return JSONResponse(trends)
    except Exception:
        return JSONResponse([])


@app.get("/api/analytics/tools/{agent_id}")
async def get_analytics_tools(agent_id: str) -> JSONResponse:
    """Tool stats from analytics store."""
    try:
        from soma.analytics import AnalyticsStore
    except ImportError:
        return JSONResponse({})

    try:
        store = AnalyticsStore()
        stats = store.get_tool_stats(agent_id)
        store.close()
        return JSONResponse(stats)
    except Exception:
        return JSONResponse({})


@app.get("/api/threshold-tuner/status")
async def get_threshold_tuner_status() -> JSONResponse:
    """Current vs optimal thresholds."""
    try:
        from soma.threshold_tuner import compute_optimal_thresholds, DEFAULT_THRESHOLDS
    except ImportError:
        return JSONResponse({"current": {}, "optimal": {}, "status": "module_unavailable"})

    try:
        _, cfg = _read_config()
        current = cfg.get("thresholds", dict(DEFAULT_THRESHOLDS))

        # Load benchmark results if available
        benchmark_results = _read_json(SOMA_DIR / "benchmark_results.json", default=[])
        if isinstance(benchmark_results, list) and benchmark_results:
            optimal = compute_optimal_thresholds(benchmark_results)
        else:
            optimal = dict(DEFAULT_THRESHOLDS)

        return JSONResponse({
            "current": current,
            "optimal": optimal,
            "defaults": dict(DEFAULT_THRESHOLDS),
            "has_benchmark_data": bool(benchmark_results),
        })
    except Exception:
        return JSONResponse({"current": {}, "optimal": {}, "status": "error"})


# ===================================================================
# 10. Policy endpoints (new)
# ===================================================================

@app.get("/api/policies")
async def get_policies() -> JSONResponse:
    """Policy rule catalog."""
    try:
        rules: list[dict] = []

        # From config
        _, cfg = _read_config()
        policies_cfg = cfg.get("policies", {})
        if isinstance(policies_cfg, dict):
            for name, rule_data in policies_cfg.items():
                rules.append({
                    "name": name,
                    "conditions": rule_data.get("when", []),
                    "action": rule_data.get("do", {}),
                    "source": "config",
                })

        # From JSON policy store
        policy_store = _read_json(SOMA_DIR / "policies.json", default=[])
        if isinstance(policy_store, list):
            for rule in policy_store:
                if isinstance(rule, dict):
                    rules.append({**rule, "source": "store"})

        # From YAML policy files (if yaml available)
        policy_dir = SOMA_DIR / "policies"
        if policy_dir.is_dir():
            try:
                import yaml
                for pf in policy_dir.glob("*.yaml"):
                    data = yaml.safe_load(pf.read_text())
                    if isinstance(data, dict):
                        for policy in data.get("policies", []):
                            rules.append({
                                "name": policy.get("name", pf.stem),
                                "conditions": policy.get("when", []),
                                "action": policy.get("do", {}),
                                "source": str(pf),
                            })
            except ImportError:
                pass

        return JSONResponse(rules)
    except Exception:
        return JSONResponse([])


@app.post("/api/policies")
async def add_policy(request: Request) -> JSONResponse:
    """Add a new policy rule."""
    try:
        body = await request.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"ok": False, "error": "name is required"}, status_code=400)

        rule = {
            "name": name,
            "conditions": body.get("conditions", body.get("when", [])),
            "action": body.get("action", body.get("do", {})),
        }

        # Store in JSON policy store
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        store_path = SOMA_DIR / "policies.json"
        store = _read_json(store_path, default=[])
        if not isinstance(store, list):
            store = []

        # Replace if exists, append otherwise
        store = [r for r in store if r.get("name") != name]
        store.append(rule)
        store_path.write_text(json.dumps(store, indent=2))

        return JSONResponse({"ok": True, "rule": rule})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.delete("/api/policies/{rule_name}")
async def delete_policy(rule_name: str) -> JSONResponse:
    """Delete a policy rule by name."""
    try:
        store_path = SOMA_DIR / "policies.json"
        store = _read_json(store_path, default=[])
        if not isinstance(store, list):
            return JSONResponse({"ok": False, "error": "no policies found"}, status_code=404)

        original_len = len(store)
        store = [r for r in store if r.get("name") != rule_name]
        if len(store) == original_len:
            return JSONResponse({"ok": False, "error": f"rule '{rule_name}' not found"}, status_code=404)

        store_path.write_text(json.dumps(store, indent=2))
        return JSONResponse({"ok": True, "deleted": rule_name})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


# ===================================================================
# 11. Export endpoints
# ===================================================================

@app.get("/api/export/audit")
async def export_audit_csv() -> StreamingResponse:
    """Export audit as CSV."""
    try:
        entries = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 1000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp", "time", "agent_id", "tool_name", "pressure", "mode", "error"])
        for e in entries:
            writer.writerow([
                e.get("timestamp", ""),
                _fmt_ts(e.get("timestamp")) or "",
                e.get("agent_id", ""),
                e.get("tool_name", ""),
                e.get("pressure", ""),
                e.get("mode", ""),
                e.get("error", ""),
            ])
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=soma_audit.csv"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/export/session/{session_id}")
async def export_session_json(session_id: str):
    """Export session as JSON download."""
    try:
        session_dir = SESSIONS_DIR / session_id
        if not session_dir.is_dir():
            return JSONResponse({"error": f"Session {session_id} not found"}, status_code=404)

        data = {
            "session_id": session_id,
            "trajectory": _read_json(session_dir / "trajectory.json", default=[]),
            "action_log": _read_json(session_dir / "action_log.json", default=[]),
            "quality": _read_json(session_dir / "quality.json"),
            "predictor": _read_json(session_dir / "predictor.json"),
        }
        content = json.dumps(data, indent=2)
        return StreamingResponse(
            io.StringIO(content),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=soma_session_{session_id}.json"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/activity-heatmap")
async def get_activity_heatmap() -> JSONResponse:
    """Activity by hour-of-day for heatmap visualization."""
    try:
        entries = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 2000)
        buckets: dict[int, dict] = {h: {"count": 0, "errors": 0, "pressure_sum": 0.0} for h in range(24)}

        for e in entries:
            ts = e.get("timestamp")
            if ts is None:
                continue
            try:
                hour = time.localtime(ts).tm_hour
            except Exception:
                continue
            buckets[hour]["count"] += 1
            if e.get("error"):
                buckets[hour]["errors"] += 1
            pressure = e.get("pressure")
            if isinstance(pressure, (int, float)):
                buckets[hour]["pressure_sum"] += pressure

        hours = []
        for h in range(24):
            b = buckets[h]
            avg_p = round(b["pressure_sum"] / b["count"], 4) if b["count"] else 0.0
            hours.append({"hour": h, "count": b["count"], "errors": b["errors"], "avg_pressure": avg_p})

        return JSONResponse({"hours": hours})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===================================================================
# 12. LLM endpoints
# ===================================================================

LLM_CONFIG_PATH = SOMA_DIR / "llm_config.json"


def _mask_api_key(key: str | None) -> str:
    """Mask all but last 4 chars of an API key."""
    if not key or len(key) < 8:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def _read_llm_config() -> dict:
    """Read LLM configuration from disk."""
    return _read_json(LLM_CONFIG_PATH)


async def _call_llm(cfg: dict, system_prompt: str, user_content: str) -> str:
    """Call the configured LLM provider and return the response text.

    Raises on import failure, HTTP error, or unknown provider.
    """
    import httpx

    api_key = cfg.get("api_key", "")
    provider = cfg.get("provider", "anthropic")
    model = cfg.get("model", "claude-sonnet-4-20250514")

    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider == "anthropic":
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_content}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content", [{}])[0].get("text", "")

        elif provider == "openai":
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

        else:
            raise ValueError(f"Unknown provider: {provider}")


@app.get("/api/settings/llm")
async def get_llm_settings() -> JSONResponse:
    """Read LLM config with masked API key."""
    cfg = _read_llm_config()
    if not cfg:
        return JSONResponse({})
    safe = {**cfg, "api_key": _mask_api_key(cfg.get("api_key"))}
    return JSONResponse(safe)


@app.patch("/api/settings/llm")
async def patch_llm_settings(request: Request) -> JSONResponse:
    """Save LLM API settings to ~/.soma/llm_config.json."""
    try:
        body = await request.json()
        provider = body.get("provider")
        if provider not in ("anthropic", "openai"):
            return JSONResponse(
                {"ok": False, "error": "provider must be 'anthropic' or 'openai'"},
                status_code=400,
            )
        api_key = body.get("api_key", "")
        if not api_key or len(api_key) < 8:
            return JSONResponse(
                {"ok": False, "error": "api_key is required (minimum 8 characters)"},
                status_code=400,
            )
        cfg = {
            "provider": provider,
            "api_key": api_key,
            "model": body.get("model", "claude-sonnet-4-20250514"),
            "enabled": body.get("enabled", True),
        }
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        LLM_CONFIG_PATH.write_text(json.dumps(cfg))
        safe = {**cfg, "api_key": _mask_api_key(cfg["api_key"])}
        return JSONResponse({"ok": True, **safe})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/api/llm/analyze")
async def llm_analyze(request: Request) -> JSONResponse:
    """Send context to LLM for semantic analysis."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        return JSONResponse(
            {"error": "httpx is not installed. Run: pip install httpx"},
            status_code=501,
        )

    try:
        body = await request.json()
        analysis_type = body.get("type", "session")
        context = body.get("context", {})

        cfg = _read_llm_config()
        if not cfg or not cfg.get("enabled"):
            return JSONResponse(
                {"error": "LLM not configured or disabled. Configure via PATCH /api/settings/llm"},
                status_code=400,
            )

        system_prompt = (
            "You are SOMA, a behavioral monitoring system for AI agents. "
            "Analyze the following monitoring data and provide actionable insights. Be concise."
        )
        user_content = json.dumps({"type": analysis_type, "data": context}, indent=2)

        analysis = await _call_llm(cfg, system_prompt, user_content)

        return JSONResponse({
            "analysis": analysis,
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
        })
    except Exception as e:
        error_msg = str(e)
        if "httpx" in error_msg.lower() or "status" in error_msg.lower():
            return JSONResponse({"error": f"LLM API error: {error_msg}"}, status_code=502)
        return JSONResponse({"error": error_msg}, status_code=500)


@app.post("/api/llm/explain-pressure")
async def llm_explain_pressure(request: Request) -> JSONResponse:
    """Explain why pressure is at current level for an agent."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        return JSONResponse(
            {"error": "httpx is not installed. Run: pip install httpx"},
            status_code=501,
        )

    try:
        body = await request.json()
        agent_id = body.get("agent_id")
        if not agent_id:
            return JSONResponse({"error": "agent_id is required"}, status_code=400)

        cfg = _read_llm_config()
        if not cfg or not cfg.get("enabled"):
            return JSONResponse(
                {"error": "LLM not configured or disabled. Configure via PATCH /api/settings/llm"},
                status_code=400,
            )

        agent_state = _get_agent_state(agent_id)
        vitals = agent_state.get("vitals", {})
        pressure = agent_state.get("pressure", 0.0)
        level = agent_state.get("level", "OBSERVE")

        session = _agent_session_path(agent_id)
        trajectory = _read_json(session / "trajectory.json", default=[])
        action_log = _read_json(session / "action_log.json", default=[])

        quality = _read_json(session / "quality.json")
        grade = "unknown"
        if quality and "events" in quality:
            grade = _quality_grade_only(quality["events"])

        system_prompt = (
            "You are SOMA, a behavioral monitoring system for AI agents. "
            "Analyze the following monitoring data and provide actionable insights. Be concise."
        )
        user_content = (
            f"Explain why this agent's pressure is at {round(pressure * 100, 1)}%. "
            f"Current level: {level}. "
            f"Vitals: {json.dumps(vitals)}. "
            f"Recent trajectory (last 20): {json.dumps(trajectory[-20:])}. "
            f"Recent actions (last 10): {json.dumps(action_log[-10:])}. "
            f"Quality: {grade}. "
            f"What's driving the pressure and what should change?"
        )

        analysis = await _call_llm(cfg, system_prompt, user_content)

        return JSONResponse({
            "analysis": analysis,
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "agent_id": agent_id,
            "pressure_pct": round(pressure * 100, 1),
        })
    except Exception as e:
        error_msg = str(e)
        if "httpx" in error_msg.lower() or "status" in error_msg.lower():
            return JSONResponse({"error": f"LLM API error: {error_msg}"}, status_code=502)
        return JSONResponse({"error": error_msg}, status_code=500)


# ===================================================================
# 13. Predictions, findings, fingerprints, patterns, audit, tool-usage
# ===================================================================

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


@app.get("/api/audit/detailed")
async def get_audit_detailed() -> JSONResponse:
    """Extended audit — last 500 entries with relative timestamps."""
    entries = _read_jsonl_tail(SOMA_DIR / "audit.jsonl", 500)
    for e in entries:
        if "timestamp" in e:
            e["time_fmt"] = _fmt_ts(e["timestamp"])
            e["ago"] = _relative_time(e["timestamp"])
    return JSONResponse(entries)


@app.get("/api/fingerprints")
async def get_fingerprints() -> JSONResponse:
    """Fingerprint data."""
    data = _read_json(SOMA_DIR / "fingerprint.json")
    return JSONResponse(data)


@app.get("/api/patterns")
async def get_patterns() -> JSONResponse:
    """Mirror pattern database."""
    data = _read_json(SOMA_DIR / "patterns.json")
    return JSONResponse(data)


@app.get("/api/tool-usage")
async def get_tool_usage() -> JSONResponse:
    """Tool usage distribution from fingerprints."""
    fp = _read_json(SOMA_DIR / "fingerprint.json")
    if not fp or "fingerprints" not in fp:
        return JSONResponse({})

    combined: dict[str, float] = {}
    for _fid, fdata in fp.get("fingerprints", {}).items():
        dist = fdata.get("tool_distribution", {})
        for tool, pct in dist.items():
            combined[tool] = combined.get(tool, 0) + pct

    total = sum(combined.values()) or 1
    normalized = {k: round(v / total, 4) for k, v in sorted(combined.items(), key=lambda x: -x[1])}
    return JSONResponse(normalized)


# ===================================================================
# 14. SSE — Server-Sent Events stream
# ===================================================================

from soma.dashboard.sse import sse_endpoint  # noqa: E402

app.add_api_route("/api/stream", sse_endpoint, methods=["GET"])


# ===================================================================
# 15. Static files (frontend) — mounted last so API routes take priority
# ===================================================================

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
