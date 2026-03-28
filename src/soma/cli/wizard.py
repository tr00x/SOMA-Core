"""Interactive setup wizard that creates soma.toml."""

from __future__ import annotations

import os
from typing import Literal

import tomli_w
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

SensitivityLevel = Literal["aggressive", "balanced", "relaxed"]

SENSITIVITY_PRESETS: dict[str, dict[str, float]] = {
    "aggressive": {
        "caution": 0.15,
        "degrade": 0.35,
        "quarantine": 0.55,
        "restart": 0.75,
    },
    "balanced": {
        "caution": 0.25,
        "degrade": 0.50,
        "quarantine": 0.75,
        "restart": 0.90,
    },
    "relaxed": {
        "caution": 0.35,
        "degrade": 0.60,
        "quarantine": 0.85,
        "restart": 0.95,
    },
}


def _prompt(question: str, default: str) -> str:
    """Print a colored prompt and return user input (or default on empty Enter)."""
    prompt_text = f"[cyan]{question}[/cyan] [dim]\\[{default}][/dim]: "
    console.print(prompt_text, end="")
    value = input()
    return value.strip() if value.strip() else default


def _prompt_choice(question: str, choices: list[str], default: str) -> str:
    """Prompt until the user enters one of the valid choices."""
    while True:
        value = _prompt(question, default)
        if value in choices:
            return value
        console.print(
            f"[red]Invalid choice '[bold]{value}[/bold]'. "
            f"Please choose one of: {', '.join(choices)}[/red]"
        )


def _prompt_int(question: str, default: int) -> int:
    """Prompt until the user enters a valid integer."""
    while True:
        value = _prompt(question, str(default))
        try:
            return int(value)
        except ValueError:
            console.print(f"[red]Please enter a whole number (e.g. {default}).[/red]")


def _prompt_float(question: str, default: float) -> float:
    """Prompt until the user enters a valid float."""
    while True:
        value = _prompt(question, str(default))
        try:
            return float(value)
        except ValueError:
            console.print(
                f"[red]Please enter a number (e.g. {default}).[/red]"
            )


def _prompt_yn(question: str, default: bool) -> bool:
    """Prompt a yes/no question."""
    default_str = "y" if default else "n"
    while True:
        value = _prompt(question, default_str).lower()
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        console.print("[red]Please answer y or n.[/red]")


def get_sensitivity_thresholds(sensitivity: str) -> dict[str, float]:
    """Return threshold dict for the given sensitivity preset name."""
    return SENSITIVITY_PRESETS[sensitivity]


# ---------------------------------------------------------------------------
# Per-project-type flows
# ---------------------------------------------------------------------------


def _flow_claude_code() -> dict:
    """Collect config for a Claude Code plugin project."""
    console.print("\n[bold yellow]Claude Code Plugin Configuration[/bold yellow]")

    token_budget = _prompt_int("Token budget per session?", 100_000)
    cost_limit = _prompt_float("Cost limit (USD)?", 5.0)
    sensitivity = _prompt_choice(
        "Sensitivity (aggressive/balanced/relaxed)?",
        ["aggressive", "balanced", "relaxed"],
        "balanced",
    )

    thresholds = get_sensitivity_thresholds(sensitivity)

    config = {
        "project": {"type": "claude_code"},
        "budget": {
            "tokens": token_budget,
            "cost_usd": cost_limit,
        },
        "thresholds": thresholds,
        "sensitivity": sensitivity,
    }
    return config


def _flow_python_sdk() -> dict:
    """Collect config for a Python SDK project."""
    console.print("\n[bold yellow]Python SDK Configuration[/bold yellow]")

    num_agents = _prompt_int("How many agents?", 3)

    default_names = ", ".join(f"Agent {i + 1}" for i in range(num_agents))
    raw_names = _prompt("Agent names (comma-separated)?", default_names)
    agent_names = [name.strip() for name in raw_names.split(",") if name.strip()]

    # Ensure we have exactly num_agents names; pad or trim as needed
    while len(agent_names) < num_agents:
        agent_names.append(f"Agent {len(agent_names) + 1}")
    agent_names = agent_names[:num_agents]

    chain = _prompt_yn("Connect agents in a chain? (y/n)", True)
    token_budget = _prompt_int("Token budget?", 100_000)
    sensitivity = _prompt_choice(
        "Sensitivity (aggressive/balanced/relaxed)?",
        ["aggressive", "balanced", "relaxed"],
        "balanced",
    )

    thresholds = get_sensitivity_thresholds(sensitivity)

    config = {
        "project": {"type": "python_sdk"},
        "agents": {
            "count": num_agents,
            "names": agent_names,
            "chain": chain,
        },
        "budget": {"tokens": token_budget},
        "thresholds": thresholds,
        "sensitivity": sensitivity,
    }
    return config


def _flow_ci() -> dict:
    """Collect config for a CI/CD testing project."""
    console.print("\n[bold yellow]CI/CD Testing Configuration[/bold yellow]")

    max_level = _prompt_choice(
        "Max level allowed (healthy/caution/degrade)?",
        ["healthy", "caution", "degrade"],
        "caution",
    )
    token_budget = _prompt_int("Token budget per test?", 10_000)

    config = {
        "project": {"type": "ci"},
        "ci": {
            "max_level": max_level,
        },
        "budget": {"tokens": token_budget},
    }
    return config


# ---------------------------------------------------------------------------
# Snippet printers
# ---------------------------------------------------------------------------


def _print_claude_code_snippet() -> None:
    console.print("\n[bold green]Next steps:[/bold green]")
    console.print(
        Panel(
            "Install the soma-claude-code plugin:\n\n"
            "  [bold cyan]npm install -g soma-claude-code[/bold cyan]\n\n"
            "Then add to your Claude Code settings:\n\n"
            '  [bold cyan]"plugins": ["soma-claude-code"][/bold cyan]',
            title="Claude Code Integration",
            border_style="green",
        )
    )


def _print_python_sdk_snippet(agent_names: list[str]) -> None:
    names_repr = repr(agent_names)
    snippet = (
        "import soma\n\n"
        f"engine = soma.SOMAEngine(\n"
        f"    agents={names_repr},\n"
        f"    config='soma.toml',\n"
        f")\n\n"
        f"# Record an action\n"
        f"action = soma.Action(tool_name='bash', output_text='...', token_count=500)\n"
        f"result = engine.record('{agent_names[0] if agent_names else 'agent1'}', action)"
    )
    console.print("\n[bold green]Integration snippet:[/bold green]")
    console.print(Panel(snippet, title="Python SDK", border_style="green"))


def _print_ci_snippet() -> None:
    snippet = (
        "from soma.testing import Monitor\n\n"
        "with Monitor(config='soma.toml') as mon:\n"
        "    mon.record('agent1', action)\n\n"
        "mon.assert_healthy()  # raises AssertionError if level exceeded"
    )
    console.print("\n[bold green]CI Integration snippet:[/bold green]")
    console.print(Panel(snippet, title="CI Testing", border_style="green"))


# ---------------------------------------------------------------------------
# Main wizard entry point
# ---------------------------------------------------------------------------


def run_wizard() -> None:
    """Interactive wizard that creates soma.toml."""

    console.print(
        Panel(
            Text("SOMA Setup Wizard", style="bold magenta", justify="center"),
            border_style="magenta",
        )
    )

    console.print("\n[bold]What type of project?[/bold]")
    console.print("  [cyan]1)[/cyan] Claude Code plugin — monitor Claude Code agents")
    console.print("  [cyan]2)[/cyan] Python SDK — integrate SOMA into your Python code")
    console.print("  [cyan]3)[/cyan] CI/CD testing — test agent behavior in CI")

    project_type = _prompt_choice("\nChoose", ["1", "2", "3"], "1")

    if project_type == "1":
        config = _flow_claude_code()
    elif project_type == "2":
        config = _flow_python_sdk()
    else:
        config = _flow_ci()

    # Write soma.toml
    output_path = os.path.join(os.getcwd(), "soma.toml")
    with open(output_path, "wb") as fh:
        tomli_w.dump(config, fh)

    console.print(
        f"\n[bold green]soma.toml created![/bold green] "
        f"Run [bold cyan]`soma`[/bold cyan] to open the dashboard."
    )

    # Print integration snippet
    if project_type == "1":
        _print_claude_code_snippet()
    elif project_type == "2":
        agent_names = config.get("agents", {}).get("names", [])
        _print_python_sdk_snippet(agent_names)
    else:
        _print_ci_snippet()
