"""SOMA Dashboard data layer — single source of truth for all dashboard data."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from soma.contextual_guidance import REAL_PATTERN_KEYS
from soma.dashboard.types import (
    ActionEvent,
    AgentSnapshot,
    BudgetSnapshot,
    GraphSnapshot,
    HeatmapCell,
    OverviewStats,
    PressurePoint,
    QualitySnapshot,
    SessionDetail,
    SessionSummary,
    ToolStat,
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
    names = _get_name_registry()
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
            display_name=names.get(agent_id) or data.get("display_name") or agent_id,
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


# ------------------------------------------------------------------
# Overview / budget
# ------------------------------------------------------------------


def get_budget_status() -> BudgetSnapshot | None:
    """Read budget info from state.json."""
    state_path = SOMA_DIR / "state.json"
    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    budget = state.get("budget")
    if not budget:
        return None

    limits = budget.get("limits", {})
    spent = budget.get("spent", {})

    return BudgetSnapshot(
        health=budget.get("health", 1.0),
        tokens_limit=limits.get("tokens", 0),
        tokens_spent=spent.get("tokens", 0),
        cost_limit=limits.get("cost_usd", 0.0),
        cost_spent=spent.get("cost_usd", 0.0),
    )


def get_overview_stats() -> OverviewStats:
    """Combine live agents + sessions into overview statistics."""
    agents = get_live_agents()
    sessions = get_all_sessions()
    budget = get_budget_status()

    total_actions = sum(s.action_count for s in sessions)
    all_pressures = [a.pressure for a in agents if a.pressure > 0]
    avg_pressure = (
        round(sum(all_pressures) / len(all_pressures), 4)
        if all_pressures else 0.0
    )

    # Aggregate top signals from agent vitals
    signal_totals: dict[str, list[float]] = {}
    for a in agents:
        for sig, val in a.vitals.items():
            if val is not None and val > 0:
                signal_totals.setdefault(sig, []).append(val)

    top_signals = {
        sig: round(sum(vals) / len(vals), 4)
        for sig, vals in signal_totals.items()
    }

    return OverviewStats(
        total_agents=len(agents),
        total_sessions=len(sessions),
        total_actions=total_actions,
        avg_pressure=avg_pressure,
        top_signals=top_signals,
        budget=budget,
    )


# ------------------------------------------------------------------
# Pressure history / timeline
# ------------------------------------------------------------------


def get_pressure_history(agent_id: str) -> list[PressurePoint]:
    """Return pressure values over time for an agent."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT timestamp, pressure, mode FROM actions "
            "WHERE agent_id = ? ORDER BY timestamp",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        PressurePoint(
            timestamp=r["timestamp"],
            pressure=r["pressure"],
            mode=r["mode"] or "OBSERVE",
        )
        for r in rows
    ]


def get_agent_timeline(agent_id: str) -> list[ActionEvent]:
    """Return all actions for an agent as timeline events."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT timestamp, tool_name, pressure, error, mode, "
            "token_count, cost FROM actions "
            "WHERE agent_id = ? ORDER BY timestamp",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        ActionEvent(
            timestamp=r["timestamp"],
            tool_name=r["tool_name"],
            pressure=r["pressure"],
            error=bool(r["error"]),
            mode=r["mode"] or "OBSERVE",
            token_count=r["token_count"] or 0,
            cost=r["cost"] or 0.0,
        )
        for r in rows
    ]


# ------------------------------------------------------------------
# Tool stats / heatmap
# ------------------------------------------------------------------


def get_tool_stats(agent_id: str) -> list[ToolStat]:
    """Return per-tool usage counts and error rates."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT tool_name, COUNT(*) as cnt, SUM(error) as errs "
            "FROM actions WHERE agent_id = ? "
            "GROUP BY tool_name ORDER BY cnt DESC",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        ToolStat(
            tool_name=r["tool_name"],
            count=r["cnt"],
            error_count=r["errs"] or 0,
            error_rate=round((r["errs"] or 0) / r["cnt"], 4) if r["cnt"] else 0.0,
        )
        for r in rows
    ]


def get_activity_heatmap(agent_id: str) -> list[HeatmapCell]:
    """Return hour x day-of-week action counts."""
    from datetime import datetime

    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT timestamp FROM actions WHERE agent_id = ?",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    grid: dict[tuple[int, int], int] = {}
    for r in rows:
        dt = datetime.fromtimestamp(r["timestamp"])
        key = (dt.hour, dt.weekday())
        grid[key] = grid.get(key, 0) + 1

    return [HeatmapCell(hour=h, day=d, count=c) for (h, d), c in sorted(grid.items())]


# ------------------------------------------------------------------
# Audit log / findings
# ------------------------------------------------------------------


def get_audit_log(agent_id: str) -> list[dict]:
    """Read guidance audit log entries for an agent."""
    path = SOMA_DIR / f"audit_{agent_id}.jsonl"
    if not path.exists():
        return []
    entries = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        pass
    return entries


def get_findings(agent_id: str) -> list[dict]:
    """Collect findings from quality tracker and audit log for an agent."""
    results: list[dict] = []

    # Quality-based findings
    qt = get_quality(agent_id)
    if qt is not None:
        if qt.write_error_rate > 0.2:
            results.append({"priority": 1, "category": "quality",
                            "title": "High write error rate",
                            "detail": f"{qt.write_error_rate:.0%} of writes have errors"})
        if qt.bash_error_rate > 0.3:
            results.append({"priority": 1, "category": "quality",
                            "title": "High bash error rate",
                            "detail": f"{qt.bash_error_rate:.0%} of bash commands fail"})

    # Audit-based findings (recent throttles/blocks)
    audit = get_audit_log(agent_id)
    throttles = [e for e in audit if e.get("type") == "throttle"]
    if len(throttles) >= 3:
        results.append({"priority": 0, "category": "guidance",
                        "title": "Repeated throttling",
                        "detail": f"{len(throttles)} throttle events recorded"})

    return results


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------


def get_config() -> dict:
    """Read current soma.toml config."""
    try:
        from soma.cli.config_loader import load_config
        return load_config()
    except Exception:
        return {}


def update_config(patch: dict) -> dict:
    """Update soma.toml with partial config via deep merge."""
    try:
        import tomllib
        import tomli_w

        # Try CWD first, then SOMA_DIR
        config_path = Path("soma.toml")
        if not config_path.exists():
            config_path = SOMA_DIR / "soma.toml"

        if config_path.exists():
            current = tomllib.loads(config_path.read_text())
        else:
            current = {}
            config_path = Path("soma.toml")  # create in CWD

        def _merge(base: dict, updates: dict) -> dict:
            for k, v in updates.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    _merge(base[k], v)
                else:
                    base[k] = v
            return base

        merged = _merge(current, patch)
        config_path.write_text(tomli_w.dumps(merged))
        return merged
    except Exception:
        return get_config()


# ------------------------------------------------------------------
# Subsystem state readers
# ------------------------------------------------------------------


def get_quality(agent_id: str) -> QualitySnapshot | None:
    """Read quality tracker state for a specific agent session."""
    try:
        from soma.state import get_quality_tracker
        qt = get_quality_tracker(agent_id)
        if qt is None:
            return None
        return QualitySnapshot(
            total_writes=qt.total_writes,
            total_bashes=qt.total_bashes,
            syntax_errors=qt.syntax_errors,
            lint_issues=qt.lint_issues,
            bash_errors=qt.bash_errors,
            write_error_rate=round(qt.syntax_errors / max(qt.total_writes, 1), 4),
            bash_error_rate=round(qt.bash_errors / max(qt.total_bashes, 1), 4),
        )
    except Exception:
        return None


def get_fingerprint(agent_id: str) -> dict | None:
    """Read behavioral fingerprint data."""
    try:
        from soma.state import get_fingerprint_engine
        fe = get_fingerprint_engine()
        if fe is None:
            return None
        return {"patterns": fe.patterns if hasattr(fe, "patterns") else {}}
    except Exception:
        return None


def get_baselines(agent_id: str) -> dict[str, float]:
    """Read EMA baselines from engine state."""
    path = SOMA_DIR / "engine_state.json"
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text())
        agent_state = state.get("agents", {}).get(agent_id, {})
        baseline = agent_state.get("baseline", {})
        return {k: round(v, 4) for k, v in baseline.items() if isinstance(v, (int, float))}
    except (json.JSONDecodeError, OSError):
        return {}


def get_prediction(agent_id: str) -> dict | None:
    """Read pressure prediction for a specific agent session."""
    try:
        from soma.state import get_predictor
        pred = get_predictor(agent_id)
        if pred is None:
            return None
        prediction = pred.predict(agent_id) if hasattr(pred, "predict") else None
        if prediction is None:
            return None
        return {
            "predicted_pressure": prediction.predicted_pressure,
            "confidence": prediction.confidence,
            "horizon_actions": prediction.horizon_actions,
        }
    except Exception:
        return None


def get_agent_graph() -> GraphSnapshot | None:
    """Read the agent pressure graph from engine state."""
    path = SOMA_DIR / "engine_state.json"
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
        graph_data = state.get("graph", {})
        if not graph_data:
            return None
        nodes = [
            {"id": aid, "pressure": adata.get("level", "OBSERVE")}
            for aid, adata in state.get("agents", {}).items()
        ]
        edges = [
            {"source": e.get("source"), "target": e.get("target"),
             "trust": e.get("trust", 1.0)}
            for e in graph_data.get("edges", [])
        ]
        return GraphSnapshot(nodes=nodes, edges=edges)
    except (json.JSONDecodeError, OSError):
        return None


def get_learning_state(agent_id: str) -> dict | None:
    """Read learning engine state, scoped to agent if available."""
    path = SOMA_DIR / "engine_state.json"
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
        learning = state.get("learning", {})
        if not learning:
            return None
        # Return agent-scoped data if keyed by agent_id, else full state
        if agent_id in learning:
            return learning[agent_id]
        return learning
    except (json.JSONDecodeError, OSError):
        return None


def export_session(session_id: str, fmt: str = "json") -> bytes:
    """Export session data as JSON or CSV bytes."""
    detail = get_session_detail(session_id)
    if detail is None:
        return b""

    if fmt == "csv":
        import csv
        import io
        output = io.StringIO()
        if detail.actions:
            writer = csv.DictWriter(output, fieldnames=detail.actions[0].keys())
            writer.writeheader()
            writer.writerows(detail.actions)
        return output.getvalue().encode("utf-8")
    else:
        import dataclasses
        return json.dumps(dataclasses.asdict(detail), indent=2).encode("utf-8")


# ------------------------------------------------------------------
# ROI (Return on Investment)
# ------------------------------------------------------------------

# Average tokens wasted per error cascade action (conservative estimate)
_AVG_TOKENS_PER_ERROR_ACTION = 800

# Whitelist of pattern_keys produced by real production guidance paths.
# Anything else in guidance_outcomes is test-fixture pollution and must be
# excluded from ROI metrics. Sourced from contextual_guidance so adding a
# new pattern there automatically unblocks it on the dashboard — no
# second place to update.
_REAL_PATTERN_KEYS = REAL_PATTERN_KEYS
_REAL_PATTERN_PLACEHOLDERS = ",".join("?" for _ in _REAL_PATTERN_KEYS)


def get_roi_data() -> dict:
    """Aggregate all ROI metrics into a single response."""
    return {
        "guidance_effectiveness": _get_guidance_effectiveness(),
        "pattern_hit_rates": _get_pattern_hit_rates(),
        "tokens_saved_estimate": _get_tokens_saved_estimate(),
        "session_health": _get_session_health_score(),
        "cascades_broken": _get_cascades_broken(),
        # P1.3: A/B verdict becomes the primary pattern metric.
        # `pattern_hit_rates` stays for back-compat but the frontend
        # renders `pattern_ab_status` as the headline and demotes
        # helped% to the expand panel.
        "pattern_ab_status": get_pattern_ab_status(),
        "ab_reset_info": get_ab_reset_info(),
    }


def _get_guidance_effectiveness() -> dict:
    """Guidance precision: followthrough True / total followthrough results."""
    conn = _get_db_connection()
    if not conn:
        return {"total": 0, "helped": 0, "effectiveness_rate": 0.0}
    try:
        cursor = conn.execute(
            f"SELECT COUNT(*) as total, SUM(helped) as helped "
            f"FROM guidance_outcomes "
            f"WHERE pattern_key IN ({_REAL_PATTERN_PLACEHOLDERS})",
            _REAL_PATTERN_KEYS,
        )
        row = cursor.fetchone()
        total = row["total"] or 0
        helped = row["helped"] or 0
        return {
            "total": total,
            "helped": helped,
            "effectiveness_rate": helped / total if total > 0 else 0.0,
        }
    except Exception:
        return {"total": 0, "helped": 0, "effectiveness_rate": 0.0}
    finally:
        conn.close()


def _get_pattern_hit_rates() -> list[dict]:
    """Which patterns fire most and which get followed."""
    conn = _get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.execute(
            f"SELECT pattern_key, COUNT(*) as fires, "
            f"SUM(helped) as followed, "
            f"ROUND(CAST(SUM(helped) AS REAL) / COUNT(*), 3) as follow_rate "
            f"FROM guidance_outcomes "
            f"WHERE pattern_key IN ({_REAL_PATTERN_PLACEHOLDERS}) "
            f"GROUP BY pattern_key ORDER BY fires DESC",
            _REAL_PATTERN_KEYS,
        )
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _get_tokens_saved_estimate() -> dict:
    """ROUGH estimate of tokens saved by breaking error cascades.

    NOT a measured number. Two stacked unverified multipliers:
    - 3 × ``helped`` (assumed prevented error actions per intervention)
    - 800 (``_AVG_TOKENS_PER_ERROR_ACTION``, single hand-picked constant)

    Surfaced with ``is_estimate=True`` so the UI can label it honestly
    instead of presenting it as measurement. Demoted from the ROI hero
    on 2026-04-25 (ultra-review): the headline metric must be
    something measured, not a 3× synthetic multiplier.
    """
    methodology = (
        "rough estimate: helped_interventions × 3 assumed prevented "
        "error actions × 800 tokens per error action — both multipliers "
        "are unmeasured constants, not derived from this user's data"
    )
    conn = _get_db_connection()
    if not conn:
        return {
            "estimated_tokens_saved": 0,
            "interventions_helped": 0,
            "is_estimate": True,
            "methodology": methodology,
        }
    try:
        cursor = conn.execute(
            f"SELECT COUNT(*) as total, SUM(helped) as helped "
            f"FROM guidance_outcomes "
            f"WHERE pattern_key IN ({_REAL_PATTERN_PLACEHOLDERS})",
            _REAL_PATTERN_KEYS,
        )
        row = cursor.fetchone()
        helped = row["helped"] or 0
        estimated = helped * 3 * _AVG_TOKENS_PER_ERROR_ACTION
        return {
            "estimated_tokens_saved": estimated,
            "interventions_helped": helped,
            "is_estimate": True,
            "methodology": methodology,
        }
    except Exception:
        return {
            "estimated_tokens_saved": 0,
            "interventions_helped": 0,
            "is_estimate": True,
            "methodology": methodology,
        }
    finally:
        conn.close()


def _get_session_health_score() -> dict:
    """Session health 0-100 from current vitals (entropy, error_rate, drift)."""
    # Read latest vitals from engine_state.json
    state_path = SOMA_DIR / "engine_state.json"
    if not state_path.exists():
        return {"score": 100, "components": {}}
    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"score": 100, "components": {}}

    # Find the most recent agent's vitals
    agents = state.get("agents", {})
    if not agents:
        return {"score": 100, "components": {}}

    # Average across all active agents
    total_error = 0.0
    total_uncertainty = 0.0
    total_drift = 0.0
    count = 0
    for agent_data in agents.values():
        vitals = agent_data.get("last_vitals", {})
        if vitals:
            total_error += vitals.get("error_rate", 0.0)
            total_uncertainty += vitals.get("uncertainty", 0.0)
            total_drift += vitals.get("drift", 0.0)
            count += 1

    if count == 0:
        return {"score": 100, "components": {}}

    avg_error = total_error / count
    avg_uncertainty = total_uncertainty / count
    avg_drift = total_drift / count

    # Score: 100 = perfect, penalize for each signal
    # Calibrated: 5% error + 8% uncertainty + 2% drift ≈ 83 (healthy)
    # 20% error + 20% uncertainty + 20% drift ≈ 30 (bad)
    error_penalty = min(avg_error * 150, 40)  # 10% = 15pts, 27%+ = 40 cap
    uncertainty_penalty = min(avg_uncertainty * 100, 30)  # 10% = 10pts, 30%+ = 30 cap
    drift_penalty = min(avg_drift * 100, 30)  # 10% = 10pts, 30%+ = 30 cap

    score = max(0, round(100 - error_penalty - uncertainty_penalty - drift_penalty))
    return {
        "score": score,
        "components": {
            "error_rate": round(avg_error, 4),
            "uncertainty": round(avg_uncertainty, 4),
            "drift": round(avg_drift, 4),
        },
    }


def get_pattern_ab_status() -> list[dict]:
    """Per-pattern A/B validation cards for the dashboard ROI page.

    For each real pattern, runs :func:`soma.ab_control.validate` across
    every family's rows and returns one card with the primary A/B
    verdict (``status``), mean Δp difference, p-value, effect size,
    plus the legacy helped% metric demoted to a secondary field the UI
    renders under an "expand" toggle. Patterns with zero outcome rows
    still appear as ``collecting`` so the grid is always dense.
    """
    from soma import ab_control
    from soma.analytics import AnalyticsStore

    db_path = SOMA_DIR / "analytics.db"
    if not db_path.exists():
        return []
    try:
        store = AnalyticsStore(path=db_path)
    except Exception:
        return []

    # Helped% comes from guidance_outcomes and is one extra query per
    # dashboard tick. Aggregate up-front so the per-pattern loop is a
    # pure dict lookup.
    helped_by_pattern: dict[str, dict[str, int]] = {}
    try:
        # AnalyticsStore._conn uses the stdlib default row factory
        # (returns tuples), so index into the SELECT projection rather
        # than by column name.
        cursor = store._conn.execute(
            f"SELECT pattern_key, COUNT(*) as fires, SUM(helped) as helped "
            f"FROM guidance_outcomes "
            f"WHERE pattern_key IN ({_REAL_PATTERN_PLACEHOLDERS}) "
            f"GROUP BY pattern_key",
            _REAL_PATTERN_KEYS,
        )
        for pattern_key, fires, helped in cursor.fetchall():
            helped_by_pattern[pattern_key] = {
                "fires": fires or 0,
                "helped": helped or 0,
            }
    except Exception:
        pass

    cards: list[dict] = []
    try:
        for pattern in _REAL_PATTERN_KEYS:
            try:
                outcomes = store.get_ab_outcomes(pattern, agent_family=None)
            except Exception:
                outcomes = []
            result = ab_control.validate(outcomes, pattern=pattern)
            legacy = helped_by_pattern.get(pattern, {"fires": 0, "helped": 0})
            helped_rate = (
                legacy["helped"] / legacy["fires"] if legacy["fires"] else 0.0
            )
            cards.append({
                "pattern": pattern,
                "status": result.status,
                "fires_treatment": result.fires_treatment,
                "fires_control": result.fires_control,
                "min_pairs": ab_control.DEFAULT_MIN_PAIRS,
                "mean_treatment_delta": round(result.mean_treatment_delta, 4),
                "mean_control_delta": round(result.mean_control_delta, 4),
                "delta_difference": round(result.delta_difference, 4),
                "p_value": (
                    round(result.p_value, 4) if result.p_value is not None else None
                ),
                "effect_size": (
                    round(result.effect_size, 3)
                    if result.effect_size is not None else None
                ),
                # Legacy — kept for the "expand" section so returning
                # users can still see the old metric they remember.
                "legacy_helped": {
                    "fires": legacy["fires"],
                    "helped": legacy["helped"],
                    "helped_rate": round(helped_rate, 3),
                },
            })
    finally:
        try:
            store.close()
        except Exception:
            pass

    return cards


def get_ab_reset_info() -> dict | None:
    """Return the most recent A/B data-reset record, or None.

    Reads ``~/.soma/ab_reset.log`` (JSONL). Only the latest row is
    surfaced — older entries stay in the file for post-mortem auditing
    but the dashboard banner only needs to explain *why this window
    is thin*.
    """
    path = SOMA_DIR / "ab_reset.log"
    if not path.exists():
        return None
    try:
        lines = [line for line in path.read_text().splitlines() if line.strip()]
    except OSError:
        return None
    if not lines:
        return None
    try:
        latest = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    if not isinstance(latest, dict):
        return None
    return {
        "ts": latest.get("ts"),
        "archived_rows": latest.get("archived_rows"),
        "reason": latest.get("reason", ""),
        "soma_version": latest.get("soma_version", ""),
    }


def _get_cascades_broken() -> dict:
    """Count of error cascades broken by intervention type."""
    conn = _get_db_connection()
    if not conn:
        return {"total": 0, "by_pattern": {}}
    try:
        cascade_patterns = ("error_cascade", "bash_retry")
        placeholders = ",".join("?" for _ in cascade_patterns)
        cursor = conn.execute(
            f"SELECT pattern_key, COUNT(*) as count "
            f"FROM guidance_outcomes "
            f"WHERE helped = 1 AND pattern_key IN ({placeholders}) "
            f"GROUP BY pattern_key",
            cascade_patterns,
        )
        by_pattern = {row["pattern_key"]: row["count"] for row in cursor.fetchall()}
        return {
            "total": sum(by_pattern.values()),
            "by_pattern": by_pattern,
        }
    except Exception:
        return {"total": 0, "by_pattern": {}}
    finally:
        conn.close()
