"""
Regression for v2026.6.x fix #24 — engine_state.json must not grow
unboundedly as Claude Code PIDs come and go. Each session writes a
new agent_id (``cc-{ppid}``); without pruning the state file
accumulates indefinitely.

Pruning policy: drop agents whose ``last_active`` is older than
``AGENT_RETENTION_HOURS`` (default 168h = 7 days). Applied at load
time so the next save reflects the trimmed set.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from soma.persistence import load_engine_state, save_engine_state


def test_stale_agents_pruned_on_load(tmp_path: Path) -> None:
    """Agents with last_active >7d ago must be evicted on load."""
    from soma.engine import SOMAEngine

    engine = SOMAEngine(budget={"tokens": 100000})
    engine.register_agent("fresh-agent")
    engine.register_agent("stale-agent")
    # Put fresh-agent's last_active to now and stale-agent's to 8 days ago.
    now = time.time()
    engine._agents["fresh-agent"]._last_active = now
    engine._agents["stale-agent"]._last_active = now - 8 * 86400

    state_path = tmp_path / "engine_state.json"
    save_engine_state(engine, str(state_path))

    # Sanity: state was saved with both agents.
    state = json.loads(state_path.read_text())
    assert "fresh-agent" in state["agents"]
    assert "stale-agent" in state["agents"]

    # Now load → stale must be gone.
    reloaded = load_engine_state(str(state_path))
    assert "fresh-agent" in reloaded._agents
    assert "stale-agent" not in reloaded._agents


def test_fresh_agents_kept(tmp_path: Path) -> None:
    """Sanity — recent agents (last_active within retention) survive."""
    from soma.engine import SOMAEngine

    engine = SOMAEngine(budget={"tokens": 100000})
    now = time.time()
    for i in range(5):
        aid = f"cc-{1000 + i}"
        engine.register_agent(aid)
        engine._agents[aid]._last_active = now - i * 3600  # 0, 1, 2, 3, 4h ago
    state_path = tmp_path / "fresh.json"
    save_engine_state(engine, str(state_path))
    reloaded = load_engine_state(str(state_path))
    assert len(reloaded._agents) == 5


def test_no_last_active_means_keep(tmp_path: Path) -> None:
    """Defensive: if last_active is missing (legacy state file), keep
    the agent rather than evicting silently. Otherwise a v2026.6.x
    upgrade would wipe pre-existing agents from older installs."""
    state_path = tmp_path / "legacy.json"
    state_path.write_text(json.dumps({
        "agents": {
            "legacy-agent": {
                "baseline": {},
                "action_count": 5,
                "known_tools": [],
                "baseline_vector": None,
                "level": "OBSERVE",
                # no "last_active" field
            }
        },
        "budget": {"limits": {"tokens": 100000}, "spent": {}},
        "graph": {},
        "learning": {},
        "custom_weights": None,
        "custom_thresholds": None,
    }))
    reloaded = load_engine_state(str(state_path))
    assert "legacy-agent" in reloaded._agents
