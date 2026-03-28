"""SOMA CLI — replay a recorded session.json file and print results as a table."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from soma.recorder import SessionRecorder
from soma.replay import replay_session
from soma.types import Level
from soma.cli.config_loader import load_config, DEFAULT_CONFIG


# Level -> rich colour mapping
_LEVEL_COLOURS: dict[Level, str] = {
    Level.HEALTHY: "green",
    Level.CAUTION: "yellow",
    Level.DEGRADE: "dark_orange",
    Level.QUARANTINE: "red",
    Level.RESTART: "bold red",
    Level.SAFE_MODE: "magenta",
}


def _level_markup(level: Level) -> str:
    colour = _LEVEL_COLOURS.get(level, "white")
    return f"[{colour}]{level.name}[/{colour}]"


def run_replay_cli(session_path: str) -> None:
    """Replay a session file and print results to terminal."""
    console = Console()
    path = Path(session_path)

    # Load the recording
    recording = SessionRecorder.load(path)

    # Derive header stats
    total_actions = len(recording.actions)
    agent_ids: list[str] = []
    seen: set[str] = set()
    for ra in recording.actions:
        if ra.agent_id not in seen:
            seen.add(ra.agent_id)
            agent_ids.append(ra.agent_id)
    num_agents = len(agent_ids)

    console.print(
        f"\n[bold]SOMA Replay:[/bold] {path.name} "
        f"([cyan]{total_actions}[/cyan] actions, "
        f"[cyan]{num_agents}[/cyan] agents)\n"
    )

    # Build budget from config (best-effort; fall back to default)
    config = load_config()
    budget_section = config.get("budget", DEFAULT_CONFIG["budget"])
    budget: dict[str, float] = {}
    if "tokens" in budget_section:
        budget["tokens"] = float(budget_section["tokens"])
    if "cost_usd" in budget_section:
        budget["cost_usd"] = float(budget_section["cost_usd"])

    # Replay
    results = replay_session(recording, budget=budget or None)

    # ------------------------------------------------------------------ table
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("Step", justify="right", style="dim", no_wrap=True)
    table.add_column("Agent", no_wrap=True)
    table.add_column("Level", no_wrap=True)
    table.add_column("Pressure", justify="right")
    table.add_column("Uncertainty", justify="right")
    table.add_column("Drift", justify="right")
    table.add_column("Errors", justify="right")

    for i, (ra, result) in enumerate(zip(recording.actions, results), start=1):
        table.add_row(
            str(i),
            ra.agent_id,
            _level_markup(result.level),
            f"{result.pressure:.3f}",
            f"{result.vitals.uncertainty:.3f}",
            f"{result.vitals.drift:.3f}",
            f"{result.vitals.error_rate:.3f}",
        )

    console.print(table)

    # --------------------------------------------------------------- summary
    # Per-agent max level and max pressure
    agent_max_level: dict[str, Level] = {}
    agent_max_pressure: dict[str, float] = {}

    for ra, result in zip(recording.actions, results):
        aid = ra.agent_id
        if aid not in agent_max_level or result.level > agent_max_level[aid]:
            agent_max_level[aid] = result.level
        if aid not in agent_max_pressure or result.pressure > agent_max_pressure[aid]:
            agent_max_pressure[aid] = result.pressure

    console.print("[bold]Summary:[/bold]")
    for aid in agent_ids:
        max_level = agent_max_level.get(aid, Level.HEALTHY)
        max_pressure = agent_max_pressure.get(aid, 0.0)
        level_str = _level_markup(max_level)
        console.print(
            f"  {aid}: max level {level_str}, "
            f"max pressure [cyan]{max_pressure:.3f}[/cyan]"
        )
    console.print()
