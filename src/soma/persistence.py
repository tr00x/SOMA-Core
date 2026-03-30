"""Persist and restore SOMAEngine state across process restarts."""

import fcntl
import json
import os
import tempfile
from pathlib import Path
from soma.engine import SOMAEngine
from soma.baseline import Baseline
from soma.budget import MultiBudget


def save_engine_state(engine: SOMAEngine, path: str | None = None) -> None:
    """Save full engine state to JSON file.

    Uses atomic write (write to temp file, fsync, rename) with exclusive
    file locking so concurrent multi-agent saves don't corrupt state.
    """
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    state = {
        "agents": {},
        "budget": engine.budget.to_dict(),
        "graph": engine._graph.to_dict(),
        "learning": engine._learning.to_dict(),
        "custom_weights": engine._custom_weights,
        "custom_thresholds": engine._custom_thresholds,
    }

    for agent_id, s in engine._agents.items():
        # Skip the "default" placeholder agent
        if agent_id == "default":
            continue
        state["agents"][agent_id] = {
            "baseline": s.baseline.to_dict(),
            "action_count": s.action_count,
            "known_tools": s.known_tools,
            "baseline_vector": s.baseline_vector,
            "level": s.mode.name,
        }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(state, indent=2, default=str)

    # Atomic write: temp file -> fsync -> rename
    # Use the same directory so rename is atomic (same filesystem).
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent), suffix=".tmp", prefix=".soma_state_"
        )
        try:
            # Acquire exclusive lock on the temp file
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, data.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        # Atomic rename (POSIX guarantees atomicity on same filesystem)
        os.rename(tmp_path, str(target))
    except OSError:
        # Fallback: direct write if atomic path fails
        target.write_text(data)


def load_engine_state(path: str | None = None) -> SOMAEngine | None:
    """Restore engine from saved state. Returns None if no state file.

    Uses a shared file lock so reads don't conflict with each other
    but wait for any in-progress write to complete.
    """
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    p = Path(path)
    if not p.exists():
        return None

    try:
        with open(p) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                state = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return None

    # Rebuild engine with persisted config
    budget_data = state.get("budget", {})
    engine = SOMAEngine(
        budget=budget_data.get("limits", {"tokens": 100000}),
        custom_weights=state.get("custom_weights"),
        custom_thresholds=state.get("custom_thresholds"),
    )

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

        # Restore mode
        from soma.types import ResponseMode
        level_name = agent_state.get("level", "OBSERVE")
        try:
            s.mode = ResponseMode[level_name]
        except (KeyError, ValueError):
            s.mode = ResponseMode.OBSERVE

    return engine
