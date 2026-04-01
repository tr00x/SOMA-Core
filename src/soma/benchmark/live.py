"""Live benchmark — real LLM tasks with SOMA vs without.

Runs the same coding task through a real Anthropic API multiple times,
comparing results with SOMA guidance enabled vs disabled.

Requires: ANTHROPIC_API_KEY environment variable.
Uses claude-haiku for cost efficiency (~$0.01 per run).
"""

from __future__ import annotations

import json
import os
import statistics
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

import soma
from soma.types import Action


# ------------------------------------------------------------------
# Task definitions — real coding tasks for the LLM
# ------------------------------------------------------------------

TASKS = [
    {
        "name": "fizzbuzz_with_tests",
        "description": "Write FizzBuzz with edge cases and tests",
        "system": "You are a Python developer. Write clean, tested code. Respond with ONLY code, no explanations.",
        "messages": [
            {
                "role": "user",
                "content": textwrap.dedent("""\
                    Write a Python function `fizzbuzz(n: int) -> list[str]` that returns
                    FizzBuzz for numbers 1 to n. Then write pytest tests covering:
                    - n=0 (empty list)
                    - n=1 (['1'])
                    - n=15 (includes Fizz, Buzz, FizzBuzz)
                    - n=100 (check count of FizzBuzz entries)

                    Return the code as a single Python file with both the function and tests.
                """),
            }
        ],
        "validate": lambda text: (
            "def fizzbuzz" in text
            and "def test_" in text
            and "FizzBuzz" in text
        ),
    },
    {
        "name": "retry_prone_task",
        "description": "Ambiguous task that causes retries and uncertainty",
        "system": "You are a Python developer. Be precise.",
        "messages": [
            {"role": "user", "content": "Write a Python class for a binary search tree with insert, search, delete, and in-order traversal. Include type hints."},
            {"role": "assistant", "content": "I'll write a BST class. Let me start with the node class and basic operations."},
            {"role": "user", "content": "Actually wait, make it a self-balancing AVL tree instead. And add tests."},
            {"role": "assistant", "content": "Switching to AVL tree with rotations and rebalancing."},
            {"role": "user", "content": "Hmm, on second thought, keep it as a regular BST but add serialization to JSON and deserialization. And make delete handle all 3 cases properly. Show me the full code."},
        ],
        "validate": lambda text: (
            "class" in text
            and "def insert" in text
            and "def delete" in text
            and ("json" in text.lower() or "serialize" in text.lower())
        ),
    },
    {
        "name": "debug_scenario",
        "description": "Fix a buggy function with subtle error",
        "system": "You are a senior Python developer debugging code. Fix the bug and explain what was wrong.",
        "messages": [
            {
                "role": "user",
                "content": textwrap.dedent("""\
                    This function should merge two sorted lists but has a bug. Fix it:

                    ```python
                    def merge_sorted(a: list[int], b: list[int]) -> list[int]:
                        result = []
                        i = j = 0
                        while i < len(a) and j < len(b):
                            if a[i] <= b[j]:
                                result.append(a[i])
                                i += 1
                            else:
                                result.append(b[j])
                                j += 1
                        # Bug: only appends remaining from one list
                        result.extend(a[i:])
                        return result
                    ```

                    Write the fix and a test that catches the bug.
                """),
            }
        ],
        "validate": lambda text: (
            "def merge_sorted" in text
            and "b[j:]" in text or "extend(b" in text
            and "def test_" in text or "assert" in text
        ),
    },
]


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class LiveRunResult:
    """Result from a single LLM run."""
    task_name: str
    soma_enabled: bool
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    response_text: str
    validation_passed: bool
    final_pressure: float
    final_mode: str
    actions_recorded: int
    error: str | None = None


@dataclass
class LiveTaskResult:
    """A/B comparison for one task."""
    task_name: str
    description: str
    soma_runs: list[LiveRunResult] = field(default_factory=list)
    baseline_runs: list[LiveRunResult] = field(default_factory=list)

    @property
    def avg_soma_tokens(self) -> float:
        runs = [r for r in self.soma_runs if not r.error]
        return statistics.mean(r.total_tokens for r in runs) if runs else 0

    @property
    def avg_baseline_tokens(self) -> float:
        runs = [r for r in self.baseline_runs if not r.error]
        return statistics.mean(r.total_tokens for r in runs) if runs else 0

    @property
    def token_savings(self) -> float:
        b = self.avg_baseline_tokens
        return (b - self.avg_soma_tokens) / b if b > 0 else 0

    @property
    def avg_soma_duration(self) -> float:
        runs = [r for r in self.soma_runs if not r.error]
        return statistics.mean(r.duration_seconds for r in runs) if runs else 0

    @property
    def avg_baseline_duration(self) -> float:
        runs = [r for r in self.baseline_runs if not r.error]
        return statistics.mean(r.duration_seconds for r in runs) if runs else 0

    @property
    def soma_validation_rate(self) -> float:
        runs = [r for r in self.soma_runs if not r.error]
        return sum(1 for r in runs if r.validation_passed) / len(runs) if runs else 0

    @property
    def baseline_validation_rate(self) -> float:
        runs = [r for r in self.baseline_runs if not r.error]
        return sum(1 for r in runs if r.validation_passed) / len(runs) if runs else 0


@dataclass
class LiveBenchmarkResult:
    """Top-level live benchmark result."""
    tasks: list[LiveTaskResult] = field(default_factory=list)
    model: str = ""
    runs_per_task: int = 3
    timestamp: str = ""
    total_cost_estimate: float = 0.0


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------


def _run_single(
    task: dict,
    soma_enabled: bool,
    model: str,
) -> LiveRunResult:
    """Run a single task through the LLM with or without SOMA."""
    import anthropic

    if soma_enabled:
        engine = soma.quickstart()
        engine.register_agent("live-bench")
        client = soma.wrap(
            anthropic.Anthropic(),
            engine=engine,
            agent_id="live-bench",
            budget={"tokens": 100_000},
        )
    else:
        client = anthropic.Anthropic()
        engine = None

    t0 = time.monotonic()
    error_msg = None
    response_text = ""
    input_tokens = 0
    output_tokens = 0

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=task["system"],
            messages=task["messages"],
        )
        response_text = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
    except Exception as e:
        error_msg = str(e)

    elapsed = time.monotonic() - t0
    total_tokens = input_tokens + output_tokens

    # Validation
    validation_passed = False
    if not error_msg and response_text:
        try:
            validation_passed = task["validate"](response_text)
        except Exception:
            validation_passed = False

    # Get SOMA state
    final_pressure = 0.0
    final_mode = "NONE"
    actions_recorded = 0
    if engine:
        try:
            snap = engine.get_snapshot("live-bench")
            final_pressure = snap.get("pressure", 0.0)
            final_mode = snap.get("mode", "OBSERVE")
            if hasattr(final_mode, "name"):
                final_mode = final_mode.name
            actions_recorded = snap.get("action_count", 0)
        except Exception:
            pass

    return LiveRunResult(
        task_name=task["name"],
        soma_enabled=soma_enabled,
        duration_seconds=elapsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        response_text=response_text,
        validation_passed=validation_passed,
        final_pressure=final_pressure,
        final_mode=str(final_mode),
        actions_recorded=actions_recorded,
        error=error_msg,
    )


def run_live_benchmark(
    runs_per_task: int = 3,
    model: str = "claude-haiku-4-5-20251001",
    tasks: list[dict] | None = None,
) -> LiveBenchmarkResult:
    """Run all tasks with SOMA on/off and collect results.

    Uses claude-haiku by default for cost efficiency.
    Estimated cost: ~$0.05 for 3 tasks x 3 runs x 2 conditions.
    """
    import datetime

    if "ANTHROPIC_API_KEY" not in os.environ:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it first:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )

    task_defs = tasks or TASKS
    task_results: list[LiveTaskResult] = []
    total_tokens = 0

    for task in task_defs:
        tr = LiveTaskResult(
            task_name=task["name"],
            description=task["description"],
        )

        for run_idx in range(runs_per_task):
            # SOMA-enabled run
            result_soma = _run_single(task, soma_enabled=True, model=model)
            tr.soma_runs.append(result_soma)
            total_tokens += result_soma.total_tokens

            # Baseline run (no SOMA)
            result_base = _run_single(task, soma_enabled=False, model=model)
            tr.baseline_runs.append(result_base)
            total_tokens += result_base.total_tokens

        task_results.append(tr)

    # Rough cost estimate (haiku pricing)
    cost_per_1k_input = 0.001  # $1/MTok
    cost_per_1k_output = 0.005  # $5/MTok
    est_cost = total_tokens * (cost_per_1k_input + cost_per_1k_output) / 2000

    return LiveBenchmarkResult(
        tasks=task_results,
        model=model,
        runs_per_task=runs_per_task,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        total_cost_estimate=est_cost,
    )


# ------------------------------------------------------------------
# Report generation
# ------------------------------------------------------------------


def generate_live_report(result: LiveBenchmarkResult) -> str:
    """Generate markdown report from live benchmark results."""
    lines = [
        "# SOMA Live Benchmark Results",
        "",
        f"> **Model:** {result.model}",
        f"> **Runs per task:** {result.runs_per_task}",
        f"> **Generated:** {result.timestamp}",
        f"> **Estimated cost:** ${result.total_cost_estimate:.3f}",
        "",
        "## Summary",
        "",
        "| Task | Metric | Without SOMA | With SOMA | Difference |",
        "|------|--------|-------------|-----------|------------|",
    ]

    for tr in result.tasks:
        lines.append(
            f"| {tr.task_name} | Tokens | {tr.avg_baseline_tokens:.0f} | "
            f"{tr.avg_soma_tokens:.0f} | {tr.token_savings:+.1%} |"
        )
        lines.append(
            f"| | Duration | {tr.avg_baseline_duration:.1f}s | "
            f"{tr.avg_soma_duration:.1f}s | |"
        )
        lines.append(
            f"| | Validation | {tr.baseline_validation_rate:.0%} | "
            f"{tr.soma_validation_rate:.0%} | |"
        )

    lines.extend(["", "## Per-Task Details", ""])

    for tr in result.tasks:
        lines.extend([
            f"### {tr.task_name}",
            "",
            f"_{tr.description}_",
            "",
            "| Run | Mode | Tokens | Duration | Valid | Pressure | SOMA Mode |",
            "|-----|------|--------|----------|-------|----------|-----------|",
        ])

        for i, run in enumerate(tr.baseline_runs, 1):
            err = f" ERROR: {run.error}" if run.error else ""
            lines.append(
                f"| B-{i} | baseline | {run.total_tokens} | "
                f"{run.duration_seconds:.1f}s | "
                f"{'PASS' if run.validation_passed else 'FAIL'} | — | —{err} |"
            )
        for i, run in enumerate(tr.soma_runs, 1):
            err = f" ERROR: {run.error}" if run.error else ""
            lines.append(
                f"| S-{i} | SOMA | {run.total_tokens} | "
                f"{run.duration_seconds:.1f}s | "
                f"{'PASS' if run.validation_passed else 'FAIL'} | "
                f"{run.final_pressure:.0%} | {run.final_mode}{err} |"
            )
        lines.append("")

    lines.extend([
        "---",
        "",
        "*Generated by `soma benchmark --live`*",
    ])

    return "\n".join(lines)


def render_live_terminal(result: LiveBenchmarkResult) -> None:
    """Print live benchmark results using rich tables."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()
    except ImportError:
        # Fallback to plain text
        print(generate_live_report(result))
        return

    console.print()
    console.print(Panel(
        f"[bold]SOMA Live Benchmark[/bold]\n"
        f"[dim]Model: {result.model} | Runs: {result.runs_per_task} | "
        f"Cost: ${result.total_cost_estimate:.3f}[/dim]",
        border_style="magenta",
        width=70,
    ))

    table = Table(title="Results", border_style="magenta", width=70)
    table.add_column("Task")
    table.add_column("Metric", style="dim")
    table.add_column("Baseline", justify="right")
    table.add_column("SOMA", justify="right")
    table.add_column("Diff", justify="right")

    for tr in result.tasks:
        savings = tr.token_savings
        color = "green" if savings > 0 else "red" if savings < 0 else "white"

        table.add_row(
            tr.task_name,
            "tokens",
            f"{tr.avg_baseline_tokens:.0f}",
            f"{tr.avg_soma_tokens:.0f}",
            f"[{color}]{savings:+.1%}[/{color}]",
        )
        table.add_row(
            "",
            "valid",
            f"{tr.baseline_validation_rate:.0%}",
            f"{tr.soma_validation_rate:.0%}",
            "",
        )
        table.add_row(
            "",
            "time",
            f"{tr.avg_baseline_duration:.1f}s",
            f"{tr.avg_soma_duration:.1f}s",
            "",
        )

    console.print(table)
    console.print()
