"""SOMA Dashboard — baselines routes."""
from __future__ import annotations

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["baselines"])


@router.get("/agents/{agent_id}/baselines")
async def get_baselines(agent_id: str):
    return data.get_baselines(agent_id)
