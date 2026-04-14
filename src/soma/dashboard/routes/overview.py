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


@router.get("/heatmap/{agent_id}")
async def get_heatmap(agent_id: str):
    cells = data.get_activity_heatmap(agent_id)
    return [dataclasses.asdict(c) for c in cells]
