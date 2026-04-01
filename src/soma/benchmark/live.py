"""Live benchmark — multi-turn agent loop with SOMA vs without.

Simulates a real agentic coding session: agent writes code, runs tests,
gets errors, retries — with and without SOMA guidance injection.

SOMA's value shows in multi-turn loops where guidance prevents:
- Blind retries (same failing approach)
- Scope drift (editing unrelated files)
- Error spirals (cascading failures)

Requires: ANTHROPIC_API_KEY environment variable.
Uses claude-haiku for cost efficiency (~$0.10 per full run).
"""

from __future__ import annotations

import datetime
import os
import statistics
import subprocess
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path


# ------------------------------------------------------------------
# Task definitions — multi-turn coding tasks
# ------------------------------------------------------------------

TASKS = [
    {
        "name": "calculator_with_bugs",
        "description": "Build a calculator with intentional test failures to trigger retries",
        "system": textwrap.dedent("""\
            You are a Python developer. Write code and respond with ONLY the code block.
            No explanations. Just ```python ... ``` blocks.
            When you get test failures, fix the code and return the COMPLETE fixed file.
        """),
        "steps": [
            {
                "prompt": textwrap.dedent("""\
                    Write a Python file calc.py with:
                    - add(a, b), subtract(a, b), multiply(a, b), divide(a, b)
                    - divide should raise ValueError on zero
                    - A function power(base, exp) that handles negative exponents
                    Include pytest tests at the bottom.
                """),
                "test_cmd": "python -m py_compile {file}",
                "expect_pass": True,
            },
            {
                "prompt": "The tests found an issue: power(2, -1) returns an integer instead of a float. Fix the entire file.",
                "test_cmd": "python -c \"exec(open('{file}').read()); assert isinstance(power(2, -1), float), f'Expected float, got {{type(power(2, -1))}}'\"",
                "expect_pass": True,
            },
            {
                "prompt": "New requirement: add a sqrt(x) function that raises ValueError for negative numbers. Add tests for it. Return the COMPLETE file.",
                "test_cmd": "python -c \"exec(open('{file}').read()); assert sqrt(16) == 4.0; assert sqrt(0) == 0.0\"",
                "expect_pass": True,
            },
        ],
    },
    {
        "name": "data_processor_errors",
        "description": "Build a data processor with deliberate error cascade",
        "system": textwrap.dedent("""\
            You are a Python developer writing data processing code.
            Respond with ONLY code blocks. No explanations.
            Fix ALL issues when given error feedback.
        """),
        "steps": [
            {
                "prompt": textwrap.dedent("""\
                    Write processor.py with a class DataProcessor that:
                    - __init__(self, data: list[dict]) stores data
                    - filter_by(key, value) returns matching records
                    - group_by(key) returns dict mapping key values to lists of records
                    - aggregate(key, func) applies func to each group
                    - to_csv(path) writes data to CSV file
                    Include tests with sample data.
                """),
                "test_cmd": "python -m py_compile {file}",
                "expect_pass": True,
            },
            {
                "prompt": textwrap.dedent("""\
                    Error when testing:
                    TypeError: group_by() got multiple values for argument 'key'
                    Also: to_csv fails with AttributeError: 'dict' object has no attribute 'keys'
                    on empty data. Fix the COMPLETE file.
                """),
                "test_cmd": "python -c \"exec(open('{file}').read()); dp = DataProcessor([]); dp.to_csv('/dev/null')\"",
                "expect_pass": True,
            },
            {
                "prompt": textwrap.dedent("""\
                    New test failure:
                    AssertionError: aggregate with sum on empty group returns None, expected 0.
                    Also add: sort_by(key, reverse=False) method.
                    Return COMPLETE file.
                """),
                "test_cmd": "python -c \"exec(open('{file}').read()); dp = DataProcessor([{{'a':1}},{{'a':2}}]); assert dp.sort_by('a')[0]['a'] == 1\"",
                "expect_pass": True,
            },
            {
                "prompt": "Add error handling: filter_by on missing key should return empty list, not KeyError. Same for group_by. Return COMPLETE file.",
                "test_cmd": "python -c \"exec(open('{file}').read()); dp = DataProcessor([{{'a':1}}]); assert dp.filter_by('missing', 1) == []\"",
                "expect_pass": True,
            },
        ],
    },
    {
        "name": "api_client_retry_storm",
        "description": "Build an API client where error handling causes retry loops",
        "system": textwrap.dedent("""\
            You are a Python developer. Write code and respond with ONLY code blocks.
            When given errors, fix the code. Return COMPLETE files.
        """),
        "steps": [
            {
                "prompt": textwrap.dedent("""\
                    Write api_client.py with a class APIClient that:
                    - __init__(self, base_url, max_retries=3, timeout=5)
                    - get(endpoint) -> dict (mock implementation, returns {"status": "ok"})
                    - post(endpoint, data) -> dict
                    - Retry logic: on failure, retry up to max_retries with exponential backoff
                    - Rate limiting: track requests per second, raise if > 10 rps
                    Include tests using mocked responses.
                """),
                "test_cmd": "python -m py_compile {file}",
                "expect_pass": True,
            },
            {
                "prompt": textwrap.dedent("""\
                    Test failure: the retry logic enters an infinite loop when all retries fail.
                    After max_retries, it should raise an APIError(message, status_code).
                    Also: rate limiter doesn't reset the counter. Fix the COMPLETE file.
                """),
                "test_cmd": "python -c \"exec(open('{file}').read()); c = APIClient('http://test'); assert c.max_retries == 3\"",
                "expect_pass": True,
            },
            {
                "prompt": textwrap.dedent("""\
                    New requirement: add request/response logging.
                    - log_request(method, endpoint, data) stores in self.history
                    - Each entry: {"method": str, "endpoint": str, "status": str, "timestamp": float}
                    - Add get_history() -> list[dict]
                    Return COMPLETE file with tests.
                """),
                "test_cmd": "python -c \"exec(open('{file}').read()); c = APIClient('http://test'); c.get('/ping'); assert len(c.get_history()) >= 1\"",
                "expect_pass": True,
            },
        ],
    },
]


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class StepResult:
    """Result from a single agent step."""
    step_index: int
    prompt: str
    response_text: str
    input_tokens: int
    output_tokens: int
    test_passed: bool
    test_output: str
    duration_seconds: float
    soma_pressure: float
    soma_mode: str
    guidance_injected: str  # guidance text injected (empty if no SOMA)


@dataclass
class LiveRunResult:
    """Result from a single multi-turn run."""
    task_name: str
    soma_enabled: bool
    steps: list[StepResult] = field(default_factory=list)
    total_tokens: int = 0
    total_duration: float = 0.0
    final_test_passed: bool = False
    total_retries: int = 0  # steps where test failed
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
    def token_diff(self) -> float:
        b = self.avg_baseline_tokens
        return (b - self.avg_soma_tokens) / b if b > 0 else 0

    @property
    def avg_soma_retries(self) -> float:
        runs = [r for r in self.soma_runs if not r.error]
        return statistics.mean(r.total_retries for r in runs) if runs else 0

    @property
    def avg_baseline_retries(self) -> float:
        runs = [r for r in self.baseline_runs if not r.error]
        return statistics.mean(r.total_retries for r in runs) if runs else 0

    @property
    def soma_pass_rate(self) -> float:
        runs = [r for r in self.soma_runs if not r.error]
        return sum(1 for r in runs if r.final_test_passed) / len(runs) if runs else 0

    @property
    def baseline_pass_rate(self) -> float:
        runs = [r for r in self.baseline_runs if not r.error]
        return sum(1 for r in runs if r.final_test_passed) / len(runs) if runs else 0


@dataclass
class LiveBenchmarkResult:
    """Top-level live benchmark result."""
    tasks: list[LiveTaskResult] = field(default_factory=list)
    model: str = ""
    runs_per_task: int = 3
    timestamp: str = ""
    total_cost_estimate: float = 0.0


# ------------------------------------------------------------------
# Multi-turn agent runner
# ------------------------------------------------------------------


def _extract_code(text: str) -> str:
    """Extract Python code from markdown code blocks."""
    if "```python" in text:
        parts = text.split("```python")
        if len(parts) > 1:
            code = parts[1].split("```")[0]
            return code.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) > 1:
            code = parts[1]
            if code.startswith("\n"):
                code = code[1:]
            code = code.split("```")[0]
            return code.strip()
    return text.strip()


def _run_test(cmd: str, file_path: str) -> tuple[bool, str]:
    """Run a test command, return (passed, output)."""
    cmd = cmd.replace("{file}", file_path)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        passed = result.returncode == 0
        output = result.stdout + result.stderr
        return passed, output.strip()[:500]  # cap output length
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)[:500]


def _build_guidance(engine, agent_id: str) -> str:
    """Build SOMA guidance string from engine state."""
    try:
        snap = engine.get_snapshot(agent_id)
        pressure = snap.get("pressure", 0.0)
        mode = snap.get("mode")
        mode_name = mode.name if hasattr(mode, "name") else str(mode)

        if mode_name == "OBSERVE":
            return ""

        vitals = snap.get("vitals", {})
        parts = [f"[SOMA {mode_name} p={pressure:.0%}]"]

        er = vitals.get("error_rate", 0)
        if er > 0.3:
            parts.append(f"Error rate {er:.0%} — try a different approach instead of retrying.")
        drift = vitals.get("drift", 0)
        if drift > 0.2:
            parts.append("You're drifting from the original task. Refocus.")
        unc = vitals.get("uncertainty", 0)
        if unc > 0.3:
            parts.append("High uncertainty — read the error carefully before changing code.")

        return " ".join(parts)
    except Exception:
        return ""


def _run_multi_turn(
    task: dict,
    soma_enabled: bool,
    model: str,
) -> LiveRunResult:
    """Run a multi-turn agent loop for one task."""
    import anthropic
    import soma as soma_mod

    engine = None
    if soma_enabled:
        engine = soma_mod.quickstart()
        engine.register_agent("live-bench")

    client = anthropic.Anthropic()

    steps_results: list[StepResult] = []
    messages: list[dict] = []
    total_tokens = 0
    total_retries = 0
    last_test_passed = False

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        tmp_file = f.name

    try:
        for step_idx, step in enumerate(task["steps"]):
            t0 = time.monotonic()

            # Build prompt — include SOMA guidance if enabled
            guidance_text = ""
            if engine and soma_enabled:
                guidance_text = _build_guidance(engine, "live-bench")

            user_prompt = step["prompt"]
            if guidance_text:
                user_prompt = f"{guidance_text}\n\n{user_prompt}"

            messages.append({"role": "user", "content": user_prompt})

            # Call LLM
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=task["system"],
                    messages=messages,
                )
                response_text = response.content[0].text if response.content else ""
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
            except Exception as e:
                return LiveRunResult(
                    task_name=task["name"],
                    soma_enabled=soma_enabled,
                    error=str(e),
                )

            messages.append({"role": "assistant", "content": response_text})
            total_tokens += input_tokens + output_tokens

            # Extract code and write to file
            code = _extract_code(response_text)
            Path(tmp_file).write_text(code)

            # Run test
            test_passed, test_output = _run_test(step["test_cmd"], tmp_file)
            if not test_passed:
                total_retries += 1
            last_test_passed = test_passed

            # Record action in SOMA engine
            pressure = 0.0
            mode_name = "NONE"
            if engine:
                from soma.types import Action
                result = engine.record_action(
                    "live-bench",
                    Action(
                        tool_name="Edit" if step_idx > 0 else "Write",
                        output_text=test_output[:200] if not test_passed else "tests passed",
                        token_count=input_tokens + output_tokens,
                        error=not test_passed,
                    ),
                )
                pressure = result.pressure
                mode_name = result.mode.name

            elapsed = time.monotonic() - t0

            steps_results.append(StepResult(
                step_index=step_idx,
                prompt=step["prompt"][:100],
                response_text=response_text[:200],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                test_passed=test_passed,
                test_output=test_output[:200],
                duration_seconds=elapsed,
                soma_pressure=pressure,
                soma_mode=mode_name,
                guidance_injected=guidance_text,
            ))

    finally:
        Path(tmp_file).unlink(missing_ok=True)

    return LiveRunResult(
        task_name=task["name"],
        soma_enabled=soma_enabled,
        steps=steps_results,
        total_tokens=total_tokens,
        total_duration=sum(s.duration_seconds for s in steps_results),
        final_test_passed=last_test_passed,
        total_retries=total_retries,
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def run_live_benchmark(
    runs_per_task: int = 3,
    model: str = "claude-haiku-4-5-20251001",
    tasks: list[dict] | None = None,
) -> LiveBenchmarkResult:
    """Run multi-turn agent tasks with SOMA on/off.

    Estimated cost: ~$0.10 for 3 tasks x 3 runs x 2 conditions.
    """
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

        for _run_idx in range(runs_per_task):
            # SOMA run
            result_soma = _run_multi_turn(task, soma_enabled=True, model=model)
            tr.soma_runs.append(result_soma)
            total_tokens += result_soma.total_tokens

            # Baseline run
            result_base = _run_multi_turn(task, soma_enabled=False, model=model)
            tr.baseline_runs.append(result_base)
            total_tokens += result_base.total_tokens

        task_results.append(tr)

    # Rough cost estimate
    est_cost = total_tokens * 0.003 / 1000  # ~$3/MTok blended haiku rate

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
        "# SOMA Live Benchmark — Multi-Turn Agent Results",
        "",
        f"> **Model:** {result.model}",
        f"> **Runs per task:** {result.runs_per_task}",
        f"> **Generated:** {result.timestamp}",
        f"> **Estimated cost:** ${result.total_cost_estimate:.3f}",
        "",
        "## Summary",
        "",
        "| Task | Tokens (base) | Tokens (SOMA) | Diff | Retries (base) | Retries (SOMA) | Pass (base) | Pass (SOMA) |",
        "|------|--------------|---------------|------|---------------|----------------|-------------|-------------|",
    ]

    for tr in result.tasks:
        lines.append(
            f"| {tr.task_name} | {tr.avg_baseline_tokens:.0f} | "
            f"{tr.avg_soma_tokens:.0f} | {tr.token_diff:+.1%} | "
            f"{tr.avg_baseline_retries:.1f} | {tr.avg_soma_retries:.1f} | "
            f"{tr.baseline_pass_rate:.0%} | {tr.soma_pass_rate:.0%} |"
        )

    lines.extend(["", "## Per-Task Details", ""])

    for tr in result.tasks:
        lines.extend([
            f"### {tr.task_name}",
            f"_{tr.description}_",
            "",
        ])

        for label, runs in [("Baseline", tr.baseline_runs), ("SOMA", tr.soma_runs)]:
            lines.append(f"**{label} runs:**")
            lines.append("")
            for i, run in enumerate(runs, 1):
                if run.error:
                    lines.append(f"- Run {i}: ERROR — {run.error}")
                    continue
                lines.append(
                    f"- Run {i}: {run.total_tokens} tokens, "
                    f"{run.total_retries} retries, "
                    f"{'PASS' if run.final_test_passed else 'FAIL'}, "
                    f"{run.total_duration:.1f}s"
                )
                for step in run.steps:
                    guidance = f" | guidance: {step.guidance_injected[:60]}" if step.guidance_injected else ""
                    lines.append(
                        f"  - Step {step.step_index + 1}: "
                        f"{'PASS' if step.test_passed else 'FAIL'} "
                        f"p={step.soma_pressure:.0%} {step.soma_mode}"
                        f"{guidance}"
                    )
            lines.append("")

    lines.extend(["---", "*Generated by `soma benchmark --live`*"])
    return "\n".join(lines)


def render_live_terminal(result: LiveBenchmarkResult) -> None:
    """Print live benchmark results using rich."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()
    except ImportError:
        print(generate_live_report(result))
        return

    console.print()
    console.print(Panel(
        f"[bold]SOMA Live Benchmark — Multi-Turn Agent[/bold]\n"
        f"[dim]Model: {result.model} | Runs: {result.runs_per_task} | "
        f"Cost: ${result.total_cost_estimate:.3f}[/dim]",
        border_style="magenta",
        width=72,
    ))

    table = Table(border_style="magenta", width=72)
    table.add_column("Task")
    table.add_column("Metric", style="dim")
    table.add_column("Baseline", justify="right")
    table.add_column("SOMA", justify="right")
    table.add_column("Verdict", justify="right")

    for tr in result.tasks:
        # Tokens
        diff = tr.token_diff
        color = "green" if diff > 0 else "red" if diff < -0.05 else "yellow"
        table.add_row(
            f"[bold]{tr.task_name}[/bold]", "tokens",
            f"{tr.avg_baseline_tokens:.0f}", f"{tr.avg_soma_tokens:.0f}",
            f"[{color}]{diff:+.1%}[/{color}]",
        )
        # Retries
        br, sr = tr.avg_baseline_retries, tr.avg_soma_retries
        color = "green" if sr < br else "red" if sr > br else "yellow"
        table.add_row(
            "", "retries",
            f"{br:.1f}", f"{sr:.1f}",
            f"[{color}]{sr - br:+.1f}[/{color}]" if br != sr else "same",
        )
        # Pass rate
        table.add_row(
            "", "pass rate",
            f"{tr.baseline_pass_rate:.0%}", f"{tr.soma_pass_rate:.0%}",
            "",
        )

    console.print(table)
    console.print()
