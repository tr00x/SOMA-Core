"""EventLog widget — scrolling log of SOMA events."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import RichLog


class EventLog(RichLog):
    """A scrolling event log for SOMA events."""

    DEFAULT_CSS = """
    EventLog {
        background: #0f0f0f;
        border-top: solid #222222;
        height: 10;
        padding: 0 1;
        color: #aaaaaa;
    }
    """

    def add_event(self, text: str) -> None:
        """Append a timestamped event line to the log."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.write(f"[dim]{ts}[/dim]  {text}")
