"""A/B benchmark verdict report — honest, data-driven, no spin.

Generates the final A/B benchmark report from live benchmark results.
Uses statistical analysis to determine whether SOMA helps, hurts, or
makes no measurable difference.

Honesty rules enforced:
- Negative results are reported as "SOMA HURTS" in red.
- Both directions (improvements AND degradations) are always shown.
- Raw numbers accompany percentages.
- Kill criteria are prominently displayed.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict

from soma.benchmark.live import (
    LiveBenchmarkResult,
    LiveRunResult,
)
from soma.benchmark.stats import (
    ABVerdict,
    StatResult,
    bootstrap_ci,
    compare_paired,
    compare_proportions,
    compute_verdict,
)


# ------------------------------------------------------------------
# Analyze: extract paired metrics and run statistical tests
# ------------------------------------------------------------------


def _extract_paired_values(
    result: LiveBenchmarkResult,
) -> dict[str, list[float]]:
    """Extract paired per-run metric values across all tasks.

    Returns dict with keys like 'soma_tokens', 'base_tokens', etc.
    Pairs with errors on either side are excluded.
    """
    out: dict[str, list[float]] = {
        "soma_tokens": [],
        "base_tokens": [],
        "soma_retries": [],
        "base_retries": [],
        "soma_duration": [],
        "base_duration": [],
        "soma_passed": [],
        "base_passed": [],
    }
    for task in result.tasks:
        n_pairs = min(len(task.soma_runs), len(task.baseline_runs))
        for i in range(n_pairs):
            sr = task.soma_runs[i]
            br = task.baseline_runs[i]
            # Skip pairs where either run had an error — not a fair comparison
            if sr.error or br.error:
                continue
            out["soma_tokens"].append(float(sr.total_tokens))
            out["base_tokens"].append(float(br.total_tokens))
            out["soma_retries"].append(float(sr.total_retries))
            out["base_retries"].append(float(br.total_retries))
            out["soma_duration"].append(sr.total_duration)
            out["base_duration"].append(br.total_duration)
            out["soma_passed"].append(1.0 if sr.final_test_passed else 0.0)
            out["base_passed"].append(1.0 if br.final_test_passed else 0.0)
    return out


def analyze_ab_results(result: LiveBenchmarkResult) -> ABVerdict:
    """Extract paired metrics from LiveBenchmarkResult and run statistical tests.

    For each task, pairs SOMA runs vs baseline runs on:
    - total_tokens (lower is better for SOMA)
    - total_retries (lower is better for SOMA)
    - total_duration (lower is better for SOMA)
    - final_test_passed (higher is better for SOMA)

    Returns ABVerdict with all metric comparisons.
    """
    vals = _extract_paired_values(result)

    metric_results: dict[str, StatResult] = {}

    # Continuous metrics: lower is better for SOMA.
    # compare_paired returns positive effect_size when SOMA > baseline.
    # For lower-is-better, we flip the inputs so positive = SOMA is lower = good.
    for name, flip in [("tokens", True), ("retries", True), ("duration", True)]:
        soma_vals = vals[f"soma_{name}"]
        base_vals = vals[f"base_{name}"]
        n = min(len(soma_vals), len(base_vals))
        if n == 0:
            continue
        if flip:
            # Pass baseline as "soma" and soma as "baseline" so that
            # positive effect_size = baseline higher = SOMA wins
            metric_results[name] = compare_paired(
                base_vals[:n], soma_vals[:n], metric_name=name
            )
        else:
            metric_results[name] = compare_paired(
                soma_vals[:n], base_vals[:n], metric_name=name
            )

    # Binary metric: pass rate — higher is better for SOMA
    soma_pass = vals["soma_passed"]
    base_pass = vals["base_passed"]
    if soma_pass and base_pass:
        soma_successes = int(sum(soma_pass))
        base_successes = int(sum(base_pass))
        metric_results["pass_rate"] = compare_proportions(
            soma_successes=soma_successes,
            soma_total=len(soma_pass),
            baseline_successes=base_successes,
            baseline_total=len(base_pass),
            metric_name="pass_rate",
        )

    return compute_verdict(metric_results)


# ------------------------------------------------------------------
# Markdown report generation
# ------------------------------------------------------------------


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Compute mean and std dev, handling edge cases."""
    if not values:
        return 0.0, 0.0
    m = statistics.mean(values)
    s = statistics.stdev(values) if len(values) > 1 else 0.0
    return m, s


def _pct_change(soma_mean: float, base_mean: float) -> str:
    """Format percentage change.  Negative = SOMA is lower."""
    if base_mean == 0:
        return "N/A"
    pct = ((soma_mean - base_mean) / base_mean) * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def _verdict_emoji(overall: str) -> str:
    """Traffic light emoji for verdict."""
    if overall == "soma_hurts":
        return "\U0001f534"  # red circle
    if overall == "soma_wins":
        return "\U0001f7e2"  # green circle
    return "\U0001f7e1"  # yellow circle


def _verdict_label(overall: str) -> str:
    """Human-readable verdict label."""
    if overall == "soma_hurts":
        return "SOMA HURTS"
    if overall == "soma_wins":
        return "SOMA HELPS"
    return "NO SIGNIFICANT DIFFERENCE"


def _sig_mark(stat: StatResult) -> str:
    """Significance marker for tables."""
    if not stat.significant:
        return "\u2717"
    if stat.direction == "soma_better":
        return "\u2713"
    return "\u2713\u26a0"  # significant but hurts


def _fmt_ci(values: list[float], label: str = "") -> str:
    """Format bootstrap 95% CI."""
    if len(values) < 3:
        return ""
    lo, hi = bootstrap_ci(values, n_bootstrap=5_000, ci=0.95)
    if label == "tokens":
        return f"[{lo:,.0f}, {hi:,.0f}]"
    if label == "duration":
        return f"[{lo:.1f}s, {hi:.1f}s]"
    return f"[{lo:.2f}, {hi:.2f}]"


def generate_ab_report(result: LiveBenchmarkResult, verdict: ABVerdict) -> str:
    """Generate complete Markdown A/B benchmark report.

    Includes statistical tables, per-task breakdown, raw data,
    and methodology section.  Kill criteria displayed at bottom.
    """
    lines: list[str] = []
    _a = lines.append
    vals = _extract_paired_values(result)

    emoji = _verdict_emoji(verdict.overall)
    label = _verdict_label(verdict.overall)

    _a("# SOMA A/B Benchmark \u2014 Verdict\n")
    _a(
        f"> **Model:** {result.model} | **Tasks:** {len(result.tasks)} "
        f"| **Runs:** {result.runs_per_task} per task | "
        f"**Cost:** ${result.total_cost_estimate:.2f}  "
    )
    _a(f"> **Generated:** {result.timestamp}\n")

    # ---- Verdict ----
    _a(f"## {emoji} VERDICT: {label}\n")
    _a(f"{verdict.summary}\n")
    _a(f"**Recommendation:** {verdict.recommendation}  ")
    _a(f"**Confidence:** {verdict.confidence}  \n")

    # ---- Statistical Results Table ----
    _a("## Statistical Results\n")
    _a(
        "| Metric | SOMA (mean\u00b1std) | Baseline (mean\u00b1std) "
        "| \u0394 | p-value | Effect | 95% CI (SOMA) | Sig? |"
    )
    _a(
        "|--------|-----------------|--------------------"
        "|----|---------|--------|---------------|------|"
    )

    # Map metric names to value-dict keys
    _val_key = {
        "tokens": "tokens",
        "retries": "retries",
        "duration": "duration",
        "pass_rate": "passed",
    }

    for name in ("tokens", "retries", "duration", "pass_rate"):
        stat = verdict.metrics.get(name)
        if stat is None:
            continue

        vk = _val_key[name]
        soma_vals = vals.get(f"soma_{vk}", [])
        base_vals = vals.get(f"base_{vk}", [])

        if name == "pass_rate":
            s_rate = (sum(soma_vals) / len(soma_vals) * 100) if soma_vals else 0
            b_rate = (sum(base_vals) / len(base_vals) * 100) if base_vals else 0
            soma_str = f"{s_rate:.0f}%"
            base_str = f"{b_rate:.0f}%"
            delta = f"{s_rate - b_rate:+.0f}pp"
            ci_str = ""
        else:
            sm, ss = _mean_std(soma_vals)
            bm, bs = _mean_std(base_vals)
            if name == "tokens":
                soma_str = f"{sm:,.0f}\u00b1{ss:,.0f}"
                base_str = f"{bm:,.0f}\u00b1{bs:,.0f}"
            elif name == "duration":
                soma_str = f"{sm:.1f}s\u00b1{ss:.1f}s"
                base_str = f"{bm:.1f}s\u00b1{bs:.1f}s"
            else:
                soma_str = f"{sm:.1f}\u00b1{ss:.1f}"
                base_str = f"{bm:.1f}\u00b1{bs:.1f}"
            delta = _pct_change(sm, bm)
            ci_str = _fmt_ci(soma_vals, name)

        p_str = f"{stat.p_value:.3f}" if stat.p_value >= 0.001 else "<0.001"
        _a(
            f"| {name} | {soma_str} | {base_str} "
            f"| {delta} | {p_str} | {stat.effect_label} "
            f"| {ci_str} | {_sig_mark(stat)} |"
        )

    _a("")

    # ---- Effect Direction Summary ----
    _a("### Effect Direction Summary\n")
    for name in ("tokens", "retries", "duration", "pass_rate"):
        stat = verdict.metrics.get(name)
        if stat is None:
            continue
        if stat.significant:
            if stat.direction == "soma_better":
                _a(f"- **{name}**: SOMA is better (p={stat.p_value:.3f}, "
                   f"effect={stat.effect_label})")
            else:
                _a(f"- **{name}**: SOMA is WORSE (p={stat.p_value:.3f}, "
                   f"effect={stat.effect_label})")
        else:
            _a(f"- **{name}**: No significant difference (p={stat.p_value:.3f})")
    _a("")

    # ---- Per-Task Breakdown ----
    _a("## Per-Task Breakdown\n")

    for task in result.tasks:
        _a(f"### Task: {task.task_name}")
        _a(f"_{task.description}_\n")
        _a("| Run | Mode | Tokens | Retries | Duration | Pass | Reflex Blocks |")
        _a("|-----|------|--------|---------|----------|------|---------------|")

        all_runs: list[tuple[str, LiveRunResult]] = []
        for r in task.baseline_runs:
            all_runs.append(("Baseline", r))
        for r in task.soma_runs:
            all_runs.append(("SOMA", r))
        for r in task.reflex_runs:
            all_runs.append(("Reflex", r))

        for idx, (mode, run) in enumerate(all_runs, 1):
            if run.error:
                _a(f"| {idx} | {mode} | ERROR: {run.error[:40]} | - | - | - | - |")
                continue
            passed = "\u2713" if run.final_test_passed else "\u2717"
            _a(
                f"| {idx} | {mode} | {run.total_tokens:,} "
                f"| {run.total_retries} | {run.total_duration:.1f}s "
                f"| {passed} | {run.total_reflex_blocks} |"
            )

        # Per-task averages
        s_runs = [r for r in task.soma_runs if not r.error]
        b_runs = [r for r in task.baseline_runs if not r.error]
        if s_runs and b_runs:
            s_tok = statistics.mean(r.total_tokens for r in s_runs)
            b_tok = statistics.mean(r.total_tokens for r in b_runs)
            _a(f"\n_Avg tokens: SOMA {s_tok:,.0f} vs Baseline {b_tok:,.0f} "
               f"({_pct_change(s_tok, b_tok)})_")

        _a("")

    # ---- Raw Data ----
    _a("## Raw Data\n")
    _a("<details>")
    _a("<summary>Click to expand JSON (for reproducibility)</summary>\n")
    _a("```json")
    try:
        raw = asdict(result)
        _a(json.dumps(raw, indent=2, default=str))
    except Exception:
        _a('{"error": "Could not serialize result"}')
    _a("```\n")
    _a("</details>\n")

    # ---- Methodology ----
    _a("## Methodology\n")
    _a(f"- Each task ran **{result.runs_per_task}** times with SOMA enabled, "
       f"**{result.runs_per_task}** times without (baseline)")
    _a("- Same model, same prompts, same temperature")
    _a("- Tasks include deliberate error injection to trigger retries")
    _a("- Pairs with errors on either side excluded from statistical analysis")

    # Report which tests were used
    test_names = {s.test_name for s in verdict.metrics.values()}
    for tn in sorted(test_names):
        _a(f"- **Test used:** {tn}")

    _a("- **Significance threshold:** \u03b1 = 0.05 (two-sided)")
    _a("- **Effect size:** Cohen's d / rank-biserial for continuous; "
       "rate difference for binary")
    _a("- **Confidence intervals:** Bootstrap (5,000 resamples, percentile method)")
    n_tests = len(verdict.metrics)
    _a(f"- {n_tests} tests performed; no multiple-comparison correction applied "
       f"(Bonferroni-adjusted \u03b1 would be {0.05 / n_tests:.4f})"
       if n_tests > 0 else "")
    _a("")

    # ---- Kill Criteria ----
    _a("---\n")
    any_sig_positive = any(
        s.significant and s.direction == "soma_better"
        for s in verdict.metrics.values()
    )
    if any_sig_positive:
        _a("**Kill criteria: PASSED** \u2014 at least one metric shows "
           "p < 0.05 improvement.")
    else:
        _a("**Kill criteria: FAILED** \u2014 no metric shows p < 0.05 improvement. "
           "The project approach must be redesigned.")
    _a("")
    _a("*This report was generated automatically.  SOMA project kill criteria: "
       "if no metric shows p < 0.05 improvement, the project approach is "
       "considered failed.*")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Rich terminal output
# ------------------------------------------------------------------


def render_ab_terminal(
    result: LiveBenchmarkResult, verdict: ABVerdict
) -> None:
    """Rich terminal output of A/B verdict with color coding.

    Green: SOMA wins (p < 0.05, positive effect)
    Red: SOMA hurts (p < 0.05, negative effect)
    Yellow: Inconclusive (p >= 0.05)
    Bold: significant results
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        # Fallback: print markdown report
        print(generate_ab_report(result, verdict))
        return

    console = Console()
    vals = _extract_paired_values(result)

    # ---- Header Panel ----
    verdict_color = {
        "soma_wins": "green",
        "soma_hurts": "red",
        "no_difference": "yellow",
    }.get(verdict.overall, "white")

    header = Text()
    header.append("SOMA A/B Benchmark Verdict\n", style="bold white")
    header.append(
        f"Model: {result.model} | Tasks: {len(result.tasks)} | "
        f"Runs: {result.runs_per_task}/task | "
        f"Cost: ${result.total_cost_estimate:.2f}\n",
        style="dim",
    )
    header.append(f"\n{verdict.summary}\n", style=f"bold {verdict_color}")
    header.append("\nRecommendation: ", style="bold")
    header.append(verdict.recommendation)
    header.append("\nConfidence: ", style="bold")
    header.append(verdict.confidence, style=verdict_color)

    console.print(Panel(
        header,
        title="[bold]A/B Verdict[/bold]",
        border_style=verdict_color,
    ))

    # ---- Statistical Table ----
    table = Table(title="Statistical Results", show_lines=True)
    table.add_column("Metric", style="bold")
    table.add_column("SOMA", justify="right")
    table.add_column("Baseline", justify="right")
    table.add_column("\u0394", justify="right")
    table.add_column("p-value", justify="right")
    table.add_column("Effect", justify="center")
    table.add_column("Sig?", justify="center")

    _vk = {"tokens": "tokens", "retries": "retries",
           "duration": "duration", "pass_rate": "passed"}

    for name in ("tokens", "retries", "duration", "pass_rate"):
        stat = verdict.metrics.get(name)
        if stat is None:
            continue

        vk = _vk[name]
        soma_vals = vals.get(f"soma_{vk}", [])
        base_vals = vals.get(f"base_{vk}", [])

        if name == "pass_rate":
            s_rate = (sum(soma_vals) / len(soma_vals) * 100) if soma_vals else 0
            b_rate = (sum(base_vals) / len(base_vals) * 100) if base_vals else 0
            soma_str = f"{s_rate:.0f}%"
            base_str = f"{b_rate:.0f}%"
            delta = f"{s_rate - b_rate:+.0f}pp"
        else:
            sm, ss = _mean_std(soma_vals)
            bm, bs = _mean_std(base_vals)
            if name == "tokens":
                soma_str = f"{sm:,.0f}"
                base_str = f"{bm:,.0f}"
            elif name == "duration":
                soma_str = f"{sm:.1f}s"
                base_str = f"{bm:.1f}s"
            else:
                soma_str = f"{sm:.1f}"
                base_str = f"{bm:.1f}"
            delta = _pct_change(sm, bm)

        # Color coding: green = SOMA wins, red = SOMA hurts, yellow = inconclusive
        if stat.significant and stat.direction == "soma_better":
            row_style = "green"
            sig_str = "\u2713 WINS"
        elif stat.significant and stat.direction == "baseline_better":
            row_style = "red"
            sig_str = "\u2717 HURTS"
        else:
            row_style = "yellow"
            sig_str = "-"

        p_str = f"{stat.p_value:.3f}" if stat.p_value >= 0.001 else "<0.001"

        table.add_row(
            name,
            soma_str,
            base_str,
            delta,
            p_str,
            stat.effect_label,
            sig_str,
            style=row_style if stat.significant else "dim",
        )

    console.print(table)

    # ---- Per-Task Summary ----
    task_table = Table(title="Per-Task Summary", show_lines=True)
    task_table.add_column("Task", style="bold")
    task_table.add_column("SOMA Tokens (avg)", justify="right")
    task_table.add_column("Base Tokens (avg)", justify="right")
    task_table.add_column("SOMA Pass", justify="center")
    task_table.add_column("Base Pass", justify="center")
    task_table.add_column("SOMA Retries (avg)", justify="right")
    task_table.add_column("Base Retries (avg)", justify="right")

    for task in result.tasks:
        s_runs = [r for r in task.soma_runs if not r.error]
        b_runs = [r for r in task.baseline_runs if not r.error]

        s_tok = statistics.mean(r.total_tokens for r in s_runs) if s_runs else 0
        b_tok = statistics.mean(r.total_tokens for r in b_runs) if b_runs else 0
        s_pass = f"{sum(r.final_test_passed for r in s_runs)}/{len(s_runs)}"
        b_pass = f"{sum(r.final_test_passed for r in b_runs)}/{len(b_runs)}"
        s_ret = (
            statistics.mean(r.total_retries for r in s_runs) if s_runs else 0
        )
        b_ret = (
            statistics.mean(r.total_retries for r in b_runs) if b_runs else 0
        )

        # Color: green if SOMA uses fewer tokens, red if more
        style = ""
        if s_runs and b_runs:
            if s_tok < b_tok * 0.9:
                style = "green"
            elif s_tok > b_tok * 1.1:
                style = "red"

        task_table.add_row(
            task.task_name,
            f"{s_tok:,.0f}",
            f"{b_tok:,.0f}",
            s_pass,
            b_pass,
            f"{s_ret:.1f}",
            f"{b_ret:.1f}",
            style=style,
        )

    console.print(task_table)

    # ---- Kill Criteria ----
    console.print()
    any_sig_positive = any(
        s.significant and s.direction == "soma_better"
        for s in verdict.metrics.values()
    )
    if any_sig_positive:
        console.print(
            "[bold green]Kill criteria: PASSED[/bold green] "
            "\u2014 at least one metric shows significant improvement."
        )
    else:
        console.print(
            "[bold red]Kill criteria: FAILED[/bold red] "
            "\u2014 no metric shows p < 0.05 improvement. "
            "Project approach must be redesigned."
        )
    console.print()
