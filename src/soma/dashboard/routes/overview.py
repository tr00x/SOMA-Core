"""SOMA Dashboard — overview routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview")
async def get_overview():
    stats = data.get_overview_stats()
    return dataclasses.asdict(stats)


@router.get("/heatmap")
async def get_heatmap(agent_id: str = ""):
    if not agent_id:
        # Default to first live agent
        agents = data.get_live_agents()
        if not agents:
            return []
        agent_id = agents[0].agent_id
    cells = data.get_activity_heatmap(agent_id)
    return [dataclasses.asdict(c) for c in cells]
