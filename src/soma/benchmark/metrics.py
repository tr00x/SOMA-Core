"""Benchmark metric types — frozen dataclasses for A/B comparison results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ScenarioAction:
    """A single action in a benchmark scenario.

    ``guidance_responsive`` marks actions that the agent would skip if SOMA
    issues GUIDE-level (or higher) guidance.  This models real agent behavior
    where guidance causes the agent to choose a safer path.
    """

    tool_name: str
    output_text: str
    token_count: int = 100
    error: bool = False
    retried: bool = False
    guidance_responsive: bool = False


@dataclass(frozen=True, slots=True)
class ActionMetric:
    """Per-action deep metrics collected during a benchmark run."""

    action_index: int
    pressure: float
    uncertainty: float
    drift: float
    error_rate: float
    token_usage: float
    cost: float
    mode: str  # ResponseMode name
    guidance_issued: bool
    guidance_followed: bool  # True if guidance_responsive action was skipped


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    """Aggregated metrics from a single benchmark run (one scenario, one seed)."""

    total_errors: int
    error_rate: float
    total_retries: int
    retry_rate: float
    total_tokens: int
    duration_seconds: float
    total_actions: int
    mode_transitions: list[dict[str, object]] = field(default_factory=list)
    false_positives: int = 0
    true_positives: int = 0
    per_action: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """A/B comparison result for one scenario across multiple seeds."""

    scenario_name: str
    description: str
    soma_runs: list[BenchmarkMetrics] = field(default_factory=list)
    baseline_runs: list[BenchmarkMetrics] = field(default_factory=list)
    error_reduction: float = 0.0
    retry_reduction: float = 0.0
    token_savings: float = 0.0
    time_savings: float = 0.0


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Top-level result: all scenarios with overall averages."""

    scenarios: list[ScenarioResult] = field(default_factory=list)
    timestamp: str = ""
    runs_per_scenario: int = 5
    overall_error_reduction: float = 0.0
    overall_retry_reduction: float = 0.0
    overall_token_savings: float = 0.0
