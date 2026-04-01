"""Tests for SOMA session report generation."""

from __future__ import annotations

import re
from pathlib import Path

from soma.engine import SOMAEngine
from soma.report import generate_session_report, save_report
from soma.types import Action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine_with_actions(n_actions: int = 3) -> SOMAEngine:
    """Create an engine with *n_actions* recorded for agent 'test-agent'."""
    engine = SOMAEngine(budget={"tokens": 100_000}, context_window=200_000)
    engine.register_agent("test-agent")
    for i in range(n_actions):
        action = Action(
            tool_name="Bash" if i % 2 == 0 else "Read",
            output_text=f"output {i}",
            token_count=100,
            cost=0.001,
            error=(i == 2),  # third action is an error
        )
        engine.record_action("test-agent", action)
    return engine


# ---------------------------------------------------------------------------
# Report content tests
# ---------------------------------------------------------------------------

def test_report_contains_title():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "# SOMA Session Report" in report


def test_report_contains_summary_section():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "## Summary" in report
    assert "Actions:" in report


def test_report_contains_interventions_section():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "## Interventions" in report


def test_report_contains_cost_section():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "## Cost" in report
    assert "tokens" in report.lower()


def test_report_contains_patterns_section():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "## Patterns" in report


def test_report_contains_quality_score_section():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "## Quality Score" in report
    assert "Score:" in report


def test_empty_session_returns_no_actions():
    engine = SOMAEngine(budget={"tokens": 100_000})
    engine.register_agent("empty-agent")
    report = generate_session_report(engine, "empty-agent")
    assert "No actions recorded" in report


def test_unknown_agent_handled():
    engine = SOMAEngine(budget={"tokens": 100_000})
    report = generate_session_report(engine, "nonexistent")
    assert "not found" in report


def test_report_contains_reflexes_section():
    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "## Reflexes" in report


def test_report_reflexes_no_activity():
    """When no blocks/checkpoints, show 'No reflex activity'."""
    engine = _make_engine_with_actions()
    # Default: no block_count or checkpoint_count files exist
    report = generate_session_report(engine, "test-agent")
    assert "No reflex activity" in report


def test_report_reflexes_with_blocks(tmp_path, monkeypatch):
    """When blocks exist, show reflex stats."""
    monkeypatch.setattr("soma.hooks.common.SOMA_DIR", tmp_path)
    monkeypatch.setattr("soma.hooks.common.SESSIONS_DIR", tmp_path / "sessions")

    # Write block_count for the agent
    agent_dir = tmp_path / "sessions" / "test-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "block_count").write_text("3")
    (agent_dir / "checkpoint_count").write_text("1")

    engine = _make_engine_with_actions()
    report = generate_session_report(engine, "test-agent")
    assert "**Blocks:** 3" in report
    assert "**Checkpoints:** 1" in report
    assert "**Estimated errors prevented:** 3" in report


def test_save_report_creates_file(tmp_path: Path):
    report = "# SOMA Session Report\n\nTest report content."
    path = save_report(report, "test-agent", reports_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".md"
    assert "test-agent" in path.name
    assert path.read_text() == report


def test_save_report_filename_pattern(tmp_path: Path):
    report = "# Test"
    path = save_report(report, "my-agent", reports_dir=tmp_path)
    # Pattern: YYYY-MM-DD_HH-MM-SS_my-agent.md
    assert re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_my-agent\.md", path.name)
