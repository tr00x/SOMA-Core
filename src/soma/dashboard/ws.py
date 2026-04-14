"""SOMA Dashboard — WebSocket for live updates."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()

SOMA_DIR = Path.home() / ".soma"


class ConnectionManager:
    """Manages WebSocket connections and state diffing."""

    def __init__(self) -> None:
        self.connections: list[WebSocket] = []
        self._last_state: dict = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict) -> None:
        for ws in list(self.connections):
            try:
                await ws.send_json(data)
            except Exception:
                if ws in self.connections:
                    self.connections.remove(ws)

    def get_state_diff(self) -> dict | None:
        """Read state.json and return it if changed since last check."""
        state_path = SOMA_DIR / "state.json"
        if not state_path.exists():
            return None
        try:
            current = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if current != self._last_state:
            self._last_state = current
            return current
        return None


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            # Poll state every 1 second
            diff = manager.get_state_diff()
            if diff is not None:
                await ws.send_json({"type": "state_update", "data": diff})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
