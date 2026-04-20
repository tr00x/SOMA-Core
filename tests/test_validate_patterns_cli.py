"""End-to-end test for `soma validate-patterns` CLI command."""

from __future__ import annotations

import json
import subprocess
import sys

from soma.analytics import AnalyticsStore


def _seed_treatment_vs_control(store: AnalyticsStore, pattern: str):
    """Seed 35 treatment (Δp≈0.30) vs 35 control (Δp≈0.05) rows."""
    import random
    rng = random.Random(2026)
    for _ in range(35):
        before = 0.8
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="treatment",
            pressure_before=before,
            pressure_after=before - rng.gauss(0.30, 0.05),
        )
    for _ in range(35):
        before = 0.8
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="control",
            pressure_before=before,
            pressure_after=before - rng.gauss(0.05, 0.05),
        )


def _run_cli(args: list[str], env_home) -> subprocess.CompletedProcess:
    """Invoke the CLI with HOME pointed at a tmp dir so ~/.soma resolves there."""
    proc = subprocess.run(
        [sys.executable, "-m", "soma.cli.main", *args],
        capture_output=True, text=True, env={"HOME": str(env_home), "PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    return proc


def test_validate_patterns_reports_validated(tmp_path):
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    store = AnalyticsStore(path=soma_dir / "analytics.db")
    _seed_treatment_vs_control(store, pattern="error_cascade")
    store.close()

    proc = _run_cli(["validate-patterns", "--json"], env_home=tmp_path)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert len(payload) == 1
    row = payload[0]
    assert row["pattern"] == "error_cascade"
    assert row["status"] == "validated"
    assert row["fires_treatment"] == 35
    assert row["fires_control"] == 35


def test_validate_patterns_empty_db(tmp_path):
    (tmp_path / ".soma").mkdir()
    # Don't create the DB; CLI should initialize and report no data.
    proc = _run_cli(["validate-patterns"], env_home=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "No A/B outcomes recorded" in proc.stdout


def test_validate_patterns_respects_min_pairs(tmp_path):
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    store = AnalyticsStore(path=soma_dir / "analytics.db")
    _seed_treatment_vs_control(store, pattern="bash_retry")
    store.close()

    # Artificially high min-pairs → report as still collecting.
    proc = _run_cli(
        ["validate-patterns", "--json", "--min-pairs", "100"],
        env_home=tmp_path,
    )
    payload = json.loads(proc.stdout)
    assert payload[0]["status"] == "collecting"


def test_validate_patterns_filters_by_family(tmp_path):
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    store = AnalyticsStore(path=soma_dir / "analytics.db")
    _seed_treatment_vs_control(store, pattern="entropy_drop")
    # Add noise for a different family that shouldn't appear.
    for _ in range(5):
        store.record_ab_outcome(
            agent_family="swe", pattern="noise_pattern", arm="treatment",
            pressure_before=0.1, pressure_after=0.0,
        )
    store.close()

    proc = _run_cli(
        ["validate-patterns", "--family", "cc", "--json"],
        env_home=tmp_path,
    )
    payload = json.loads(proc.stdout)
    # Only the `cc` family pattern should be in the report.
    patterns = {row["pattern"] for row in payload}
    assert "entropy_drop" in patterns
    assert "noise_pattern" not in patterns
