"""Tests for the SOMA Dashboard WebSocket module."""
from __future__ import annotations

import json

import pytest

from soma.dashboard.ws import ConnectionManager, _compute_diff


# ------------------------------------------------------------------
# _compute_diff tests
# ------------------------------------------------------------------


def test_compute_diff_no_change():
    old = {"a": 1, "b": 2}
    assert _compute_diff(old, old) == {}


def test_compute_diff_value_changed():
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 3}
    assert _compute_diff(old, new) == {"b": 3}


def test_compute_diff_key_added():
    old = {"a": 1}
    new = {"a": 1, "b": 2}
    assert _compute_diff(old, new) == {"b": 2}


def test_compute_diff_key_removed():
    old = {"a": 1, "b": 2}
    new = {"a": 1}
    assert _compute_diff(old, new) == {"b": None}


def test_compute_diff_nested_change():
    old = {"agents": {"cc-1": {"pressure": 0.3}}}
    new = {"agents": {"cc-1": {"pressure": 0.5}}}
    diff = _compute_diff(old, new)
    assert "agents" in diff
    assert diff["agents"]["cc-1"]["pressure"] == 0.5


# ------------------------------------------------------------------
# ConnectionManager tests
# ------------------------------------------------------------------


def test_connection_manager_state_diff(tmp_path, monkeypatch):
    """get_state_diff returns full state on first read, diff on subsequent."""
    monkeypatch.setattr("soma.dashboard.ws.SOMA_DIR", tmp_path)

    mgr = ConnectionManager()

    # No state file → None
    assert mgr.get_state_diff() is None

    # Write initial state
    state1 = {"agents": {"cc-1": {"pressure": 0.2}}, "budget": {"health": 0.9}}
    (tmp_path / "state.json").write_text(json.dumps(state1))

    # First read → full state
    result = mgr.get_state_diff()
    assert result == state1

    # No change → None
    assert mgr.get_state_diff() is None

    # Change pressure → diff only contains agents key
    state2 = {"agents": {"cc-1": {"pressure": 0.5}}, "budget": {"health": 0.9}}
    (tmp_path / "state.json").write_text(json.dumps(state2))

    diff = mgr.get_state_diff()
    assert diff is not None
    assert "agents" in diff
    # Budget unchanged → not in diff
    assert "budget" not in diff


def test_connection_manager_disconnect_missing():
    """Disconnecting a non-connected websocket should not crash."""
    mgr = ConnectionManager()

    class FakeWS:
        pass

    mgr.disconnect(FakeWS())  # Should not raise
