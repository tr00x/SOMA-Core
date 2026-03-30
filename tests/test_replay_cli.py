"""Tests for soma.cli.replay_cli — run_replay_cli."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from soma.types import Action
from soma.recorder import SessionRecorder
from soma.cli.replay_cli import run_replay_cli


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_session(path: Path, agent_actions: dict[str, list[Action]]) -> Path:
    """Write a session.json to *path* and return the path."""
    rec = SessionRecorder()
    for agent_id, actions in agent_actions.items():
        for action in actions:
            rec.record(agent_id, action)
    session_file = path / "session.json"
    rec.export(session_file)
    return session_file


def _normal_actions(n: int = 5) -> list[Action]:
    tools = ["search", "edit", "bash", "read", "write"]
    return [
        Action(
            tool_name=tools[i % len(tools)],
            output_text=f"Normal output step {i}: " + "word " * 10,
            token_count=100 + i * 5,
            cost=0.005,
            duration_sec=1.0,
        )
        for i in range(n)
    ]


def _capture_replay(session_file: Path) -> str:
    """Run run_replay_cli and capture all rich output as plain text."""
    buf = StringIO()
    console = Console(file=buf, no_color=True, width=120)

    # Monkeypatch Console inside the module so it uses our buffer
    import soma.cli.replay_cli as mod
    original_console_cls = mod.Console

    class _PatchedConsole(Console):
        def __init__(self, **kwargs):  # noqa: ANN001
            super().__init__(file=buf, no_color=True, width=120)

    mod.Console = _PatchedConsole  # type: ignore[assignment]
    try:
        run_replay_cli(str(session_file))
    finally:
        mod.Console = original_console_cls  # type: ignore[assignment]

    return buf.getvalue()


# ---------------------------------------------------------------------------
# basic smoke test — single agent
# ---------------------------------------------------------------------------

def test_replay_cli_runs_without_error(tmp_path):
    """run_replay_cli should complete without raising for a well-formed session."""
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(5)})
    # Should not raise
    run_replay_cli(str(session_file))


# ---------------------------------------------------------------------------
# output content checks
# ---------------------------------------------------------------------------

def test_replay_cli_prints_header(tmp_path):
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(5)})
    output = _capture_replay(session_file)
    assert "SOMA Replay" in output
    assert "session.json" in output
    assert "5" in output        # action count
    assert "1" in output        # agent count


def test_replay_cli_prints_table_columns(tmp_path):
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(5)})
    output = _capture_replay(session_file)
    for col in ("Step", "Agent", "Level", "Pressure", "Uncertainty", "Drift", "Errors"):
        assert col in output, f"Expected column header '{col}' in output"


def test_replay_cli_prints_summary(tmp_path):
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(5)})
    output = _capture_replay(session_file)
    assert "Summary" in output
    assert "Agent 1" in output
    assert "max level" in output
    assert "max pressure" in output


def test_replay_cli_multi_agent(tmp_path):
    """Session with multiple agents should list all agents in the summary."""
    agents = {
        "Agent 1": _normal_actions(4),
        "Agent 2": _normal_actions(3),
        "Agent 3": _normal_actions(3),
    }
    session_file = _make_session(tmp_path, agents)
    output = _capture_replay(session_file)
    assert "Agent 1" in output
    assert "Agent 2" in output
    assert "Agent 3" in output
    assert "10" in output   # total 10 actions
    assert "3" in output    # 3 agents


def test_replay_cli_step_numbers(tmp_path):
    """Each action should appear as a numbered step in the table."""
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(5)})
    output = _capture_replay(session_file)
    for step in range(1, 6):
        assert str(step) in output


def test_replay_cli_empty_session(tmp_path):
    """An empty session (no actions) should run without error."""
    rec = SessionRecorder()
    session_file = tmp_path / "session.json"
    rec.export(session_file)
    # Should not raise
    run_replay_cli(str(session_file))


def test_replay_cli_level_names_present(tmp_path):
    """At least one valid level name should appear in the table output."""
    from soma.types import ResponseMode
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(5)})
    output = _capture_replay(session_file)
    assert any(mode.name in output for mode in ResponseMode if mode.value <= 3), (
        f"Expected at least one level name in output; got:\n{output}"
    )


def test_replay_cli_pressure_values_formatted(tmp_path):
    """Pressure values should be formatted to 3 decimal places."""
    session_file = _make_session(tmp_path, {"Agent 1": _normal_actions(3)})
    output = _capture_replay(session_file)
    import re
    # e.g. "0.030" or "0.000"
    assert re.search(r"\d+\.\d{3}", output), "Expected 3-decimal pressure values in output"
