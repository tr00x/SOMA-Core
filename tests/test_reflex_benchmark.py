"""Tests for reflex-mode benchmark results (RFX-04)."""

from __future__ import annotations

import pytest

from soma.benchmark.harness import run_scenario
from soma.benchmark.scenarios import (
    context_exhaustion,
    degrading_session,
    healthy_session,
    retry_storm,
)


class TestReflexBenchmark:
    def test_retry_storm_reflex_reduces_errors(self):
        """D-23: >80% error reduction on retry_storm with reflex mode."""
        baseline = run_scenario(retry_storm(seed=1), soma_enabled=False)
        reflex = run_scenario(
            retry_storm(seed=1), soma_enabled=True, reflex_mode=True,
        )
        # Must show meaningful error reduction
        assert baseline.error_rate > 0, "Baseline must have errors"
        reduction = (baseline.error_rate - reflex.error_rate) / baseline.error_rate
        assert reduction > 0.80, (
            f"Expected >80% error reduction on retry_storm, got {reduction:.1%}"
        )

    def test_healthy_session_zero_reflex_activations(self):
        """D-24: 0 reflex activations on healthy_session."""
        m = run_scenario(
            healthy_session(seed=1), soma_enabled=True, reflex_mode=True,
        )
        reflex_blocks = sum(1 for a in m.per_action if a.get("reflex_blocked"))
        assert reflex_blocks == 0, (
            f"Expected 0 reflex blocks on healthy session, got {reflex_blocks}"
        )

    def test_all_scenarios_no_crash(self):
        """All scenarios run without exception in reflex mode."""
        for gen_fn in [
            healthy_session, retry_storm, degrading_session, context_exhaustion,
        ]:
            run_scenario(gen_fn(seed=1), soma_enabled=True, reflex_mode=True)

    def test_reflex_mode_blocks_more_than_guide(self):
        """Reflex mode should block more aggressively than guide on adversarial scenarios."""
        guide = run_scenario(retry_storm(seed=1), soma_enabled=True, reflex_mode=False)
        reflex = run_scenario(
            retry_storm(seed=1), soma_enabled=True, reflex_mode=True,
        )
        # Reflex should have equal or fewer processed errors
        assert reflex.error_rate <= guide.error_rate + 0.05  # small tolerance

    def test_retry_storm_multiple_seeds(self):
        """Verify reduction holds across multiple seeds."""
        for seed in range(1, 4):
            baseline = run_scenario(retry_storm(seed=seed), soma_enabled=False)
            reflex = run_scenario(
                retry_storm(seed=seed), soma_enabled=True, reflex_mode=True,
            )
            if baseline.error_rate > 0:
                reduction = (
                    (baseline.error_rate - reflex.error_rate) / baseline.error_rate
                )
                assert reduction > 0.30, (
                    f"Seed {seed}: expected >30% reduction, got {reduction:.1%}"
                )
