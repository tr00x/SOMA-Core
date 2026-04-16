"""Tests for soma.benchmark.stats — statistical analysis for A/B benchmarks."""

from __future__ import annotations

import pytest

from soma.benchmark.stats import (
    StatResult,
    ABVerdict,
    compare_paired,
    compare_proportions,
    bootstrap_ci,
    compute_verdict,
    HAS_SCIPY,
    _cohens_d,
    _effect_label,
)


# ------------------------------------------------------------------
# Effect size helpers
# ------------------------------------------------------------------


class TestEffectLabel:
    def test_negligible(self) -> None:
        assert _effect_label(0.1) == "negligible"
        assert _effect_label(-0.1) == "negligible"

    def test_small(self) -> None:
        assert _effect_label(0.3) == "small"

    def test_medium(self) -> None:
        assert _effect_label(0.6) == "medium"

    def test_large(self) -> None:
        assert _effect_label(1.2) == "large"


class TestCohensD:
    def test_zero_difference(self) -> None:
        a = [1.0, 2.0, 3.0]
        assert _cohens_d(a, a) == 0.0

    def test_positive_difference(self) -> None:
        a = [10.0, 20.0, 30.0]
        b = [1.0, 2.0, 3.0]
        d = _cohens_d(a, b)
        assert d > 0

    def test_single_value(self) -> None:
        # Single pair — stdev is 0
        d = _cohens_d([5.0], [3.0])
        assert d == 0.0  # Returns 0.0 for n<2


# ------------------------------------------------------------------
# compare_paired
# ------------------------------------------------------------------


class TestComparePaired:
    def test_too_few_samples(self) -> None:
        result = compare_paired([1.0, 2.0], [3.0, 4.0])
        assert isinstance(result, StatResult)
        assert result.p_value == 1.0  # inconclusive
        assert not result.significant
        assert result.n == 2

    def test_identical_samples(self) -> None:
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = compare_paired(vals, vals)
        assert isinstance(result, StatResult)
        assert result.p_value >= 0.05  # No difference
        assert not result.significant

    def test_clearly_different(self) -> None:
        # SOMA much better (lower values = better)
        soma = [10.0, 12.0, 11.0, 9.0, 13.0, 10.0, 11.0, 12.0, 10.0, 11.0]
        base = [50.0, 48.0, 52.0, 49.0, 51.0, 50.0, 47.0, 53.0, 50.0, 49.0]
        result = compare_paired(soma, base)
        assert result.significant
        assert result.n == 10

    def test_direction_soma_higher(self) -> None:
        # compare_paired(soma, base): positive effect = soma > base
        # "soma_better" means soma values are HIGHER than baseline
        soma = [50.0, 60.0, 40.0, 55.0, 65.0, 45.0]
        base = [5.0, 6.0, 4.0, 5.0, 6.0, 5.0]
        result = compare_paired(soma, base)
        assert result.direction == "soma_better"

    def test_direction_baseline_higher(self) -> None:
        # Baseline values higher → "baseline_better"
        soma = [5.0, 6.0, 4.0, 5.0, 6.0, 5.0]
        base = [50.0, 60.0, 40.0, 55.0, 65.0, 45.0]
        result = compare_paired(soma, base)
        assert result.direction == "baseline_better"


# ------------------------------------------------------------------
# compare_proportions
# ------------------------------------------------------------------


class TestCompareProportions:
    def test_equal_rates(self) -> None:
        result = compare_proportions(5, 10, 5, 10)
        assert isinstance(result, StatResult)
        assert not result.significant

    def test_very_different_rates(self) -> None:
        result = compare_proportions(9, 10, 1, 10)
        assert isinstance(result, StatResult)
        # 90% vs 10% should be significant or near it


# ------------------------------------------------------------------
# bootstrap_ci
# ------------------------------------------------------------------


class TestBootstrapCI:
    def test_returns_tuple(self) -> None:
        lo, hi = bootstrap_ci([1.0, 2.0, 3.0, 4.0, 5.0])
        assert isinstance(lo, float)
        assert isinstance(hi, float)
        assert lo <= hi

    def test_contains_mean(self) -> None:
        import statistics
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        lo, hi = bootstrap_ci(vals)
        m = statistics.mean(vals)
        assert lo <= m <= hi

    def test_narrow_for_constant(self) -> None:
        lo, hi = bootstrap_ci([5.0, 5.0, 5.0, 5.0, 5.0])
        assert lo == 5.0
        assert hi == 5.0


# ------------------------------------------------------------------
# compute_verdict
# ------------------------------------------------------------------


class TestComputeVerdict:
    def test_no_difference(self) -> None:
        metrics = {
            "tokens": StatResult(
                test_name="t-test", statistic=0.5, p_value=0.6,
                effect_size=0.1, effect_label="negligible", n=10,
                significant=False,
            ),
            "retries": StatResult(
                test_name="t-test", statistic=0.3, p_value=0.7,
                effect_size=0.05, effect_label="negligible", n=10,
                significant=False,
            ),
        }
        verdict = compute_verdict(metrics)
        assert isinstance(verdict, ABVerdict)
        assert verdict.overall == "no_difference"
        assert verdict.recommendation == "kill"

    def test_soma_wins(self) -> None:
        # Positive effect_size = soma_better (ab_report flips lower-is-better)
        metrics = {
            "tokens": StatResult(
                test_name="t-test", statistic=3.0, p_value=0.01,
                effect_size=0.8, effect_label="large", n=10,
                significant=True,
            ),
            "retries": StatResult(
                test_name="t-test", statistic=2.5, p_value=0.02,
                effect_size=0.6, effect_label="medium", n=10,
                significant=True,
            ),
        }
        verdict = compute_verdict(metrics)
        assert verdict.overall == "soma_wins"
        assert verdict.recommendation == "continue"

    def test_soma_hurts(self) -> None:
        # Negative effect_size = baseline_better → soma hurts
        metrics = {
            "tokens": StatResult(
                test_name="t-test", statistic=-3.0, p_value=0.01,
                effect_size=-0.8, effect_label="large", n=10,
                significant=True,
            ),
        }
        verdict = compute_verdict(metrics)
        assert verdict.overall == "soma_hurts"
        assert verdict.recommendation == "kill"
