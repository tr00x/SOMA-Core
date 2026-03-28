"""Persist and restore SOMAEngine state across process restarts."""

import json
from pathlib import Path
from soma.engine import SOMAEngine
from soma.baseline import Baseline
from soma.budget import MultiBudget


def save_engine_state(engine: SOMAEngine, path: str | None = None) -> None:
    """Save full engine state to JSON file."""
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    state = {
        "agents": {},
        "budget": engine.budget.to_dict(),
        "graph": engine._graph.to_dict(),
        "learning": engine._learning.to_dict(),
    }

    for agent_id, s in engine._agents.items():
        state["agents"][agent_id] = {
            "baseline": s.baseline.to_dict(),
            "action_count": s.action_count,
            "known_tools": s.known_tools,
            "baseline_vector": s.baseline_vector,
            "level": s.ladder.current.name,
        }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, indent=2, default=str))


def load_engine_state(path: str | None = None) -> SOMAEngine | None:
    """Restore engine from saved state. Returns None if no state file."""
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    p = Path(path)
    if not p.exists():
        return None

    try:
        state = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Rebuild engine
    budget_data = state.get("budget", {})
    engine = SOMAEngine(budget=budget_data.get("limits", {"tokens": 100000}))

    # Restore budget spent
    budget = MultiBudget.from_dict(budget_data)
    engine._budget = budget

    # Restore graph
    from soma.graph import PressureGraph
    graph_data = state.get("graph")
    if graph_data:
        engine._graph = PressureGraph.from_dict(graph_data)

    # Restore learning engine
    from soma.learning import LearningEngine
    learning_data = state.get("learning")
    if learning_data:
        engine._learning = LearningEngine.from_dict(learning_data)

    # Restore agents
    for agent_id, agent_state in state.get("agents", {}).items():
        engine.register_agent(agent_id)
        s = engine._agents[agent_id]
        s.baseline = Baseline.from_dict(agent_state.get("baseline", {}))
        s.action_count = agent_state.get("action_count", 0)
        s.known_tools = agent_state.get("known_tools", [])
        s.baseline_vector = agent_state.get("baseline_vector")

        # Restore level
        from soma.types import Level
        level_name = agent_state.get("level", "HEALTHY")
        try:
            s.ladder.force_level(Level[level_name])
        except (KeyError, ValueError):
            pass

    return engine
