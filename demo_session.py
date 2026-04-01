"""SOMA Demo — Real behavioral monitoring of a degrading AI agent.

This script simulates a realistic agent session where behavior
degrades over time. All data flows through the real SOMA engine —
pressure, vitals, mode transitions, and guidance are computed live.
"""
from __future__ import annotations

import time

import soma

# ── Rich formatting ──────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def bar(value: float, width: int = 20) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def mode_color(mode_name: str) -> str:
    return {
        "OBSERVE": "green",
        "GUIDE": "yellow",
        "WARN": "bright_red",
        "BLOCK": "red bold",
    }.get(mode_name, "white")


# ── Engine setup ─────────────────────────────────────────────
engine = soma.quickstart()
engine.register_agent("agent-1", system_prompt="Implement auth module with tests")

if HAS_RICH:
    console.print()
    console.print(
        Panel(
            "[bold]SOMA[/bold] — Behavioral Monitoring Demo\n"
            "[dim]Real engine, real pressure computation, real guidance[/dim]",
            border_style="magenta",
            width=60,
        )
    )
    console.print()

# ── Scenario: agent starts well, then degrades ──────────────

scenario = [
    # Phase 1: Good behavior — reading before writing
    ("Read", "src/auth.py", False, 80, "Reading target file first"),
    ("Read", "tests/test_auth.py", False, 60, "Reading existing tests"),
    ("Glob", "src/**/*.py", False, 30, "Exploring project structure"),
    ("Edit", "src/auth.py", False, 120, "Clean edit after reading"),
    ("Read", "src/auth.py", False, 80, "Verify edit result"),
    # Phase 2: Starting to drift — edits without reads
    ("Edit", "src/auth.py", False, 150, "Edit without reading first"),
    ("Edit", "src/config.py", False, 150, "Editing unrelated file"),
    ("Edit", "src/utils.py", False, 200, "Scope creep — 3rd file"),
    # Phase 3: Errors start — retrying failed commands
    ("Bash", "Error: ModuleNotFoundError: No module named 'jwt'", True, 100, "Command failed"),
    ("Bash", "Error: ModuleNotFoundError: No module named 'jwt'", True, 100, "Same error, retry #1"),
    ("Bash", "Error: ModuleNotFoundError: No module named 'jwt'", True, 120, "Same error, retry #2"),
    ("Bash", "Error: pip install failed", True, 80, "Install attempt failed"),
    # Phase 4: Spiral — errors + blind writes + high tokens
    ("Edit", "src/auth.py", False, 300, "Blind write, no read"),
    ("Bash", "Error: SyntaxError line 42", True, 200, "Introduced syntax error"),
    ("Edit", "src/auth.py", False, 350, "Panic fix attempt"),
    ("Bash", "Error: SyntaxError line 38", True, 250, "Still broken"),
    ("Bash", "Error: tests failed (12 failures)", True, 300, "Test suite broken"),
    ("Edit", "src/auth.py", False, 400, "Desperate rewrite"),
    ("Bash", "Error: tests failed (8 failures)", True, 350, "Still failing"),
    ("Bash", "Error: tests failed (8 failures)", True, 350, "Retry same command"),
]

results = []

for i, (tool, output, error, tokens, desc) in enumerate(scenario, 1):
    result = engine.record_action(
        "agent-1",
        soma.Action(
            tool_name=tool,
            output_text=output,
            token_count=tokens,
            error=error,
        ),
    )
    snap = engine.get_snapshot("agent-1")
    results.append((i, tool, desc, error, result, snap))

    if HAS_RICH:
        mode_name = result.mode.name
        p = result.pressure
        color = mode_color(mode_name)

        # Show action
        err_marker = " [red]ERROR[/red]" if error else ""
        console.print(
            f"  [dim]#{i:2d}[/dim]  [bold]{tool:6s}[/bold]{err_marker}  "
            f"[dim]{desc}[/dim]"
        )

        # Show pressure bar on every action for visual impact
        if True:
            console.print(
                f"         [{color}]{bar(p)} {p:5.0%}  {mode_name}[/{color}]"
            )

            # Show context action (guidance)
            if result.context_action not in ("pass", None):
                console.print(
                    f"         [bold {color}]→ {result.context_action.upper()}[/bold {color}]"
                )
        console.print()
        time.sleep(0.15)
    else:
        mode_name = result.mode.name
        err_str = " ERROR" if error else ""
        print(
            f"  #{i:2d}  {tool:6s}{err_str:6s}  "
            f"p={result.pressure:5.0%}  {mode_name:8s}  {desc}"
        )

# ── Final report ─────────────────────────────────────────────
final = results[-1]
final_result = final[4]
final_snap = final[5]

if HAS_RICH:
    console.print()

    table = Table(title="Final Vitals", border_style="magenta", width=55)
    table.add_column("Signal", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("", width=20)

    vitals = final_snap["vitals"]
    for signal, value in vitals.items():
        v = float(value)
        table.add_row(signal, f"{v:.2f}", bar(min(v, 1.0), 15))

    table.add_row("", "", "")
    p = final_result.pressure
    table.add_row(
        "[bold]PRESSURE[/bold]",
        f"[bold]{p:.0%}[/bold]",
        f"[bold {mode_color(final_result.mode.name)}]{bar(p, 15)}[/bold {mode_color(final_result.mode.name)}]",
    )
    table.add_row(
        "[bold]MODE[/bold]",
        f"[bold {mode_color(final_result.mode.name)}]{final_result.mode.name}[/bold {mode_color(final_result.mode.name)}]",
        "",
    )

    console.print(table)
    console.print()
    console.print(
        f"  [dim]Actions: {final_snap['action_count']}  |  "
        f"Budget: {final_snap['budget_health']:.0%}  |  "
        f"Errors: {sum(1 for r in results if r[3])}/{len(results)}[/dim]"
    )
    console.print()
else:
    print(f"\nPressure: {final_result.pressure:.0%}")
    print(f"Mode:     {final_result.mode.name}")
    print(f"Actions:  {final_snap['action_count']}")
    print(f"Errors:   {sum(1 for r in results if r[3])}/{len(results)}")
