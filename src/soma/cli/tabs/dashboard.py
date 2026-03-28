"""SOMA Hub — Dashboard Tab (Tab 1).

Shows live agent data from the state file. No simulation. No fake data.
Agents appear when a layer (soma-claude-code, soma-langchain, etc.) writes
actions to the state file, or when using the Python SDK directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static, RichLog, TabPane
from textual.timer import Timer

from soma.types import Level

# ── Colors ──────────────────────────────────────────────────────

LEVEL_COLORS = {
    Level.HEALTHY:    "#22c55e",
    Level.CAUTION:    "#eab308",
    Level.DEGRADE:    "#f97316",
    Level.QUARANTINE: "#ef4444",
    Level.RESTART:    "#a855f7",
    Level.SAFE_MODE:  "#ffffff",
}

LEVEL_LABEL = {
    Level.HEALTHY:    "OK",
    Level.CAUTION:    "WATCH",
    Level.DEGRADE:    "BAD",
    Level.QUARANTINE: "STOP",
    Level.RESTART:    "RESET",
    Level.SAFE_MODE:  "EMERGENCY",
}

LEVEL_CSS_CLASS = {
    Level.HEALTHY:    "healthy",
    Level.CAUTION:    "caution",
    Level.DEGRADE:    "degrade",
    Level.QUARANTINE: "quarantine",
    Level.RESTART:    "restart",
    Level.SAFE_MODE:  "safe-mode",
}


# ── Agent Card ──────────────────────────────────────────────────

class AgentCard(Static):
    DEFAULT_CSS = """
    AgentCard {
        width: 1fr; height: auto; min-height: 5;
        background: #141414; border: round #333; padding: 0 1; margin: 1;
    }
    AgentCard.healthy    { border: round #22c55e; }
    AgentCard.caution    { border: round #eab308; }
    AgentCard.degrade    { border: round #f97316; }
    AgentCard.quarantine { border: round #ef4444; }
    AgentCard.restart    { border: round #a855f7; }
    AgentCard.safe-mode  { border: round #fff; background: #7f1d1d; }
    """

    def __init__(self, agent_id: str) -> None:
        super().__init__()
        self.agent_id = agent_id
        self._text = f"[bold]{agent_id}[/bold]  No data yet"

    def update_vitals(self, level, pressure, uncertainty, drift, error_rate, action_count=0):
        color = LEVEL_COLORS.get(level, "white")
        label = LEVEL_LABEL.get(level, "?")

        bar_len = 20
        filled = min(int(pressure * bar_len), bar_len)
        bar = f"[{color}]{'█' * filled}[/]{'░' * (bar_len - filled)}"

        for cls in LEVEL_CSS_CLASS.values():
            self.remove_class(cls)
        self.add_class(LEVEL_CSS_CLASS.get(level, "healthy"))

        self._text = (
            f"[bold]{self.agent_id}[/bold] [dim]#{action_count}[/dim]  [{color} bold]{label}[/]\n"
            f"{bar}  {pressure:.0%}\n"
            f"[dim]u={uncertainty:.2f}  d={drift:.2f}  e={error_rate:.2f}[/]"
        )
        self.update(self._text)

    def render(self):
        return self._text


# ── Dashboard Tab ───────────────────────────────────────────────

class DashboardTab(TabPane):
    """Live dashboard — reads from state file, shows real agent data."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__("Dashboard", id="tab-dashboard")
        self._cards: dict[str, AgentCard] = {}
        self._state_path = Path.home() / ".soma" / "state.json"
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Horizontal(id="dash-agents")
        yield Static("  EVENTS", id="dash-log-label")
        yield RichLog(id="dash-log", markup=True, wrap=True)
        yield Static("", id="dash-status")

    def on_mount(self) -> None:
        self._timer = self.set_interval(1.0, self._poll_state)
        log = self.query_one("#dash-log", RichLog)
        log.write("[bold]SOMA Dashboard[/bold]")
        log.write(f"[dim]Watching: {self._state_path}[/dim]")
        log.write("[dim]Waiting for agent data from a SOMA layer or SDK...[/dim]")
        log.write("")
        log.write("[dim]To send data, use the Python SDK:[/dim]")
        log.write("[dim]  import soma[/dim]")
        log.write("[dim]  engine = soma.SOMAEngine(budget={...})[/dim]")
        log.write("[dim]  engine.register_agent('my-agent')[/dim]")
        log.write("[dim]  result = engine.record_action('my-agent', action)[/dim]")
        log.write("")
        log.write("[dim]Press R to refresh manually.[/dim]")

    def _poll_state(self) -> None:
        """Read state file and update cards."""
        if not self._state_path.exists():
            return

        try:
            data = json.loads(self._state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        agents = data.get("agents", {})
        container = self.query_one("#dash-agents", Horizontal)

        for agent_id, state in agents.items():
            if agent_id not in self._cards:
                card = AgentCard(agent_id)
                self._cards[agent_id] = card
                container.mount(card)

                log = self.query_one("#dash-log", RichLog)
                log.write(f"  [#22c55e]New agent: {agent_id}[/]")

            level_name = state.get("level", "HEALTHY")
            try:
                level = Level[level_name]
            except KeyError:
                level = Level.HEALTHY

            vitals = state.get("vitals", {})
            self._cards[agent_id].update_vitals(
                level=level,
                pressure=state.get("pressure", 0.0),
                uncertainty=vitals.get("uncertainty", 0.0),
                drift=vitals.get("drift", 0.0),
                error_rate=vitals.get("error_rate", 0.0),
                action_count=state.get("action_count", 0),
            )

        # Update status
        n = len(agents)
        self.query_one("#dash-status", Static).update(
            f"  {n} agent{'s' if n != 1 else ''} monitored  |  "
            f"[dim]Polling {self._state_path} every 1s[/dim]"
        )

    def action_refresh(self) -> None:
        self._poll_state()
        log = self.query_one("#dash-log", RichLog)
        log.write("[dim]Refreshed.[/dim]")
