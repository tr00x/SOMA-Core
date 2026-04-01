"""Tests for SOMA cross-session predictor — trajectory-based prediction."""

from __future__ import annotations

import json
import math

from soma.cross_session import CrossSessionPredictor, _cosine_similarity
from soma.session_store import SessionRecord, append_session


def _make_record(trajectory: list[float], **overrides) -> SessionRecord:
    defaults = dict(
        session_id="sess-001",
        agent_id="agent-1",
        started=1000.0,
        ended=2000.0,
        action_count=len(trajectory),
        final_pressure=trajectory[-1] if trajectory else 0.0,
        max_pressure=max(trajectory) if trajectory else 0.0,
        avg_pressure=sum(trajectory) / len(trajectory) if trajectory else 0.0,
        error_count=0,
        retry_count=0,
        total_tokens=1000,
        mode_transitions=[],
        pressure_trajectory=trajectory,
        tool_distribution={"Read": 10},
        phase_sequence=["research"],
        fingerprint_divergence=0.0,
    )
    defaults.update(overrides)
    return SessionRecord(**defaults)


def test_cosine_similarity_identical():
    """Cosine similarity of identical vectors is 1.0."""
    assert _cosine_similarity([1, 2, 3], [1, 2, 3]) == 1.0


def test_cosine_similarity_zero_vector():
    """Cosine similarity returns 0.0 for zero-length vector."""
    assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


def test_cosine_similarity_orthogonal():
    """Cosine similarity of orthogonal vectors is 0.0."""
    assert abs(_cosine_similarity([1, 0], [0, 1])) < 1e-10


def test_fallback_with_few_sessions():
    """CrossSessionPredictor.predict falls back to base when <3 sessions."""
    pred = CrossSessionPredictor(window=10, horizon=5)
    # Add only 2 session patterns
    pred._session_patterns = [
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    ]
    pred.update(0.3)
    pred.update(0.4)
    pred.update(0.5)

    result = pred.predict(0.75)
    # Should use base predictor (no cross-session blending)
    assert result.dominant_reason != "cross_session"


def test_predict_with_similar_trajectories():
    """CrossSessionPredictor blends prediction from similar past trajectories."""
    pred = CrossSessionPredictor(window=10, horizon=5)

    # Create 5 sessions with similar trajectory pattern: slow rise then spike
    trajectory = [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    for i in range(5):
        pred._session_patterns.append(trajectory)

    # Feed current pressures that match the beginning of the pattern
    for p in [0.1, 0.15, 0.2, 0.25, 0.3]:
        pred.update(p)

    result = pred.predict(0.75)
    # Should detect the pattern and predict escalation
    assert result.predicted_pressure > 0.3  # Higher than current


def test_cosine_threshold_08():
    """Cosine similarity > 0.8 required for cross-session match."""
    pred = CrossSessionPredictor(window=10, horizon=5)

    # Create patterns that are dissimilar from current
    for i in range(5):
        pred._session_patterns.append([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01])

    # Feed ascending pressures (opposite direction)
    for p in [0.1, 0.2, 0.3, 0.4, 0.5]:
        pred.update(p)

    result = pred.predict(0.75)
    # Should NOT find a cross-session match (cosine < 0.8 for reversed pattern)
    assert result.dominant_reason != "cross_session"


def test_to_dict_from_dict_roundtrip():
    """CrossSessionPredictor.to_dict/from_dict round-trips including session patterns."""
    pred = CrossSessionPredictor(window=8, horizon=3)
    pred._session_patterns = [[0.1, 0.2, 0.3, 0.4, 0.5]]
    pred.update(0.5)
    pred.update(0.6, {"tool": "Read", "error": False})

    d = pred.to_dict()
    restored = CrossSessionPredictor.from_dict(d)

    assert restored.window == 8
    assert restored.horizon == 3
    assert restored._session_patterns == [[0.1, 0.2, 0.3, 0.4, 0.5]]
    assert list(restored._pressures) == [0.5, 0.6]
    assert len(restored._action_log) == 1


def test_min_trajectory_length():
    """Pattern matching uses minimum trajectory length of 5 points."""
    pred = CrossSessionPredictor(window=10, horizon=5)

    # Add sessions with short trajectories (< 5)
    for i in range(5):
        pred._session_patterns.append([0.1, 0.2, 0.3])  # Only 3 points — too short

    # These should be filtered during load_history, but even if set directly,
    # the predict code should handle gracefully
    for p in [0.1, 0.2, 0.3]:
        pred.update(p)

    result = pred.predict(0.75)
    # Should fall back to base (no patterns long enough for matching)
    assert result.dominant_reason != "cross_session"


def test_load_history_filters_short(tmp_path):
    """load_history only loads trajectories with 5+ points."""
    # Write sessions — some short, some long
    short_record = _make_record([0.1, 0.2, 0.3], session_id="short")
    long_record = _make_record([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], session_id="long")

    append_session(short_record, base_dir=tmp_path)
    append_session(long_record, base_dir=tmp_path)

    pred = CrossSessionPredictor()
    pred.load_history(base_dir=tmp_path)

    assert len(pred._session_patterns) == 1  # Only the long one
    assert pred._session_patterns[0] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]


def test_predict_clamps_output():
    """Predicted pressure is clamped to [0.0, 1.0]."""
    pred = CrossSessionPredictor(window=10, horizon=5)

    # Very high trajectory
    for i in range(5):
        pred._session_patterns.append([0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.98, 0.99, 1.0, 1.0, 1.0])

    for p in [0.8, 0.85, 0.9, 0.92, 0.95]:
        pred.update(p)

    result = pred.predict(0.75)
    assert 0.0 <= result.predicted_pressure <= 1.0
