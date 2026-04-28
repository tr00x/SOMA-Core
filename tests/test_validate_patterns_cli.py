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
    for i in range(35):
        before = 0.8
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="treatment",
            pressure_before=before,
            pressure_after=before - rng.gauss(0.30, 0.05),
            firing_id=f"cc-1|{pattern}|t{i}",
        )
    for i in range(35):
        before = 0.8
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="control",
            pressure_before=before,
            pressure_after=before - rng.gauss(0.05, 0.05),
            firing_id=f"cc-1|{pattern}|c{i}",
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
    for i in range(5):
        store.record_ab_outcome(
            agent_family="swe", pattern="noise_pattern", arm="treatment",
            pressure_before=0.1, pressure_after=0.0,
            firing_id=f"swe-1|noise_pattern|{i}",
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


def _seed_with_h5(store: AnalyticsStore, pattern: str):
    """Seed 35 treatment + 35 control rows where h=2 looks flat but
    h=5 shows a clear treatment win — exercises --horizon 5."""
    import random
    rng = random.Random(2026)
    for _ in range(35):
        before = 0.8
        after_h2 = before - rng.gauss(0.05, 0.02)
        after_h5 = before - rng.gauss(0.30, 0.05)
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="treatment",
            pressure_before=before, pressure_after=after_h2,
            firing_id=f"t-{_}", pressure_after_h1=after_h2,
        )
        store.update_ab_outcome_horizon(
            firing_id=f"t-{_}", horizon=5, pressure_after=after_h5,
        )
    for _ in range(35):
        before = 0.8
        after_h2 = before - rng.gauss(0.05, 0.02)
        after_h5 = before - rng.gauss(0.05, 0.02)
        store.record_ab_outcome(
            agent_family="cc", pattern=pattern, arm="control",
            pressure_before=before, pressure_after=after_h2,
            firing_id=f"c-{_}", pressure_after_h1=after_h2,
        )
        store.update_ab_outcome_horizon(
            firing_id=f"c-{_}", horizon=5, pressure_after=after_h5,
        )


def test_validate_patterns_horizon_5(tmp_path):
    """At h=2 effect is invisible; at h=5 the t-test classifies as
    validated. Confirms --horizon flag actually picks the right column."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    store = AnalyticsStore(path=soma_dir / "analytics.db")
    _seed_with_h5(store, pattern="error_cascade")
    store.close()

    # h=2 is flat → inconclusive / not validated.
    proc = _run_cli(
        ["validate-patterns", "--json", "--horizon", "2"],
        env_home=tmp_path,
    )
    payload = json.loads(proc.stdout)
    assert payload[0]["status"] != "validated"

    # h=5 reveals the win.
    proc = _run_cli(
        ["validate-patterns", "--json", "--horizon", "5"],
        env_home=tmp_path,
    )
    payload = json.loads(proc.stdout)
    assert payload[0]["status"] == "validated"
    assert payload[0]["horizon"] == 5


def test_validate_patterns_horizon_all_emits_per_horizon_block(tmp_path):
    """--horizon all should produce a 'horizons' sub-dict per pattern
    with stats at h1/h2/h5/h10."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    store = AnalyticsStore(path=soma_dir / "analytics.db")
    _seed_with_h5(store, pattern="bash_retry")
    store.close()

    proc = _run_cli(
        ["validate-patterns", "--json", "--horizon", "all"],
        env_home=tmp_path,
    )
    payload = json.loads(proc.stdout)
    row = payload[0]
    assert row["horizon"] == 1  # primary horizon = first in horizons list
    assert "horizons" in row
    assert set(row["horizons"].keys()) == {"1", "2", "5", "10"}
    # h=5 carries the validated signal; h=2 does not.
    assert row["horizons"]["5"]["status"] == "validated"


def test_validate_patterns_definition_pressure_drop_annotates_report(tmp_path):
    """--definition pressure_drop should add definition_stats to the
    JSON payload from guidance_outcomes' helped_pressure_drop column."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    store = AnalyticsStore(path=soma_dir / "analytics.db")
    # Need at least one ab_outcomes row so the pattern shows up.
    store.record_ab_outcome(
        agent_family="cc", pattern="bash_retry", arm="treatment",
        pressure_before=0.7, pressure_after=0.3,
        firing_id="cc-1|bash_retry|1",
    )
    # And matching guidance_outcomes rows with helped_pressure_drop set.
    for helped in (1, 1, 1, 0):
        store.record_guidance_outcome(
            agent_id="cc", session_id="s",
            pattern_key="bash_retry", helped=bool(helped),
            pressure_at_injection=0.7, pressure_after=0.4,
            helped_pressure_drop=bool(helped),
            helped_tool_switch=False,
            helped_error_resolved=True,
        )
    store.close()

    proc = _run_cli(
        ["validate-patterns", "--json", "--definition", "pressure_drop"],
        env_home=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    row = payload[0]
    assert row["definition"] == "pressure_drop"
    assert row["definition_stats"]["n"] == 4
    assert abs(row["definition_stats"]["rate"] - 0.75) < 0.001
