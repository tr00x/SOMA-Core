"""SOMA Dashboard — ROI (Return on Investment) route."""
from __future__ import annotations

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["roi"])


@router.get("/roi")
async def get_roi():
    return data.get_roi_data()
