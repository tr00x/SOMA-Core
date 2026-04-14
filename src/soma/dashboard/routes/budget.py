"""SOMA Dashboard — budget routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["budget"])


@router.get("/budget")
async def get_budget():
    budget = data.get_budget_status()
    if budget is None:
        return {}
    return dataclasses.asdict(budget)
