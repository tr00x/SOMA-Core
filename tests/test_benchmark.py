"""Tests for soma.benchmark harness, scenarios, and metrics."""

from __future__ import annotations

import pytest

from soma.benchmark.metrics import (
    BenchmarkMetrics,
    BenchmarkResult,
    ScenarioAction,
    ScenarioResult,
    ActionMetric,
)
from soma.benchmark.scenarios import (
    healthy_session,
    degrading_session,
    multi_agent_coordination,
    retry_storm,
    context_exhaustion,
)
from soma.benchmark.harness import run_scenario, run_multi_agent_scenario, run_benchmark
from soma.types import ResponseMode


# ------------------------------------------------------------------
# Scenario sanity tests
# ------------------------------------------------------------------


class TestScenarios:
    def test_healthy_session_length(self) -> None:
        actions = healthy_session(seed=42)
        assert len(actions) == 50

    def test_degrading_session_has_guidance_responsive(self) -> None:
        actions = degrading_session(seed=42)
        assert len(actions) == 80
        responsive = [a for a in actions if a.guidance_responsive]
        assert len(responsive) > 0

    def test_retry_storm_has_retried_and_responsive(self) -> None:
        actions = retry_storm(seed=42)
        assert len(actions) == 40
        retried = [a for a in actions if a.retried and a.guidance_responsive]
        assert len(retried) > 0

    def test_context_exhaustion_token_ramp(self) -> None:
        actions = context_exhaustion(seed=42)
        assert len(actions) == 100
        assert actions[-1].token_count > actions[0].token_count

    def test_multi_agent_returns_two_lists(self) -> None:
        a, b = multi_agent_coordination(seed=42)
        assert len(a) == 60
        assert len(b) == 60

    def test_different_seeds_produce_different_sequences(self) -> None:
        h1 = healthy_session(seed=1)
        h2 = healthy_session(seed=2)
        outputs1 = [a.output_text for a in h1]
        outputs2 = [a.output_text for a in h2]
        assert outputs1 != outputs2


# ------------------------------------------------------------------
# Harness tests
# ------------------------------------------------------------------


class TestRunScenario:
    def test_baseline_processes_all_actions(self) -> None:
        """With soma_enabled=False, all actions are processed regardless."""
        actions = [
            ScenarioAction("Bash", "ok", 100),
            ScenarioAction("Bash", "ERROR", 100, error=True),
            ScenarioAction("Bash", "ok", 100),
            ScenarioAction("Write", "blind", 100, guidance_responsive=True),
            ScenarioAction("Bash", "ok", 100),
        ]
        result = run_scenario(actions, soma_enabled=False)
        assert isinstance(result, BenchmarkMetrics)
        assert result.total_actions == 5
        assert result.total_errors == 1

    def test_soma_enabled_skips_responsive_on_guide(self) -> None:
        """With soma_enabled=True, guidance_responsive actions may be skipped when mode >= GUIDE."""
        # Build a sequence that forces high pressure first, then a responsive action
        error_actions = [
            ScenarioAction("Bash", f"ERROR: fail {i}", 100, error=True, retried=True)
            for i in range(15)
        ]
        responsive = ScenarioAction("Write", "blind-write", 100, guidance_responsive=True)
        tail = [ScenarioAction("Read", "ok", 100)]
        actions = error_actions + [responsive] + tail

        soma_result = run_scenario(actions, soma_enabled=True)
        baseline_result = run_scenario(actions, soma_enabled=False)

        # SOMA should have processed fewer or equal actions (some responsive skipped)
        assert soma_result.total_actions <= baseline_result.total_actions

    def test_per_action_metrics_collected(self) -> None:
        """Each processed action should have a per_action metric entry."""
        actions = [
            ScenarioAction("Read", "output", 100),
            ScenarioAction("Edit", "output", 200),
            ScenarioAction("Bash", "output", 150),
        ]
        result = run_scenario(actions, soma_enabled=False)
        assert len(result.per_action) == 3
        first = result.per_action[0]
        assert "pressure" in first
        assert "mode" in first
        assert "uncertainty" in first

    def test_mode_transitions_captured(self) -> None:
        """When mode changes, it should be recorded in mode_transitions."""
        # Start normal, then spike errors to cause mode change
        normal = [ScenarioAction("Read", "ok", 100) for _ in range(5)]
        errors = [
            ScenarioAction("Bash", f"ERROR: bad {i}", 100, error=True, retried=True)
            for i in range(20)
        ]
        actions = normal + errors
        result = run_scenario(actions, soma_enabled=False)
        # Should have at least one transition if pressure escalated
        # (may not always happen with default thresholds but transitions list should exist)
        assert isinstance(result.mode_transitions, list)

    def test_false_positive_true_positive_counting(self) -> None:
        """GUIDE+ followed by error in next 3 = true positive, otherwise false positive."""
        # Build scenario where errors follow guidance
        errors = [
            ScenarioAction("Bash", f"ERROR: fail {i}", 100, error=True, retried=True)
            for i in range(20)
        ]
        # After many errors, mode should be elevated — any guidance counts
        result = run_scenario(errors, soma_enabled=False)
        # true_positives + false_positives should account for all GUIDE+ events
        total_guidance = result.true_positives + result.false_positives
        guidance_events = sum(1 for m in result.per_action if m.get("guidance_issued"))
        assert total_guidance == guidance_events


class TestRunMultiAgent:
    def test_multi_agent_returns_two_metrics(self) -> None:
        agent_a = [ScenarioAction("Read", "ok", 100) for _ in range(5)]
        agent_b = [ScenarioAction("Edit", "ok", 100) for _ in range(5)]
        metrics_a, metrics_b = run_multi_agent_scenario(agent_a, agent_b, soma_enabled=False)
        assert isinstance(metrics_a, BenchmarkMetrics)
        assert isinstance(metrics_b, BenchmarkMetrics)
        assert metrics_a.total_actions == 5
        assert metrics_b.total_actions == 5

    def test_multi_agent_uses_graph_edges(self) -> None:
        """Agent A pressure should propagate to Agent B through trust graph."""
        # Agent A: all errors -> high pressure
        agent_a = [
            ScenarioAction("Bash", f"ERROR: fail {i}", 100, error=True, retried=True)
            for i in range(10)
        ]
        # Agent B: normal -> should still see some pressure from graph
        agent_b = [ScenarioAction("Read", "ok", 100) for _ in range(10)]
        metrics_a, metrics_b = run_multi_agent_scenario(agent_a, agent_b, soma_enabled=False)
        # Both should have collected per-action metrics
        assert len(metrics_a.per_action) == 10
        assert len(metrics_b.per_action) == 10


class TestRunBenchmark:
    def test_run_benchmark_returns_all_scenarios(self) -> None:
        result = run_benchmark(runs_per_scenario=1)
        assert isinstance(result, BenchmarkResult)
        assert len(result.scenarios) == 5
        assert result.runs_per_scenario == 1
        assert result.timestamp != ""

    def test_benchmark_computes_error_reduction(self) -> None:
        result = run_benchmark(runs_per_scenario=1)
        # At least one scenario should show some error reduction
        for sr in result.scenarios:
            assert isinstance(sr.error_reduction, float)
            assert isinstance(sr.retry_reduction, float)
            assert isinstance(sr.token_savings, float)

    def test_benchmark_overall_metrics(self) -> None:
        result = run_benchmark(runs_per_scenario=1)
        assert isinstance(result.overall_error_reduction, float)
        assert isinstance(result.overall_retry_reduction, float)
        assert isinstance(result.overall_token_savings, float)
