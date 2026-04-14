"""SOMA Dashboard — config routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
async def get_config():
    return data.get_config()


@router.patch("/config")
async def patch_config(request: Request):
    body = await request.json()
    updated = data.update_config(body)
    return updated
