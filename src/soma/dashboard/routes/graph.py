"""SOMA Dashboard — graph routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
async def get_graph():
    graph = data.get_agent_graph()
    if graph is None:
        return {}
    return dataclasses.asdict(graph)
