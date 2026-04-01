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
]
