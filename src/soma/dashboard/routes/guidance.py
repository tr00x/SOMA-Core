"""SOMA Dashboard — guidance routes."""
from __future__ import annotations

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["guidance"])


@router.get("/agents/{agent_id}/audit")
async def get_agent_audit(agent_id: str):
    return data.get_audit_log(agent_id)


@router.get("/agents/{agent_id}/guidance")
async def get_agent_guidance_state(agent_id: str):
    # Guidance state is part of the circuit file, read via get_live_agents
    agents = data.get_live_agents()
    for a in agents:
        if a.agent_id == agent_id:
            return {
                "escalation_level": a.escalation_level,
                "dominant_signal": a.dominant_signal,
                "throttled_tool": a.throttled_tool,
                "consecutive_block": a.consecutive_block,
                "is_open": a.is_open,
            }
    return {"error": "agent not found"}
