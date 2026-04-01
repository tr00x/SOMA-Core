"""Tests for SOMA session memory matching and injection."""

from __future__ import annotations

from soma.session_memory import (
    _cosine_similarity,
    evaluate_session_memory,
    find_similar_session,
)
from soma.session_store import SessionRecord


# ── Helpers ──────────────────────────────────────────────────────────


def _make_record(
    session_id: str = "s1",
    tool_distribution: dict | None = None,
    final_pressure: float = 0.2,
    action_count: int = 10,
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        agent_id="agent-1",
        started=1000.0,
        ended=2000.0,
        action_count=action_count,
        final_pressure=final_pressure,
        max_pressure=0.5,
        avg_pressure=0.3,
        error_count=1,
        retry_count=0,
        total_tokens=5000,
        mode_transitions=[],
        pressure_trajectory=[0.1, 0.2],
        tool_distribution=tool_distribution or {},
        phase_sequence=["research", "implement"],
        fingerprint_divergence=0.05,
    )


# ── Cosine similarity ───────────────────────────────────────────────


def test_cosine_identical_vectors():
    assert _cosine_similarity({"Read": 5, "Write": 3}, {"Read": 5, "Write": 3}) == 1.0


def test_cosine_orthogonal_vectors():
    assert _cosine_similarity({"Read": 10}, {"Write": 10}) == 0.0


def test_cosine_empty_vector():
    assert _cosine_similarity({}, {"Read": 1}) == 0.0


# ── find_similar_session ─────────────────────────────────────────────


def test_find_similar_returns_best_match():
    good = _make_record("good", {"Read": 10, "Write": 5}, final_pressure=0.2)
    ok = _make_record("ok", {"Read": 8, "Write": 4}, final_pressure=0.3)
    sessions = [good, ok]
    match, sim = find_similar_session({"Read": 10, "Write": 5}, sessions)
    assert match is not None
    assert match.session_id == "good"
    assert sim > 0.7


def test_find_similar_returns_none_below_threshold():
    different = _make_record("diff", {"Bash": 20}, final_pressure=0.1)
    match, sim = find_similar_session({"Read": 10, "Write": 5}, [different])
    assert match is None
    assert sim == 0.0


def test_find_similar_skips_unsuccessful():
    """Sessions with final_pressure > 0.5 are unsuccessful and skipped."""
    high_p = _make_record("bad", {"Read": 10, "Write": 5}, final_pressure=0.8)
    match, sim = find_similar_session({"Read": 10, "Write": 5}, [high_p])
    assert match is None
    assert sim == 0.0


# ── evaluate_session_memory ──────────────────────────────────────────


def test_evaluate_returns_injection_on_match():
    past = _make_record("past-1", {"Read": 10, "Write": 5}, final_pressure=0.15)
    result = evaluate_session_memory({"Read": 10, "Write": 5}, [past], action_count=5)
    assert result.allow is True
    assert result.reflex_kind == "session_memory"
    assert result.inject_message is not None
    assert "past-1" in result.detail


def test_evaluate_returns_allow_only_no_match():
    different = _make_record("diff", {"Bash": 20}, final_pressure=0.1)
    result = evaluate_session_memory({"Read": 10}, [different], action_count=5)
    assert result.allow is True
    assert result.inject_message is None


def test_evaluate_returns_allow_only_early_actions():
    past = _make_record("past-1", {"Read": 10, "Write": 5}, final_pressure=0.15)
    result = evaluate_session_memory({"Read": 10, "Write": 5}, [past], action_count=2)
    assert result.allow is True
    assert result.inject_message is None
