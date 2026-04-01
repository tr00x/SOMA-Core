"""Webhook exporter — fire-and-forget HTTP POST alerting."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Any


__all__ = ["WebhookExporter"]


class WebhookExporter:
    """Fire-and-forget webhook alerting on WARN/BLOCK/policy/budget/context events.

    Each HTTP POST is dispatched on a daemon thread so the engine is never
    blocked.  On failure the exporter retries once, then silently drops.
    """

    def __init__(
        self,
        urls: list[str],
        events: list[str] | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._urls = urls
        self._events = set(
            events or ["warn", "block", "policy_violation", "budget_exhausted", "context_critical"]
        )
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Exporter protocol
    # ------------------------------------------------------------------

    def on_action(self, data: dict[str, Any]) -> None:
        """No-op for regular actions. Webhook only fires on mode changes."""
        pass

    def on_mode_change(self, data: dict[str, Any]) -> None:
        """Fire webhook when response mode escalates to a watched level."""
        new_mode = data.get("new_level")
        if hasattr(new_mode, "name"):
            mode_name = new_mode.name.lower()
        else:
            mode_name = str(new_mode).lower()

        if mode_name not in self._events:
            return

        payload = {
            "event_type": f"mode_change_{mode_name}",
            "agent_id": data.get("agent_id"),
            "pressure": data.get("pressure"),
            "mode": mode_name,
            "timestamp": time.time(),
            "details": {k: str(v) for k, v in data.items()},
        }
        self._dispatch_all(payload)

    def on_event(self, data: dict[str, Any]) -> None:
        """Handle context_critical, budget_exhausted, policy_violation events."""
        event_type = data.get("event_type", "unknown")
        if event_type not in self._events:
            return

        payload = {
            "event_type": event_type,
            "agent_id": data.get("agent_id"),
            "pressure": data.get("pressure", 0.0),
            "mode": data.get("mode", "unknown"),
            "timestamp": time.time(),
            "details": {k: str(v) for k, v in data.items()},
        }
        self._dispatch_all(payload)

    def shutdown(self) -> None:
        """No-op — daemon threads clean up on process exit."""
        pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _dispatch_all(self, payload: dict[str, Any]) -> None:
        """Send payload to every configured URL on daemon threads."""
        for url in self._urls:
            t = threading.Thread(target=self._send, args=(url, payload), daemon=True)
            t.start()

    def _send(self, url: str, payload: dict[str, Any]) -> None:
        """POST payload to *url*. Retry once on failure, then drop."""
        encoded = json.dumps(payload, default=str).encode("utf-8")
        req = urllib.request.Request(
            url, data=encoded, headers={"Content-Type": "application/json"}
        )
        for _ in range(2):  # retry once
            try:
                urllib.request.urlopen(req, timeout=self._timeout)
                return
            except Exception:
                continue
