"""SOMA Inbox — processes action files from Claude Code hooks."""

from __future__ import annotations

import json
import time
from pathlib import Path

from soma.types import Action

INBOX_DIR = Path.home() / ".soma" / "inbox"


def ensure_inbox():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)


def process_inbox(engine) -> int:
    """Process all pending inbox files. Returns count of actions processed."""
    ensure_inbox()
    count = 0

    for f in sorted(INBOX_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            agent_id = data.get("agent_id", "unknown")
            tool_name = data.get("tool_name", "unknown")
            token_count = data.get("token_count", 150)  # estimate if not provided

            # Register agent if new
            from soma.errors import AgentNotFound
            try:
                engine.get_level(agent_id)
            except (KeyError, AgentNotFound):
                engine.register_agent(agent_id, tools=[tool_name])

            # Record the action
            action = Action(
                tool_name=tool_name,
                output_text=data.get("output", "")[:500],
                token_count=token_count,
                cost=token_count * 0.5 / 1_000_000,
                error=data.get("error", False),
                timestamp=data.get("timestamp", time.time()),
            )
            engine.record_action(agent_id, action)
            count += 1

        except Exception:
            pass  # skip bad files
        finally:
            f.unlink(missing_ok=True)  # always delete processed file

    return count
