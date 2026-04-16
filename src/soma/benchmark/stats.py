"""Statistical analysis for A/B benchmark results.

Provides paired comparison tests, proportion tests, bootstrap confidence
intervals, and an overall verdict engine.  Works with or without scipy —
pure-Python fallbacks cover every code path.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable

# ------------------------------------------------------------------
# Optional scipy — graceful fallback to pure-Python implementations
# ------------------------------------------------------------------

try:
    from scipy import stats as sp_stats

    HAS_SCIPY = True
except ImportError:
    sp_stats = None  # type: ignore[assignment]
    HAS_SCIPY = False


# ------------------------------------------------------------------
# Effect-size labeling (Cohen's conventions)
# ------------------------------------------------------------------


def _effect_label(d: float) -> str:
    """Classify absolute effect size *d* into a human-readable label."""
    ad = abs(d)
    if ad < 0.2:
        return "negligible"
    if ad < 0.5:
        return "small"
    if ad < 0.8:
        return "medium"
    return "large"


# ------------------------------------------------------------------
# Pure-Python statistical helpers
# ------------------------------------------------------------------


def _cohens_d(a: list[float], b: list[float]) -> float:
    """Paired Cohen's d — mean difference / SD of differences."""
    diffs = [x - y for x, y in zip(a, b)]
    if len(diffs) < 2:
        return 0.0
    md = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0:
        return 0.0 if md == 0 else float("inf") * (1 if md > 0 else -1)
    return md / sd


def _paired_ttest(a: list[float], b: list[float]) -> tuple[float, float]:
    """Return (t-statistic, two-sided p-value) for paired samples.

    Uses scipy when available; otherwise a pure-Python t-distribution
    approximation via the regularized incomplete beta function.
    """
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    md = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0:
        return (0.0, 1.0)
    t = md / (sd / math.sqrt(n))
    df = n - 1

    if HAS_SCIPY:
        p = float(sp_stats.t.sf(abs(t), df) * 2)
        return (t, p)

    p = _t_two_sided_p(t, df)
    return (t, p)


def _t_two_sided_p(t: float, df: int) -> float:
    """Two-sided p-value from t-distribution (pure Python).

    Uses the relationship between the t-distribution CDF and the
    regularized incomplete beta function.
    """
    x = df / (df + t * t)
    p_one_tail = 0.5 * _regularized_beta(x, df / 2.0, 0.5)
    return min(2.0 * p_one_tail, 1.0)


def _regularized_beta(
    x: float, a: float, b: float, max_iter: int = 200,
) -> float:
    """Regularized incomplete beta function I_x(a, b) via continued fraction.

    Lentz's modified algorithm — converges quickly for typical inputs.
    """
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    lnbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lnbeta) / a

    # Lentz's algorithm
    d = 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d

    for m in range(1, max_iter + 1):
        # Even step
        num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + num
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        f *= d * c

        # Odd step
        num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + num
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        f *= delta

        if abs(delta - 1.0) < 1e-10:
            break

    return front * f


def _wilcoxon_test(
    a: list[float], b: list[float],
) -> tuple[float, float, float]:
    """Wilcoxon signed-rank test.  Returns (statistic, p_value, rank_biserial).

    Uses scipy when available.  Fallback uses a normal approximation
    (valid for n > ~10) with continuity correction.
    """
    if HAS_SCIPY:
        result = sp_stats.wilcoxon(a, b, alternative="two-sided")
        stat = float(result.statistic)
        p = float(result.pvalue)
        diffs = [x - y for x, y in zip(a, b)]
        nonzero = [d for d in diffs if d != 0]
        nn = len(nonzero)
        if nn > 0:
            r = 1.0 - (2.0 * stat) / (nn * (nn + 1) / 2.0)
        else:
            r = 0.0
        return (stat, p, r)

    # Pure-Python Wilcoxon signed-rank
    diffs = [x - y for x, y in zip(a, b)]
    nonzero = [(abs(d), d) for d in diffs if d != 0]
    n = len(nonzero)
    if n == 0:
        return (0.0, 1.0, 0.0)

    # Rank absolute differences (handle ties via average rank)
    nonzero.sort(key=lambda t: t[0])
    ranks: list[float] = []
    i = 0
    while i < n:
        j = i
        while j < n and nonzero[j][0] == nonzero[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for _ in range(i, j):
            ranks.append(avg_rank)
        i = j

    w_plus = sum(r for r, (_, d) in zip(ranks, nonzero) if d > 0)
    w_minus = sum(r for r, (_, d) in zip(ranks, nonzero) if d < 0)
    w = min(w_plus, w_minus)

    # Rank-biserial correlation
    r_rb = 1.0 - (2.0 * w) / (n * (n + 1) / 2.0)

    # Normal approximation with continuity correction
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return (w, 1.0, r_rb)
    z = (abs(w - mu) - 0.5) / sigma
    p = 2.0 * _norm_sf(abs(z))
    return (w, min(p, 1.0), r_rb)


def _norm_sf(z: float) -> float:
    """Survival function (1 - CDF) for the standard normal distribution."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def _shapiro_wilk_normal(values: list[float]) -> bool:
    """Quick normality check.  Returns True if data looks normal.

    Uses scipy Shapiro-Wilk when available.  Fallback uses a simple
    skewness heuristic — sufficient for the small-n gating decision.
    """
    if len(values) < 3:
        return True

    if HAS_SCIPY:
        _, p = sp_stats.shapiro(values)
        return p > 0.05

    n = len(values)
    mu = statistics.mean(values)
    sd = statistics.stdev(values)
    if sd == 0:
        return True
    skew = sum((x - mu) ** 3 for x in values) / (n * sd**3)
    return abs(skew) < 1.0


# ------------------------------------------------------------------
# Proportion tests (Fisher's exact)
# ------------------------------------------------------------------


def _fisher_exact(
    a: int, b: int, c: int, d: int,
) -> tuple[float, float]:
    """Fisher's exact test for 2x2 table [[a,b],[c,d]].

    Returns (odds_ratio, two_sided_p).
    """
    if HAS_SCIPY:
        result = sp_stats.fisher_exact([[a, b], [c, d]], alternative="two-sided")
        return (float(result.statistic), float(result.pvalue))  # type: ignore[union-attr]

    # Pure-Python via hypergeometric pmf
    n = a + b + c + d
    r1 = a + b
    c1 = a + c

    def _log_choose(nn: int, kk: int) -> float:
        if kk < 0 or kk > nn:
            return -float("inf")
        return (
            math.lgamma(nn + 1)
            - math.lgamma(kk + 1)
            - math.lgamma(nn - kk + 1)
        )

    def _pmf(x: int) -> float:
        return math.exp(
            _log_choose(r1, x)
            + _log_choose(n - r1, c1 - x)
            - _log_choose(n, c1)
        )

    p_obs = _pmf(a)
    lo = max(0, c1 - (n - r1))
    hi = min(r1, c1)
    p_val = sum(_pmf(x) for x in range(lo, hi + 1) if _pmf(x) <= p_obs + 1e-12)

    if b == 0 or c == 0:
        odds = float("inf") if (b == 0 and a > 0) or (c == 0 and d > 0) else 0.0
    else:
        odds = (a * d) / (b * c)

    return (odds, min(p_val, 1.0))


# ------------------------------------------------------------------
# StatResult
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StatResult:
    """Result of a statistical test."""

    test_name: str
    statistic: float
    p_value: float
    effect_size: float
    effect_label: str
    n: int
    significant: bool
    alpha: float = 0.05

    @property
    def direction(self) -> str:
        """'soma_better', 'baseline_better', or 'no_difference'."""
        if not self.significant:
            return "no_difference"
        if self.effect_size > 0:
            return "soma_better"
        if self.effect_size < 0:
            return "baseline_better"
        return "no_difference"


# ------------------------------------------------------------------
# Core comparison functions
# ------------------------------------------------------------------


def compare_paired(
    soma_values: list[float],
    baseline_values: list[float],
    metric_name: str = "",
    alpha: float = 0.05,
) -> StatResult:
    """Compare paired A/B measurements using the appropriate test.

    - If n >= 20: Wilcoxon signed-rank test
    - If n < 20: paired t-test (with Shapiro-Wilk normality check)
    - If n < 5: return inconclusive (too few samples)

    Effect size: rank-biserial correlation for Wilcoxon, Cohen's d for t-test.

    Convention: positive effect_size means SOMA values are *higher* than
    baseline.  Callers should interpret "higher is better" or "lower is better"
    according to their metric semantics.
    """
    if len(soma_values) != len(baseline_values):
        raise ValueError(
            f"Paired samples must have equal length: "
            f"got {len(soma_values)} vs {len(baseline_values)}"
        )

    n = len(soma_values)

    # Too few samples
    if n < 5:
        d = _cohens_d(soma_values, baseline_values) if n >= 2 else 0.0
        return StatResult(
            test_name="inconclusive (n < 5)",
            statistic=0.0,
            p_value=1.0,
            effect_size=d,
            effect_label=_effect_label(d),
            n=n,
            significant=False,
            alpha=alpha,
        )

    # Large sample — Wilcoxon signed-rank (non-parametric)
    if n >= 20:
        stat, p, r_rb = _wilcoxon_test(soma_values, baseline_values)
        return StatResult(
            test_name="Wilcoxon signed-rank",
            statistic=stat,
            p_value=p,
            effect_size=r_rb,
            effect_label=_effect_label(r_rb),
            n=n,
            significant=p < alpha,
            alpha=alpha,
        )

    # Small sample — paired t-test (check normality first)
    diffs = [s - b for s, b in zip(soma_values, baseline_values)]
    normal = _shapiro_wilk_normal(diffs)

    if normal:
        t_stat, p = _paired_ttest(soma_values, baseline_values)
        d = _cohens_d(soma_values, baseline_values)
        return StatResult(
            test_name="paired t-test",
            statistic=t_stat,
            p_value=p,
            effect_size=d,
            effect_label=_effect_label(d),
            n=n,
            significant=p < alpha,
            alpha=alpha,
        )

    # Non-normal small sample — Wilcoxon fallback
    stat, p, r_rb = _wilcoxon_test(soma_values, baseline_values)
    return StatResult(
        test_name="Wilcoxon signed-rank (non-normal)",
        statistic=stat,
        p_value=p,
        effect_size=r_rb,
        effect_label=_effect_label(r_rb),
        n=n,
        significant=p < alpha,
        alpha=alpha,
    )


def compare_proportions(
    soma_successes: int,
    soma_total: int,
    baseline_successes: int,
    baseline_total: int,
    metric_name: str = "",
    alpha: float = 0.05,
) -> StatResult:
    """Compare success rates using Fisher's exact test.

    Effect size is the difference in proportions (SOMA rate - baseline rate).
    """
    soma_failures = soma_total - soma_successes
    baseline_failures = baseline_total - baseline_successes

    n = soma_total + baseline_total
    if n == 0:
        return StatResult(
            test_name="inconclusive (n = 0)",
            statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            effect_label="negligible",
            n=0,
            significant=False,
            alpha=alpha,
        )

    _, p = _fisher_exact(
        soma_successes, soma_failures,
        baseline_successes, baseline_failures,
    )

    p_soma = soma_successes / soma_total if soma_total > 0 else 0.0
    p_base = baseline_successes / baseline_total if baseline_total > 0 else 0.0
    diff = p_soma - p_base

    return StatResult(
        test_name="Fisher's exact test",
        statistic=diff,
        p_value=p,
        effect_size=diff,
        effect_label=_effect_label(diff),
        n=n,
        significant=p < alpha,
        alpha=alpha,
    )


# ------------------------------------------------------------------
# Bootstrap confidence intervals
# ------------------------------------------------------------------


def bootstrap_ci(
    values: list[float],
    stat_func: Callable[..., float] = statistics.mean,
    n_bootstrap: int = 10_000,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Bootstrap confidence interval for any statistic.

    Returns (lower, upper) bounds at the given confidence level.
    Uses the percentile method with a fixed seed for reproducibility.
    """
    if not values:
        return (0.0, 0.0)

    n = len(values)
    rng = random.Random(42)
    replicates: list[float] = []

    for _ in range(n_bootstrap):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        replicates.append(stat_func(sample))

    replicates.sort()
    tail = (1.0 - ci) / 2.0
    lo_idx = max(0, int(math.floor(tail * n_bootstrap)))
    hi_idx = min(n_bootstrap - 1, int(math.ceil((1.0 - tail) * n_bootstrap)) - 1)
    return (replicates[lo_idx], replicates[hi_idx])


# ------------------------------------------------------------------
# Verdict engine
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ABVerdict:
    """Overall A/B benchmark verdict."""

    metrics: dict[str, StatResult]
    overall: str        # "soma_wins", "no_difference", "soma_hurts"
    confidence: str     # "high", "medium", "low"
    summary: str        # Human-readable 1-2 sentence summary
    recommendation: str  # "continue", "investigate", "kill"


def compute_verdict(
    metric_results: dict[str, StatResult],
) -> ABVerdict:
    """Compute overall verdict from multiple metric comparisons.

    Rules:
    - If ANY metric shows baseline_better with p < alpha: "soma_hurts"
    - If >= 2 metrics show soma_better with p < alpha: "soma_wins"
    - If 1 metric shows soma_better: needs investigation
    - If no significant differences: "no_difference" -> "kill"

    Confidence:
    - "high" if min(n) >= 20 and any significant effect sizes are medium+
    - "medium" if min(n) >= 10
    - "low" if min(n) < 10
    """
    if not metric_results:
        return ABVerdict(
            metrics={},
            overall="no_difference",
            confidence="low",
            summary="No metrics to evaluate.",
            recommendation="kill",
        )

    soma_better: list[str] = []
    soma_worse: list[str] = []

    for name, result in metric_results.items():
        if result.significant:
            direction = result.direction
            if direction == "soma_better":
                soma_better.append(name)
            elif direction == "baseline_better":
                soma_worse.append(name)

    # Overall verdict
    if soma_worse:
        overall = "soma_hurts"
        recommendation = "kill"
    elif len(soma_better) >= 2:
        overall = "soma_wins"
        recommendation = "continue"
    elif len(soma_better) == 1:
        overall = "no_difference"
        recommendation = "investigate"
    else:
        overall = "no_difference"
        recommendation = "kill"

    # Confidence level
    ns = [r.n for r in metric_results.values()]
    min_n = min(ns) if ns else 0
    has_medium_plus = any(
        r.effect_label in ("medium", "large")
        for r in metric_results.values()
        if r.significant
    )

    if min_n >= 20 and has_medium_plus:
        confidence = "high"
    elif min_n >= 10:
        confidence = "medium"
    else:
        confidence = "low"

    # Human-readable summary
    total = len(metric_results)
    parts: list[str] = []

    if overall == "soma_wins":
        parts.append(
            f"SOMA shows significant improvement in {len(soma_better)}/{total}"
            f" metrics ({', '.join(soma_better)})."
        )
    elif overall == "soma_hurts":
        parts.append(
            f"SOMA shows significant HARM in {len(soma_worse)}/{total}"
            f" metrics ({', '.join(soma_worse)})."
        )
    else:
        if soma_better:
            parts.append(
                f"Only 1/{total} metrics shows improvement ({soma_better[0]});"
                f" not enough evidence."
            )
        else:
            parts.append(
                f"No significant differences found across {total} metrics."
            )

    if confidence == "low":
        parts.append("Sample size is small — results are unreliable.")

    summary = " ".join(parts)

    return ABVerdict(
        metrics=metric_results,
        overall=overall,
        confidence=confidence,
        summary=summary,
        recommendation=recommendation,
    )
