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
        "pressure_before REAL, pressure_after REAL, followed INTEGER, "
        "firing_id TEXT)"
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
                "INSERT INTO ab_outcomes VALUES (?, 'cc', ?, 'treatment', 0, 0, 0, ?)",
                (ts + i, pattern, f"fid-{pattern}-t-{i}"),
            )
        for i in range(c):
            conn.execute(
                "INSERT INTO ab_outcomes VALUES (?, 'cc', ?, 'control', 0, 0, 0, ?)",
                (ts + i, pattern, f"fid-{pattern}-c-{i}"),
            )
    conn.commit()
    conn.close()


def test_passes_when_all_top_patterns_have_15_15(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={
            "bash_retry": 100, "cost_spiral": 90, "blind_edit": 80,
            "error_cascade": 70, "budget": 60,
        },
        arms={
            "bash_retry": (15, 15), "cost_spiral": (15, 15),
            "blind_edit": (15, 15), "error_cascade": (15, 15),
            "budget": (15, 15),
        },
    )
    report = gate.build_report(db)
    assert report.passes
    assert len(report.patterns) == 5
    assert all(p.status == "ready" for p in report.patterns)


def test_fails_when_one_arm_has_evidence_and_other_doesnt(tmp_path):
    """Asymmetric bias rule: (14, 15) means one arm has crossed the
    claim threshold and the other hasn't. That's the structural bias
    the gate exists to catch.
    """
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={
            "bash_retry": 100, "cost_spiral": 90, "blind_edit": 80,
            "error_cascade": 70, "budget": 60,
        },
        arms={
            "bash_retry": (14, 15), "cost_spiral": (15, 15),
            "blind_edit": (15, 15), "error_cascade": (15, 15),
            "budget": (15, 15),
        },
    )
    report = gate.build_report(db)
    assert not report.passes
    biased = next(p for p in report.patterns if p.pattern == "bash_retry")
    assert biased.treatment == 14
    assert biased.status == "biased"
    assert not biased.passes


def test_fails_when_control_short_treatment_full(tmp_path):
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={"bash_retry": (15, 14)},
    )
    report = gate.build_report(db)
    assert not report.passes
    assert report.patterns[0].status == "biased"


def test_passes_when_pattern_has_no_ab_rows_yet(tmp_path):
    """A pattern that fired but hasn't yet recorded any A/B rows is
    bootstrapping — no claim is being made, so there's no bias to
    catch. The gate lets it through.
    """
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={},
    )
    report = gate.build_report(db)
    assert report.passes
    assert report.patterns[0].status == "collecting"


def test_empty_db_passes_gate(tmp_path):
    """No fires post-reset = no claims = no bias risk. The gate
    passes. Compare to the previous policy where empty was an
    automatic FAIL — that fought the project's "ship while
    collecting" posture without catching real bias.
    """
    db = tmp_path / "analytics.db"
    _make_db(db, fires={}, arms={})
    report = gate.build_report(db)
    assert report.passes
    assert report.patterns == []


def test_missing_db_passes_gate(tmp_path):
    report = gate.build_report(tmp_path / "does_not_exist.db")
    assert report.passes


def test_gate_retired_set_matches_soma_source_of_truth():
    """The gate hardcodes RETIRED_PATTERN_KEYS because it runs as a
    standalone script in CI without the soma package installed. This
    test (which DOES have the package) pins the two copies together —
    if a future commit retires a pattern in
    ``soma.contextual_guidance`` and forgets the gate copy, the gate
    would silently include a pattern in top-N that can never
    accumulate new rows.
    """
    from soma.contextual_guidance import RETIRED_PATTERN_KEYS as soma_set
    assert gate.RETIRED_PATTERN_KEYS == soma_set, (
        "RETIRED_PATTERN_KEYS drift between gate script "
        f"({sorted(gate.RETIRED_PATTERN_KEYS)}) and "
        f"soma.contextual_guidance ({sorted(soma_set)}). Update "
        ".github/scripts/ab_coverage_gate.py to match."
    )


def test_retired_patterns_excluded_from_top_n(tmp_path, monkeypatch):
    """Retired patterns can never accumulate new rows; they must not
    appear in the gate's top-N list or they'd pin the gate to FAIL
    forever after retirement.

    The current ``RETIRED_PATTERN_KEYS`` is empty (everything was
    resurrected 2026-04-30), so this test simulates a future retirement
    by patching the set, then confirms the SQL exclusion still works.
    """
    monkeypatch.setattr(
        gate, "RETIRED_PATTERN_KEYS", frozenset({"old_a", "old_b", "old_c"}),
    )
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={
            # Simulated-retired (high historical fire count) — filtered out.
            "old_a": 500, "old_b": 400, "old_c": 300,
            # Active patterns with valid coverage.
            "bash_retry": 100, "budget": 90, "blind_edit": 80,
            "cost_spiral": 70, "error_cascade": 60,
        },
        arms={
            "bash_retry": (15, 15), "budget": (15, 15),
            "blind_edit": (15, 15), "cost_spiral": (15, 15),
            "error_cascade": (15, 15),
        },
    )
    report = gate.build_report(db)
    pattern_names = [p.pattern for p in report.patterns]
    assert set(pattern_names).isdisjoint(gate.RETIRED_PATTERN_KEYS)
    assert pattern_names == [
        "bash_retry", "budget", "blind_edit", "cost_spiral", "error_cascade",
    ]
    assert report.passes


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
        "pressure_before REAL, pressure_after REAL, followed INTEGER, "
        "firing_id TEXT)"
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
    for i in range(30):
        conn.execute(
            "INSERT INTO ab_outcomes VALUES (2000.0, 'cc', 'bash_retry', 'treatment', 0, 0, 0, ?)",
            (f"fid-bash_retry-t-{i}",),
        )
        conn.execute(
            "INSERT INTO ab_outcomes VALUES (2000.0, 'cc', 'bash_retry', 'control', 0, 0, 0, ?)",
            (f"fid-bash_retry-c-{i}",),
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
    # Path scrubbing: committed snapshots must use the canonical
    # placeholder, never the maintainer's $HOME path.
    assert data["db_path"] == "~/.soma/analytics.db"

    rc = gate.main(["verify", str(snapshot)])
    assert rc == 0


def test_snapshot_roundtrip_fail(tmp_path):
    """Asymmetric coverage (treatment full, control empty) must fail
    both at snapshot time and on verify replay.
    """
    db = tmp_path / "analytics.db"
    _make_db(
        db,
        fires={"bash_retry": 100},
        arms={"bash_retry": (20, 0)},
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
    """A snapshot claiming 'passes: true' is still failed if counts
    say otherwise. Use asymmetric coverage (treatment crossed
    threshold, control didn't) so the reevaluation actually flips.
    """
    snapshot = tmp_path / "lying.json"
    snapshot.write_text(json.dumps({
        "db_path": "whatever",
        "reset_ts": 0.0,
        "min_pairs": 30,
        "top_n": 5,
        "patterns": [
            {"pattern": "bash_retry", "fires": 100, "treatment": 20, "control": 1},
        ],
        "passes": True,  # Lying!
    }))
    rc = gate.main(["verify", str(snapshot)])
    assert rc == 1


def test_arm_counts_excludes_null_firing_id(tmp_path):
    """v2026.6.1 fix #2 — gate must agree with the t-test on which rows count.

    validate-patterns filters firing_id IS NOT NULL (analytics.py); the
    gate must apply the same filter so a future bias-class row written
    without a firing_id can't inflate the gate while being silently
    excluded from the t-test population.
    """
    db = tmp_path / "analytics.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE ab_outcomes ("
        "timestamp REAL NOT NULL, agent_family TEXT NOT NULL, "
        "pattern TEXT NOT NULL, arm TEXT NOT NULL, "
        "pressure_before REAL, pressure_after REAL, followed INTEGER, "
        "firing_id TEXT)"
    )
    # Two clean rows with firing_id, plus one legacy row with NULL.
    conn.execute(
        "INSERT INTO ab_outcomes VALUES (1.0, 'cc', 'budget', 'treatment', 0, 0, 0, 'fid-1')"
    )
    conn.execute(
        "INSERT INTO ab_outcomes VALUES (2.0, 'cc', 'budget', 'control', 0, 0, 0, 'fid-2')"
    )
    conn.execute(
        "INSERT INTO ab_outcomes VALUES (3.0, 'cc', 'budget', 'treatment', 0, 0, 0, NULL)"
    )
    conn.commit()
    t, c = gate._arm_counts(conn, "budget")
    conn.close()
    assert (t, c) == (1, 1), (
        f"NULL firing_id row leaked into gate counts: got T={t} C={c}, "
        f"expected T=1 C=1 (only rows with firing_id)"
    )
