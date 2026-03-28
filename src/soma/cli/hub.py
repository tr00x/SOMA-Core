"""SOMA Hub — Main Textual App with 4-tab interface.

Entry point:
    from soma.cli.hub import run_hub
    run_hub()
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane

from soma.cli.tabs.dashboard import DashboardTab
from soma.cli.tabs.agents import AgentsTab
from soma.cli.tabs.replay_tab import ReplayTab
from soma.cli.tabs.config_tab import ConfigTab


class SOMAHub(App):
    """SOMA Control Panel — 4 tabs."""

    TITLE = "SOMA Hub"
    SUB_TITLE = "System of Oversight and Monitoring for Agents"

    CSS = """
    Screen { background: #0a0a0a; }
    TabbedContent { background: #0a0a0a; }
    TabPane { padding: 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("1", "switch_tab('tab-dashboard')", "Dashboard"),
        ("2", "switch_tab('tab-agents')", "Agents"),
        ("3", "switch_tab('tab-replay')", "Replay"),
        ("4", "switch_tab('tab-config')", "Config"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            yield DashboardTab()
            yield AgentsTab()
            yield ReplayTab()
            yield ConfigTab()
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a tab by its DOM id."""
        try:
            self.query_one(TabbedContent).active = tab_id
        except Exception:
            pass


def run_hub() -> None:
    """Called by `soma` with no args."""
    app = SOMAHub()
    app.run()
