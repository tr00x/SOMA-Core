"""SOMA Dashboard — session routes."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/sessions")
async def list_sessions():
    sessions = data.get_all_sessions()
    return [dataclasses.asdict(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    detail = data.get_session_detail(session_id)
    if detail is None:
        return {"error": "session not found"}
    return dataclasses.asdict(detail)
