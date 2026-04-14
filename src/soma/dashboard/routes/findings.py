"""SOMA Dashboard — findings routes."""
from __future__ import annotations

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["findings"])


@router.get("/agents/{agent_id}/findings")
async def get_agent_findings(agent_id: str):
    return data.get_findings(agent_id)
