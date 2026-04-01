"""SOMA Phase-Aware Drift — task-phase-weighted drift computation.

Reduces drift score when tool usage matches the expected distribution for
the current task phase. No LLM calls — pure tool pattern matching.
"""

from __future__ import annotations

from collections import Counter

from soma.types import Action
from soma.vitals import compute_drift

# Expected tool distribution weights per task phase.
# Keys are tool names, values are expected usage fractions.
PHASE_WEIGHTS: dict[str, dict[str, float]] = {
    "research": {"Read": 0.4, "Grep": 0.3, "Glob": 0.2, "Bash": 0.1},
    "implement": {"Edit": 0.4, "Write": 0.3, "Read": 0.2, "Bash": 0.1},
    "test": {"Bash": 0.5, "Read": 0.3, "Edit": 0.2},
    "debug": {"Bash": 0.3, "Read": 0.3, "Edit": 0.2, "Grep": 0.2},
}


def compute_phase_aware_drift(
    actions: list[Action],
    baseline_vector: list[float],
    known_tools: list[str],
    current_phase: str,
) -> float:
    """Drift that accounts for expected tool distribution in current task phase.

    If tools match expected phase pattern, drift is reduced by up to 50%.
    If phase is unknown or tools don't match, raw drift returned unchanged.

    Args:
        actions: Recent agent actions.
        baseline_vector: Baseline behavior vector for drift comparison.
        known_tools: List of known tool names (for vector dimensionality).
        current_phase: Current task phase ("research", "implement", "test", "debug").

    Returns:
        Phase-adjusted drift value in [0, 1].
    """
    raw_drift = compute_drift(actions, baseline_vector, known_tools)

    phase_pattern = PHASE_WEIGHTS.get(current_phase, {})
    if not phase_pattern:
        return raw_drift

    if not actions:
        return raw_drift

    # Compute actual tool distribution from actions
    tool_counts = Counter(a.tool_name for a in actions)
    total = len(actions)

    # Compute phase alignment: average of min(actual_pct / expected_pct, 1.0)
    alignment_scores: list[float] = []
    for tool, expected_pct in phase_pattern.items():
        actual_pct = tool_counts.get(tool, 0) / total
        if expected_pct > 0:
            alignment_scores.append(min(actual_pct / expected_pct, 1.0))
        else:
            alignment_scores.append(1.0)

    if not alignment_scores:
        return raw_drift

    phase_alignment = sum(alignment_scores) / len(alignment_scores)

    # Reduce drift by up to 50% based on alignment
    return raw_drift * (1.0 - 0.5 * phase_alignment)
