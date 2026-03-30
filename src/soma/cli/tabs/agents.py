"""SOMA Hub — Agents Tab (Tab 2).

DataTable of live agents. Keybinds: A=add, K=kill, H=heal, D=delete.
Selecting a row shows the last 10 actions for that agent.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, DataTable, RichLog, TabPane
from textual.reactive import reactive

from soma.types import ResponseMode

# ── Color helpers ────────────────────────────────────────────────

MODE_COLORS = {
    ResponseMode.OBSERVE:  "#22c55e",
    ResponseMode.GUIDE:    "#eab308",
    ResponseMode.WARN:     "#f97316",
    ResponseMode.BLOCK:    "#ef4444",
}

MODE_LABELS = {
    ResponseMode.OBSERVE:  "OK",
    ResponseMode.GUIDE:    "GUIDE",
    ResponseMode.WARN:     "WARN",
    ResponseMode.BLOCK:    "BLOCK",
}


def _level_markup(level: ResponseMode) -> str:
    color = MODE_COLORS.get(level, "white")
    label = MODE_LABELS.get(level, level.name)
    return f"[{color}]{label}[/]"


# ── AgentRow dataclass ───────────────────────────────────────────

class AgentRow:
    """In-memory record for one agent shown in the table."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.level = ResponseMode.OBSERVE
        self.pressure: float = 0.0
        self.action_count: int = 0
        self.recent_actions: list[str] = []  # last 10 human-readable action strings

    def push_action(self, description: str) -> None:
        self.recent_actions.append(description)
        if len(self.recent_actions) > 10:
            self.recent_actions.pop(0)


# ── AgentsTab ────────────────────────────────────────────────────

class AgentsTab(TabPane):
    """Tab 2 — list of agents with live stats and detail panel."""

    DEFAULT_CSS = """
    AgentsTab {
        layout: vertical;
    }
    #agents-header {
        height: 3; background: #111; padding: 1 2; color: #ccc;
    }
    #agents-split {
        layout: horizontal; height: 1fr;
    }
    #agents-table-panel {
        width: 2fr; height: 100%; border-right: solid #333;
    }
    #agents-detail-panel {
        width: 1fr; height: 100%; padding: 1 2;
    }
    #detail-title {
        height: 2; color: #58a6ff; padding: 0 0 1 0;
    }
    #detail-log {
        height: 1fr; background: #0f0f0f; border: round #333;
    }
    #agents-hints {
        height: 3; background: #0d1117; padding: 1 2; color: #555;
    }
    """

    BINDINGS = [
        Binding("a", "add_agent", "Add"),
        Binding("k", "kill_agent", "Kill"),
        Binding("h", "heal_agent", "Heal"),
        Binding("d", "delete_agent", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__("Agents", id="tab-agents")
        # agent_id -> AgentRow
        self._rows: dict[str, AgentRow] = {}
        self._selected_id: str | None = None
        self._agent_counter = 0

        # No placeholder agents — only real agents from state file

    # ── Compose ──────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Agents[/bold]  — Select a row to view action history.",
            id="agents-header",
        )
        with Horizontal(id="agents-split"):
            with Vertical(id="agents-table-panel"):
                table: DataTable[str] = DataTable(id="agents-table", cursor_type="row")
                table.add_column("Agent ID", key="agent_id")
                table.add_column("Level", key="level")
                table.add_column("Pressure", key="pressure")
                table.add_column("Actions", key="actions")
                for row in self._rows.values():
                    table.add_row(
                        row.agent_id,
                        _level_markup(row.level),
                        f"{row.pressure:.3f}",
                        str(row.action_count),
                        key=row.agent_id,
                    )
                yield table
            with Vertical(id="agents-detail-panel"):
                yield Static("Select an agent to see details.", id="detail-title")
                yield RichLog(id="detail-log", markup=True, wrap=True)
        yield Static(
            "  [#58a6ff]A[/]=Add  [#58a6ff]K[/]=Kill  [#58a6ff]H[/]=Heal  "
            "[#58a6ff]D[/]=Delete  [#58a6ff]↑/↓[/]=Select",
            id="agents-hints",
        )

    # ── Public API — called by hub to push updates ───────────────

    def update_agent(
        self,
        agent_id: str,
        level: ResponseMode,
        pressure: float,
        action_count: int,
        action_desc: str = "",
    ) -> None:
        """Refresh a row's data and optionally append an action description."""
        if agent_id not in self._rows:
            row = AgentRow(agent_id)
            self._rows[agent_id] = row
            try:
                table = self.query_one("#agents-table", DataTable)
                table.add_row(
                    agent_id,
                    _level_markup(level),
                    f"{pressure:.3f}",
                    str(action_count),
                    key=agent_id,
                )
            except Exception:
                pass

        row = self._rows[agent_id]
        row.level = level
        row.pressure = pressure
        row.action_count = action_count
        if action_desc:
            row.push_action(action_desc)

        try:
            table = self.query_one("#agents-table", DataTable)
            table.update_cell(agent_id, "level", _level_markup(level))
            table.update_cell(agent_id, "pressure", f"{pressure:.3f}")
            table.update_cell(agent_id, "actions", str(action_count))
        except Exception:
            pass

        # Refresh detail panel if this agent is selected
        if self._selected_id == agent_id:
            self._refresh_detail(agent_id)

    def _refresh_detail(self, agent_id: str) -> None:
        row = self._rows.get(agent_id)
        if row is None:
            return
        try:
            title = self.query_one("#detail-title", Static)
            color = MODE_COLORS.get(row.level, "white")
            label = MODE_LABELS.get(row.level, row.level.name)
            title.update(
                f"[bold]{agent_id}[/bold]  [{color}]{label}[/]  "
                f"[dim]p={row.pressure:.3f}  #{row.action_count}[/]"
            )
            log = self.query_one("#detail-log", RichLog)
            log.clear()
            if row.recent_actions:
                for i, desc in enumerate(reversed(row.recent_actions), 1):
                    log.write(f"[dim]{i:2d}.[/] {desc}")
            else:
                log.write("[dim]No actions yet.[/]")
        except Exception:
            pass

    # ── Table selection ──────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._selected_id = str(event.row_key.value)
        self._refresh_detail(self._selected_id)

    # ── Actions ─────────────────────────────────────────────────

    def action_add_agent(self) -> None:
        self._agent_counter += 1
        new_id = f"Agent {self._agent_counter}"
        row = AgentRow(new_id)
        self._rows[new_id] = row
        try:
            table = self.query_one("#agents-table", DataTable)
            table.add_row(
                new_id,
                _level_markup(ResponseMode.OBSERVE),
                "0.000",
                "0",
                key=new_id,
            )
        except Exception:
            pass

    def action_kill_agent(self) -> None:
        """Mark the selected (or first) agent as killed — visual only here."""
        target = self._selected_id or (next(iter(self._rows), None))
        if target is None:
            return
        row = self._rows[target]
        row.level = ResponseMode.BLOCK
        row.push_action("[#ef4444]KILLED — sending errors[/]")
        self._refresh_detail(target)
        try:
            table = self.query_one("#agents-table", DataTable)
            table.update_cell(target, "level", _level_markup(ResponseMode.BLOCK))
        except Exception:
            pass

    def action_heal_agent(self) -> None:
        target = self._selected_id or (next(iter(self._rows), None))
        if target is None:
            return
        row = self._rows[target]
        row.level = ResponseMode.OBSERVE
        row.pressure = 0.0
        row.push_action("[#22c55e]HEALED — back to normal[/]")
        self._refresh_detail(target)
        try:
            table = self.query_one("#agents-table", DataTable)
            table.update_cell(target, "level", _level_markup(ResponseMode.OBSERVE))
            table.update_cell(target, "pressure", "0.000")
        except Exception:
            pass

    def action_delete_agent(self) -> None:
        target = self._selected_id
        if target is None:
            return
        self._rows.pop(target, None)
        self._selected_id = None
        try:
            table = self.query_one("#agents-table", DataTable)
            table.remove_row(target)
        except Exception:
            pass
        try:
            self.query_one("#detail-title", Static).update("Select an agent to see details.")
            self.query_one("#detail-log", RichLog).clear()
        except Exception:
            pass
