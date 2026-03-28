"""Session recorder for SOMA Core — captures and persists agent actions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from soma.types import Action


@dataclass
class RecordedAction:
    """A single recorded agent action with metadata."""
    agent_id: str
    action: Action
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "action": {
                "tool_name": self.action.tool_name,
                "output_text": self.action.output_text,
                "token_count": self.action.token_count,
                "cost": self.action.cost,
                "error": self.action.error,
                "retried": self.action.retried,
                "duration_sec": self.action.duration_sec,
                "timestamp": self.action.timestamp,
                "metadata": self.action.metadata,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordedAction:
        action = Action(
            tool_name=data["action"]["tool_name"],
            output_text=data["action"]["output_text"],
            token_count=data["action"].get("token_count", 0),
            cost=data["action"].get("cost", 0.0),
            error=data["action"].get("error", False),
            retried=data["action"].get("retried", False),
            duration_sec=data["action"].get("duration_sec", 0.0),
            timestamp=data["action"].get("timestamp", 0.0),
            metadata=data["action"].get("metadata", {}),
        )
        return cls(
            agent_id=data["agent_id"],
            action=action,
            timestamp=data["timestamp"],
        )


class SessionRecorder:
    """Records agent actions and supports export/load of sessions."""

    def __init__(self) -> None:
        self.actions: list[RecordedAction] = []

    def record(self, agent_id: str, action: Action) -> None:
        """Append a new RecordedAction to the session."""
        self.actions.append(RecordedAction(agent_id=agent_id, action=action))

    def export(self, path: str | Path) -> None:
        """Write the session as JSON to *path*."""
        payload = {
            "version": 1,
            "actions": [ra.to_dict() for ra in self.actions],
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> SessionRecorder:
        """Read a JSON session file and return a populated SessionRecorder."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        recorder = cls()
        recorder.actions = [RecordedAction.from_dict(item) for item in data["actions"]]
        return recorder
