"""Persist and restore SOMAEngine state across process restarts."""

import json
import os
import tempfile
import time as _time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl

    _HAS_FLOCK = True
except ImportError:
    _HAS_FLOCK = False
from soma.engine import SOMAEngine
from soma.baseline import Baseline
from soma.budget import MultiBudget


def update_engine_state(
    mutator,
    *,
    path: str | None = None,
    default_budget: dict | None = None,
) -> None:
    """One-shot RMW helper — call ``mutator(engine)`` under the
    transaction lock. Sugar for the most common pattern:

        update_engine_state(lambda e: e.record_action(...))

    Use this instead of the legacy ``load_engine_state() + … +
    save_engine_state()`` pair when you can — the legacy pair has a
    race window where concurrent hooks lose updates.

    Migration note (2026-04-27 onward): production hook callers in
    ``hooks/common.py`` still use the legacy pair for performance
    reasons (the hook process structure assumes load-once-at-start,
    save-once-at-end). Migrating those is a separate refactor; the
    primitive is here so new code paths can be safe by construction.
    """
    with engine_state_transaction(path, default_budget=default_budget) as engine:
        mutator(engine)


@contextmanager
def engine_state_transaction(
    path: str | None = None,
    *,
    default_budget: dict | None = None,
):
    """Atomic read-modify-write of engine_state.json under flock EX.

    2026-04-27 onward: ``save_engine_state`` and ``load_engine_state`` each
    take a per-call flock, but they don't cover the
    read-mutate-write *cycle*. Two concurrent hooks can both load
    (SH locks are compatible), both mutate in memory, then race to
    save — last writer wins and the first writer's updates are
    silently lost.

    This context manager holds flock EX for the entire cycle: load
    inside the lock, yield the engine for mutation, save inside the
    same lock, then release. Concurrent callers serialize cleanly.

    On entry: yields an engine reconstituted from disk, or a fresh
    one if the state file doesn't exist (using ``default_budget``).
    On exit: writes the engine state back, atomically.

    Falls back to non-locking RMW on systems without ``fcntl`` —
    same Windows-compat compromise as the rest of persistence.py.
    """
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(".lock")

    lock_fh = None
    if _HAS_FLOCK:
        # Defensive: if we can't open the lock file (read-only FS,
        # exhausted FDs), proceed without locking rather than crash —
        # mirrors save_engine_state's resilience contract.
        try:
            lock_fh = open(lock_path, "w")
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            if lock_fh is not None:
                lock_fh.close()
            lock_fh = None
    try:
        if target.exists():
            engine = _load_engine_from_path(target)
            if engine is None:
                engine = SOMAEngine(
                    budget=default_budget or {"tokens": 100000},
                )
        else:
            engine = SOMAEngine(
                budget=default_budget or {"tokens": 100000},
            )
        yield engine
        # Save while still holding the lock — no race window.
        _save_engine_to_path(engine, target)
    finally:
        if lock_fh is not None:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            lock_fh.close()


def _load_engine_from_path(p: Path) -> SOMAEngine | None:
    """Internal helper: parse engine state JSON without taking the lock."""
    try:
        state = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return _engine_from_state(state)


def _save_engine_to_path(engine: SOMAEngine, target: Path) -> None:
    """Internal helper: atomic write without taking the lock."""
    state = _engine_to_state(engine)
    data = json.dumps(state, indent=2, default=str).encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent), suffix=".tmp", prefix=".soma_state_"
    )
    closed = False
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        closed = True
        os.rename(tmp_path, str(target))
    except BaseException:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _engine_to_state(engine: SOMAEngine) -> dict:
    """Build the JSON-serialisable state dict from an engine."""
    state = {
        "agents": {},
        "budget": engine.budget.to_dict(),
        "graph": engine._graph.to_dict(),
        "learning": engine._learning.to_dict(),
        "custom_weights": engine._custom_weights,
        "custom_thresholds": engine._custom_thresholds,
    }
    for agent_id, s in engine._agents.items():
        if agent_id == "default":
            continue
        state["agents"][agent_id] = {
            "baseline": s.baseline.to_dict(),
            "action_count": s.action_count,
            "known_tools": s.known_tools,
            "baseline_vector": s.baseline_vector,
            "level": s.mode.name,
            "last_active": s._last_active,
        }
    return state


def _engine_from_state(state: dict) -> SOMAEngine:
    """Build an engine from a state dict."""
    budget_data = state.get("budget", {})
    engine = SOMAEngine(
        budget=budget_data.get("limits", {"tokens": 100000}),
        custom_weights=state.get("custom_weights"),
        custom_thresholds=state.get("custom_thresholds"),
    )
    engine._budget = MultiBudget.from_dict(budget_data)

    from soma.graph import PressureGraph
    graph_data = state.get("graph")
    if graph_data:
        engine._graph = PressureGraph.from_dict(graph_data)

    from soma.learning import LearningEngine
    learning_data = state.get("learning")
    if learning_data:
        engine._learning = LearningEngine.from_dict(learning_data)

    # 2026-04-27 onward: prune stale agents at load time. Each Claude Code PID
    # becomes a unique agent_id; without this, engine_state.json grows
    # unboundedly as users open and close sessions. Threshold lives in
    # tunables (default 168h = 7 days). Agents missing last_active
    # (legacy state files from before that field was added) are kept
    # so an upgrade doesn't wipe pre-existing state.
    from soma.tunables import AGENT_RETENTION_HOURS
    cutoff = _time.time() - AGENT_RETENTION_HOURS * 3600

    for agent_id, agent_state in state.get("agents", {}).items():
        last_active = agent_state.get("last_active")
        if last_active is not None and last_active < cutoff:
            continue  # stale — drop on load, next save reflects the trim
        engine.register_agent(agent_id)
        s = engine._agents[agent_id]
        s.baseline = Baseline.from_dict(agent_state.get("baseline", {}))
        s.action_count = agent_state.get("action_count", 0)
        s.known_tools = agent_state.get("known_tools", [])
        s.baseline_vector = agent_state.get("baseline_vector")
        s._last_active = last_active if last_active is not None else _time.time()
        from soma.types import ResponseMode
        level_name = agent_state.get("level", "OBSERVE")
        try:
            s.mode = ResponseMode[level_name]
        except (KeyError, ValueError):
            s.mode = ResponseMode.OBSERVE
    return engine


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
            "last_active": s._last_active,
        }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(state, indent=2, default=str).encode("utf-8")

    # Atomic write: temp file -> fsync -> rename
    # Use a shared lock file so all writers and readers coordinate.
    lock_path = target.with_suffix(".lock")
    try:
        lock_fh = open(lock_path, "w") if _HAS_FLOCK else None
        try:
            if lock_fh is not None:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), suffix=".tmp", prefix=".soma_state_"
            )
            closed = False
            try:
                os.write(fd, data)
                os.fsync(fd)
                os.close(fd)
                closed = True
                # Atomic rename (POSIX guarantees atomicity on same filesystem)
                os.rename(tmp_path, str(target))
            except BaseException:
                if not closed:
                    os.close(fd)
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        finally:
            if lock_fh is not None:
                lock_fh.close()
    except OSError:
        # Fallback: direct write if atomic path fails
        target.write_text(data.decode("utf-8"))


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
        lock_path = p.with_suffix(".lock")
        lock_fh = open(lock_path, "w") if _HAS_FLOCK else None
        try:
            if lock_fh is not None:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_SH)
            state = json.loads(p.read_text())
        finally:
            if lock_fh is not None:
                lock_fh.close()
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

    # Restore agents — 2026-04-27 onward: prune stale ones at load time.
    # Each Claude Code PID becomes a unique agent_id; without this,
    # engine_state.json grows unboundedly. Threshold lives in tunables
    # (default 168h = 7 days). Agents missing last_active (legacy
    # state files) are kept so an upgrade doesn't wipe pre-existing
    # state.
    from soma.tunables import AGENT_RETENTION_HOURS
    cutoff = _time.time() - AGENT_RETENTION_HOURS * 3600

    for agent_id, agent_state in state.get("agents", {}).items():
        last_active = agent_state.get("last_active")
        if last_active is not None and last_active < cutoff:
            continue
        engine.register_agent(agent_id)
        s = engine._agents[agent_id]
        s.baseline = Baseline.from_dict(agent_state.get("baseline", {}))
        s.action_count = agent_state.get("action_count", 0)
        s.known_tools = agent_state.get("known_tools", [])
        s.baseline_vector = agent_state.get("baseline_vector")

        # Restore last_active
        s._last_active = last_active if last_active is not None else _time.time()

        # Restore mode
        from soma.types import ResponseMode
        level_name = agent_state.get("level", "OBSERVE")
        try:
            s.mode = ResponseMode[level_name]
        except (KeyError, ValueError):
            s.mode = ResponseMode.OBSERVE

    return engine
