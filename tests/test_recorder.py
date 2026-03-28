"""Tests for soma.recorder — SessionRecorder and RecordedAction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.types import Action
from soma.recorder import RecordedAction, SessionRecorder


@pytest.fixture
def sample_action() -> Action:
    return Action(
        tool_name="bash",
        output_text="hello world",
        token_count=42,
        cost=0.001,
        duration_sec=0.5,
    )


@pytest.fixture
def recorder_with_actions(sample_action) -> SessionRecorder:
    rec = SessionRecorder()
    rec.record("agent-1", sample_action)
    rec.record("agent-2", sample_action)
    return rec


# ---------------------------------------------------------------------------
# record_action adds to list
# ---------------------------------------------------------------------------

def test_record_action_adds_to_list(sample_action):
    rec = SessionRecorder()
    assert len(rec.actions) == 0

    rec.record("agent-1", sample_action)
    assert len(rec.actions) == 1

    recorded = rec.actions[0]
    assert isinstance(recorded, RecordedAction)
    assert recorded.agent_id == "agent-1"
    assert recorded.action == sample_action
    assert recorded.timestamp > 0


def test_record_multiple_actions(sample_action):
    rec = SessionRecorder()
    for i in range(5):
        rec.record(f"agent-{i}", sample_action)
    assert len(rec.actions) == 5


# ---------------------------------------------------------------------------
# export_json writes valid JSON with correct structure
# ---------------------------------------------------------------------------

def test_export_json_valid_structure(tmp_path, recorder_with_actions):
    out = tmp_path / "session.json"
    recorder_with_actions.export(out)

    assert out.exists()
    data = json.loads(out.read_text())

    assert data["version"] == 1
    assert "actions" in data
    assert len(data["actions"]) == 2

    first = data["actions"][0]
    assert first["agent_id"] == "agent-1"
    assert "timestamp" in first
    assert "action" in first
    assert first["action"]["tool_name"] == "bash"
    assert first["action"]["output_text"] == "hello world"


def test_export_json_string_path(tmp_path, recorder_with_actions):
    out = str(tmp_path / "session_str.json")
    recorder_with_actions.export(out)
    data = json.loads(Path(out).read_text())
    assert data["version"] == 1


# ---------------------------------------------------------------------------
# import_json roundtrip — export → load → same data
# ---------------------------------------------------------------------------

def test_roundtrip_export_load(tmp_path, recorder_with_actions):
    out = tmp_path / "roundtrip.json"
    recorder_with_actions.export(out)

    loaded = SessionRecorder.load(out)

    assert len(loaded.actions) == len(recorder_with_actions.actions)

    for original, restored in zip(recorder_with_actions.actions, loaded.actions):
        assert restored.agent_id == original.agent_id
        assert abs(restored.timestamp - original.timestamp) < 1e-6
        assert restored.action.tool_name == original.action.tool_name
        assert restored.action.output_text == original.action.output_text
        assert restored.action.token_count == original.action.token_count
        assert restored.action.cost == original.action.cost
        assert restored.action.error == original.action.error
        assert restored.action.retried == original.action.retried
        assert restored.action.duration_sec == original.action.duration_sec


def test_roundtrip_preserves_metadata(tmp_path):
    action = Action(tool_name="search", output_text="result", metadata={"key": "value", "n": 99})
    rec = SessionRecorder()
    rec.record("agent-x", action)

    out = tmp_path / "meta.json"
    rec.export(out)
    loaded = SessionRecorder.load(out)

    assert loaded.actions[0].action.metadata == {"key": "value", "n": 99}
