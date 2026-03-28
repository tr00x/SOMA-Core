#!/usr/bin/env python3
"""
SOMA Real Dashboard — monitors REAL Claude agents in real time.

Uses `claude -p` to run actual Claude calls. No simulation. No fake data.
Each agent gets a real task, sends it to Claude, and SOMA monitors the response.

    cd /Users/timur/projectos/SOMA
    source .venv/bin/activate
    python examples/real_dashboard.py
"""

import subprocess
import time
import threading
import random
from collections import deque

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, RichLog, Input
from textual.screen import ModalScreen
from textual.timer import Timer

from soma.engine import SOMAEngine
from soma.types import Action, Level
from soma.recorder import SessionRecorder

# ── Config ──────────────────────────────────────────────────────

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

# Tasks for agents — real prompts sent to Claude
AGENT_TASKS = [
    [
        "List 5 real challenges in AI agent monitoring. Be brief, one line each.",
        "What are the top 3 metrics to track for AI agent health? Brief answer.",
        "Explain behavioral drift in AI agents in 2 sentences.",
        "What is the difference between observability and monitoring for AI agents?",
        "Name 3 open source tools for AI agent monitoring.",
        "What causes an AI agent to get stuck in a loop? Brief answer.",
        "How do you detect when an AI agent is hallucinating? One paragraph.",
        "What is a pressure graph in multi-agent systems? Brief.",
        "Explain the concept of trust dynamics between AI agents.",
        "What happens when you run out of context window in a long agent session?",
    ],
    [
        "Write a Python function that computes Shannon entropy of a string. Just the code.",
        "Write a Python function for cosine similarity between two lists. Just code.",
        "Write a Python function for exponential moving average. Just code.",
        "Write a Python dataclass for tracking agent health metrics. Just code.",
        "Write a Python function that detects if text output is repetitive. Just code.",
        "Write a ring buffer implementation in Python. Just code.",
        "Write a Python function to compute z-score normalization. Just code.",
        "Write a sigmoid function in Python. Just code.",
        "Write a Python function for weighted average. Just code.",
        "Write a Python class for a simple event bus. Just code.",
    ],
    [
        "Review this code: `def f(x): return 1/(1+exp(-x+3))`. What does it compute?",
        "Is `min(remaining/limit for each dim)` a good way to compute budget health? Why?",
        "Code review: `trust -= decay_rate * uncertainty`. Is asymmetric decay/recovery good?",
        "Should AI agent monitoring use time-based or action-based windows? Brief opinion.",
        "Review: using cosine distance for behavioral drift detection. Pros and cons?",
        "Is 70/30 weighted mean/max a good way to aggregate pressure signals? Brief.",
        "Review: hysteresis with -0.05 offset for level transitions. Good idea?",
        "Should a monitoring system physically modify agent context, or just alert?",
        "Review: EMA with alpha=0.15 for baseline tracking. Too fast? Too slow?",
        "Is it better to have 6 escalation levels or just 3 (healthy/warning/critical)?",
    ],
]


# ── Real Agent Runner ───────────────────────────────────────────

def run_claude_task(prompt: str, timeout: int = 30) -> tuple[str, int, float, bool]:
    """Run a real Claude call via CLI. Returns (output, token_est, duration, error)."""
    start = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=timeout,
        )
        duration = time.time() - start
        output = result.stdout.strip() if result.stdout else ""
        error = result.returncode != 0 or not output

        # Estimate tokens (~4 chars per token)
        prompt_tokens = len(prompt) // 4
        output_tokens = len(output) // 4
        total_tokens = prompt_tokens + output_tokens

        # Estimate cost (haiku pricing ~$0.25/1M input, $1.25/1M output)
        cost = (prompt_tokens * 0.25 + output_tokens * 1.25) / 1_000_000

        return output, total_tokens, duration, error
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 0, time.time() - start, True
    except Exception as e:
        return str(e), 0, time.time() - start, True


# ── Agent Card ──────────────────────────────────────────────────

class AgentCard(Static):
    DEFAULT_CSS = """
    AgentCard {
        width: 1fr; height: auto; min-height: 14;
        background: #141414; border: round #333; padding: 1 2; margin: 1;
    }
    AgentCard.healthy    { border: round #22c55e; }
    AgentCard.caution    { border: round #eab308; }
    AgentCard.degrade    { border: round #f97316; }
    AgentCard.quarantine { border: round #ef4444; }
    AgentCard.restart    { border: round #a855f7; }
    AgentCard.safe-mode  { border: round #fff; background: #7f1d1d; }
    """

    def __init__(self, agent_id: str, role: str) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.role = role
        self._text = f"[bold]{agent_id}[/bold]  [dim]{role}[/dim]\n\n  Starting..."

    def update_vitals(self, level, pressure, uncertainty, drift, error_rate, task="", action_count=0):
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

        # Truncate task
        short_task = task[:40] + "..." if len(task) > 40 else task

        self._text = (
            f"[bold]{self.agent_id}[/bold]  [dim]{self.role} | #{action_count}[/dim]\n"
            f"\n"
            f"  Status:      [{color} bold]{label} ({level.name})[/]\n"
            f"  Pressure:    {bar}  {pressure:.1%}\n"
            f"  Uncertainty: [#888]{mini(uncertainty)}[/]  {uncertainty:.3f}\n"
            f"  Drift:       [#888]{mini(drift)}[/]  {drift:.3f}\n"
            f"  Errors:      [#888]{mini(error_rate)}[/]  {error_rate:.3f}\n"
            f"\n"
            f"  [dim]Task: {short_task}[/dim]\n"
        )
        self.update(self._text)

    def set_working(self, task: str):
        short = task[:50] + "..." if len(task) > 50 else task
        self._text = (
            f"[bold]{self.agent_id}[/bold]  [dim]{self.role}[/dim]\n"
            f"\n"
            f"  [bold #58a6ff]WORKING...[/]\n"
            f"\n"
            f"  [dim]{short}[/dim]\n"
        )
        self.update(self._text)

    def render(self):
        return self._text


# ── Main App ────────────────────────────────────────────────────

class RealDashboard(App):
    CSS = """
    Screen { background: #0a0a0a; }
    #title-bar {
        dock: top; height: 3; background: #0d1117;
        content-align: center middle; padding: 1; color: #fff;
    }
    #agents { layout: horizontal; height: auto; padding: 0 1; }
    #legend { height: 3; background: #111; padding: 1 2; text-align: center; }
    #log-label { height: 1; background: #0a0a0a; padding: 0 2; color: #666; }
    #log { height: 10; background: #0f0f0f; border-top: solid #222; padding: 0 1; }
    #status { height: 3; background: #111; padding: 1 2; dock: bottom; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_pause", "Pause"),
        Binding("e", "export_session", "Export"),
        Binding("question_mark", "show_help", "Help", key_display="?"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.engine = SOMAEngine(budget={"tokens": 100_000, "cost_usd": 1.0})

        self._agents = {
            "Agent 1": {"role": "Researcher", "tasks": list(AGENT_TASKS[0])},
            "Agent 2": {"role": "Coder", "tasks": list(AGENT_TASKS[1])},
            "Agent 3": {"role": "Reviewer", "tasks": list(AGENT_TASKS[2])},
        }

        for aid in self._agents:
            self.engine.register_agent(aid, tools=["claude"])

        # Agent 1 feeds into Agent 2, Agent 2 into Agent 3
        self.engine.add_edge("Agent 1", "Agent 2", trust_weight=0.8)
        self.engine.add_edge("Agent 2", "Agent 3", trust_weight=0.7)

        self._cards: dict[str, AgentCard] = {}
        self._recorder = SessionRecorder()
        self._paused = False
        self._task_idx: dict[str, int] = {aid: 0 for aid in self._agents}
        self._total_calls = 0
        self._total_cost = 0.0
        self._working: dict[str, bool] = {aid: False for aid in self._agents}
        self._results_queue: deque = deque()
        self._lock = threading.Lock()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "[bold #ef4444]LIVE[/]  [bold]SOMA[/bold]  "
            "[dim]Real Claude agents — no simulation[/dim]",
            id="title-bar",
        )
        with Horizontal(id="agents"):
            for aid, cfg in self._agents.items():
                card = AgentCard(aid, cfg["role"])
                self._cards[aid] = card
                yield card
        yield Static(
            "[#22c55e]██[/] OK   [#eab308]██[/] WATCH   "
            "[#f97316]██[/] BAD   [#ef4444]██[/] STOP   "
            "     [dim]SPACE=pause  E=export  ?=help  Q=quit[/dim]",
            id="legend",
        )
        yield Static("  LIVE EVENTS", id="log-label")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Static("  Starting...", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "SOMA"
        self.sub_title = "Real Agent Monitor"
        self.engine.events.on("level_changed", self._on_level_change)

        log = self.query_one("#log", RichLog)
        log.write("[bold]SOMA Real Dashboard[/]")
        log.write("[dim]Each agent runs REAL Claude calls via `claude -p`[/]")
        log.write("[dim]SOMA monitors every response in real time[/]")
        log.write("")

        # Start agents in background threads
        self.set_interval(0.5, self._check_results)
        self._dispatch_all()

    def _on_level_change(self, data: dict) -> None:
        with self._lock:
            self._results_queue.append(("level_change", data))

    def _dispatch_all(self) -> None:
        """Dispatch one task per agent in background threads."""
        for aid in self._agents:
            if not self._working.get(aid) and not self._paused:
                self._dispatch_agent(aid)

    def _dispatch_agent(self, agent_id: str) -> None:
        """Send one task to an agent in a background thread."""
        idx = self._task_idx.get(agent_id, 0)
        tasks = self._agents[agent_id]["tasks"]
        if idx >= len(tasks):
            return  # All tasks done

        task = tasks[idx]
        self._task_idx[agent_id] = idx + 1
        self._working[agent_id] = True

        # Show "WORKING" state
        if agent_id in self._cards:
            self._cards[agent_id].set_working(task)

        def _run():
            output, tokens, duration, error = run_claude_task(task)
            with self._lock:
                self._results_queue.append(("result", {
                    "agent_id": agent_id,
                    "task": task,
                    "output": output,
                    "tokens": tokens,
                    "duration": duration,
                    "error": error,
                }))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _check_results(self) -> None:
        """Called every 0.5s — process results from background threads."""
        while True:
            with self._lock:
                if not self._results_queue:
                    break
                msg_type, data = self._results_queue.popleft()

            if msg_type == "level_change":
                log = self.query_one("#log", RichLog)
                color = LEVEL_COLORS.get(data["new_level"], "white")
                log.write(
                    f"  [{color}]{data['agent_id']}[/]: "
                    f"{data['old_level'].name} -> {data['new_level'].name}  "
                    f"[dim]p={data['pressure']:.3f}[/]"
                )

            elif msg_type == "result":
                self._process_result(data)

        # Dispatch next tasks for idle agents
        self._dispatch_all()

        # Update status bar
        self._update_status()

    def _process_result(self, data: dict) -> None:
        """Process a completed agent result."""
        agent_id = data["agent_id"]
        self._working[agent_id] = False
        self._total_calls += 1
        self._total_cost += (data["tokens"] * 0.5) / 1_000_000  # rough estimate

        # Record in SOMA
        action = Action(
            tool_name="claude",
            output_text=data["output"][:500],  # cap for vitals computation
            token_count=data["tokens"],
            cost=(data["tokens"] * 0.5) / 1_000_000,
            error=data["error"],
            retried=False,
            duration_sec=data["duration"],
        )

        result = self.engine.record_action(agent_id, action)
        self._recorder.record(agent_id, action)

        # Update card
        snap = self.engine.get_snapshot(agent_id)
        self._cards[agent_id].update_vitals(
            result.level, result.pressure,
            result.vitals.uncertainty, result.vitals.drift, result.vitals.error_rate,
            task=data["task"], action_count=snap["action_count"],
        )

        # Log
        log = self.query_one("#log", RichLog)
        status = "[#22c55e]OK[/]" if not data["error"] else "[#ef4444]ERR[/]"
        log.write(
            f"  {status} {agent_id}: [dim]{data['task'][:60]}[/]  "
            f"[dim]{data['tokens']}tok {data['duration']:.1f}s[/]"
        )

    def _update_status(self) -> None:
        health = self.engine.budget.health()
        bar_len = 25
        filled = int(health * bar_len)
        bcolor = "#22c55e" if health > 0.5 else "#eab308" if health > 0.2 else "#ef4444"
        bar = f"[{bcolor}]{'█' * filled}[/]{'░' * (bar_len - filled)}"

        done = sum(1 for aid in self._agents if self._task_idx.get(aid, 0) >= len(self._agents[aid]["tasks"]) and not self._working.get(aid))
        total_tasks = sum(len(cfg["tasks"]) for cfg in self._agents.values())
        completed = sum(self._task_idx.get(aid, 0) for aid in self._agents)

        state = "[bold #22c55e]LIVE[/]" if not self._paused else "[bold #eab308]PAUSED[/]"

        self.query_one("#status", Static).update(
            f"  {state}  |  Calls: {self._total_calls}  |  "
            f"Tasks: {completed}/{total_tasks}  |  "
            f"Budget: {bar} {health:.0%}  |  "
            f"Est. cost: ${self._total_cost:.4f}"
        )

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        log = self.query_one("#log", RichLog)
        log.write(f"[bold]{'PAUSED' if self._paused else 'RESUMED'}[/]")
        if not self._paused:
            self._dispatch_all()

    def action_export_session(self) -> None:
        from pathlib import Path
        path = Path("soma_real_session.json")
        self._recorder.export(path)
        log = self.query_one("#log", RichLog)
        log.write(f"[bold #58a6ff]Exported {len(self._recorder.actions)} actions to {path}[/]")

    def action_show_help(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("")
        log.write("[bold]Help:[/]")
        log.write("  This dashboard runs REAL Claude calls via `claude -p`")
        log.write("  3 agents work in parallel on different tasks")
        log.write("  SOMA monitors every response (uncertainty, drift, errors)")
        log.write("  Pressure propagates: Agent 1 -> Agent 2 -> Agent 3")
        log.write("  SPACE=pause  E=export  Q=quit")
        log.write("")


if __name__ == "__main__":
    RealDashboard().run()
