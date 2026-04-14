"""SOMA Dashboard — quality routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["quality"])


@router.get("/agents/{agent_id}/quality")
async def get_quality(agent_id: str):
    q = data.get_quality(agent_id)
    if q is None:
        return {"grade": "-", "score": 0.0, "total": 0}
    return dataclasses.asdict(q)


@router.get("/agents/{agent_id}/fingerprint")
async def get_fingerprint(agent_id: str):
    fp = data.get_fingerprint(agent_id)
    if fp is None:
        return {}
    return fp
