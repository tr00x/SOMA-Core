"""SOMA Dashboard — analytics routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/agents/{agent_id}/pressure-history")
async def get_pressure_history(agent_id: str):
    points = data.get_pressure_history(agent_id)
    return [dataclasses.asdict(p) for p in points]


@router.get("/agents/{agent_id}/timeline")
async def get_timeline(agent_id: str):
    events = data.get_agent_timeline(agent_id)
    return [dataclasses.asdict(e) for e in events]


@router.get("/agents/{agent_id}/predictions")
async def get_predictions(agent_id: str):
    result = data.get_prediction(agent_id)
    if result is None:
        return {}
    return result
