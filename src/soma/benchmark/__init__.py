"""SOMA Benchmark — A/B harness for measuring SOMA's impact on agent behavior."""

from __future__ import annotations

from soma.benchmark.metrics import (
    BenchmarkMetrics,
    BenchmarkResult,
    ScenarioResult,
    ScenarioAction,
    ActionMetric,
)
from soma.benchmark.harness import run_benchmark, run_scenario, run_multi_agent_scenario
from soma.benchmark.report import generate_markdown, render_terminal
from soma.benchmark.tasks import TaskStep, TASKS, get_task_by_name
from soma.benchmark.stats import (
    StatResult,
    ABVerdict,
    compare_paired,
    compare_proportions,
    bootstrap_ci,
    compute_verdict,
    HAS_SCIPY,
)

__all__ = [
    "run_benchmark",
    "run_scenario",
    "run_multi_agent_scenario",
    "BenchmarkResult",
    "ScenarioResult",
    "BenchmarkMetrics",
    "ScenarioAction",
    "ActionMetric",
    "generate_markdown",
    "render_terminal",
    "TaskStep",
    "TASKS",
    "get_task_by_name",
    "StatResult",
    "ABVerdict",
    "compare_paired",
    "compare_proportions",
    "bootstrap_ci",
    "compute_verdict",
    "HAS_SCIPY",
]
