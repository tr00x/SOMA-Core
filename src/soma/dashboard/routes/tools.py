"""SOMA Dashboard — tools routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["tools"])


@router.get("/agents/{agent_id}/tools")
async def get_tools(agent_id: str):
    stats = data.get_tool_stats(agent_id)
    return [dataclasses.asdict(s) for s in stats]
