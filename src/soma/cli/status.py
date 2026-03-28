"""SOMA CLI status command — prints a quick text summary of the current session."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from rich.console import Console
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

from soma.cli.config_loader import load_config, DEFAULT_CONFIG

# Level display colours (rich markup style names)
_LEVEL_COLOURS = {
    "HEALTHY": "green",
    "CAUTION": "yellow",
    "DEGRADE": "dark_orange",
    "QUARANTINE": "red",
    "RESTART": "bright_red",
    "SAFE_MODE": "magenta",
}


def _read_state(state_path: str) -> dict[str, Any] | None:
    """Return the parsed state JSON, or None if the file does not exist."""
    expanded = os.path.expanduser(state_path)
    if not os.path.exists(expanded):
        return None
    with open(expanded, "r", encoding="utf-8") as fh:
        return json.load(fh)


def print_status(config: dict[str, Any] | None = None) -> None:
    """Print a quick text status of the current SOMA session to stdout."""
    if config is None:
        config = load_config()

    store_path: str = config.get("soma", {}).get(
        "store", DEFAULT_CONFIG["soma"]["store"]
    )
    version: str = config.get("soma", {}).get(
        "version", DEFAULT_CONFIG["soma"]["version"]
    )
    budget_limits = config.get("budget", DEFAULT_CONFIG["budget"])
    token_limit = int(budget_limits.get("tokens", 100_000))

    state = _read_state(store_path)

    if _HAS_RICH:
        console = Console()
    else:
        console = None  # type: ignore[assignment]

    def _print(text: str | Any) -> None:
        if _HAS_RICH and console is not None:
            console.print(text)
        else:
            # Strip any Rich markup for plain output
            if hasattr(text, "__str__"):
                print(str(text))
            else:
                print(text)

    if state is None:
        msg = "No SOMA session active. Run `soma init` to get started."
        _print(msg)
        return

    # Extract agents list from state
    agents: list[dict[str, Any]] = state.get("agents", [])
    n_agents = len(agents)

    # Header
    header = f"SOMA v{version} — {n_agents} agent{'s' if n_agents != 1 else ''} monitored"
    if _HAS_RICH:
        _print(Text(header, style="bold"))
    else:
        _print(header)
    _print("")

    # Agent rows
    for i, agent in enumerate(agents, start=1):
        agent_id = agent.get("id", f"Agent {i}")
        level_str = str(agent.get("level", "HEALTHY")).upper()
        pressure = float(agent.get("pressure", 0.0))
        vitals = agent.get("vitals", {})
        uncertainty = float(vitals.get("uncertainty", 0.0))
        drift = float(vitals.get("drift", 0.0))
        error_rate = float(vitals.get("error_rate", 0.0))
        action_count = int(agent.get("action_count", 0))

        colour = _LEVEL_COLOURS.get(level_str, "white")
        row = (
            f"  {agent_id:<12}"
            f"  {level_str:<12}"
            f"  p={pressure:.2f}"
            f"  u={uncertainty:.2f}"
            f"  d={drift:.2f}"
            f"  e={error_rate:.2f}"
            f"   #{action_count}"
        )

        if _HAS_RICH:
            text = Text()
            text.append(f"  {agent_id:<12}  ")
            text.append(f"{level_str:<12}", style=colour)
            text.append(
                f"  p={pressure:.2f}"
                f"  u={uncertainty:.2f}"
                f"  d={drift:.2f}"
                f"  e={error_rate:.2f}"
                f"   #{action_count}"
            )
            _print(text)
        else:
            _print(row)

    _print("")

    # Budget line
    budget_state = state.get("budget", {})
    tokens_spent = int(budget_state.get("tokens_spent", 0))
    budget_pct = int((tokens_spent / token_limit * 100)) if token_limit else 0
    budget_line = (
        f"  Budget: {budget_pct}%"
        f" (tokens: {tokens_spent:,}/{token_limit:,})"
    )
    _print(budget_line)
