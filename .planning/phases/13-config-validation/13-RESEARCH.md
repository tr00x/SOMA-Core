# Phase 13: Intelligence (Benchmark-First) - Research

**Researched:** 2026-03-31
**Domain:** Benchmark harness, cross-session learning, threshold tuning, anomaly prediction
**Confidence:** HIGH

## Summary

Phase 13 is about proving SOMA works (benchmark-first) then making it smarter (cross-session learning). The codebase is exceptionally well-prepared: `SOMAEngine.record_action()` is a deterministic pipeline (given same inputs, produces same outputs) which makes A/B benchmarking straightforward. The existing `test_stress.py` (16 scenarios), `demo_session.py` (scripted degradation), and `SessionRecorder` (JSON export/load) provide ready-made infrastructure.

The core technical challenge is the benchmark harness design: running identical action sequences through the engine with SOMA guidance enabled vs disabled, collecting deep per-action metrics. The engine already has no side effects beyond `~/.soma/` state files, so isolation is trivial (just don't pass `auto_export=True`). Cross-session learning (D-12, D-13, D-14) builds naturally on top of existing `FingerprintEngine`, `PressurePredictor`, and `LearningEngine` which already have `to_dict()`/`from_dict()` serialization.

**Primary recommendation:** Build the benchmark harness first as a standalone module (`src/soma/benchmark/`), wire it into CLI as `soma benchmark`, then use benchmark data to drive threshold tuning and cross-session predictor improvements. The benchmark module should be entirely self-contained with no impact on the core engine.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Build a benchmark harness that runs identical tasks with SOMA enabled vs disabled
- D-02: Tasks are Python scripts that simulate realistic agent sessions (not toy examples) -- file editing, debugging, multi-step implementations
- D-03: Metrics collected per run: total errors, retries, tool calls, tokens used, time, drift, final code quality (pass/fail tests)
- D-04: Results stored as JSON, rendered as rich terminal tables AND markdown for README
- D-05: Minimum 3 scenarios: healthy session, degrading session, multi-agent coordination
- D-06: Each scenario runs 5x with and 5x without SOMA for statistical significance
- D-07: Benchmark is a CLI command: `soma benchmark` -- anyone can reproduce
- D-08: Primary metric: error reduction rate (errors with SOMA / errors without)
- D-09: Secondary metrics: retry reduction, token savings, time to completion
- D-10: Tertiary: mode transition accuracy (did GUIDE fire at the right time?), false positive rate
- D-11: Deep engine metrics per action: pressure, all 5 vitals, mode, guidance issued, was guidance followed
- D-12: Session history in append-only JSON Lines at `~/.soma/sessions/` -- one file per session, lightweight
- D-13: Threshold tuning uses benchmark data -- statistical optimization (percentile-based), not ML models. Keep it simple, explainable, no sklearn dependency
- D-14: Anomaly prediction extends existing PressurePredictor with cross-session pattern matching -- "last 3 sessions showed this pattern before escalation"
- D-15: No LLM calls for monitoring -- too expensive, too slow, creates dependency
- D-16: Use existing behavior vectors weighted by detected task phase (exploring/implementing/testing/debugging) -- phase detection from tool usage patterns already in context.py
- D-17: Benchmark results go in `docs/BENCHMARK.md` -- auto-generated, always reproducible
- D-18: Summary table for README showing before/after with real numbers
- D-19: Rich terminal output during benchmark run -- live progress, per-scenario results

### Claude's Discretion
- Exact scenario scripts and action sequences
- JSON schema for session history
- Statistical methods for threshold optimization
- Terminal output formatting details

### Deferred Ideas (OUT OF SCOPE)
- Web dashboard visualization of benchmark results -- Phase 14
- Community benchmarks / collective learning (BEN-02) -- Phase 15
- Open research datasets from benchmark data (SAF-02) -- Phase 15
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PRED-01 | Context-aware degradation score (context window + half-life + error trend) | Existing `halflife.py` has `predict_success_rate()`, engine already computes `context_usage` and `predicted_success_rate`. Benchmark validates these predictions against actual outcomes. Cross-session predictor extends `PressurePredictor` with session history lookback. |
| TUNE-01 | ML-optimized thresholds per agent type, per task type | Benchmark data provides ground truth for threshold optimization. Percentile-based statistical tuning (D-13) uses collected pressure distributions to find optimal guide/warn/block thresholds. No sklearn -- pure statistics. |
| TASK-01 | Semantic task-aware monitoring (drift from goal, not just from stats) | Existing `TaskTracker` already detects phases (research/implement/test/debug). Enhancement: weight behavior vectors by detected phase so pressure calculation is task-aware. D-15/D-16 lock this to non-LLM approach. |
| ANOM-01 | Cross-session anomaly prediction (5-10 actions ahead) | Extend `PressurePredictor` with cross-session pattern library (D-14). Session history (D-12) provides training data. Pattern matching: "these first N actions look like session X which escalated at action M". |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `statistics` | 3.11+ | Percentile computation, mean, stdev for threshold tuning | Zero dependency, sufficient for D-13's statistical optimization |
| Python stdlib `json` | 3.11+ | JSON Lines session history, benchmark results | Already used everywhere in SOMA |
| Python stdlib `time` | 3.11+ | Benchmark timing | No external timer needed |
| `rich>=13.0` | Already dep | Rich terminal output for benchmark progress, tables, panels | Already a project dependency, used in demo_session.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `math` | 3.11+ | Cosine similarity for cross-session pattern matching | Already used in fingerprint.py divergence |
| Python stdlib `pathlib` | 3.11+ | Session history file management | Already used in state.py |
| Python stdlib `dataclasses` | 3.11+ | Benchmark result types | Project convention |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib statistics | numpy/scipy | Overkill; adds heavy dependency for simple percentile/mean/stdev |
| JSON Lines | SQLite (like analytics.py) | JSON Lines is append-only, human-readable, greppable -- better for session history per D-12 |
| Custom benchmark | pytest-benchmark | pytest-benchmark measures wall-clock Python performance, not engine behavioral metrics |

**Installation:**
No new dependencies needed. Everything uses existing project dependencies + Python stdlib.

## Architecture Patterns

### Recommended Project Structure
```
src/soma/
  benchmark/
    __init__.py           # Public API: run_benchmark(), BenchmarkResult
    harness.py            # Core harness: run scenarios with/without SOMA
    scenarios.py          # Scenario definitions (action sequences)
    metrics.py            # Metric collection and aggregation
    report.py             # Markdown + terminal output generation
  session_store.py        # Cross-session JSON Lines storage (D-12)
  threshold_tuner.py      # Percentile-based threshold optimization (D-13)
```

### Pattern 1: Benchmark Harness (A/B Testing)
**What:** Run identical action sequences through SOMAEngine twice: once with guidance affecting behavior (SOMA-enabled simulation), once without (baseline run). The key insight is that "without SOMA" means actions proceed unchanged regardless of pressure -- the engine still computes metrics but guidance is ignored.
**When to use:** Every benchmark run.
**Example:**
```python
# The engine is deterministic given the same action sequence.
# "SOMA enabled" = scenario script responds to guidance (e.g., stops retrying when GUIDE fires)
# "SOMA disabled" = scenario script ignores guidance completely

@dataclass(frozen=True, slots=True)
class ScenarioAction:
    """A single step in a benchmark scenario."""
    tool_name: str
    output_text: str
    token_count: int = 100
    error: bool = False
    retried: bool = False
    # If True, this action is skippable when SOMA issues GUIDE/WARN
    # (simulates agent following guidance)
    guidance_responsive: bool = False

def run_scenario(
    actions: list[ScenarioAction],
    soma_enabled: bool,
) -> BenchmarkRun:
    """Run a scenario with or without SOMA guidance response."""
    engine = SOMAEngine(budget={"tokens": 500_000})
    engine.register_agent("benchmark-agent")

    results = []
    skipped = 0
    for action in actions:
        # In SOMA-enabled mode, skip guidance-responsive actions
        # when the engine is in GUIDE/WARN/BLOCK mode
        if soma_enabled and action.guidance_responsive:
            current_mode = engine.get_level("benchmark-agent")
            if current_mode >= ResponseMode.GUIDE:
                skipped += 1
                continue

        result = engine.record_action("benchmark-agent", Action(
            tool_name=action.tool_name,
            output_text=action.output_text,
            token_count=action.token_count,
            error=action.error,
            retried=action.retried,
        ))
        results.append(result)

    return BenchmarkRun(results=results, skipped_by_guidance=skipped)
```

### Pattern 2: Session History (JSON Lines)
**What:** Append-only session summaries for cross-session learning.
**When to use:** At session end (engine shutdown or explicit save).
**Example:**
```python
# ~/.soma/sessions/session-{timestamp}.jsonl
# Each line is a complete action record with full engine state

@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Summary of one completed session, stored as single JSON line."""
    session_id: str
    agent_id: str
    started: float
    ended: float
    action_count: int
    final_pressure: float
    max_pressure: float
    error_count: int
    mode_transitions: list[dict]  # [{from, to, at_action}]
    pressure_trajectory: list[float]  # pressure at each action
    tool_distribution: dict[str, int]
    final_phase: str  # from TaskTracker

def append_session(record: SessionRecord) -> None:
    """Append one session record to history."""
    path = Path.home() / ".soma" / "sessions" / "history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(asdict(record)) + "\n")
```

### Pattern 3: Cross-Session Pattern Matching (ANOM-01)
**What:** Extend PressurePredictor to look up similar pressure trajectories from past sessions and predict escalation.
**When to use:** After each action, when session history has 3+ sessions.
**Example:**
```python
class CrossSessionPredictor(PressurePredictor):
    """Extends PressurePredictor with cross-session pattern matching."""

    def __init__(self, window: int = 10, horizon: int = 5) -> None:
        super().__init__(window=window, horizon=horizon)
        self._session_patterns: list[list[float]] = []  # past pressure trajectories

    def load_history(self, history_path: Path) -> None:
        """Load past session pressure trajectories."""
        if not history_path.exists():
            return
        with open(history_path) as f:
            for line in f:
                record = json.loads(line)
                trajectory = record.get("pressure_trajectory", [])
                if len(trajectory) >= self.window:
                    self._session_patterns.append(trajectory)

    def predict(self, next_threshold: float) -> Prediction:
        """Enhanced prediction with cross-session pattern matching."""
        base = super().predict(next_threshold)

        if not self._session_patterns or len(self._pressures) < 3:
            return base

        # Find most similar past trajectory prefix
        current_prefix = self._pressures[-min(len(self._pressures), self.window):]
        best_match_score = 0.0
        best_continuation = None

        for past in self._session_patterns:
            for start in range(len(past) - len(current_prefix) - self.horizon):
                segment = past[start:start + len(current_prefix)]
                similarity = _cosine_similarity(current_prefix, segment)
                if similarity > best_match_score and similarity > 0.8:
                    best_match_score = similarity
                    best_continuation = past[start + len(current_prefix):
                                             start + len(current_prefix) + self.horizon]

        if best_continuation:
            cross_session_prediction = max(best_continuation)
            # Blend: 60% linear trend, 40% cross-session
            blended = 0.6 * base.predicted_pressure + 0.4 * cross_session_prediction
            confidence = base.confidence * 0.6 + best_match_score * 0.4
            return Prediction(
                current_pressure=base.current_pressure,
                predicted_pressure=min(1.0, max(0.0, blended)),
                actions_ahead=base.actions_ahead,
                will_escalate=blended >= next_threshold and confidence > 0.3,
                next_threshold=next_threshold,
                dominant_reason="cross_session" if cross_session_prediction > base.predicted_pressure else base.dominant_reason,
                confidence=confidence,
            )

        return base
```

### Pattern 4: Percentile-Based Threshold Tuning (TUNE-01)
**What:** Use benchmark data to find optimal thresholds. Collect all pressure values at mode transitions, compute percentiles to find where transitions should fire.
**When to use:** After benchmark completes with sufficient data.
**Example:**
```python
def compute_optimal_thresholds(
    benchmark_results: list[BenchmarkRun],
    target_false_positive_rate: float = 0.05,
) -> dict[str, float]:
    """Find thresholds that minimize false positives while catching real problems.

    Strategy: collect pressure at each action where the engine was correct
    (truly needed guidance) vs incorrect (false alarm). Set threshold at
    the percentile that achieves target false positive rate.
    """
    true_positive_pressures = []
    false_positive_pressures = []

    for run in benchmark_results:
        for i, result in enumerate(run.results):
            # Action was a "true problem" if it was an error or
            # if the next 3 actions showed degradation
            is_real_problem = _is_real_problem(run.results, i)
            if result.mode >= ResponseMode.GUIDE:
                if is_real_problem:
                    true_positive_pressures.append(result.pressure)
                else:
                    false_positive_pressures.append(result.pressure)

    # Set guide threshold at percentile where false positives are below target
    import statistics
    all_pressures = sorted(false_positive_pressures)
    if all_pressures:
        idx = int(len(all_pressures) * (1.0 - target_false_positive_rate))
        guide_threshold = all_pressures[min(idx, len(all_pressures) - 1)]
    else:
        guide_threshold = 0.25  # default

    return {
        "guide": guide_threshold,
        "warn": guide_threshold + 0.25,
        "block": guide_threshold + 0.50,
    }
```

### Pattern 5: Task-Phase-Weighted Behavior Vectors (TASK-01)
**What:** Weight behavior vector components by detected task phase so that drift is measured relative to what's expected for that phase, not just overall statistics.
**When to use:** Integrated into engine's drift computation.
**Example:**
```python
# Phase-specific expected tool distributions
PHASE_WEIGHTS: dict[str, dict[str, float]] = {
    "research": {"Read": 0.4, "Grep": 0.3, "Glob": 0.2, "Bash": 0.1},
    "implement": {"Edit": 0.4, "Write": 0.3, "Read": 0.2, "Bash": 0.1},
    "test": {"Bash": 0.5, "Read": 0.3, "Edit": 0.2},
    "debug": {"Bash": 0.3, "Read": 0.3, "Edit": 0.2, "Grep": 0.2},
}

def compute_phase_aware_drift(
    actions: list[Action],
    baseline_vector: list[float],
    known_tools: list[str],
    current_phase: str,
) -> float:
    """Drift computation that accounts for expected phase behavior."""
    raw_drift = compute_drift(actions, baseline_vector, known_tools)

    # If current tool usage matches expected phase pattern, reduce drift score
    phase_pattern = PHASE_WEIGHTS.get(current_phase, {})
    if not phase_pattern:
        return raw_drift

    tool_counts = {}
    for a in actions:
        tool_counts[a.tool_name] = tool_counts.get(a.tool_name, 0) + 1
    total = len(actions)
    actual_dist = {t: c / total for t, c in tool_counts.items()}

    # How well does actual distribution match expected phase?
    phase_alignment = 0.0
    for tool, expected in phase_pattern.items():
        actual = actual_dist.get(tool, 0.0)
        phase_alignment += min(actual / max(expected, 0.01), 1.0)
    phase_alignment /= len(phase_pattern)

    # High phase alignment = reduce drift (behavior matches expected phase)
    return raw_drift * (1.0 - 0.5 * phase_alignment)
```

### Anti-Patterns to Avoid
- **Non-deterministic benchmarks:** Always use fixed random seeds. The benchmark must be 100% reproducible (`random.Random(seed)`).
- **Modifying the engine for benchmarks:** The benchmark harness wraps the existing engine, never patches internals. Engine code stays clean.
- **Mixing benchmark and production state:** Benchmark runs must never touch `~/.soma/`. Use isolated in-memory engines.
- **Overcomplicating threshold tuning:** D-13 explicitly forbids ML/sklearn. Percentile-based statistics are sufficient and explainable.
- **LLM calls in monitoring:** D-15 explicitly forbids this. All task understanding comes from tool usage patterns.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Statistical aggregation | Custom mean/percentile | `statistics.mean()`, `statistics.quantiles()` | stdlib handles edge cases (empty data, single value) |
| Rich terminal tables | Custom formatting | `rich.table.Table`, `rich.progress.Progress` | Already a dependency, handles terminal width, color, alignment |
| JSON Lines file handling | Custom file rotation | Follow `AuditLogger` pattern from `audit.py` | Already battle-tested in the codebase with rotation and error handling |
| Behavior vector math | Custom linear algebra | Existing `compute_behavior_vector()` + `compute_drift()` from `vitals.py` | Already handles tool distribution, cosine distance, edge cases |
| Session state persistence | Custom file IO | Follow `state.py` patterns with `mkdir(parents=True)` and silent exception handling | Established project convention |

**Key insight:** The entire benchmark infrastructure is a composition problem, not a creation problem. Every component exists: `SOMAEngine` for the pipeline, `Action`/`ActionResult` for data types, `Rich` for output, `json` for serialization, `SessionRecorder` for replay. The benchmark harness just orchestrates these in a new way.

## Common Pitfalls

### Pitfall 1: Benchmark Scenarios Too Simple
**What goes wrong:** Toy scenarios (5 actions each) don't stress the engine's EMA baselines, cold-start blending, or graph propagation. Results look good but don't reflect real usage.
**Why it happens:** Real agent sessions are 50-200+ actions with complex phase transitions.
**How to avoid:** Each scenario should have 30-100 actions minimum. Include warm-up phases (10+ normal actions to establish baselines), then degradation, then optionally recovery. Use `test_stress.py` patterns as templates.
**Warning signs:** All scenarios complete in < 5 actions. No mode transitions observed.

### Pitfall 2: A/B Comparison Apples-to-Oranges
**What goes wrong:** SOMA-enabled runs have fewer actions (because guidance skips some), making direct metric comparison misleading.
**Why it happens:** The point of SOMA is to prevent bad actions. Fewer total actions with SOMA is a feature, not a bug.
**How to avoid:** Compare rates (error rate, retry rate) not counts. Also compare "actions to recovery" -- how many actions until pressure drops below GUIDE threshold after a problem starts.
**Warning signs:** SOMA-enabled shows more errors because the denominator (total actions) is smaller.

### Pitfall 3: Cold-Start Baseline Dominates
**What goes wrong:** The first 10 actions are in grace period (pressure forced to 0.0). If scenarios are short, half the data is in grace period.
**Why it happens:** `engine.py` line 586: `if s.action_count <= s.baseline.min_samples: effective = 0.0`
**How to avoid:** Scenarios must be long enough that the grace period (default 10 actions) is a small fraction. Or: pre-warm the engine with a fixed warm-up sequence before the measured scenario begins.
**Warning signs:** Pressure stays at 0.0 for the first ~10 actions in every run.

### Pitfall 4: Session History File Growth
**What goes wrong:** JSON Lines files grow unbounded if sessions are never cleaned up.
**Why it happens:** Append-only by design (D-12).
**How to avoid:** Cap at configurable max sessions (e.g., last 100) or max file size (e.g., 10MB, like `AuditLogger`). Old sessions get rotated, not deleted.
**Warning signs:** `~/.soma/sessions/` grows to megabytes.

### Pitfall 5: Cross-Session Pattern Overfitting
**What goes wrong:** Predictor matches current trajectory to a past session and predicts escalation, but the match is coincidental (different context, different task).
**Why it happens:** Short pressure trajectories can be similar by chance.
**How to avoid:** Require high cosine similarity (> 0.8) AND minimum trajectory length (5+ points). Weight by recency (recent sessions more relevant). Include task phase as a matching dimension.
**Warning signs:** High false positive rate on anomaly predictions.

### Pitfall 6: Benchmark Results Vary Between Machines
**What goes wrong:** Benchmark uses `time.time()` for timing and results differ by machine speed.
**Why it happens:** Wall-clock time depends on CPU, load, OS scheduling.
**How to avoid:** Primary metrics should be action-count-based (errors per 100 actions, retries per scenario), not time-based. Time is a secondary metric only. Ensure deterministic random seeds.
**Warning signs:** Same scenario gives different results on different runs.

## Code Examples

### Existing Engine Usage (from demo_session.py)
```python
# Source: demo_session.py
engine = soma.quickstart()
engine.register_agent("agent-1", system_prompt="Implement auth module with tests")

result = engine.record_action(
    "agent-1",
    soma.Action(
        tool_name=tool,
        output_text=output,
        token_count=tokens,
        error=error,
    ),
)
# result.mode, result.pressure, result.vitals, result.context_action all available
```

### Existing Stress Test Pattern (from test_stress.py)
```python
# Source: tests/test_stress.py
engine = SOMAEngine(budget={"tokens": 500_000})
engine.register_agent("agent")

# Ramp error probability from 0 to 1 over 50 steps
rng = random.Random(42)
for step in range(50):
    error_prob = step / 49.0
    is_error = rng.random() < error_prob
    action = _error_action(step) if is_error else _normal_action(step)
    result = engine.record_action("agent", action)
```

### Existing AuditLogger JSON Lines Pattern (from audit.py)
```python
# Source: src/soma/audit.py
# Append one JSON line, never crash on failure
try:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._maybe_rotate()
    with open(self._path, "a") as f:
        f.write(json.dumps(entry) + "\n")
except OSError:
    pass
```

### Existing TaskTracker Phase Detection (from task_tracker.py)
```python
# Source: src/soma/task_tracker.py
_PHASE_TOOLS = {
    "research": {"Read", "Grep", "Glob", "WebSearch", "WebFetch"},
    "implement": {"Write", "Edit", "NotebookEdit"},
    "test": {"Bash"},
    "debug": set(),  # Detected by error patterns
}
# Already detects: research, implement, test, debug, unknown
```

### Existing PressurePredictor Serialization (from predictor.py)
```python
# Source: src/soma/predictor.py
# PressurePredictor already has to_dict()/from_dict() for persistence
def to_dict(self) -> dict:
    return {
        "window": self.window,
        "horizon": self.horizon,
        "pressures": list(self._pressures),
        "action_log": list(self._action_log),
    }
```

### CLI Subcommand Registration Pattern (from cli/main.py)
```python
# Source: src/soma/cli/main.py
# Adding 'benchmark' follows the same pattern as all other subcommands:
# 1. Add parser in _build_parser()
benchmark_parser = subparsers.add_parser("benchmark", help="Run SOMA behavioral benchmarks")
benchmark_parser.add_argument("--scenarios", nargs="*", help="Specific scenarios to run")
benchmark_parser.add_argument("--runs", type=int, default=5, help="Runs per scenario (default: 5)")
# 2. Add handler function
def _cmd_benchmark(args): ...
# 3. Add to dispatch dict
dispatch["benchmark"] = _cmd_benchmark
```

## Benchmark Scenario Design

### Scenario 1: Healthy Session (Baseline)
- 50 actions: structured research -> implement -> test cycle
- ~5% natural error rate (1 retry, 2-3 minor errors)
- Expected: SOMA stays in OBSERVE entire time, no guidance issued
- Purpose: Measure false positive rate

### Scenario 2: Degrading Session
- 80 actions: starts healthy, degrades around action 30
- Pattern: 20 normal -> 10 errors start appearing -> 20 error-heavy -> 15 blind writes -> 15 recovery
- Expected with SOMA: GUIDE fires around action 35, recovery starts earlier
- Expected without SOMA: Errors continue unchecked through action 65
- Primary metric: error count difference

### Scenario 3: Multi-Agent Coordination
- 2 agents: agent-A (upstream) -> agent-B (downstream) via trust edge
- 60 actions each interleaved
- agent-A degrades at action 20, agent-B should see pressure propagation
- Expected with SOMA: agent-B adjusts behavior when upstream pressure detected
- Purpose: Tests graph propagation and multi-agent value

### Scenario 4 (bonus): Retry Storm
- 40 actions: good start, then enters retry loop (same error 8+ times)
- Expected with SOMA: WARN fires, stops retry loop
- Purpose: Most dramatic improvement metric

### Scenario 5 (bonus): Context Exhaustion
- 100 actions with increasing token counts
- Expected: Context usage pressure rises, handoff suggestion issued
- Purpose: Tests CTX-01 / half-life predictions

## Benchmark Metrics Schema

```python
@dataclass(frozen=True)
class BenchmarkMetrics:
    """Collected per-run metrics for A/B comparison."""
    # Primary (D-08)
    total_errors: int
    error_rate: float

    # Secondary (D-09)
    total_retries: int
    retry_rate: float
    total_tokens: int
    total_actions: int

    # Tertiary (D-10)
    mode_transitions: list[dict]  # [{from, to, at_action, pressure}]
    false_positives: int  # GUIDE/WARN when no real problem
    true_positives: int   # GUIDE/WARN that preceded real problem

    # Deep (D-11)
    per_action: list[dict]  # [{pressure, vitals, mode, guidance, action_index}]

@dataclass(frozen=True)
class ScenarioResult:
    """Complete result for one scenario: N runs with SOMA, N runs without."""
    scenario_name: str
    soma_runs: list[BenchmarkMetrics]
    baseline_runs: list[BenchmarkMetrics]

    # Computed summary
    error_reduction: float  # (baseline_errors - soma_errors) / baseline_errors
    retry_reduction: float
    token_savings: float
```

## Session History Schema (D-12)

```json
{
  "session_id": "ses-1711900000",
  "agent_id": "claude-code",
  "started": 1711900000.0,
  "ended": 1711903600.0,
  "action_count": 87,
  "final_pressure": 0.12,
  "max_pressure": 0.68,
  "avg_pressure": 0.24,
  "error_count": 12,
  "retry_count": 5,
  "total_tokens": 45000,
  "mode_transitions": [
    {"from": "OBSERVE", "to": "GUIDE", "at_action": 34, "pressure": 0.27},
    {"from": "GUIDE", "to": "OBSERVE", "at_action": 52, "pressure": 0.18}
  ],
  "pressure_trajectory": [0.0, 0.0, 0.02, 0.03, ...],
  "tool_distribution": {"Read": 20, "Edit": 15, "Bash": 30, "Grep": 12, "Write": 10},
  "phase_sequence": ["research", "implement", "test", "debug", "test"],
  "fingerprint_divergence": 0.15
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-session predictor | Cross-session pattern matching | This phase | Predictions informed by historical session trajectories |
| Fixed thresholds (guide=0.25) | Data-driven percentile thresholds | This phase | Thresholds tuned to actual engine behavior, fewer false positives |
| Phase-unaware drift | Task-phase-weighted drift | This phase | Drift during expected phase transitions not penalized |
| No benchmark proof | Reproducible A/B benchmarks | This phase | Concrete evidence that SOMA improves agent behavior |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run python -m pytest tests/test_benchmark.py -x -q` |
| Full suite command | `uv run python -m pytest -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PRED-01 | Cross-session predictor improves prediction accuracy over baseline predictor | unit | `uv run python -m pytest tests/test_cross_session_predictor.py -x` | Wave 0 |
| TUNE-01 | Percentile-based thresholds produce lower false positive rate than defaults | unit | `uv run python -m pytest tests/test_threshold_tuner.py -x` | Wave 0 |
| TASK-01 | Phase-weighted drift is lower during expected phase transitions | unit | `uv run python -m pytest tests/test_task_phase_drift.py -x` | Wave 0 |
| ANOM-01 | Cross-session pattern matching detects recurring escalation patterns | unit | `uv run python -m pytest tests/test_cross_session_predictor.py::test_pattern_matching -x` | Wave 0 |
| D-01-07 | Benchmark harness runs, collects metrics, produces output | integration | `uv run python -m pytest tests/test_benchmark.py -x` | Wave 0 |
| D-04,17-19 | Benchmark produces valid markdown and terminal output | unit | `uv run python -m pytest tests/test_benchmark.py::test_report_generation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_benchmark.py tests/test_cross_session_predictor.py tests/test_threshold_tuner.py -x -q`
- **Per wave merge:** `uv run python -m pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_benchmark.py` -- benchmark harness tests (covers D-01 through D-11, D-17-19)
- [ ] `tests/test_cross_session_predictor.py` -- cross-session pattern matching (covers PRED-01, ANOM-01)
- [ ] `tests/test_threshold_tuner.py` -- percentile threshold tuning (covers TUNE-01)
- [ ] `tests/test_task_phase_drift.py` -- phase-weighted drift (covers TASK-01)
- [ ] `tests/test_session_store.py` -- session history JSON Lines (covers D-12)

## Open Questions

1. **"Guidance followed" metric design**
   - What we know: D-11 wants to track "was guidance followed". In benchmark scenarios, this is controllable (we decide which actions respond to guidance). In real usage, we'd need to detect if the agent changed behavior after receiving guidance.
   - What's unclear: How to detect "guidance followed" in real sessions (not benchmarks).
   - Recommendation: For benchmarks, explicitly mark actions as `guidance_responsive=True/False`. For real sessions, use a heuristic: if pressure drops within 5 actions of guidance, count as "followed".

2. **Number of benchmark runs for statistical significance**
   - What we know: D-06 says 5x each. With deterministic random seeds, each run is identical.
   - What's unclear: If runs are deterministic (same seed), multiple runs add no statistical power.
   - Recommendation: Use different random seeds per run (seed=1 through seed=5). This tests robustness across random variation while keeping reproducibility (same seeds every time).

3. **Cross-session predictor cold start**
   - What we know: Needs 3+ sessions before it has useful patterns.
   - What's unclear: How to handle the first 3 sessions gracefully.
   - Recommendation: Fall back to base PressurePredictor (linear trend + patterns) when insufficient history. This is the existing behavior -- the enhancement is additive.

## Sources

### Primary (HIGH confidence)
- `src/soma/engine.py` -- full pipeline, ActionResult, grace period logic
- `src/soma/predictor.py` -- PressurePredictor, linear trend, pattern boosts, serialization
- `src/soma/learning.py` -- LearningEngine, threshold/weight adjustments
- `src/soma/halflife.py` -- success rate prediction, handoff suggestions
- `src/soma/fingerprint.py` -- cross-session behavioral fingerprinting with EMA
- `src/soma/task_tracker.py` -- phase detection, scope drift, tool distribution
- `src/soma/baseline.py` -- EMA with cold-start blending, min_samples=10
- `src/soma/audit.py` -- JSON Lines pattern with rotation
- `src/soma/analytics.py` -- SQLite analytics store (alternative pattern reference)
- `src/soma/state.py` -- session-scoped state persistence
- `src/soma/pressure.py` -- DEFAULT_WEIGHTS, signal pressure computation
- `src/soma/guidance.py` -- DEFAULT_THRESHOLDS (guide=0.25, warn=0.50, block=0.75)
- `src/soma/types.py` -- Action, ActionResult, VitalsSnapshot, ResponseMode
- `tests/test_stress.py` -- 10 stress scenarios as benchmark seed templates
- `demo_session.py` -- scripted scenario pattern with Rich output
- `src/soma/cli/main.py` -- CLI subcommand registration pattern

### Secondary (MEDIUM confidence)
- Python `statistics` stdlib documentation -- percentile/quantile computation
- Rich library table/progress APIs -- verified via existing usage in project

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all stdlib + existing project dependencies, no new packages
- Architecture: HIGH - every component maps to existing codebase patterns
- Pitfalls: HIGH - derived from actual engine code analysis (grace period, EMA, etc.)
- Benchmark design: HIGH - directly informed by existing test_stress.py and demo_session.py
- Cross-session learning: MEDIUM - novel code, but extends well-understood PressurePredictor pattern

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable domain, no external dependencies to change)
