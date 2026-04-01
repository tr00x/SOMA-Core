---
phase: 13-config-validation
verified: 2026-03-31T12:00:00Z
status: gaps_found
score: 11/12 must-haves verified
re_verification: false
gaps:
  - truth: "Percentile-based threshold tuner produces lower false-positive thresholds from benchmark data"
    status: partial
    reason: "ActionMetric dataclass lacks an 'error' field, but threshold_tuner.py looks for actions[j].get('error', False) in per_action dicts. When fed real benchmark data, every GUIDE+ event is classified as a false positive, causing the tuner to return inflated thresholds (0.56 vs expected ~0.25-0.35). The fix is adding `error: bool = False` to ActionMetric, or changing the tuner to check `error_rate > 0`."
    artifacts:
      - path: "src/soma/benchmark/metrics.py"
        issue: "ActionMetric dataclass missing 'error: bool' field — only has 'error_rate: float'"
      - path: "src/soma/threshold_tuner.py"
        issue: "Looks for 'error' key in per_action entries via .get('error', False) which returns False for all real ActionMetric dicts"
    missing:
      - "Add `error: bool = False` field to ActionMetric in src/soma/benchmark/metrics.py"
      - "OR change threshold_tuner.py to use `error_rate > 0` instead of `error`"
human_verification:
  - test: "Run `uv run python -m soma benchmark --runs 2` and inspect terminal output"
    expected: "Rich colored tables appear with per-scenario A/B comparison, progress displayed during run"
    why_human: "Visual quality and formatting readability cannot be verified programmatically"
  - test: "Open docs/BENCHMARK.md and read it as a project stakeholder"
    expected: "Document reads as compelling proof: clear summary table, per-scenario breakdowns with real numbers, auto-generated footer"
    why_human: "Narrative quality and overall readability require human judgment"
  - test: "Run `uv run python -m soma benchmark --runs 1 --tune-thresholds` (after fixing error field gap)"
    expected: "Threshold output appears after benchmark and shows thresholds closer to 0.25 range, not 0.56"
    why_human: "After gap fix, actual threshold values should be reviewed to confirm they make intuitive sense"
---

# Phase 13: Intelligence Verification Report

**Phase Goal:** Benchmark-first proof that SOMA improves agent behavior, then cross-session learning
**Verified:** 2026-03-31
**Status:** gaps_found — 1 wiring gap in threshold tuner data format
**Re-verification:** No — initial verification

## Goal Achievement

The phase goal has two components:
1. Benchmark-first proof — VERIFIED (harness, 5 scenarios, CLI, docs/BENCHMARK.md all exist and work)
2. Cross-session learning — VERIFIED (session_store, cross_session, threshold_tuner, phase_drift exist with tests)

One wiring gap exists in the threshold tuner's integration with real benchmark data.

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Benchmark harness runs identical action sequences with SOMA enabled vs disabled | VERIFIED | `harness.py:run_scenario()` with `soma_enabled` flag; `run_benchmark(1)` returns 5 scenarios, 12.4% overall error reduction |
| 2  | At least 3 scenarios exist: healthy, degrading, multi-agent coordination | VERIFIED | 5 scenarios: healthy (50 actions), degrading (80), multi_agent (60x2), retry_storm (40), context_exhaustion (100) |
| 3  | Each scenario runs 5x with different random seeds for statistical variation | VERIFIED | `run_benchmark()` iterates `seed in range(1, runs_per_scenario+1)`; `different_seeds_produce_different_sequences` test passes |
| 4  | Per-run metrics include errors, retries, tokens, mode transitions, per-action deep data | VERIFIED | `BenchmarkMetrics` collects all; `test_per_action_metrics_collected` and `test_mode_transitions_captured` pass |
| 5  | BenchmarkResult objects contain A/B comparison with error_reduction, retry_reduction, token_savings | VERIFIED | `ScenarioResult` has all three fields computed via `_safe_reduction()`; retry_storm shows 55.6% error reduction |
| 6  | Session history is stored as append-only JSON Lines at ~/.soma/sessions/ | VERIFIED | `session_store.py:append_session()` writes to `{base_dir}/.soma/sessions/history.jsonl`; 8 tests pass |
| 7  | Cross-session predictor finds similar past pressure trajectories and predicts escalation | VERIFIED | `CrossSessionPredictor` extends `PressurePredictor`, uses cosine similarity > 0.8, 60/40 blend; 10 tests pass |
| 8  | Percentile-based threshold tuner produces lower false-positive thresholds from benchmark data | PARTIAL | Module exists with correct algorithm; **but** when fed real benchmark data (per_action from ActionMetric), the `error` field is missing so all GUIDE+ events are falsely classified as false positives, inflating thresholds to 0.56 instead of ~0.25 |
| 9  | Phase-weighted drift reduces drift score when tool usage matches expected task phase | VERIFIED | `compute_phase_aware_drift()` with `PHASE_WEIGHTS` for 4 phases; max 50% reduction; `test_returns_lower_drift_when_tools_match_phase` confirms |
| 10 | `soma benchmark` CLI command runs all scenarios and prints rich terminal output | VERIFIED | `_cmd_benchmark()` wired in `dispatch["benchmark"]`; `run_benchmark()` called; `render_terminal()` called |
| 11 | Benchmark produces docs/BENCHMARK.md with results table auto-generated from data | VERIFIED | File exists (86 lines), contains real numbers (13.7% error reduction, 55.6% retry storm), auto-generated footer present |
| 12 | Results include error reduction, retry reduction, token savings per scenario | VERIFIED | All 5 scenarios in BENCHMARK.md show per-metric tables; degrading session: -13.2% errors, -26.5% tokens; retry storm: -55.6% |

**Score:** 11/12 truths verified (1 partial)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/soma/benchmark/__init__.py` | Public API: run_benchmark, BenchmarkResult, ScenarioResult | VERIFIED | Exports 9 symbols including generate_markdown, render_terminal |
| `src/soma/benchmark/harness.py` | A/B harness with run_scenario(), run_benchmark() | VERIFIED | 392 lines, fully implemented A/B logic with guidance_responsive skipping |
| `src/soma/benchmark/scenarios.py` | 5 scenario definitions, 30-100 actions each | VERIFIED | 5 scenarios: 50/80/60+60/40/100 actions |
| `src/soma/benchmark/metrics.py` | BenchmarkMetrics, ScenarioResult, BenchmarkResult, ScenarioAction, ActionMetric | VERIFIED | All 5 frozen dataclasses present |
| `src/soma/session_store.py` | SessionRecord, append_session(), load_sessions() | VERIFIED | Fully implemented with JSON Lines and rotation |
| `src/soma/cross_session.py` | CrossSessionPredictor extending PressurePredictor | VERIFIED | Class extends PressurePredictor, cosine matching, to_dict/from_dict |
| `src/soma/threshold_tuner.py` | compute_optimal_thresholds() | VERIFIED (partial wiring) | Algorithm correct, but data format mismatch with real per_action dicts |
| `src/soma/phase_drift.py` | PHASE_WEIGHTS, compute_phase_aware_drift() | VERIFIED | 4 phases, calls compute_drift from vitals |
| `src/soma/benchmark/report.py` | generate_markdown(), render_terminal() | VERIFIED | Both functions fully implemented with rich output |
| `src/soma/cli/main.py` | soma benchmark subcommand | VERIFIED | `_cmd_benchmark` handler with 6 flags, wired in dispatch dict |
| `docs/BENCHMARK.md` | Auto-generated benchmark results | VERIFIED | 86 lines with real numbers, summary table, 5 scenarios, auto-footer |
| `tests/test_benchmark.py` | Tests for harness, scenarios, metrics | VERIFIED | 16 tests, all pass |
| `tests/test_session_store.py` | Session store tests | VERIFIED | 8 tests |
| `tests/test_cross_session_predictor.py` | Cross-session predictor tests | VERIFIED | 10 tests |
| `tests/test_threshold_tuner.py` | Threshold tuner tests | VERIFIED (isolated) | 7 tests pass using manually-constructed dicts with `error` field, not real ActionMetric output |
| `tests/test_task_phase_drift.py` | Phase drift tests | VERIFIED | 6 tests |
| `tests/test_benchmark_report.py` | Report formatting tests | VERIFIED | 7 tests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `harness.py` | `engine.py` | `engine.record_action()` | WIRED | Pattern found 2x; result vitals accessed directly |
| `harness.py` | `scenarios.py` | `ScenarioAction` | WIRED | Imported and used in type annotation + action iteration |
| `harness.py` | `metrics.py` | `BenchmarkMetrics` | WIRED | Found 9x; return type and construction |
| `cross_session.py` | `predictor.py` | `class CrossSessionPredictor(PressurePredictor)` | WIRED | Direct inheritance, `super().predict()` called |
| `cross_session.py` | `session_store.py` | `load_sessions` | WIRED | Imported and called in `load_history()` |
| `threshold_tuner.py` | `types.py` | `ResponseMode` | WIRED | Imported (used for `_TRIGGERED_MODES` reference) |
| `phase_drift.py` | `vitals.py` | `compute_drift` | WIRED | Imported and called as first step |
| `cli/main.py` | `harness.py` | `run_benchmark` | WIRED | Imported inside handler, called with `args.runs` |
| `report.py` | `metrics.py` | `BenchmarkResult` | WIRED | Imported, used as parameter type |
| `cli/main.py` | `report.py` | `render_terminal`, `generate_markdown` | WIRED | Both imported and called |
| `cli/main.py` | `threshold_tuner.py` | `compute_optimal_thresholds` | PARTIAL | Called correctly, but `per_action` dicts fed to it lack `error` field ActionMetric doesn't provide |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PRED-01 | 13-01, 13-03 | Context-aware degradation score (context window + half-life + error trend) | SATISFIED | Benchmark harness proves SOMA reduces errors 13.7% overall; degrading_session 76.9% detection precision; retry_storm 55.6% reduction |
| TUNE-01 | 13-02, 13-03 | ML-optimized thresholds per agent type, per task type | PARTIAL | Threshold tuner algorithm correct (percentile-based); tuner incorrectly classifies all GUIDE+ events as false positives when fed real ActionMetric data (missing `error` field) |
| TASK-01 | 13-02 | Semantic task-aware monitoring (drift from goal, not just from stats) | SATISFIED | `compute_phase_aware_drift()` reduces drift up to 50% when tools match expected phase pattern for research/implement/test/debug |
| ANOM-01 | 13-02 | Cross-session anomaly prediction (5-10 actions ahead) | SATISFIED | `CrossSessionPredictor` extends PressurePredictor with 60/40 blend; finds similar past trajectories via cosine > 0.8 sliding window |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/soma/benchmark/metrics.py` | 25-38 | `ActionMetric` lacks `error: bool` field required by `threshold_tuner.py` | Warning | Threshold tuner produces wrong thresholds (0.56 vs ~0.25) when called from CLI `--tune-thresholds`; does not crash |
| `docs/BENCHMARK.md` | 37 | degrading_session retry_rate shows +23.1% (SOMA increased retries) | Info | Artifact of guidance_responsive skipping: actions skipped by SOMA aren't counted, altering denominator; not a real regression |
| `docs/BENCHMARK.md` | 45-83 | 3 of 5 scenarios show 0% improvement (healthy, multi_agent, context_exhaustion) | Info | Honest results; SOMA only helps when there are correctable errors and guidance_responsive actions are present |

### Human Verification Required

#### 1. Rich Terminal Output Quality

**Test:** Run `uv run python -m soma benchmark --runs 2`
**Expected:** Rich colored tables appear with per-scenario A/B comparison data, progress shown during run, green highlighting for improvements > 10%
**Why human:** Visual layout and color coding readability require direct observation

#### 2. BENCHMARK.md Narrative Quality

**Test:** Open `docs/BENCHMARK.md` and read it as a potential SOMA adopter
**Expected:** Document reads as compelling evidence — clear summary table, per-scenario breakdowns with real numbers, 76.9% precision stat for degrading session, honest about 0% improvement scenarios
**Why human:** Narrative coherence and persuasiveness require human judgment

#### 3. Plan 02 Modules Engine Integration (Out of Scope for Phase 13)

**Test:** Confirm that `session_store`, `cross_session`, `threshold_tuner`, `phase_drift` are intentionally standalone (not yet wired to engine pipeline)
**Expected:** These modules are "ready for integration" per the summaries; engine integration is deferred to a future phase
**Why human:** Design intent confirmation — are these modules supposed to be standalone libraries at this stage, or were engine integrations missed?

### Gaps Summary

One gap blocks full TUNE-01 satisfaction: the `ActionMetric` dataclass in `src/soma/benchmark/metrics.py` does not include an `error: bool` field, but `threshold_tuner.py` relies on that field to distinguish true positives from false positives in per_action data. When the CLI calls `compute_optimal_thresholds()` with real benchmark data (via `--tune-thresholds`), every GUIDE+ event is classified as a false positive, causing the tuner to raise the guide threshold to 0.56 (vs the default 0.25 and a reasonable tuned value of ~0.25-0.35).

The threshold tuner tests all pass because they construct per_action dicts with the `error` key explicitly, never using real `ActionMetric` output. The integration gap is invisible to unit tests.

Fix: Add `error: bool = False` to `ActionMetric` and populate it in `harness.py:_collect_metrics()` from `sa.error` for each processed action.

The remaining 11/12 truths are fully verified. The benchmark harness works correctly, produces real results (13.7% overall error reduction, 55.6% retry storm reduction, 76.9% degrading session detection precision), the CLI command works, and docs/BENCHMARK.md contains honest data. The cross-session predictor, phase-aware drift, and session store are all implemented and tested. The full test suite passes: 944 tests, 5 skipped.

---

*Verified: 2026-03-31*
*Verifier: Claude (gsd-verifier)*
