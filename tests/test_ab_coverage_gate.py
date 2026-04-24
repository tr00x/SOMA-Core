"""Tests for the A/B coverage release gate (P2.2)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import ab_coverage_gate as gate  # noqa: E402


def _make_db(path: Path, fires: dict[str, int], arms: dict[str, tuple[int, int]]) -> None:
    """Create a fixture analytics DB with the given fires and arm counts.

    ``fires`` maps pattern_key → number of rows to insert in
    ``guidance_outcomes``. ``arms`` maps pattern → (treatment, control).
    """
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE guidance_outcomes ("
        "timestamp REAL NOT NULL, agent_id TEXT, session_id TEXT, "
        "pattern_key TEXT NOT NULL, helped INTEGER, "
        "pressure_at_injection REAL, pressure_after REAL, source TEXT)"
    )
    conn.execute(
        "CREATE TABLE ab_outcomes ("
        "timestamp REAL NOT NULL, agent_family TEXT NOT NULL, "
        "pattern TEXT NOT NULL, arm TEXT NOT NULL, "
        "pressure_before REAL, pressure_after REAL, followed INTEGER)"
    )
    ts = 1_000_000.0
    for pattern, n in fires.items():
        for i in range(n):
            conn.execute(
                "INSERT INTO guidance_outcomes VALUES (?, 'cc', 's', ?, 0, 0, 0, 'hook')",
                (ts + i, pattern),
            )
    for pattern, (t, c) in arms.items():
        for i in range(t):
            conn.execute(
                "INSERT INTO ab_outcomes VALUES (?, 'cc', ?, 'treatment', 0, 0, 0)",
                (ts + i, pattern),
            )
        for i in range(c):
            conn.execute(
                "INSERT INTO ab_outcomes VALUES (?, 'cc', ?, 'control', 0, 0, 0)",
                (ts + i, pattern),
            )
    conn.commit()
    conn.close()


def test_passes_when_all_top_patterns_have_30_30(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={
            "bash_retry": 100, "cost_spiral": 90, "blind_edit": 80,
            "context": 70, "budget": 60,
        },
        arms={
            "bash_retry": (30, 30), "cost_spiral": (30, 30),
            "blind_edit": (30, 30), "context": (30, 30),
            "budget": (30, 30),
        },
    )
    report = gate.build_report(db)
    assert report.passes
    assert len(report.patterns) == 5


def test_fails_when_one_pattern_short_on_treatment(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={
            "bash_retry": 100, "cost_spiral": 90, "blind_edit": 80,
            "context": 70, "budget": 60,
        },
        arms={
            "bash_retry": (29, 30), "cost_spiral": (30, 30),
            "blind_edit": (30, 30), "context": (30, 30),
            "budget": (30, 30),
        },
    )
    report = gate.build_report(db)
    assert not report.passes
    shorted = next(p for p in report.patterns if p.pattern == "bash_retry")
    assert shorted.treatment == 29
    assert not shorted.passes


def test_fails_when_one_pattern_short_on_control(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={"bash_retry": (30, 29)},
    )
    report = gate.build_report(db)
    assert not report.passes


def test_fails_when_pattern_has_no_ab_rows(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={},
    )
    report = gate.build_report(db)
    assert not report.passes
    assert report.patterns[0].treatment == 0
    assert report.patterns[0].control == 0


def test_empty_db_fails_gate(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(db, fires={}, arms={})
    report = gate.build_report(db)
    assert not report.passes
    assert report.patterns == []


def test_missing_db_fails_gate(tmp_path):
    report = gate.build_report(tmp_path / "does_not_exist.db")
    assert not report.passes


def test_top_n_limits_to_five(tmp_path):
    """A sixth pattern doesn't count toward the gate even if undercovered."""
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={
            "p1": 100, "p2": 90, "p3": 80, "p4": 70, "p5": 60, "p6": 50,
        },
        arms={
            "p1": (30, 30), "p2": (30, 30), "p3": (30, 30),
            "p4": (30, 30), "p5": (30, 30), "p6": (0, 0),
        },
    )
    report = gate.build_report(db)
    assert report.passes
    assert [p.pattern for p in report.patterns] == ["p1", "p2", "p3", "p4", "p5"]


def test_reset_ts_filter_ignores_pre_reset_fires(tmp_path):
    """Fires with timestamp < reset_ts must not contribute to top-5."""
    db = tmp_path / "analytics.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE guidance_outcomes ("
        "timestamp REAL NOT NULL, agent_id TEXT, session_id TEXT, "
        "pattern_key TEXT NOT NULL, helped INTEGER, "
        "pressure_at_injection REAL, pressure_after REAL, source TEXT)"
    )
    conn.execute(
        "CREATE TABLE ab_outcomes ("
        "timestamp REAL NOT NULL, agent_family TEXT NOT NULL, "
        "pattern TEXT NOT NULL, arm TEXT NOT NULL, "
        "pressure_before REAL, pressure_after REAL, followed INTEGER)"
    )
    # Stale, pre-reset pattern with lots of fires but no A/B data — the
    # filter must skip it so it doesn't poison the top-5.
    for i in range(500):
        conn.execute(
            "INSERT INTO guidance_outcomes VALUES (100.0, 'cc', 's', 'stale', 0, 0, 0, 'hook')"
        )
    # Post-reset patterns with good coverage.
    for _ in range(40):
        conn.execute(
            "INSERT INTO guidance_outcomes VALUES (2000.0, 'cc', 's', 'bash_retry', 0, 0, 0, 'hook')"
        )
    for _ in range(30):
        conn.execute(
            "INSERT INTO ab_outcomes VALUES (2000.0, 'cc', 'bash_retry', 'treatment', 0, 0, 0)"
        )
        conn.execute(
            "INSERT INTO ab_outcomes VALUES (2000.0, 'cc', 'bash_retry', 'control', 0, 0, 0)"
        )
    conn.commit()
    conn.close()

    # Write a reset log entry with ts=1500 → pre-reset 'stale' rows excluded.
    reset_log = db.parent / "ab_reset.log"
    reset_log.write_text(json.dumps({"ts": 1500.0}) + "\n")

    report = gate.build_report(db)
    patterns = [p.pattern for p in report.patterns]
    assert "stale" not in patterns
    assert patterns == ["bash_retry"]
    assert report.passes


def test_snapshot_roundtrip_pass(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={"bash_retry": (30, 30)},
    )
    snapshot = tmp_path / "snap.json"
    rc = gate.main(["snapshot", str(snapshot), "--db", str(db)])
    assert rc == 0
    assert snapshot.exists()
    data = json.loads(snapshot.read_text())
    assert data["passes"] is True
    assert data["patterns"][0]["pattern"] == "bash_retry"

    rc = gate.main(["verify", str(snapshot)])
    assert rc == 0


def test_snapshot_roundtrip_fail(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={"bash_retry": (10, 10)},
    )
    snapshot = tmp_path / "snap.json"
    rc = gate.main(["snapshot", str(snapshot), "--db", str(db)])
    assert rc == 1

    rc = gate.main(["verify", str(snapshot)])
    assert rc == 1


def test_verify_missing_snapshot_returns_2(tmp_path, capsys):
    rc = gate.main(["verify", str(tmp_path / "nope.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing" in err.lower()


def test_verify_corrupt_snapshot_returns_2(tmp_path, capsys):
    snap = tmp_path / "corrupt.json"
    snap.write_text("{not json")
    rc = gate.main(["verify", str(snap)])
    assert rc == 2


def test_check_json_output(tmp_path, capsys):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={"bash_retry": (30, 30)},
    )
    rc = gate.main(["check", "--db", str(db), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["passes"] is True
    assert data["patterns"][0]["pattern"] == "bash_retry"


def test_verify_reevaluates_thresholds(tmp_path):
    """A snapshot claiming 'passes: true' is still failed if counts say otherwise."""
    snapshot = tmp_path / "lying.json"
    snapshot.write_text(json.dumps({
        "db_path": "whatever",
        "reset_ts": 0.0,
        "min_pairs": 30,
        "top_n": 5,
        "patterns": [
            {"pattern": "bash_retry", "fires": 100, "treatment": 1, "control": 1},
        ],
        "passes": True,  # Lying!
    }))
    rc = gate.main(["verify", str(snapshot)])
    assert rc == 1
