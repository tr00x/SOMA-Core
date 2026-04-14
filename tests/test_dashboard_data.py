"""Tests for the dashboard data layer."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from soma.dashboard.data import get_live_agents
from soma.dashboard.types import AgentSnapshot

FIXTURES = Path(__file__).parent / "fixtures" / "dashboard"


@pytest.fixture
def soma_dir(tmp_path, monkeypatch):
    """Set up a fake ~/.soma with fixture data."""
    shutil.copy(FIXTURES / "state.json", tmp_path / "state.json")
    shutil.copy(FIXTURES / "circuit_cc-1001.json", tmp_path / "circuit_cc-1001.json")
    monkeypatch.setattr("soma.dashboard.data.SOMA_DIR", tmp_path)
    return tmp_path


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
