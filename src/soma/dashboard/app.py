# Legacy standalone dashboard. Use `soma` CLI (cli/hub.py) instead.
"""SOMA TUI Dashboard — main Textual application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import ScrollableContainer, Vertical

from soma.engine import SOMAEngine
from soma.types import Level
from soma.dashboard.widgets.agent_card import AgentCard
from soma.dashboard.widgets.event_log import EventLog
from soma.dashboard.widgets.budget_bar import BudgetBar

_CSS_PATH = Path(__file__).parent / "styles.tcss"


class SOMADashboard(App):
    """Dark-themed TUI dashboard for the SOMA engine."""

    CSS_PATH = str(_CSS_PATH)
    TITLE = "SOMA"
    DARK = True

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "settings", "Settings"),
    ]

    def __init__(self, engine: SOMAEngine, **kwargs) -> None:
        super().__init__(**kwargs)
        self._engine = engine
        # Subscribe to level-change events from the engine
        self._engine.events.subscribe("level_changed", self._on_level_changed)

    # ── Composition ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()

        # Agent grid — populated in on_mount once we know which agents exist
        with ScrollableContainer(id="agent-grid"):
            pass

        # Budget bars section
        with Vertical(id="budget-section"):
            yield BudgetBar(dimension="tokens", id="budget-tokens")
            yield BudgetBar(dimension="cost_usd", id="budget-cost")

        # Scrolling event log at the bottom
        yield EventLog(id="event-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Populate agent cards after the DOM is ready."""
        grid = self.query_one("#agent-grid", ScrollableContainer)
        agent_ids = list(self._engine._agents.keys())
        if agent_ids:
            for agent_id in agent_ids:
                card = AgentCard(agent_id=agent_id, id=f"agent-{agent_id}")
                grid.mount(card)
                self.update_agent(agent_id)
        else:
            grid.mount(Static("[dim]No agents registered.[/dim]"))

        log = self.query_one("#event-log", EventLog)
        log.add_event("[bold green]SOMA Dashboard started.[/bold green]")

        # Refresh budget bars with initial state
        self._refresh_budget()

    # ── Public API ───────────────────────────────────────────────────────────

    def update_agent(self, agent_id: str) -> None:
        """Refresh the AgentCard for agent_id from the engine snapshot."""
        try:
            snapshot: dict[str, Any] = self._engine.get_snapshot(agent_id)
        except KeyError:
            return

        level: Level = snapshot["level"]
        pressure: float = snapshot["pressure"]
        vitals: dict[str, Any] = snapshot.get("vitals", {})
        uncertainty: float = vitals.get("uncertainty") or 0.0
        drift: float = vitals.get("drift") or 0.0
        error_rate: float = vitals.get("error_rate") or 0.0

        try:
            card = self.query_one(f"#agent-{agent_id}", AgentCard)
            card.update_vitals(
                level=level,
                pressure=pressure,
                uncertainty=uncertainty,
                drift=drift,
                error_rate=error_rate,
            )
        except Exception:
            pass  # Card may not be mounted yet

        self._refresh_budget()

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_quit(self) -> None:
        self.exit()

    def action_settings(self) -> None:
        log = self.query_one("#event-log", EventLog)
        log.add_event("[yellow]Settings panel not yet implemented.[/yellow]")

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _on_level_changed(self, data: dict[str, Any]) -> None:
        """Handle level-change events from the engine event bus."""
        agent_id: str = data.get("agent_id", "?")
        old_level = data.get("old_level")
        new_level = data.get("new_level")
        pressure: float = data.get("pressure", 0.0)

        old_name = old_level.name if isinstance(old_level, Level) else str(old_level)
        new_name = new_level.name if isinstance(new_level, Level) else str(new_level)

        # We are possibly called from a non-Textual thread; use call_from_thread
        def _update() -> None:
            log = self.query_one("#event-log", EventLog)
            log.add_event(
                f"[bold]{agent_id}[/bold]  "
                f"{old_name} → [bold]{new_name}[/bold]  "
                f"(pressure={pressure:.3f})"
            )
            self.update_agent(agent_id)

        try:
            self.call_from_thread(_update)
        except Exception:
            # If we're already on the main thread, call directly
            try:
                _update()
            except Exception:
                pass

    def _refresh_budget(self) -> None:
        """Update budget bar widgets from the engine's budget state."""
        try:
            tokens_limit = self._engine.budget.limits.get("tokens")
            tokens_spent = self._engine.budget.spent.get("tokens", 0.0)
            cost_limit = self._engine.budget.limits.get("cost_usd")
            cost_spent = self._engine.budget.spent.get("cost_usd", 0.0)

            tokens_bar = self.query_one("#budget-tokens", BudgetBar)
            if tokens_limit and tokens_limit > 0:
                tokens_util = tokens_spent / tokens_limit
                tokens_bar.update_budget("tokens", tokens_util, tokens_limit - tokens_spent)
            else:
                tokens_bar.update_budget("tokens", 0.0, 0.0)

            cost_bar = self.query_one("#budget-cost", BudgetBar)
            if cost_limit and cost_limit > 0:
                cost_util = cost_spent / cost_limit
                cost_bar.update_budget("cost_usd", cost_util, cost_limit - cost_spent)
            else:
                cost_bar.update_budget("cost_usd", 0.0, 0.0)
        except Exception:
            pass
