"""Tests for the dashboard data layer."""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from soma.dashboard.data import (
    export_session,
    get_activity_heatmap,
    get_agent_graph,
    get_agent_timeline,
    get_all_sessions,
    get_audit_log,
    get_baselines,
    get_budget_status,
    get_config,
    get_findings,
    get_learning_state,
    get_live_agents,
    get_overview_stats,
    get_pressure_history,
    get_session_detail,
    get_tool_stats,
)
from soma.dashboard.types import (
    ActionEvent,
    AgentSnapshot,
    BudgetSnapshot,
    HeatmapCell,
    OverviewStats,
    PressurePoint,
    SessionDetail,
    SessionSummary,
    ToolStat,
)

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


# ------------------------------------------------------------------
# get_session_detail tests
# ------------------------------------------------------------------


def test_get_session_detail(analytics_db):
    detail = get_session_detail("sess-001")
    assert isinstance(detail, SessionDetail)
    assert detail.session_id == "sess-001"
    assert detail.action_count == 5
    assert len(detail.actions) == 5
    assert detail.tool_stats == {"Bash": 5}
    assert detail.total_tokens == 2500


def test_get_session_detail_not_found(analytics_db):
    assert get_session_detail("nonexistent") is None


# ------------------------------------------------------------------
# get_budget_status tests
# ------------------------------------------------------------------


def test_get_budget_status(soma_dir):
    budget = get_budget_status()
    assert isinstance(budget, BudgetSnapshot)
    assert budget.health == 0.85
    assert budget.tokens_limit == 1000000
    assert budget.tokens_spent == 150000
    assert budget.cost_limit == 50.0
    assert budget.cost_spent == 7.5


def test_get_budget_no_state(soma_dir):
    (soma_dir / "state.json").unlink()
    assert get_budget_status() is None


# ------------------------------------------------------------------
# get_overview_stats tests
# ------------------------------------------------------------------


def test_get_overview_stats(analytics_db):
    stats = get_overview_stats()
    assert isinstance(stats, OverviewStats)
    assert stats.total_agents == 2
    assert stats.total_sessions == 3
    assert stats.total_actions == 10  # 5 + 3 + 2
    assert stats.budget is not None
    assert stats.budget.health == 0.85


# ------------------------------------------------------------------
# get_pressure_history tests
# ------------------------------------------------------------------


def test_get_pressure_history(analytics_db):
    points = get_pressure_history("cc-1001")
    assert len(points) == 8  # 5 + 3 actions across 2 sessions
    assert all(isinstance(p, PressurePoint) for p in points)
    assert points[0].timestamp < points[-1].timestamp


def test_get_pressure_history_empty(analytics_db):
    assert get_pressure_history("nonexistent") == []


def test_get_pressure_history_no_db(soma_dir):
    assert get_pressure_history("cc-1001") == []


# ------------------------------------------------------------------
# get_agent_timeline tests
# ------------------------------------------------------------------


def test_get_agent_timeline(analytics_db):
    events = get_agent_timeline("cc-1001")
    assert len(events) == 8
    assert all(isinstance(e, ActionEvent) for e in events)
    assert events[0].tool_name == "Bash"


def test_get_agent_timeline_empty(analytics_db):
    assert get_agent_timeline("nonexistent") == []


# ------------------------------------------------------------------
# get_tool_stats tests
# ------------------------------------------------------------------


def test_get_tool_stats(analytics_db):
    stats = get_tool_stats("cc-1001")
    assert len(stats) == 2
    by_name = {s.tool_name: s for s in stats}
    assert by_name["Bash"].count == 5
    assert by_name["Bash"].error_count == 0
    assert by_name["Read"].count == 3
    assert by_name["Read"].error_count == 1
    assert by_name["Read"].error_rate == pytest.approx(1 / 3, rel=0.01)


def test_get_tool_stats_empty(analytics_db):
    assert get_tool_stats("nonexistent") == []


# ------------------------------------------------------------------
# get_activity_heatmap tests
# ------------------------------------------------------------------


def test_get_activity_heatmap(analytics_db):
    cells = get_activity_heatmap("cc-1001")
    assert len(cells) > 0
    assert all(isinstance(c, HeatmapCell) for c in cells)
    total = sum(c.count for c in cells)
    assert total == 8


def test_get_activity_heatmap_empty(analytics_db):
    assert get_activity_heatmap("nonexistent") == []


# ------------------------------------------------------------------
# get_audit_log tests
# ------------------------------------------------------------------


@pytest.fixture
def audit_log(soma_dir):
    """Create test audit log."""
    log = soma_dir / "audit_cc-1001.jsonl"
    entries = [
        {"action_num": 10, "type": "guidance", "signal": "error_rate"},
        {"action_num": 15, "type": "throttle", "signal": "error_rate"},
        {"action_num": 20, "type": "guidance", "signal": "drift"},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries))
    return log


def test_get_audit_log(audit_log):
    entries = get_audit_log("cc-1001")
    assert len(entries) == 3
    assert entries[0]["type"] == "guidance"
    assert entries[2]["signal"] == "drift"


def test_get_audit_log_empty(soma_dir):
    assert get_audit_log("nonexistent") == []


# ------------------------------------------------------------------
# get_findings tests
# ------------------------------------------------------------------


def test_get_findings(soma_dir):
    findings = get_findings("cc-1001")
    assert isinstance(findings, list)


# ------------------------------------------------------------------
# get_config tests
# ------------------------------------------------------------------


def test_get_config(soma_dir):
    config = get_config()
    assert isinstance(config, dict)


# ------------------------------------------------------------------
# get_baselines tests
# ------------------------------------------------------------------


def test_get_baselines_from_engine_state(soma_dir):
    engine_state = {
        "agents": {"cc-1001": {"baseline": {"uncertainty": 0.05, "drift": 0.03}}}
    }
    (soma_dir / "engine_state.json").write_text(json.dumps(engine_state))
    baselines = get_baselines("cc-1001")
    assert baselines["uncertainty"] == 0.05
    assert baselines["drift"] == 0.03


def test_get_baselines_no_state(soma_dir):
    assert get_baselines("cc-1001") == {}


# ------------------------------------------------------------------
# get_agent_graph tests
# ------------------------------------------------------------------


def test_get_agent_graph_no_state(soma_dir):
    assert get_agent_graph() is None


def test_get_agent_graph_with_data(soma_dir):
    state = {
        "agents": {"cc-1001": {"level": "GUIDE"}},
        "graph": {"edges": [{"source": "cc-1001", "target": "cc-1002", "trust": 0.9}]},
    }
    (soma_dir / "engine_state.json").write_text(json.dumps(state))
    graph = get_agent_graph()
    assert graph is not None
    assert len(graph.nodes) == 1
    assert len(graph.edges) == 1


# ------------------------------------------------------------------
# get_learning_state tests
# ------------------------------------------------------------------


def test_get_learning_state_no_state(soma_dir):
    assert get_learning_state("cc-1001") is None


def test_get_learning_state_with_data(soma_dir):
    state = {"learning": {"adjustments": [{"signal": "drift", "delta": 0.1}]}}
    (soma_dir / "engine_state.json").write_text(json.dumps(state))
    result = get_learning_state("cc-1001")
    assert result is not None
    assert "adjustments" in result


# ------------------------------------------------------------------
# export_session tests
# ------------------------------------------------------------------


def test_export_session_json(analytics_db):
    data = export_session("sess-001", "json")
    assert len(data) > 0
    parsed = json.loads(data)
    assert parsed["action_count"] == 5


def test_export_session_csv(analytics_db):
    data = export_session("sess-001", "csv")
    assert b"tool_name" in data
    assert b"Bash" in data


def test_export_session_not_found(analytics_db):
    assert export_session("nonexistent") == b""


# ------------------------------------------------------------------
# get_quality tests (was missing)
# ------------------------------------------------------------------


def test_get_quality_no_state(soma_dir):
    from soma.dashboard.data import get_quality
    assert get_quality("cc-1001") is None


# ------------------------------------------------------------------
# get_fingerprint tests (was missing)
# ------------------------------------------------------------------


def test_get_fingerprint_no_state(soma_dir):
    from soma.dashboard.data import get_fingerprint
    result = get_fingerprint("cc-1001")
    # Without state files, returns patterns dict or None
    assert result is None or isinstance(result, dict)


# ------------------------------------------------------------------
# get_prediction tests (was missing)
# ------------------------------------------------------------------


def test_get_prediction_no_state(soma_dir):
    from soma.dashboard.data import get_prediction
    # Without predictor state, returns None or empty
    result = get_prediction("cc-1001")
    assert result is None or isinstance(result, dict)


# ------------------------------------------------------------------
# update_config tests (was missing)
# ------------------------------------------------------------------


def test_update_config(soma_dir, tmp_path):
    from soma.dashboard.data import update_config
    result = update_config({"soma": {"mode": "guide"}})
    assert isinstance(result, dict)


# ------------------------------------------------------------------
# Multi-definition helped — surfaced in pattern_hit_rates
# ------------------------------------------------------------------


def test_pattern_hit_rates_includes_multi_definition_stats(soma_dir):
    """_get_pattern_hit_rates must surface helped_{pressure_drop,
    tool_switch, error_resolved} rates per pattern. Old rows that
    pre-date the multi-helped columns are NULL and excluded from
    the rate (sqlite AVG skips NULLs); n_multi tracks the count of
    rows that actually contributed."""
    from soma.analytics import AnalyticsStore
    from soma.dashboard.data import _get_pattern_hit_rates

    store = AnalyticsStore(path=soma_dir / "analytics.db")
    try:
        # Old-style row (no multi columns) — should not affect new rates.
        store.record_guidance_outcome(
            agent_id="cc-roi", session_id="s",
            pattern_key="bash_retry", helped=True,
            pressure_at_injection=0.7, pressure_after=0.4,
        )
        # Three new-style rows: 2 helped_pressure_drop, 1 not.
        for hp, ts, er in (
            (True, True, True),
            (True, False, True),
            (False, True, False),
        ):
            store.record_guidance_outcome(
                agent_id="cc-roi", session_id="s",
                pattern_key="bash_retry", helped=False,
                pressure_at_injection=0.7, pressure_after=0.6,
                helped_pressure_drop=hp,
                helped_tool_switch=ts,
                helped_error_resolved=er,
            )
    finally:
        store.close()

    rows = _get_pattern_hit_rates()
    bash_rows = [r for r in rows if r["pattern_key"] == "bash_retry"]
    assert len(bash_rows) == 1
    row = bash_rows[0]
    # 4 total fires (1 legacy + 3 new).
    assert row["fires"] == 4
    # Only the 3 new rows contribute to multi.
    assert row["n_multi"] == 3
    # 2/3 ≈ 0.667.
    assert abs(row["rate_pressure_drop"] - 0.667) < 0.005
    # 2/3 ≈ 0.667.
    assert abs(row["rate_tool_switch"] - 0.667) < 0.005
    # 2/3 ≈ 0.667.
    assert abs(row["rate_error_resolved"] - 0.667) < 0.005


def test_pattern_ab_status_card_carries_multi_helped(soma_dir):
    """``get_pattern_ab_status`` must include a ``multi_helped`` block
    on every card so RoiPage.js can render the three orthogonal rates
    without a second roundtrip."""
    from soma.analytics import AnalyticsStore
    from soma.dashboard.data import get_pattern_ab_status

    store = AnalyticsStore(path=soma_dir / "analytics.db")
    try:
        for _ in range(3):
            store.record_guidance_outcome(
                agent_id="cc-card", session_id="s",
                pattern_key="bash_retry", helped=True,
                pressure_at_injection=0.7, pressure_after=0.4,
                helped_pressure_drop=True,
                helped_tool_switch=False,
                helped_error_resolved=True,
            )
    finally:
        store.close()

    cards = get_pattern_ab_status()
    bash_cards = [c for c in cards if c["pattern"] == "bash_retry"]
    assert len(bash_cards) == 1
    multi = bash_cards[0]["multi_helped"]
    assert multi["n_multi"] == 3
    assert abs(multi["rate_pressure_drop"] - 1.0) < 0.001
    assert abs(multi["rate_tool_switch"] - 0.0) < 0.001
    assert abs(multi["rate_error_resolved"] - 1.0) < 0.001

    # A pattern with zero firings must still expose multi_helped with
    # null rates so the UI doesn't crash on undefined.
    other = next(c for c in cards if c["pattern"] != "bash_retry")
    assert "multi_helped" in other
    assert other["multi_helped"]["n_multi"] == 0
    assert other["multi_helped"]["rate_pressure_drop"] is None
