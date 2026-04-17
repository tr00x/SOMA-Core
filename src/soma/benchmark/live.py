"""Live benchmark — real LLM multi-turn sessions with SOMA vs without.

Runs coding tasks through real Anthropic API. Each task has 8-15 steps
with deliberate error injection to trigger retries and test SOMA's
ability to guide the agent through failure cascades.

Key design:
- Steps include WRONG test expectations that force the LLM to retry
- Each step feeds error output back to the LLM as next prompt
- SOMA records every action, builds pressure, injects guidance
- Reflex mode blocks repeated identical attempts
- Comparison: baseline (no SOMA) vs SOMA guidance vs SOMA reflexes

Requires: ANTHROPIC_API_KEY environment variable.
"""

from __future__ import annotations

import datetime
import os
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import soma as soma_mod
from soma.types import Action
from soma.reflexes import evaluate as reflex_evaluate
from soma.benchmark.tasks import TASKS as ALL_TASKS


# ------------------------------------------------------------------
# Legacy task definitions removed — now in soma.benchmark.tasks
# Original 3 tasks preserved there alongside 7 new tasks (10 total).
# ------------------------------------------------------------------

# Re-export for backward compatibility
TASKS = ALL_TASKS


# Task definitions live in soma.benchmark.tasks (10 tasks total).
# TASKS re-exported above for backward compatibility.


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class StepResult:
    step_index: int
    prompt_preview: str
    response_preview: str
    input_tokens: int
    output_tokens: int
    test_passed: bool
    test_output: str
    duration_seconds: float
    soma_pressure: float
    soma_mode: str
    guidance_injected: str
    reflex_blocked: bool = False


@dataclass
class LiveRunResult:
    task_name: str
    soma_enabled: bool
    reflex_enabled: bool = False
    steps: list[StepResult] = field(default_factory=list)
    total_tokens: int = 0
    total_duration: float = 0.0
    final_test_passed: bool = False
    total_retries: int = 0
    total_reflex_blocks: int = 0
    error: str | None = None


@dataclass
class LiveTaskResult:
    task_name: str
    description: str
    baseline_runs: list[LiveRunResult] = field(default_factory=list)
    soma_runs: list[LiveRunResult] = field(default_factory=list)
    reflex_runs: list[LiveRunResult] = field(default_factory=list)

    def _avg(self, runs: list[LiveRunResult], attr: str) -> float:
        good = [r for r in runs if not r.error]
        return statistics.mean(getattr(r, attr) for r in good) if good else 0

    @property
    def avg_baseline_tokens(self): return self._avg(self.baseline_runs, "total_tokens")
    @property
    def avg_soma_tokens(self): return self._avg(self.soma_runs, "total_tokens")
    @property
    def avg_reflex_tokens(self): return self._avg(self.reflex_runs, "total_tokens")
    @property
    def avg_baseline_retries(self): return self._avg(self.baseline_runs, "total_retries")
    @property
    def avg_soma_retries(self): return self._avg(self.soma_runs, "total_retries")
    @property
    def avg_reflex_retries(self): return self._avg(self.reflex_runs, "total_retries")
    @property
    def avg_reflex_blocks(self): return self._avg(self.reflex_runs, "total_reflex_blocks")

    def _pass_rate(self, runs):
        good = [r for r in runs if not r.error]
        return sum(1 for r in good if r.final_test_passed) / len(good) if good else 0

    @property
    def baseline_pass_rate(self): return self._pass_rate(self.baseline_runs)
    @property
    def soma_pass_rate(self): return self._pass_rate(self.soma_runs)
    @property
    def reflex_pass_rate(self): return self._pass_rate(self.reflex_runs)


@dataclass
class LiveBenchmarkResult:
    tasks: list[LiveTaskResult] = field(default_factory=list)
    model: str = ""
    runs_per_task: int = 3
    timestamp: str = ""
    total_cost_estimate: float = 0.0


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_code(text: str) -> str:
    """Extract Python code from markdown code blocks."""
    if "```python" in text:
        parts = text.split("```python")
        if len(parts) > 1:
            return parts[1].split("```")[0].strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) > 1:
            code = parts[1].lstrip("\n")
            return code.split("```")[0].strip()
    return text.strip()


def _run_test(cmd: str, file_path: str) -> tuple[bool, str]:
    """Run test command, return (passed, output)."""
    cmd = cmd.replace("{file}", file_path)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output[:500]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)[:500]


def _build_guidance(engine, agent_id: str, action_log: list[dict] | None = None, current_step: dict | None = None) -> str:
    """Build SOMA guidance from engine state using contextual guidance.

    Uses pattern-based contextual guidance (ContextualGuidance) that cites
    specific actions and suggests concrete next steps, instead of abstract
    pressure-based messages.
    """
    try:
        from soma.contextual_guidance import ContextualGuidance

        snap = engine.get_snapshot(agent_id)
        vitals = snap.get("vitals", {})
        if hasattr(vitals, "__dict__") and not isinstance(vitals, dict):
            vitals = {k: getattr(vitals, k, 0) for k in ("uncertainty", "drift", "error_rate", "token_usage")}

        budget_health = 1.0
        try:
            budget_health = engine.get_budget_health()
        except Exception:
            pass

        cg = ContextualGuidance()
        msg = cg.evaluate(
            action_log=action_log or [],
            current_tool=current_step.get("tool_name", "Edit") if current_step else "Edit",
            current_input=current_step or {},
            vitals=vitals,
            budget_health=budget_health,
            action_number=snap.get("action_count", 0),
        )
        if msg:
            return msg.message

        # Fallback: if contextual guidance didn't fire but mode > OBSERVE,
        # return a minimal pressure indicator
        pressure = snap.get("pressure", 0.0)
        mode = snap.get("mode")
        mode_name = mode.name if hasattr(mode, "name") else str(mode)
        if mode_name != "OBSERVE":
            return f"[SOMA {mode_name} p={pressure:.0%}]"

        return ""
    except Exception:
        return ""


# ------------------------------------------------------------------
# Multi-turn runner
# ------------------------------------------------------------------


def _run_multi_turn(
    task: dict,
    soma_enabled: bool,
    reflex_enabled: bool,
    model: str,
) -> LiveRunResult:
    """Run a multi-turn agent loop.

    When soma_enabled=True, uses soma.wrap() for deep guidance injection.
    Guidance is injected directly into messages by the wrapped client,
    not manually prepended to prompts.
    """
    import anthropic

    engine = None
    wrapped_client = None
    if soma_enabled:
        engine = soma_mod.quickstart()
        engine.register_agent("live-bench")
        # Reduce grace period from 10 to 3 so SOMA activates during the task
        agent_state = engine._agents.get("live-bench")
        if agent_state:
            agent_state.baseline.min_samples = 3

    raw_client = anthropic.Anthropic()

    if soma_enabled:
        # Deep injection: wrap() injects contextual guidance into messages
        from soma.wrap import wrap
        wrapped_client = wrap(
            raw_client,
            engine=engine,
            agent_id="live-bench",
            guidance=True,
            auto_export=False,
        )
        client = wrapped_client
    else:
        client = raw_client

    steps_results: list[StepResult] = []
    messages: list[dict] = []
    total_tokens = 0
    total_retries = 0
    total_reflex_blocks = 0
    last_test_passed = False
    action_log: list[dict] = []
    bash_history: list[str] = []

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        tmp_file = f.name

    try:
        for step_idx, step in enumerate(task["steps"]):
            t0 = time.monotonic()

            # With soma.wrap(), guidance is injected automatically into messages
            # No manual _build_guidance() needed — the wrapped client handles it
            guidance_text = ""
            if engine and soma_enabled and wrapped_client:
                # Check what guidance would fire (for logging only)
                guidance_text = _build_guidance(engine, "live-bench", action_log=action_log)

            user_prompt = step.prompt
            messages.append({"role": "user", "content": user_prompt})

            # Check reflex before calling LLM (simulates PreToolUse)
            reflex_blocked = False
            if reflex_enabled and engine and step_idx > 0:
                rr = reflex_evaluate(
                    tool_name="Edit",
                    tool_input={"file_path": tmp_file},
                    action_log=action_log[-20:],
                    pressure=engine.get_snapshot("live-bench").get("pressure", 0),
                    config={},
                    bash_history=bash_history[-10:],
                )
                if not rr.allow:
                    reflex_blocked = True
                    total_reflex_blocks += 1
                    # Inject block message into conversation instead of calling LLM
                    block_msg = rr.block_message or "Action blocked by SOMA reflex"
                    messages[-1] = {"role": "user", "content": f"[SOMA REFLEX BLOCKED previous action]\n{block_msg}\n\n{user_prompt}"}

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
                    reflex_enabled=reflex_enabled,
                    error=str(e),
                )

            messages.append({"role": "assistant", "content": response_text})
            total_tokens += input_tokens + output_tokens

            # Extract code and write
            code = _extract_code(response_text)
            Path(tmp_file).write_text(code)

            # Run test
            test_passed, test_output = _run_test(step.test_cmd, tmp_file)

            # Override with injected error if present
            if step.inject_error and test_passed:
                test_passed = False
                test_output = step.inject_error

            if not test_passed:
                total_retries += 1
                # Feed error back as next user message
                if step_idx < len(task["steps"]) - 1:
                    # Error gets picked up by next step's prompt
                    pass
            last_test_passed = test_passed

            # Record in SOMA engine
            pressure = 0.0
            mode_name = "NONE"
            if engine:
                result = engine.record_action(
                    "live-bench",
                    Action(
                        tool_name="Edit",
                        output_text=test_output[:200] if not test_passed else "tests passed",
                        token_count=input_tokens + output_tokens,
                        error=not test_passed,
                    ),
                )
                pressure = result.pressure
                mode_name = result.mode.name
                action_entry = {
                    "tool": "Edit", "error": not test_passed,
                    "file": tmp_file, "ts": time.time(),
                }
                action_log.append(action_entry)
                # Feed wrapped client's action_log for contextual guidance
                if wrapped_client is not None:
                    wrapped_client._action_log.append(action_entry)
                    if len(wrapped_client._action_log) > 20:
                        wrapped_client._action_log = wrapped_client._action_log[-20:]

            elapsed = time.monotonic() - t0

            steps_results.append(StepResult(
                step_index=step_idx,
                prompt_preview=step.prompt[:80],
                response_preview=response_text[:150],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                test_passed=test_passed,
                test_output=test_output[:200],
                duration_seconds=elapsed,
                soma_pressure=pressure,
                soma_mode=mode_name,
                guidance_injected=guidance_text,
                reflex_blocked=reflex_blocked,
            ))

    finally:
        Path(tmp_file).unlink(missing_ok=True)

    return LiveRunResult(
        task_name=task["name"],
        soma_enabled=soma_enabled,
        reflex_enabled=reflex_enabled,
        steps=steps_results,
        total_tokens=total_tokens,
        total_duration=sum(s.duration_seconds for s in steps_results),
        final_test_passed=last_test_passed,
        total_retries=total_retries,
        total_reflex_blocks=total_reflex_blocks,
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def run_live_benchmark(
    runs_per_task: int = 3,
    model: str = "claude-haiku-4-5-20251001",
    tasks: list[dict] | None = None,
) -> LiveBenchmarkResult:
    """Run live benchmark: baseline vs SOMA guidance vs SOMA reflexes.

    Each task runs 3 ways: no SOMA, SOMA guidance, SOMA reflexes.
    """
    if "ANTHROPIC_API_KEY" not in os.environ:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    task_defs = tasks or TASKS
    task_results: list[LiveTaskResult] = []
    total_tokens = 0

    for task in task_defs:
        tr = LiveTaskResult(task_name=task["name"], description=task["description"])

        for _ in range(runs_per_task):
            # Baseline (no SOMA)
            r = _run_multi_turn(task, soma_enabled=False, reflex_enabled=False, model=model)
            tr.baseline_runs.append(r)
            total_tokens += r.total_tokens

            # SOMA guidance only
            r = _run_multi_turn(task, soma_enabled=True, reflex_enabled=False, model=model)
            tr.soma_runs.append(r)
            total_tokens += r.total_tokens

            # SOMA reflexes
            r = _run_multi_turn(task, soma_enabled=True, reflex_enabled=True, model=model)
            tr.reflex_runs.append(r)
            total_tokens += r.total_tokens

        task_results.append(tr)

    est_cost = total_tokens * 0.003 / 1000

    return LiveBenchmarkResult(
        tasks=task_results,
        model=model,
        runs_per_task=runs_per_task,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        total_cost_estimate=est_cost,
    )


# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------


def generate_live_report(result: LiveBenchmarkResult) -> str:
    lines = [
        "# SOMA Live Benchmark — Real LLM Results",
        "",
        f"> **Model:** {result.model}",
        f"> **Runs per task:** {result.runs_per_task}",
        f"> **Generated:** {result.timestamp}",
        f"> **Cost:** ${result.total_cost_estimate:.2f}",
        "",
        "## Summary",
        "",
        "| Task | Mode | Tokens | Retries | Pass Rate | Reflex Blocks |",
        "|------|------|--------|---------|-----------|---------------|",
    ]

    for tr in result.tasks:
        lines.append(f"| {tr.task_name} | baseline | {tr.avg_baseline_tokens:.0f} | {tr.avg_baseline_retries:.1f} | {tr.baseline_pass_rate:.0%} | — |")
        lines.append(f"| | guidance | {tr.avg_soma_tokens:.0f} | {tr.avg_soma_retries:.1f} | {tr.soma_pass_rate:.0%} | — |")
        lines.append(f"| | **reflex** | {tr.avg_reflex_tokens:.0f} | {tr.avg_reflex_retries:.1f} | {tr.reflex_pass_rate:.0%} | {tr.avg_reflex_blocks:.1f} |")

    lines.extend(["", "## Per-Task Details", ""])

    for tr in result.tasks:
        lines.extend([f"### {tr.task_name}", f"_{tr.description}_", ""])

        for label, runs in [("Baseline", tr.baseline_runs), ("Guidance", tr.soma_runs), ("Reflex", tr.reflex_runs)]:
            lines.append(f"**{label}:**")
            for i, run in enumerate(runs, 1):
                if run.error:
                    lines.append(f"- Run {i}: ERROR — {run.error[:100]}")
                    continue
                blocks = f", {run.total_reflex_blocks} blocks" if run.total_reflex_blocks else ""
                lines.append(
                    f"- Run {i}: {run.total_tokens}tok, {run.total_retries} retries, "
                    f"{'PASS' if run.final_test_passed else 'FAIL'}, {run.total_duration:.0f}s{blocks}"
                )
                for s in run.steps:
                    g = f" | {s.guidance_injected[:50]}" if s.guidance_injected else ""
                    b = " [BLOCKED]" if s.reflex_blocked else ""
                    lines.append(f"  - Step {s.step_index+1}: {'OK' if s.test_passed else 'FAIL'} p={s.soma_pressure:.0%} {s.soma_mode}{b}{g}")
            lines.append("")

    lines.extend(["---", f"*Generated by `soma benchmark --live` | {result.timestamp}*"])
    return "\n".join(lines)


def render_live_terminal(result: LiveBenchmarkResult) -> None:
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
        f"[bold]SOMA Live Benchmark[/bold]\n"
        f"[dim]{result.model} | {result.runs_per_task} runs | ${result.total_cost_estimate:.2f}[/dim]",
        border_style="magenta", width=80,
    ))

    table = Table(border_style="magenta", width=80)
    table.add_column("Task")
    table.add_column("Mode", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Retries", justify="right")
    table.add_column("Pass", justify="right")
    table.add_column("Blocks", justify="right")

    for tr in result.tasks:
        table.add_row(f"[bold]{tr.task_name}[/bold]", "baseline", f"{tr.avg_baseline_tokens:.0f}", f"{tr.avg_baseline_retries:.1f}", f"{tr.baseline_pass_rate:.0%}", "—")
        table.add_row("", "guidance", f"{tr.avg_soma_tokens:.0f}", f"{tr.avg_soma_retries:.1f}", f"{tr.soma_pass_rate:.0%}", "—")
        table.add_row("", "[bold magenta]reflex[/bold magenta]", f"{tr.avg_reflex_tokens:.0f}", f"{tr.avg_reflex_retries:.1f}", f"{tr.reflex_pass_rate:.0%}", f"{tr.avg_reflex_blocks:.1f}")

    console.print(table)
    console.print()
