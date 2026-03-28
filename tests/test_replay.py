"""Tests for soma.replay — replay_session."""

from __future__ import annotations

import pytest

from soma.types import Action, Level
from soma.recorder import SessionRecorder
from soma.replay import replay_session
from soma.engine import ActionResult


@pytest.fixture
def normal_recording(normal_actions) -> SessionRecorder:
    """SessionRecorder with 10 normal actions under a single agent."""
    rec = SessionRecorder()
    for action in normal_actions:
        rec.record("agent-1", action)
    return rec


@pytest.fixture
def multi_agent_recording(normal_actions) -> SessionRecorder:
    """SessionRecorder with actions split across 2 agents."""
    rec = SessionRecorder()
    for i, action in enumerate(normal_actions):
        agent_id = "agent-alpha" if i % 2 == 0 else "agent-beta"
        rec.record(agent_id, action)
    return rec


# ---------------------------------------------------------------------------
# replay returns results — 10 normal actions → 10 results
# ---------------------------------------------------------------------------

def test_replay_returns_correct_count(normal_recording):
    results = replay_session(normal_recording)
    assert len(results) == 10


def test_replay_results_are_action_results(normal_recording):
    results = replay_session(normal_recording)
    for result in results:
        assert isinstance(result, ActionResult)


def test_replay_results_have_valid_levels(normal_recording):
    results = replay_session(normal_recording)
    for result in results:
        assert isinstance(result.level, Level)


def test_replay_accepts_budget(normal_recording):
    results = replay_session(normal_recording, budget={"tokens": 10_000, "cost": 5.0})
    assert len(results) == 10


def test_replay_accepts_edges(normal_recording):
    edges = [("agent-1", "agent-1", 0.9)]
    results = replay_session(normal_recording, edges=edges)
    assert len(results) == 10


def test_replay_accepts_extra_kwargs(normal_recording):
    # replay_session should work with just budget and edges
    results = replay_session(normal_recording, budget={"tokens": 50000})
    assert len(results) == 10


# ---------------------------------------------------------------------------
# replay multi-agent — actions from 2 agents → correct count
# ---------------------------------------------------------------------------

def test_replay_multi_agent_count(multi_agent_recording):
    results = replay_session(multi_agent_recording)
    assert len(results) == 10


def test_replay_multi_agent_results_are_action_results(multi_agent_recording):
    results = replay_session(multi_agent_recording)
    for result in results:
        assert isinstance(result, ActionResult)


def test_replay_empty_recording():
    rec = SessionRecorder()
    results = replay_session(rec)
    assert results == []


def test_replay_edges_two_tuple(multi_agent_recording):
    edges = [("agent-alpha", "agent-beta")]
    results = replay_session(multi_agent_recording, edges=edges)
    assert len(results) == 10
