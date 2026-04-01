"""Benchmark harness — A/B engine runner with deep metric collection.

Stub created during Task 1 — implementation follows in Task 2.
"""

from __future__ import annotations

from soma.benchmark.metrics import BenchmarkMetrics, BenchmarkResult, ScenarioAction


def run_scenario(
    actions: list[ScenarioAction],
    soma_enabled: bool,
    agent_id: str = "benchmark-agent",
    budget: dict[str, float] | None = None,
) -> BenchmarkMetrics:
    raise NotImplementedError("Implemented in Task 2")


def run_multi_agent_scenario(
    agent_a_actions: list[ScenarioAction],
    agent_b_actions: list[ScenarioAction],
    soma_enabled: bool,
    budget: dict[str, float] | None = None,
) -> tuple[BenchmarkMetrics, BenchmarkMetrics]:
    raise NotImplementedError("Implemented in Task 2")


def run_benchmark(runs_per_scenario: int = 5) -> BenchmarkResult:
    raise NotImplementedError("Implemented in Task 2")
