"""Tests for guidance state and signal pressure persistence in circuit files."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def circuit_dir(tmp_path):
    """Patch SOMA_DIR to an isolated temp directory."""
    with patch("soma.hooks.common.SOMA_DIR", tmp_path):
        yield tmp_path


def _make_guidance_state(**kwargs):
    """Create a GuidanceState with defaults, overriding with kwargs."""
    from soma.guidance_state import GuidanceState
    return GuidanceState(**kwargs)


# -- GuidanceState read/write --------------------------------------------------


def test_read_returns_default_when_no_file(circuit_dir):
    """read_guidance_state returns a fresh GuidanceState when no circuit file exists."""
    from soma.hooks.common import read_guidance_state

    gs = read_guidance_state("test-agent")
    assert gs is not None
    # Default state should have escalation_level 0
    assert gs.escalation_level == 0


def test_write_then_read_roundtrip(circuit_dir):
    """Writing then reading a GuidanceState preserves the data."""
    from soma.hooks.common import read_guidance_state, write_guidance_state

    gs = _make_guidance_state(escalation_level=2)
    write_guidance_state(gs, "roundtrip-agent")

    loaded = read_guidance_state("roundtrip-agent")
    assert loaded.escalation_level == 2


def test_write_merges_into_existing_circuit_file(circuit_dir):
    """Writing guidance state doesn't clobber other data in the circuit file."""
    path = circuit_dir / "circuit_merge-agent.json"
    path.write_text(json.dumps({
        "agent_id": "merge-agent",
        "consecutive_block": 3,
        "is_open": False,
    }))

    from soma.hooks.common import write_guidance_state

    gs = _make_guidance_state(escalation_level=1)
    write_guidance_state(gs, "merge-agent")

    data = json.loads(path.read_text())
    # Original keys preserved
    assert data["agent_id"] == "merge-agent"
    assert data["consecutive_block"] == 3
    # New key added
    assert "guidance_state" in data


def test_read_from_circuit_with_other_data(circuit_dir):
    """read_guidance_state extracts guidance_state even when circuit has other keys."""
    from soma.hooks.common import read_guidance_state

    # Seed circuit file with extra data
    path = circuit_dir / "circuit_mixed-agent.json"
    path.write_text(json.dumps({
        "agent_id": "mixed-agent",
        "is_open": True,
        "guidance_state": {"escalation_level": 3, "last_guidance_time": 100.0},
    }))

    gs = read_guidance_state("mixed-agent")
    assert gs.escalation_level == 3


# -- Signal pressures ----------------------------------------------------------


def test_write_signal_pressures_roundtrip(circuit_dir):
    """Writing then reading signal pressures preserves values."""
    from soma.hooks.common import read_signal_pressures, write_signal_pressures

    pressures = {
        "uncertainty": 0.1234,
        "drift": 0.5678,
        "error_rate": 0.0,
        "cost": 0.9999,
    }
    write_signal_pressures(pressures, "pressure-agent")

    loaded = read_signal_pressures("pressure-agent")
    assert loaded["uncertainty"] == 0.1234
    assert loaded["drift"] == 0.5678
    assert loaded["error_rate"] == 0.0
    assert loaded["cost"] == 0.9999


def test_signal_pressures_merge_with_existing(circuit_dir):
    """Signal pressures don't clobber other circuit data."""
    path = circuit_dir / "circuit_sp-merge.json"
    path.write_text(json.dumps({
        "agent_id": "sp-merge",
        "is_open": False,
        "guidance_state": {"escalation_level": 1},
    }))

    from soma.hooks.common import write_signal_pressures

    write_signal_pressures({"uncertainty": 0.5}, "sp-merge")

    data = json.loads(path.read_text())
    # Original keys preserved
    assert data["agent_id"] == "sp-merge"
    assert data["guidance_state"]["escalation_level"] == 1
    # Signal pressures added
    assert data["signal_pressures"]["uncertainty"] == 0.5
