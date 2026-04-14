"""SOMA Dashboard — agent routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents")
async def list_agents():
    agents = data.get_live_agents()
    return [dataclasses.asdict(a) for a in agents]


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agents = data.get_live_agents()
    for a in agents:
        if a.agent_id == agent_id:
            return dataclasses.asdict(a)
    raise HTTPException(status_code=404, detail="agent not found")
