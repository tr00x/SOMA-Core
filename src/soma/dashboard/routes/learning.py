"""SOMA Dashboard — learning routes."""
from __future__ import annotations

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["learning"])


@router.get("/agents/{agent_id}/learning")
async def get_learning(agent_id: str):
    state = data.get_learning_state(agent_id)
    if state is None:
        return {}
    return state
