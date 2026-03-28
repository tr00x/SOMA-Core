"""EventBus — lightweight synchronous pub/sub."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    """Simple synchronous event bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def on(self, event: str, handler: Handler) -> None:
        """Subscribe *handler* to *event*."""
        self._handlers[event].append(handler)

    def off(self, event: str, handler: Handler) -> None:
        """Unsubscribe *handler* from *event*. No-op if not subscribed."""
        try:
            self._handlers[event].remove(handler)
        except ValueError:
            pass

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Fire all handlers registered for *event* with *data*."""
        for handler in list(self._handlers.get(event, [])):
            handler(data)
