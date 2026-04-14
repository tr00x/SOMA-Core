"""SOMA Dashboard — WebSocket for live updates."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()

SOMA_DIR = Path.home() / ".soma"


def _compute_diff(old: dict, new: dict) -> dict:
    """Compute a shallow diff between two state dicts.

    Returns only keys that changed or were added/removed.
    For nested dicts (like agents), compares per-key.
    """
    diff: dict = {}
    all_keys = set(old.keys()) | set(new.keys())
    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            diff[key] = new_val
    return diff


class ConnectionManager:
    """Manages WebSocket connections and state diffing."""

    def __init__(self) -> None:
        self.connections: list[WebSocket] = []
        self._last_state: dict = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)
        # Send full state on connect
        state = self._read_state()
        if state:
            await ws.send_json({"type": "state_full", "data": state})

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

    def _read_state(self) -> dict | None:
        state_path = SOMA_DIR / "state.json"
        if not state_path.exists():
            return None
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def get_state_diff(self) -> dict | None:
        """Read state.json, compute diff against last state, return only changes."""
        current = self._read_state()
        if current is None:
            return None
        if not self._last_state:
            # First read — send full state
            self._last_state = current
            return current
        if current == self._last_state:
            return None
        diff = _compute_diff(self._last_state, current)
        self._last_state = current
        return diff if diff else None


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
