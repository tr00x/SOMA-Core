"""SOMA Dashboard data layer — single source of truth for all dashboard data."""
from __future__ import annotations

import json
from pathlib import Path

from soma.dashboard.types import AgentSnapshot

SOMA_DIR = Path.home() / ".soma"


def get_live_agents() -> list[AgentSnapshot]:
    """Return all currently active agents from state.json + circuit files."""
    state_path = SOMA_DIR / "state.json"
    if not state_path.exists():
        return []

    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    agents_data = state.get("agents", {})
    result = []

    for agent_id, data in agents_data.items():
        esc_level = 0
        dominant = ""
        throttled = ""
        cb_block = 0
        cb_open = False

        circuit_path = SOMA_DIR / f"circuit_{agent_id}.json"
        if circuit_path.exists():
            try:
                circuit = json.loads(circuit_path.read_text())
                gs = circuit.get("guidance_state", {})
                esc_level = gs.get("escalation_level", 0)
                dominant = gs.get("dominant_signal", "")
                throttled = gs.get("throttled_tool", "")
                cb_block = circuit.get("consecutive_block", 0)
                cb_open = circuit.get("is_open", False)
            except (json.JSONDecodeError, OSError):
                pass

        result.append(AgentSnapshot(
            agent_id=agent_id,
            display_name=data.get("display_name", agent_id),
            level=data.get("level", "OBSERVE"),
            pressure=data.get("pressure", 0.0),
            action_count=data.get("action_count", 0),
            vitals=data.get("vitals", {}),
            escalation_level=esc_level,
            dominant_signal=dominant,
            throttled_tool=throttled,
            consecutive_block=cb_block,
            is_open=cb_open,
        ))

    return result
