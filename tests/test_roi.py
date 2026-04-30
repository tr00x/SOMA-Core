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
            pressure_at_injection REAL, pressure_after REAL,
            source TEXT DEFAULT 'hook',
            helped_pressure_drop INTEGER,
            helped_tool_switch INTEGER,
            helped_error_resolved INTEGER
        )
    """)
    # Insert guidance outcomes
    now = time.time()
    # entropy_drop and context were retired 2026-04-25 (ultra-review).
    # Fixture uses only live REAL_PATTERN_KEYS so dashboard whitelist
    # doesn't drop the rows under us. Multi-helped columns left NULL
    # to mirror the legacy-row case the v2026.6.0 dashboard handles.
    outcomes = [
        (now - 100, "a1", "s1", "error_cascade", 1, 0.6, 0.3, "hook", None, None, None),
        (now - 90, "a1", "s1", "error_cascade", 1, 0.5, 0.2, "hook", None, None, None),
        (now - 80, "a1", "s1", "bash_retry", 1, 0.7, 0.4, "hook", None, None, None),
        (now - 70, "a1", "s1", "blind_edit", 0, 0.4, 0.5, "hook", None, None, None),
        (now - 60, "a1", "s1", "budget", 1, 0.3, 0.1, "hook", None, None, None),
        (now - 50, "a1", "s1", "budget", 0, 0.2, 0.3, "hook", None, None, None),
    ]
    conn.executemany(
        "INSERT INTO guidance_outcomes VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        assert result["estimated_tokens_saved"] == 0
        assert result["interventions_helped"] == 0
        # Honesty fields added 2026-04-25 (ultra-review): callers can
        # check is_estimate before treating the number as measurement.
        assert result["is_estimate"] is True
        assert "rough estimate" in result["methodology"]

    def test_marks_itself_as_estimate(self, analytics_db):
        with _patch_soma_dir(analytics_db):
            result = data._get_tokens_saved_estimate()
        assert result["is_estimate"] is True
        assert "synthetic" in result["methodology"] or "unmeasured" in result["methodology"]


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
            pressure_at_injection REAL, pressure_after REAL,
            source TEXT DEFAULT 'hook',
            helped_pressure_drop INTEGER,
            helped_tool_switch INTEGER,
            helped_error_resolved INTEGER
        )
    """)
    now = time.time()
    rows = [
        # Real production patterns
        (now - 10, "cc-1", "s1", "bash_retry", 1, 0.7, 0.2, "hook", None, None, None),
        (now - 20, "cc-1", "s1", "blind_edit", 1, 0.5, 0.2, "hook", None, None, None),
        # Test-fixture garbage that must be filtered
        (now - 30, "test", "s2", "retry_loop", 1, 0.6, 0.3, "hook", None, None, None),
        (now - 40, "test", "s2", "mixed", 0, 0.5, 0.5, "hook", None, None, None),
        (now - 50, "test", "s2", "bad_pattern", 0, 0.5, 0.5, "hook", None, None, None),
        (now - 60, "test", "s2", "maybe_bad", 0, 0.5, 0.5, "hook", None, None, None),
        (now - 70, "test", "s2", "test_key", 1, 0.5, 0.2, "hook", None, None, None),
    ]
    conn.executemany(
        "INSERT INTO guidance_outcomes VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
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
        assert "pattern_ab_status" in result
        assert "ab_reset_info" in result
        assert result["guidance_effectiveness"]["total"] == 6
        assert result["session_health"]["score"] >= 80


# ── Pattern A/B status cards (P1.3) ──────────────────────────────────

@pytest.fixture()
def ab_outcomes_db(tmp_path):
    """analytics.db with ab_outcomes populated for one pattern.

    Pre-registers the archive migration as applied so the post-open
    migration doesn't wipe the test rows we just inserted.
    """
    db_path = tmp_path / "analytics.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE guidance_outcomes (
            timestamp REAL, agent_id TEXT, session_id TEXT,
            pattern_key TEXT, helped INTEGER,
            pressure_at_injection REAL, pressure_after REAL,
            source TEXT DEFAULT 'hook'
        )
    """)
    conn.execute("""
        CREATE TABLE ab_outcomes (
            timestamp REAL, agent_family TEXT, pattern TEXT, arm TEXT,
            pressure_before REAL, pressure_after REAL, followed INTEGER,
            firing_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE schema_migrations (
            id TEXT PRIMARY KEY, applied_at REAL NOT NULL
        )
    """)
    now = time.time()
    for mig_id in (
        "20260424_purge_guidance_test_pollution",
        "20260424_archive_biased_ab_outcomes",
        "20260424_drop_retired_pattern_rows",
    ):
        conn.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (mig_id, now),
        )
    # 40 treatment + 40 control rows for bash_retry — enough to leave
    # the "collecting" bucket. Treatment reliably drops pressure more.
    rows = []
    for i in range(40):
        rows.append((
            now - i, "cc", "bash_retry", "treatment", 0.6, 0.3,
            f"cc-1|bash_retry|t{i}",
        ))
        rows.append((
            now - i, "cc", "bash_retry", "control", 0.6, 0.55,
            f"cc-1|bash_retry|c{i}",
        ))
    conn.executemany(
        "INSERT INTO ab_outcomes VALUES (?, ?, ?, ?, ?, ?, 0, ?)", rows,
    )
    # A few helped rows so the legacy field isn't all zero.
    conn.execute(
        "INSERT INTO guidance_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, 'hook')",
        (now, "cc", "s", "bash_retry", 1, 0.6, 0.3),
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_pattern_ab_status_returns_one_card_per_real_pattern(ab_outcomes_db):
    with _patch_soma_dir(ab_outcomes_db):
        cards = data.get_pattern_ab_status()
    from soma.contextual_guidance import REAL_PATTERN_KEYS
    patterns = {c["pattern"] for c in cards}
    assert patterns == set(REAL_PATTERN_KEYS)


def test_pattern_ab_status_validates_populated_pattern(ab_outcomes_db):
    with _patch_soma_dir(ab_outcomes_db):
        cards = data.get_pattern_ab_status()
    card = next(c for c in cards if c["pattern"] == "bash_retry")
    assert card["status"] in ("validated", "inconclusive", "collecting")
    assert card["fires_treatment"] == 40
    assert card["fires_control"] == 40
    assert card["delta_difference"] > 0  # treatment drops more pressure
    assert card["p_value"] is not None
    # Legacy helped metric is demoted but still present.
    assert card["legacy_helped"]["fires"] == 1
    assert card["legacy_helped"]["helped"] == 1


def test_pattern_ab_status_empty_pattern_is_collecting(ab_outcomes_db):
    with _patch_soma_dir(ab_outcomes_db):
        cards = data.get_pattern_ab_status()
    card = next(c for c in cards if c["pattern"] == "cost_spiral")
    assert card["status"] == "collecting"
    assert card["fires_treatment"] == 0
    assert card["fires_control"] == 0
    assert card["p_value"] is None


def test_pattern_ab_status_empty_when_no_db(tmp_path):
    with _patch_soma_dir(tmp_path):
        cards = data.get_pattern_ab_status()
    assert cards == []


# ── Reset banner ─────────────────────────────────────────────────────

def test_ab_reset_info_none_when_missing(tmp_path):
    with _patch_soma_dir(tmp_path):
        assert data.get_ab_reset_info() is None


def test_ab_reset_info_reads_latest_entry(tmp_path):
    log = tmp_path / "ab_reset.log"
    log.write_text(
        json.dumps({"ts": 1000.0, "archived_rows": 50, "reason": "old"}) + "\n"
        + json.dumps({
            "ts": 2000.0, "archived_rows": 105,
            "reason": "v2026.5.5", "soma_version": "2026.5.5",
        }) + "\n"
    )
    with _patch_soma_dir(tmp_path):
        info = data.get_ab_reset_info()
    assert info is not None
    assert info["ts"] == 2000.0
    assert info["archived_rows"] == 105
    assert info["reason"] == "v2026.5.5"
    assert info["soma_version"] == "2026.5.5"


def test_ab_reset_info_ignores_malformed_lines(tmp_path):
    log = tmp_path / "ab_reset.log"
    log.write_text("not json\n")
    with _patch_soma_dir(tmp_path):
        assert data.get_ab_reset_info() is None


# ── Archive migration writes reset log ──────────────────────────────

def test_archive_migration_writes_reset_log(tmp_path, monkeypatch):
    """The P0.3 migration must append a row to ab_reset.log so the
    dashboard banner can explain why the pattern cards are thin."""
    from soma import ab_control
    from soma.analytics import AnalyticsStore
    monkeypatch.setattr(
        ab_control, "_COUNTERS_PATH", tmp_path / "ab_counters.json",
    )

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE ab_outcomes (
            timestamp REAL NOT NULL,
            agent_family TEXT NOT NULL,
            pattern TEXT NOT NULL,
            arm TEXT NOT NULL CHECK(arm IN ('treatment', 'control')),
            pressure_before REAL, pressure_after REAL,
            followed INTEGER DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO ab_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1.0, "cc", "bash_retry", "treatment", 0.6, 0.5, 0),
    )
    conn.commit()
    conn.close()

    store = AnalyticsStore(path=db_path)
    store.close()

    reset_log = tmp_path / "ab_reset.log"
    assert reset_log.exists(), "migration must write reset log"
    entry = json.loads(reset_log.read_text().strip().splitlines()[-1])
    assert entry["archived_rows"] == 1
    assert "MD5 bias purged" in entry["reason"]
