#!/usr/bin/env python3
"""
SOMA Live Dashboard

    cd /Users/timur/projectos/SOMA
    source .venv/bin/activate
    python examples/live_dashboard.py
"""

import random
import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, RichLog, Input, Switch, Label, Rule
from textual.screen import ModalScreen
from textual.timer import Timer

from soma.engine import SOMAEngine
from soma.types import Action, Level
from soma.recorder import SessionRecorder

# ── Colors & Labels ─────────────────────────────────────────────

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
        width: 1fr; height: auto; min-height: 12;
        background: #141414; border: round #333; padding: 1 2; margin: 1;
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
        self._level = Level.HEALTHY
        self._text = f"[bold]{agent_id}[/bold]\n\n  Waiting..."

    @property
    def level(self) -> Level:
        return self._level

    def update_vitals(self, level, pressure, uncertainty, drift, error_rate, action_count=0):
        self._level = level
        color = LEVEL_COLORS.get(level, "white")
        label = LEVEL_LABEL.get(level, "?")

        bar_len = 20
        filled = min(int(pressure * bar_len), bar_len)
        bar = f"[{color}]{'█' * filled}[/]{'░' * (bar_len - filled)}"

        def mini(val, w=10):
            f = min(int(val * w), w)
            return f"{'█' * f}{'░' * (w - f)}"

        for cls in LEVEL_CSS_CLASS.values():
            self.remove_class(cls)
        self.add_class(LEVEL_CSS_CLASS.get(level, "healthy"))

        self._text = (
            f"[bold]{self.agent_id}[/bold]  [dim]#{action_count}[/dim]\n"
            f"\n"
            f"  Status:      [{color} bold]{label} ({level.name})[/]\n"
            f"\n"
            f"  Pressure:    {bar}  {pressure:.1%}\n"
            f"  Uncertainty: [#888]{mini(uncertainty)}[/]  {uncertainty:.3f}\n"
            f"  Drift:       [#888]{mini(drift)}[/]  {drift:.3f}\n"
            f"  Errors:      [#888]{mini(error_rate)}[/]  {error_rate:.3f}\n"
        )
        self.update(self._text)

    def render(self):
        return self._text


# ── Settings Screen ─────────────────────────────────────────────

class SettingsScreen(ModalScreen):
    CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-box {
        width: 60; height: auto; max-height: 30;
        background: #1a1a1a; border: round #444;
        padding: 2 3;
    }
    .setting-row {
        layout: horizontal; height: 3; margin: 1 0;
    }
    .setting-label { width: 25; padding: 1 0; color: #ccc; }
    .setting-input { width: 30; }
    #close-btn {
        width: 100%; margin-top: 2;
        background: #333; color: #fff;
        text-align: center; padding: 1;
    }
    #close-btn:hover { background: #555; }
    """

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, speed: float, num_agents: int, budget_tokens: int) -> None:
        super().__init__()
        self.speed = speed
        self.num_agents = num_agents
        self.budget_tokens = budget_tokens

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Static("[bold]Settings[/bold]\n")

            with Horizontal(classes="setting-row"):
                yield Static("Speed (sec/step):", classes="setting-label")
                yield Input(str(self.speed), id="speed-input", classes="setting-input")

            with Horizontal(classes="setting-row"):
                yield Static("Number of agents:", classes="setting-label")
                yield Input(str(self.num_agents), id="agents-input", classes="setting-input")

            with Horizontal(classes="setting-row"):
                yield Static("Token budget:", classes="setting-label")
                yield Input(str(self.budget_tokens), id="budget-input", classes="setting-input")

            yield Rule()
            yield Static("[dim]Press ESC to close and apply[/dim]")

    def action_close(self) -> None:
        try:
            speed = float(self.query_one("#speed-input", Input).value)
        except ValueError:
            speed = self.speed
        try:
            num_agents = int(self.query_one("#agents-input", Input).value)
        except ValueError:
            num_agents = self.num_agents
        try:
            budget_tokens = int(self.query_one("#budget-input", Input).value)
        except ValueError:
            budget_tokens = self.budget_tokens

        self.dismiss({"speed": max(0.1, speed), "num_agents": max(1, min(8, num_agents)), "budget_tokens": max(100, budget_tokens)})


# ── Help Screen ─────────────────────────────────────────────────

class HelpScreen(ModalScreen):
    CSS = """
    HelpScreen { align: center middle; }
    #help-box {
        width: 65; height: auto; max-height: 28;
        background: #1a1a1a; border: round #444; padding: 2 3;
    }
    """
    BINDINGS = [("escape", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(
                "[bold]SOMA Dashboard — Help[/bold]\n"
                "\n"
                "[bold]Controls:[/bold]\n"
                "  [#58a6ff]SPACE[/]    Pause / Resume simulation\n"
                "  [#58a6ff]N[/]        Next test scenario\n"
                "  [#58a6ff]R[/]        Reset current scenario\n"
                "  [#58a6ff]A[/]        Add a new agent\n"
                "  [#58a6ff]K[/]        Kill an agent (trigger errors)\n"
                "  [#58a6ff]H[/]        Heal a killed agent\n"
                "  [#58a6ff]E[/]        Export session to JSON\n"
                "  [#58a6ff]S[/]        Open settings (speed, agents, budget)\n"
                "  [#58a6ff]?[/]        This help screen\n"
                "  [#58a6ff]Q[/]        Quit\n"
                "\n"
                "[bold]What you're looking at:[/bold]\n"
                "  Each card is one AI agent being monitored by SOMA.\n"
                "  SOMA measures agent behavior (uncertainty, drift, errors)\n"
                "  and computes [bold]pressure[/bold] — how far from normal.\n"
                "\n"
                "  When pressure rises, SOMA escalates the agent:\n"
                "  [#22c55e]OK[/] -> [#eab308]WATCH[/] -> [#f97316]BAD[/] -> [#ef4444]STOP[/] -> [#a855f7]RESET[/] -> [bold white on red]EMERGENCY[/]\n"
                "\n"
                "  Pressure flows between connected agents (graph edges).\n"
                "  If Agent 1 is connected to Agent 2, and Agent 1 fails,\n"
                "  Agent 2 will also feel the pressure.\n"
                "\n"
                "[dim]Press ESC to close[/dim]"
            )

    def action_close(self) -> None:
        self.dismiss()


# ── Test Scenarios ──────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "Test 1: All healthy",
        "desc": "Baseline — everyone works fine",
        "steps": 20,
        "edges": [],
    },
    {
        "name": "Test 2: Agent 1 breaks",
        "desc": "Agent 1 starts failing at step 8",
        "steps": 30,
        "kill_agent": "Agent 1",
        "kill_at": 8,
        "edges": [],
    },
    {
        "name": "Test 3: Pressure cascade",
        "desc": "Agent 1 breaks, pressure flows through graph to Agent 2 and Agent 3",
        "steps": 35,
        "kill_agent": "Agent 1",
        "kill_at": 10,
        "edges": [("Agent 1", "Agent 2", 0.9), ("Agent 2", "Agent 3", 0.7)],
    },
    {
        "name": "Test 4: Break then recover",
        "desc": "Agent 1 breaks at step 8, heals at step 22. Watch recovery.",
        "steps": 40,
        "kill_agent": "Agent 1",
        "kill_at": 8,
        "heal_at": 22,
        "edges": [("Agent 1", "Agent 2", 0.9)],
    },
    {
        "name": "Test 5: Budget runs out",
        "desc": "All agents burn tokens fast. SAFE_MODE incoming.",
        "steps": 40,
        "budget_tokens": 4000,
        "heavy": True,
        "edges": [],
    },
]


# ── Main App ────────────────────────────────────────────────────

class LiveDashboard(App):
    CSS = """
    Screen { background: #0a0a0a; }
    #title-bar {
        dock: top; height: 3; background: #111;
        content-align: center middle; padding: 1; color: #fff;
    }
    #agents { layout: horizontal; height: auto; padding: 0 1; }
    #legend { height: 3; background: #111; padding: 1 2; text-align: center; }
    #scenario { height: 3; background: #0d1117; padding: 1 2; color: #58a6ff; }
    #log-label { height: 1; background: #0a0a0a; padding: 0 2; color: #666; }
    #log { height: 8; background: #0f0f0f; border-top: solid #222; padding: 0 1; }
    #budget { height: 3; background: #111; padding: 1 2; dock: bottom; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_pause", "Pause"),
        Binding("n", "next_scenario", "Next"),
        Binding("r", "reset_scenario", "Reset"),
        Binding("a", "add_agent", "Add Agent"),
        Binding("k", "kill_agent", "Kill Agent"),
        Binding("h", "heal_agent", "Heal Agent"),
        Binding("e", "export_session", "Export"),
        Binding("s", "open_settings", "Settings"),
        Binding("question_mark", "show_help", "Help", key_display="?"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._scenario_idx = 0
        self._cards: dict[str, AgentCard] = {}
        self._step = 0
        self._paused = False
        self._timer: Timer | None = None
        self._between_scenarios = False
        self._killed_agents: set[str] = set()
        self._recorder = SessionRecorder()
        self._speed = 0.4
        self._num_agents = 3
        self._budget_tokens = 50_000
        self._agent_counter = 3
        self._setup_scenario()

    def _setup_scenario(self) -> None:
        sc = SCENARIOS[self._scenario_idx]
        budget = sc.get("budget_tokens", self._budget_tokens)
        self.engine = SOMAEngine(budget={"tokens": budget, "cost_usd": 5.0})
        self._agent_ids = [f"Agent {i+1}" for i in range(self._num_agents)]
        self._agent_counter = self._num_agents
        for aid in self._agent_ids:
            self.engine.register_agent(aid, tools=["tool_a", "tool_b", "tool_c"])
        for src, tgt, w in sc.get("edges", []):
            if src in self._agent_ids and tgt in self._agent_ids:
                self.engine.add_edge(src, tgt, trust_weight=w)
        self.engine.events.on("level_changed", self._on_level_change)
        self._step = 0
        self._killed_agents.clear()
        self._recorder = SessionRecorder()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "[bold]SOMA[/bold]  [dim]System of Oversight and Monitoring for Agents[/dim]",
            id="title-bar",
        )
        sc = SCENARIOS[0]
        yield Static(f"  [bold]{sc['name']}[/bold]  —  {sc['desc']}", id="scenario")
        with Horizontal(id="agents"):
            for aid in self._agent_ids:
                card = AgentCard(aid)
                self._cards[aid] = card
                yield card
        yield Static(
            "[#22c55e]██[/] OK   [#eab308]██[/] WATCH   "
            "[#f97316]██[/] BAD   [#ef4444]██[/] STOP   "
            "[#a855f7]██[/] RESET   [bold white on red]██[/] EMERGENCY"
            "        [dim]Press ? for help[/dim]",
            id="legend",
        )
        yield Static("  EVENTS", id="log-label")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Static("  Initializing...", id="budget")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "SOMA"
        self.sub_title = "Live Dashboard"
        self._timer = self.set_interval(self._speed, self._tick)
        log = self.query_one("#log", RichLog)
        log.write("[bold]SOMA Dashboard started.[/]")
        log.write("[dim]SPACE=pause  N=next test  R=reset  A=add agent  K=kill  H=heal  E=export  S=settings  ?=help[/]")

    def _on_level_change(self, data: dict) -> None:
        log = self.query_one("#log", RichLog)
        color = LEVEL_COLORS.get(data["new_level"], "white")
        log.write(
            f"  [{color}]{data['agent_id']}[/]: "
            f"{data['old_level'].name} -> {data['new_level'].name}  "
            f"[dim]p={data['pressure']:.3f}[/]"
        )

    def _make_action(self, agent_id: str) -> Action:
        sc = SCENARIOS[self._scenario_idx]

        # Check scenario-level kill/heal
        is_killed = agent_id in self._killed_agents
        kill_agent = sc.get("kill_agent")
        kill_at = sc.get("kill_at", 9999)
        heal_at = sc.get("heal_at", 9999)
        heavy = sc.get("heavy", False)

        if kill_agent == agent_id:
            if self._step >= kill_at and self._step < heal_at:
                is_killed = True
            elif self._step >= heal_at:
                is_killed = False

        if is_killed:
            return Action(
                tool_name="tool_a",
                output_text="error error error " * 20,
                token_count=random.randint(200, 500),
                cost=random.uniform(0.01, 0.05),
                error=True,
                retried=True,
            )
        else:
            return Action(
                tool_name=random.choice(["tool_a", "tool_b", "tool_c"]),
                output_text=f"Result {self._step}: " + "".join(random.choices("abcdefghijklmnop ", k=50)),
                token_count=random.randint(100, 300) if heavy else random.randint(50, 200),
                cost=random.uniform(0.001, 0.01),
            )

    def _tick(self) -> None:
        if self._paused or self._between_scenarios:
            return

        sc = SCENARIOS[self._scenario_idx]
        self._step += 1

        if self._step > sc["steps"]:
            self._finish_scenario()
            return

        for aid in self._agent_ids:
            if aid not in self.engine._agents:
                continue
            action = self._make_action(aid)
            r = self.engine.record_action(aid, action)
            self._recorder.record(aid, action)
            snap = self.engine.get_snapshot(aid)
            if aid in self._cards:
                self._cards[aid].update_vitals(
                    r.level, r.pressure, r.vitals.uncertainty,
                    r.vitals.drift, r.vitals.error_rate,
                    action_count=snap["action_count"],
                )

        # Budget bar
        health = self.engine.budget.health()
        tokens_left = self.engine.budget.remaining("tokens")
        bar_len = 30
        filled = int(health * bar_len)
        bcolor = "#22c55e" if health > 0.5 else "#eab308" if health > 0.2 else "#ef4444"
        bar = f"[{bcolor}]{'█' * filled}[/]{'░' * (bar_len - filled)}"

        killed_text = ""
        if self._killed_agents:
            killed_text = f"  [#ef4444]Killed: {', '.join(sorted(self._killed_agents))}[/]  |"

        self.query_one("#budget", Static).update(
            f"  Step {self._step:3d}/{sc['steps']}  |{killed_text}  "
            f"Budget: {bar} {health:.0%}  |  Tokens: {tokens_left:,.0f}  |  "
            f"Agents: {len(self._agent_ids)}"
        )

    def _finish_scenario(self) -> None:
        sc = SCENARIOS[self._scenario_idx]
        log = self.query_one("#log", RichLog)
        log.write(f"\n[bold #22c55e]{sc['name']} — DONE[/]")
        if self._scenario_idx < len(SCENARIOS) - 1:
            log.write("[dim]Press N for next test[/]")
        else:
            log.write("[bold]All tests complete.[/]")
        self._between_scenarios = True

    # ── Actions ─────────────────────────────────────────────────

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        log = self.query_one("#log", RichLog)
        log.write(f"[bold]{'PAUSED' if self._paused else 'RESUMED'}[/]")

    def action_next_scenario(self) -> None:
        if self._scenario_idx >= len(SCENARIOS) - 1:
            return
        self._scenario_idx += 1
        self._between_scenarios = False
        self._rebuild_agents()

    def action_reset_scenario(self) -> None:
        self._between_scenarios = False
        self._rebuild_agents()
        log = self.query_one("#log", RichLog)
        log.write("[bold #58a6ff]Scenario reset.[/]")

    def action_add_agent(self) -> None:
        self._agent_counter += 1
        new_id = f"Agent {self._agent_counter}"
        self._agent_ids.append(new_id)
        self.engine.register_agent(new_id, tools=["tool_a", "tool_b", "tool_c"])

        card = AgentCard(new_id)
        self._cards[new_id] = card
        self.query_one("#agents", Horizontal).mount(card)

        log = self.query_one("#log", RichLog)
        log.write(f"[bold #22c55e]Added {new_id}[/]")

    def action_kill_agent(self) -> None:
        # Kill the first healthy agent
        for aid in self._agent_ids:
            if aid not in self._killed_agents:
                self._killed_agents.add(aid)
                log = self.query_one("#log", RichLog)
                log.write(f"[bold #ef4444]Killed {aid}[/] — sending errors now")
                return
        log = self.query_one("#log", RichLog)
        log.write("[dim]All agents already killed[/]")

    def action_heal_agent(self) -> None:
        if self._killed_agents:
            aid = sorted(self._killed_agents)[0]
            self._killed_agents.discard(aid)
            log = self.query_one("#log", RichLog)
            log.write(f"[bold #22c55e]Healed {aid}[/] — back to normal")
        else:
            log = self.query_one("#log", RichLog)
            log.write("[dim]No killed agents to heal[/]")

    def action_export_session(self) -> None:
        path = Path("soma_session.json")
        self._recorder.export(path)
        log = self.query_one("#log", RichLog)
        log.write(f"[bold #58a6ff]Session exported to {path.absolute()}[/]")
        log.write(f"[dim]{len(self._recorder.actions)} actions saved[/]")

    def action_open_settings(self) -> None:
        self.push_screen(
            SettingsScreen(self._speed, self._num_agents, self._budget_tokens),
            callback=self._apply_settings,
        )

    def _apply_settings(self, result: dict | None) -> None:
        if result is None:
            return

        changed = (
            self._speed != result["speed"]
            or self._num_agents != result["num_agents"]
            or self._budget_tokens != result["budget_tokens"]
        )

        self._speed = result["speed"]
        self._num_agents = result["num_agents"]
        self._budget_tokens = result["budget_tokens"]

        # Restart timer with new speed
        if self._timer:
            self._timer.stop()
        self._timer = self.set_interval(self._speed, self._tick)

        log = self.query_one("#log", RichLog)
        log.write(
            f"[bold]Settings applied:[/] speed={self._speed}s, "
            f"agents={self._num_agents}, budget={self._budget_tokens:,}"
        )

        # Rebuild scenario with new settings
        if changed:
            self._between_scenarios = False
            self._rebuild_agents()
            log.write("[dim]Scenario restarted with new settings[/]")

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def _rebuild_agents(self) -> None:
        """Rebuild engine and cards for current scenario."""
        self._setup_scenario()

        # Remove old cards
        container = self.query_one("#agents", Horizontal)
        for card in list(container.children):
            card.remove()
        self._cards.clear()

        # Add new cards
        for aid in self._agent_ids:
            card = AgentCard(aid)
            self._cards[aid] = card
            container.mount(card)

        sc = SCENARIOS[self._scenario_idx]
        self.query_one("#scenario", Static).update(
            f"  [bold]{sc['name']}[/bold]  —  {sc['desc']}"
        )
        log = self.query_one("#log", RichLog)
        log.write(f"\n[bold #58a6ff]{sc['name']}[/]")
        log.write(f"[dim]{sc['desc']}[/]")


if __name__ == "__main__":
    LiveDashboard().run()
