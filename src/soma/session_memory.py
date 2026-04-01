"""SOMA Session Memory — match current session against past sessions.

Pure-function module. Computes cosine similarity between tool-usage vectors,
finds similar successful past sessions, and generates experience-based
guidance injections as ReflexResult values.
"""

from __future__ import annotations

import math

from soma.reflexes import ReflexResult
from soma.session_store import SessionRecord


def _cosine_similarity(
    a: dict[str, int | float],
    b: dict[str, int | float],
) -> float:
    """Cosine similarity between two sparse tool-distribution vectors.

    Returns 0.0 for empty or orthogonal vectors, 1.0 for identical directions.
    """
    if not a or not b:
        return 0.0

    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def find_similar_session(
    current_tools: dict[str, int],
    sessions: list[SessionRecord],
    min_similarity: float = 0.7,
) -> tuple[SessionRecord | None, float]:
    """Find the most similar successful past session.

    Filters sessions by:
      - cosine similarity >= min_similarity
      - final_pressure <= 0.5 (successful outcome)

    Returns (best_match, similarity) or (None, 0.0).
    """
    best: SessionRecord | None = None
    best_sim = 0.0

    for session in sessions:
        # Skip unsuccessful sessions (high final pressure)
        if session.final_pressure > 0.5:
            continue

        sim = _cosine_similarity(current_tools, session.tool_distribution)
        if sim >= min_similarity and sim > best_sim:
            best = session
            best_sim = sim

    if best is None:
        return None, 0.0

    return best, best_sim


def evaluate_session_memory(
    current_tools: dict[str, int],
    sessions: list[SessionRecord],
    action_count: int = 0,
) -> ReflexResult:
    """Evaluate session memory for experience-based guidance injection.

    Returns a ReflexResult with an injection message when a similar
    successful past session is found. Returns allow-only on early
    actions (< 3) or when no match is found.
    """
    # Not enough actions to establish a pattern
    if action_count < 3:
        return ReflexResult(allow=True)

    match, sim = find_similar_session(current_tools, sessions)
    if match is None:
        return ReflexResult(allow=True)

    # Build top-3 tools string
    sorted_tools = sorted(
        match.tool_distribution.items(), key=lambda x: x[1], reverse=True
    )
    top_tools = ", ".join(f"{t}:{c}" for t, c in sorted_tools[:3])

    inject = (
        f"[SOMA] Similar past session found (similarity {sim:.0%}): "
        f"{match.action_count} actions, final pressure {match.final_pressure:.0%}. "
        f"Top tools: {top_tools}."
    )

    return ReflexResult(
        allow=True,
        reflex_kind="session_memory",
        inject_message=inject,
        detail=f"session={match.session_id}, similarity={sim:.2f}",
    )
