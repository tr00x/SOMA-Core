"""Tests for ROI dashboard data functions."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from soma.dashboard import data


@pytest.fixture()
def analytics_db(tmp_path):
    """Create a temporary analytics.db with test data."""
    db_path = tmp_path / "analytics.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE actions (
            timestamp REAL, agent_id TEXT, session_id TEXT,
            tool_name TEXT, pressure REAL, uncertainty REAL,
            drift REAL, error_rate REAL, context_usage REAL,
            token_count INTEGER, cost REAL, mode TEXT, error INTEGER,
            source TEXT DEFAULT 'hook', soma_version TEXT DEFAULT '2026.4.0'
        )
    """)
    conn.execute("""
        CREATE TABLE guidance_outcomes (
            timestamp REAL, agent_id TEXT, session_id TEXT,
            pattern_key TEXT, helped INTEGER,
            pressure_at_injection REAL, pressure_after REAL
        )
    """)
    # Insert guidance outcomes
    now = time.time()
    outcomes = [
        (now - 100, "a1", "s1", "error_cascade", 1, 0.6, 0.3),
        (now - 90, "a1", "s1", "error_cascade", 1, 0.5, 0.2),
        (now - 80, "a1", "s1", "bash_retry", 1, 0.7, 0.4),
        (now - 70, "a1", "s1", "blind_edit", 0, 0.4, 0.5),
        (now - 60, "a1", "s1", "entropy_drop", 1, 0.3, 0.1),
        (now - 50, "a1", "s1", "entropy_drop", 0, 0.2, 0.3),
    ]
    conn.executemany(
        "INSERT INTO guidance_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
        outcomes,
    )
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture()
def engine_state(tmp_path):
    """Create a temporary engine_state.json."""
    state = {
        "agents": {
            "a1": {
                "last_vitals": {
                    "error_rate": 0.05,
                    "uncertainty": 0.08,
                    "drift": 0.02,
                }
            }
        }
    }
    state_path = tmp_path / "engine_state.json"
    state_path.write_text(json.dumps(state))
    return tmp_path


def _patch_soma_dir(tmp_path):
    return patch.object(data, "SOMA_DIR", tmp_path)


class TestGuidanceEffectiveness:
    def test_with_data(self, analytics_db):
        with _patch_soma_dir(analytics_db):
            result = data._get_guidance_effectiveness()
        assert result["total"] == 6
        assert result["helped"] == 4
        assert abs(result["effectiveness_rate"] - 4 / 6) < 0.001

    def test_no_db(self, tmp_path):
        with _patch_soma_dir(tmp_path):
            result = data._get_guidance_effectiveness()
        assert result == {"total": 0, "helped": 0, "effectiveness_rate": 0.0}


class TestPatternHitRates:
    def test_with_data(self, analytics_db):
        with _patch_soma_dir(analytics_db):
            result = data._get_pattern_hit_rates()
        assert len(result) == 4
        # error_cascade fired most (2)
        assert result[0]["pattern_key"] == "error_cascade"
        assert result[0]["fires"] == 2
        assert result[0]["followed"] == 2
        assert result[0]["follow_rate"] == 1.0

    def test_no_db(self, tmp_path):
        with _patch_soma_dir(tmp_path):
            result = data._get_pattern_hit_rates()
        assert result == []


class TestTokensSavedEstimate:
    def test_with_data(self, analytics_db):
        with _patch_soma_dir(analytics_db):
            result = data._get_tokens_saved_estimate()
        assert result["interventions_helped"] == 4
        # 4 * 3 * 800 = 9600
        assert result["estimated_tokens_saved"] == 4 * 3 * data._AVG_TOKENS_PER_ERROR_ACTION

    def test_no_db(self, tmp_path):
        with _patch_soma_dir(tmp_path):
            result = data._get_tokens_saved_estimate()
        assert result == {"estimated_tokens_saved": 0, "interventions_helped": 0}


class TestSessionHealthScore:
    def test_with_state(self, engine_state):
        with _patch_soma_dir(engine_state):
            result = data._get_session_health_score()
        assert 0 <= result["score"] <= 100
        assert "error_rate" in result["components"]
        # With low vitals, score should be high
        assert result["score"] >= 80

    def test_no_state(self, tmp_path):
        with _patch_soma_dir(tmp_path):
            result = data._get_session_health_score()
        assert result == {"score": 100, "components": {}}


class TestCascadesBroken:
    def test_with_data(self, analytics_db):
        with _patch_soma_dir(analytics_db):
            result = data._get_cascades_broken()
        # error_cascade: 2 helped, bash_retry: 1 helped
        assert result["total"] == 3
        assert result["by_pattern"]["error_cascade"] == 2
        assert result["by_pattern"]["bash_retry"] == 1

    def test_no_db(self, tmp_path):
        with _patch_soma_dir(tmp_path):
            result = data._get_cascades_broken()
        assert result == {"total": 0, "by_pattern": {}}


# ---------------------------------------------------------------------------
# Test-fixture pollution filtering
# ---------------------------------------------------------------------------

@pytest.fixture()
def polluted_db(tmp_path):
    """analytics.db seeded with BOTH real patterns and test-fixture garbage."""
    db_path = tmp_path / "analytics.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE guidance_outcomes (
            timestamp REAL, agent_id TEXT, session_id TEXT,
            pattern_key TEXT, helped INTEGER,
            pressure_at_injection REAL, pressure_after REAL
        )
    """)
    now = time.time()
    rows = [
        # Real production patterns
        (now - 10, "cc-1", "s1", "bash_retry", 1, 0.7, 0.2),
        (now - 20, "cc-1", "s1", "blind_edit", 1, 0.5, 0.2),
        # Test-fixture garbage that must be filtered
        (now - 30, "test", "s2", "retry_loop", 1, 0.6, 0.3),
        (now - 40, "test", "s2", "mixed", 0, 0.5, 0.5),
        (now - 50, "test", "s2", "bad_pattern", 0, 0.5, 0.5),
        (now - 60, "test", "s2", "maybe_bad", 0, 0.5, 0.5),
        (now - 70, "test", "s2", "test_key", 1, 0.5, 0.2),
    ]
    conn.executemany(
        "INSERT INTO guidance_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)", rows
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_guidance_effectiveness_filters_test_fixture_patterns(polluted_db):
    """Dashboard must exclude mirror/test pattern_keys from ROI metrics."""
    with _patch_soma_dir(polluted_db):
        result = data._get_guidance_effectiveness()
    # Only bash_retry + blind_edit count (2 real, 2 helped)
    assert result["total"] == 2
    assert result["helped"] == 2
    assert result["effectiveness_rate"] == 1.0


def test_pattern_hit_rates_filters_test_fixture_patterns(polluted_db):
    """retry_loop/mixed/bad_pattern/maybe_bad/test_key must not appear."""
    with _patch_soma_dir(polluted_db):
        result = data._get_pattern_hit_rates()
    keys = {r["pattern_key"] for r in result}
    assert keys == {"bash_retry", "blind_edit"}


def test_tokens_saved_estimate_filters_test_fixture_patterns(polluted_db):
    """Tokens-saved count must only reflect real production patterns."""
    with _patch_soma_dir(polluted_db):
        result = data._get_tokens_saved_estimate()
    assert result["interventions_helped"] == 2  # not 3 (test_key excluded)


class TestGetRoiData:
    def test_aggregates_all(self, analytics_db, engine_state):
        # Copy engine_state.json into analytics_db dir
        src = engine_state / "engine_state.json"
        dst = analytics_db / "engine_state.json"
        dst.write_text(src.read_text())

        with _patch_soma_dir(analytics_db):
            result = data.get_roi_data()

        assert "guidance_effectiveness" in result
        assert "pattern_hit_rates" in result
        assert "tokens_saved_estimate" in result
        assert "session_health" in result
        assert "cascades_broken" in result
        assert result["guidance_effectiveness"]["total"] == 6
        assert result["session_health"]["score"] >= 80
