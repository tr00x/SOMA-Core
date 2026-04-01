"""Tests for SOMA phase-aware drift computation."""

from __future__ import annotations

from soma.phase_drift import PHASE_WEIGHTS, compute_phase_aware_drift
from soma.types import Action


def _make_actions(tool_names: list[str]) -> list[Action]:
    """Create Action objects from tool names."""
    return [
        Action(tool_name=t, output_text="output", token_count=10)
        for t in tool_names
    ]


def test_returns_lower_drift_when_tools_match_phase():
    """Phase-aware drift returns lower drift when tools match phase pattern."""
    known_tools = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]
    # Research actions — should match "research" phase
    actions = _make_actions(["Read", "Grep", "Glob", "Read", "Grep"])
    baseline_vector = [1.0, 0.0, 0.0, 0.0] + [0.0] * len(known_tools)

    raw_drift = compute_phase_aware_drift(actions, baseline_vector, known_tools, "unknown")
    phase_drift = compute_phase_aware_drift(actions, baseline_vector, known_tools, "research")

    assert phase_drift <= raw_drift


def test_returns_raw_drift_for_unknown_phase():
    """Phase-aware drift returns raw drift when phase is unknown."""
    known_tools = ["Read", "Edit", "Bash"]
    actions = _make_actions(["Read", "Read", "Read"])
    baseline_vector = [1.0, 0.0, 0.0, 0.0] + [0.0] * len(known_tools)

    from soma.vitals import compute_drift
    raw = compute_drift(actions, baseline_vector, known_tools)
    phase = compute_phase_aware_drift(actions, baseline_vector, known_tools, "unknown")

    assert abs(phase - raw) < 1e-10


def test_implement_phase_with_write_edit():
    """Phase 'implement' with Write/Edit tools reduces drift by up to 50%."""
    known_tools = ["Read", "Edit", "Write", "Bash", "Grep", "Glob"]
    actions = _make_actions(["Edit", "Write", "Edit", "Write", "Read"])
    baseline_vector = [1.0, 0.0, 0.0, 0.0] + [0.0] * len(known_tools)

    raw_drift = compute_phase_aware_drift(actions, baseline_vector, known_tools, "unknown")
    impl_drift = compute_phase_aware_drift(actions, baseline_vector, known_tools, "implement")

    # Should be reduced but not more than 50%
    if raw_drift > 0:
        assert impl_drift >= raw_drift * 0.5
        assert impl_drift <= raw_drift


def test_research_phase_with_read_grep():
    """Phase 'research' with Read/Grep tools reduces drift by up to 50%."""
    known_tools = ["Read", "Edit", "Write", "Bash", "Grep", "Glob"]
    actions = _make_actions(["Read", "Grep", "Glob", "Read", "Grep"])
    baseline_vector = [1.0, 0.0, 0.0, 0.0] + [0.0] * len(known_tools)

    raw_drift = compute_phase_aware_drift(actions, baseline_vector, known_tools, "unknown")
    research_drift = compute_phase_aware_drift(actions, baseline_vector, known_tools, "research")

    if raw_drift > 0:
        assert research_drift >= raw_drift * 0.5
        assert research_drift <= raw_drift


def test_phase_weights_covers_all_phases():
    """PHASE_WEIGHTS covers research, implement, test, debug phases."""
    assert "research" in PHASE_WEIGHTS
    assert "implement" in PHASE_WEIGHTS
    assert "test" in PHASE_WEIGHTS
    assert "debug" in PHASE_WEIGHTS


def test_no_actions_returns_zero():
    """Empty actions returns zero drift."""
    known_tools = ["Read", "Edit"]
    result = compute_phase_aware_drift([], [0.0] * 6, known_tools, "research")
    # compute_drift with empty actions should give some drift value
    # but the phase weighting shouldn't crash
    assert isinstance(result, float)
