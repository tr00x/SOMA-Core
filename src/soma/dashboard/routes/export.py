"""SOMA Dashboard — export routes."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from soma.dashboard import data

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str, format: str = "json"):
    fmt = format if format in ("json", "csv") else "json"
    result = data.export_session(session_id, fmt=fmt)
    if not result:
        return {"error": "session not found"}

    if fmt == "csv":
        return Response(
            content=result,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=soma_{session_id}.csv"},
        )
    return Response(
        content=result,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=soma_{session_id}.json"},
    )
