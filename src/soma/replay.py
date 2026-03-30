"""Session replay for SOMA Core — replays recorded actions through a fresh engine."""

from __future__ import annotations


from soma.engine import SOMAEngine, ActionResult
from soma.recorder import SessionRecorder


def replay_session(
    recording: SessionRecorder,
    budget: dict | None = None,
    edges: list[tuple] | None = None,
) -> list[ActionResult]:
    """Replay all recorded actions through a fresh SOMAEngine."""
    engine = SOMAEngine(budget=budget)

    seen_agents: set[str] = set()
    for ra in recording.actions:
        if ra.agent_id not in seen_agents:
            seen_agents.add(ra.agent_id)
            engine.register_agent(ra.agent_id)

    # Add graph edges if provided.
    if edges:
        for edge in edges:
            if len(edge) == 2:
                engine.add_edge(edge[0], edge[1])
            else:
                engine.add_edge(edge[0], edge[1], trust_weight=edge[2])

    # Replay actions in order.
    results: list[ActionResult] = []
    for ra in recording.actions:
        result = engine.record_action(ra.agent_id, ra.action)
        results.append(result)

    return results
