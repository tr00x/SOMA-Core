# SOMA Technical Reference
### System of Oversight and Monitoring for Agents

**Version 0.3.2 | March 2026**

A formal specification of the mathematical models, algorithms, and system architecture behind SOMA — the behavioral monitoring and control system for AI agents.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Core Pipeline](#2-core-pipeline)
3. [Signal Computation](#3-signal-computation)
   - 3.1 [Uncertainty](#31-uncertainty)
   - 3.2 [Behavioral Drift](#32-behavioral-drift)
   - 3.3 [Resource Vitals](#33-resource-vitals)
4. [Normalization: Z-Score with Sigmoid Clamping](#4-normalization-z-score-with-sigmoid-clamping)
5. [Pressure Aggregation](#5-pressure-aggregation)
6. [Baseline Learning (EMA)](#6-baseline-learning-ema)
7. [Escalation Ladder with Hysteresis](#7-escalation-ladder-with-hysteresis)
8. [Multi-Agent Pressure Propagation](#8-multi-agent-pressure-propagation)
9. [Predictive Model](#9-predictive-model)
10. [Self-Learning Engine](#10-self-learning-engine)
11. [Quality Scoring](#11-quality-scoring)
12. [Root Cause Analysis](#12-root-cause-analysis)
13. [Agent Fingerprinting](#13-agent-fingerprinting)
14. [Task Phase Detection & Scope Drift](#14-task-phase-detection--scope-drift)
15. [Drift Mode Classification](#15-drift-mode-classification)
16. [System Constants](#16-system-constants)
17. [Formal Properties](#17-formal-properties)

---

## 1. System Overview

SOMA operates on a discrete event model. Each **action** (tool call, API call) is an atomic unit of observation. The system maintains no background threads, makes no network requests, and performs no LLM inference. All computation is deterministic and completes in O(n) time where n is the ring buffer size (default 10).

### Invariants

- **Deterministic**: Same action sequence always produces the same pressure, level, and signals.
- **Bounded**: All signals, pressures, and scores are clamped to [0, 1].
- **Monotonic escalation**: Pressure can escalate multiple levels in one step, but de-escalation drops one level at a time.
- **Grace period**: First `min_samples` actions (default 10) produce zero pressure.

### Data Flow

```
Action(tool, output, error, tokens, cost, duration, retried)
  │
  ├─→ Ring Buffer (last 10 actions)
  │
  ├─→ [VITALS]
  │     ├─ Uncertainty(retry_rate, tool_deviation, format_deviation, entropy)
  │     ├─ Drift(cosine_distance(behavior_vector, baseline_vector))
  │     ├─ Error Rate(errors_in_window / actions_in_window)
  │     ├─ Token Usage(spent / limit)
  │     └─ Cost(spent / budget)
  │
  ├─→ [BASELINE UPDATE] EMA(α=0.15, cold_start_blend)
  │
  ├─→ [SIGNAL PRESSURE] z_score → sigmoid_clamp per signal
  │
  ├─→ [AGGREGATE] 0.7·weighted_mean + 0.3·max
  │
  ├─→ [GRAPH PROPAGATION] trust-weighted multi-agent
  │
  ├─→ [ESCALATION LADDER] with hysteresis + learning adjustments
  │
  ├─→ [LEARNING] evaluate intervention outcomes
  │
  └─→ ActionResult(level, pressure, vitals, context_action)
```

---

## 2. Core Pipeline

The pipeline executes on every `record_action(agent_id, action)` call. Steps are sequential and stateful.

**Source**: `src/soma/engine.py:205-417`

### Step-by-step

| Step | Computation | Output |
|------|------------|--------|
| 1 | Compute uncertainty from ring buffer + baselines | `uncertainty ∈ [0, 1]` |
| 2 | Compute behavior vector, cosine distance to baseline | `drift ∈ [0, 1]` |
| 3 | Detect time anomaly (duration > 2σ from mean) | `uncertainty += time_boost` |
| 4 | Compute resource vitals (tokens, cost, error rate) | `ResourceVitals` |
| 5 | Determine drift mode (DIRECTIVE vs INFORMATIONAL) | `DriftMode` |
| 6 | Update EMA baselines for all signals | Baselines mutated |
| 7 | Compute per-signal pressure via z-score + sigmoid | `signal_pressures: dict` |
| 8 | Apply absolute floors (error_rate > 0.3 → floor at error_rate) | Floors applied |
| 9 | Aggregate with adjusted weights | `internal_pressure ∈ [0, 1]` |
| 10 | Spend budget (tokens, cost) | Budget updated |
| 11 | Set internal pressure on graph, propagate | `effective_pressure` |
| 12 | Grace period check (action_count ≤ min_samples → pressure = 0) | |
| 13 | Trust decay/recovery based on uncertainty | Edge weights mutated |
| 14 | Evaluate ladder with learning adjustments + custom thresholds | `Level` |
| 15 | Check autonomy mode, emit events, record intervention | Events emitted |
| 16 | Evaluate pending learning interventions | `InterventionOutcome` |
| 17 | Export state (if auto_export) | JSON written |

---

## 3. Signal Computation

### 3.1 Uncertainty

**Source**: `src/soma/vitals.py:102-156`

Uncertainty is a weighted composite of four sub-signals:

```
U = w_r · R + w_t · σ(T) + w_f · F + w_e · σ(E)
```

Where:
- **R** = retry rate = `count(retried actions) / total_actions`
- **T** = tool call deviation = `|len(actions) - baseline_avg| / baseline_std` (z-score, σ-clamped)
- **F** = format deviation = `count(missing expected lines) / total_expected_lines`
- **E** = entropy deviation = `|H(output) - baseline_entropy| / baseline_entropy_std` (z-score, σ-clamped)

Default weights: `(w_r, w_t, w_f, w_e) = (0.30, 0.25, 0.20, 0.25)`

Result clamped to [0, 1].

#### Output Entropy

**Source**: `src/soma/vitals.py:41-62`

Normalized Shannon entropy over character bigrams:

```
H(text) = -Σ p(b) · log₂(p(b))  for each bigram b
H_norm = H(text) / log₂(N)       where N = count of bigrams
```

Returns 0 for text shorter than 2 characters. High entropy indicates chaotic/random output; low entropy indicates repetitive output. Both extremes deviate from baseline.

#### Time Anomaly Detection

**Source**: `src/soma/engine.py:236-244`

If an action's duration exceeds 2 standard deviations from the mean:

```
time_deviation = (duration - baseline_mean) / max(baseline_std, 0.1)
if time_deviation > 2.0:
    time_boost = min(σ(time_deviation) × 0.3, 0.3)
    uncertainty = min(1.0, uncertainty + time_boost)
```

This detects stuck or thrashing agents whose operations take abnormally long.

### 3.2 Behavioral Drift

**Source**: `src/soma/vitals.py:163-226`

#### Behavior Vector

A feature vector is computed from the action ring buffer:

```
v = [avg_tool_calls, avg_output_len/1000, avg_duration, pattern_entropy, ...tool_dist]
```

Where:
- `avg_tool_calls` = 1.0 (each action is one tool call)
- `avg_output_len` = mean character length / 1000 (normalized)
- `avg_duration` = mean `duration_sec`
- `pattern_entropy` = Shannon entropy over tool name sequence: `-Σ p(t)·log₂(p(t))`
- `tool_dist` = vector of `[count(tool_i) / n for tool_i in known_tools]`

#### Cosine Distance

```
drift = 1 - cos(v_current, v_baseline)

cos(a, b) = (a · b) / (|a| × |b|)
```

Returns 0 for zero vectors. The baseline vector is recomputed every 10 actions.

### 3.3 Resource Vitals

**Source**: `src/soma/vitals.py:260-291`

```
token_usage = min(1.0, tokens_spent / token_limit)
cost        = min(1.0, cost_spent / cost_budget)
error_rate  = min(1.0, errors_in_window / actions_in_window)
```

All clamped to [0, 1]. Zero denominators produce 0.0.

---

## 4. Normalization: Z-Score with Sigmoid Clamping

**Source**: `src/soma/pressure.py:17-25`, `src/soma/vitals.py:17-23`

Every signal is converted to a pressure value via:

```
z = (current - baseline) / max(std, 0.1)
p = σ_clamp(z)
```

The minimum std of 0.1 prevents division explosion during early sessions when variance is near zero.

### Sigmoid Clamp Function

```
σ_clamp(x) =
  0.0                    if x ≤ 0
  1 / (1 + e^(-x+3))    if 0 < x ≤ 6
  1.0                    if x > 6
```

This is a shifted sigmoid centered at x=3. Properties:
- σ(0) = 0 (values at or below baseline produce zero pressure)
- σ(3) ≈ 0.5 (3 standard deviations = 50% pressure)
- σ(6) → 1.0 (hard clamp prevents overflow)
- Monotonically increasing on (0, 6]

### Absolute Floors

**Source**: `src/soma/engine.py:279-289`

Z-score normalization can be defeated by a baseline that adapts to chronic errors. SOMA applies absolute floors:

```
if error_rate > 0.3:
    error_pressure = max(z_score_pressure, error_rate)

if retry_rate > 0.3:
    uncertainty_pressure = max(z_score_pressure, retry_rate)
```

This ensures that objectively bad signals cannot be "normalized away" by a corrupted baseline.

---

## 5. Pressure Aggregation

**Source**: `src/soma/pressure.py:28-65`

```
P = 0.7 × Σ(wᵢ · pᵢ) / Σ(wᵢ) + 0.3 × max(pᵢ)
```

Where `pᵢ` are individual signal pressures and `wᵢ` are their weights.

### Default Signal Weights

| Signal | Weight | Rationale |
|--------|--------|-----------|
| uncertainty | 2.0 | Most indicative of agent confusion |
| drift | 1.8 | Behavioral deviation from norm |
| error_rate | 1.5 | Direct indicator of failure |
| cost | 1.0 | Budget protection |
| token_usage | 0.8 | Least actionable |

### Design Rationale

The 70/30 blend of mean and max serves two purposes:
- **Weighted mean** (70%): Captures gradual, multi-signal degradation.
- **Max component** (30%): Ensures a single severe signal (e.g., error_rate = 1.0) can't be diluted by healthy signals.

### Drift Mode Exclusion

When `drift_mode == INFORMATIONAL`, the drift signal weight is set to 0 before aggregation. This prevents drift from contributing to pressure when it lacks confirmatory signals (see [Section 15](#15-drift-mode-classification)).

---

## 6. Baseline Learning (EMA)

**Source**: `src/soma/baseline.py`

Each signal maintains an independent Exponential Moving Average baseline.

### Update Rule

```
value_new = α · current + (1 - α) · value_old
variance_new = α · (current - value_old)² + (1 - α) · variance_old
```

Default α = 0.15. This gives an effective half-life of ~4.3 samples: `ln(2) / ln(1/0.85) ≈ 4.27`.

### Cold-Start Blending

During the first `min_samples` (default 10) observations:

```
blend = min(count / min_samples, 1.0)
effective_baseline = blend × computed_ema + (1 - blend) × default_value
```

Default values:

| Signal | Default |
|--------|---------|
| uncertainty | 0.05 |
| drift | 0.05 |
| token_usage | 0.01 |
| cost | 0.01 |
| error_rate | 0.01 |

This prevents the first few observations from dominating the baseline. At count=5 with min_samples=10, the blend is 50% computed + 50% default.

### Standard Deviation

```
std = max(√variance, 1e-9)
```

Returns 0.1 for signals with no observations (ensures z-scores remain bounded).

---

## 7. Escalation Ladder with Hysteresis

**Source**: `src/soma/ladder.py`

### Threshold Table

| Level | Escalation Threshold | De-escalation Threshold | Gap |
|-------|---------------------|------------------------|-----|
| HEALTHY | 0.00 | 0.00 | — |
| CAUTION | 0.25 | 0.20 | 0.05 |
| DEGRADE | 0.50 | 0.45 | 0.05 |
| QUARANTINE | 0.75 | 0.70 | 0.05 |
| RESTART | 0.90 | 0.85 | 0.05 |
| SAFE_MODE | budget ≤ 0 | budget > 0.10 | special |

### Escalation Rules (Priority Order)

1. **Budget exhaustion**: `budget_health ≤ 0` → SAFE_MODE (latches until `budget_health > 0.10`)
2. **Manual override**: `force_level` is set → that level
3. **Upward escalation**: Jump to highest level whose threshold ≤ pressure (multi-level jumps allowed)
4. **Downward de-escalation**: Drop exactly one level if `pressure < de_escalation_threshold` of current level
5. **Hold**: If `de_threshold ≤ pressure < escalation_threshold`, hold current level

### Hysteresis

The gap between escalation and de-escalation thresholds (0.05 by default) prevents rapid oscillation. An agent that escalates to CAUTION at p=0.25 must drop below p=0.20 to return to HEALTHY. Without hysteresis, noise around the threshold would cause level thrashing.

### Learning Adjustments

The learning engine (Section 10) produces threshold shifts that are added to the escalation thresholds before evaluation:

```
adjusted_threshold = base_threshold + learning_shift
```

Shifts are capped at ±0.10 per transition.

### Custom Thresholds

User-configured thresholds from `soma.toml` replace the built-in defaults. The hysteresis gap is preserved:

```
de_escalation = custom_threshold - default_gap
```

---

## 8. Multi-Agent Pressure Propagation

**Source**: `src/soma/graph.py`

### Graph Model

SOMA models agent relationships as a directed graph G = (V, E) where:
- V = set of registered agents
- E = directed edges with trust weights `w ∈ [0, 1]`

Each node maintains:
- `internal_pressure`: computed from the agent's own signals
- `effective_pressure`: after propagation from connected agents

### Propagation Algorithm

Iterative convergence (max 3 iterations):

```
For each node n:
    if no incoming edges:
        effective[n] = internal[n]
    else:
        weighted_avg = Σ(w_e · effective[source_e]) / Σ(w_e)
        effective[n] = max(internal[n], damping × weighted_avg)
```

Where `damping = 0.6` (default).

The `max` operator ensures an agent's effective pressure is never less than its internal pressure — other agents can only increase pressure, not decrease it.

### Trust Dynamics

Trust weights evolve based on agent behavior:

**Decay** (when source agent's uncertainty > 0.5):
```
w_new = clamp(w - decay_rate × uncertainty, [0, 1])
```

**Recovery** (when source agent's uncertainty ≤ 0.5):
```
w_new = clamp(w + recovery_rate × (1 - uncertainty), [0, 1])
```

Default rates: `decay_rate = 0.05`, `recovery_rate = 0.02`

Recovery is intentionally slower than decay (asymmetric): trust is hard to earn, easy to lose.

---

## 9. Predictive Model

**Source**: `src/soma/predictor.py`

The predictor estimates pressure `h` actions ahead using two components:

```
P_predicted = clamp(P_current + slope × h + boost, [0, 1])
```

### Linear Trend (OLS Regression)

**Source**: `src/soma/predictor.py:107-138`

Ordinary least squares on the sliding window of pressure readings:

```
slope = Σ((xᵢ - x̄)(yᵢ - ȳ)) / Σ((xᵢ - x̄)²)

R² = [Σ((xᵢ - x̄)(yᵢ - ȳ))]² / [Σ((xᵢ - x̄)²) × Σ((yᵢ - ȳ)²)]
```

Where x = action index, y = pressure reading. Window size = 10, horizon = 5.

### Pattern Boosters

**Source**: `src/soma/predictor.py:140-201`

Known-bad behavioral patterns detected from the action log:

| Pattern | Condition | Boost |
|---------|-----------|-------|
| `error_streak` | ≥3 consecutive errors at end of window | +0.15 |
| `blind_writes` | ≥2 Write/Edit actions without intervening Read | +0.10 |
| `thrashing` | Same file edited ≥3 times in window | +0.08 |
| `retry_storm` | Error rate > 40% across window (≥5 actions) | +0.12 |

Boosts are additive. Multiple patterns can fire simultaneously.

### Confidence Score

```
confidence = 0.6 × sample_confidence + 0.4 × fit_confidence

sample_confidence = min(n / window, 1.0)
fit_confidence = max(R², 0.0) if n ≥ 3 else 0.0
```

Escalation warning is emitted only when `confidence > 0.3`.

### Dominant Reason

If `boost > |slope × horizon|`, the dominant reason is the pattern. Otherwise, it's "trend" (positive slope) or "stable" (zero/negative slope).

---

## 10. Self-Learning Engine

**Source**: `src/soma/learning.py`

The learning engine tracks whether escalation interventions actually helped, and adjusts thresholds and signal weights accordingly.

### Intervention Lifecycle

1. **Record**: When a level change occurs, record `(agent, old_level, new_level, pressure, signals)`
2. **Wait**: Count `actions_since` until `evaluation_window` (default 5) is reached
3. **Evaluate**: Compare current pressure to recorded pressure:
   - `delta = pressure_at_intervention - pressure_now`
   - `delta > 0` → **SUCCESS** (pressure dropped, intervention helped)
   - `delta ≤ 0` → **FAILURE** (pressure held or rose, intervention was premature)

### Adaptive Step Size

**Source**: `src/soma/learning.py:246-265`

```
ratio = same_type_count / total_outcomes
multiplier = 1.0 + 2.0 × max(0, ratio - 0.5)
step = base_step × multiplier
```

At 50/50 success/failure: multiplier = 1.0x. At 100% same type: multiplier = 3.0x. This accelerates convergence when the pattern is clear.

### On Failure (False Positive)

When `failure_count ≥ min_interventions` (default 3):

**Threshold adjustment** (make escalation harder):
```
shift = min(current_shift + adaptive_step, max_threshold_shift)
```

**Weight adjustment** (reduce triggering signal importance):
```
new_adj = current_adj - weight_adj_step
floor = min_weight - original_weight
new_adj = max(new_adj, floor)
```

### On Success (True Positive)

When `success_count ≥ min_interventions` (default 3):

**Threshold adjustment** (make escalation slightly easier):
```
shift = max(current_shift - adaptive_step × 0.5, -max_threshold_shift)
```

**Weight recovery** (restore signal importance):
```
recovery = min(weight_adj_step × 0.5, |current_adj|)
new_adj = current_adj + recovery
```

Success adjustments are half the magnitude of failure adjustments. This creates a conservative bias: the system is more willing to relax restrictions than to tighten them.

### Bounds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `evaluation_window` | 5 | Actions before evaluating |
| `threshold_adj_step` | 0.02 | Base step per adjustment |
| `weight_adj_step` | 0.05 | Weight change per adjustment |
| `min_weight` | 0.2 | Floor for effective signal weight |
| `max_threshold_shift` | ±0.10 | Maximum cumulative shift per transition |
| `min_interventions` | 3 | Minimum same-type outcomes before adjusting |

---

## 11. Quality Scoring

**Source**: `src/soma/quality.py`

### Rolling Window

Quality is tracked over a rolling window (default 30 events). Events are tuples of `(type, ok, flags)` where type is "write" or "bash".

### Score Computation

```
write_score = clean_writes / total_writes        (1.0 if no writes)
bash_score  = 1 - bash_failures / total_bashes   (1.0 if no bashes)

score = (write_count / total × write_score) + (bash_count / total × bash_score)

if syntax_errors > 0:
    score *= max(0.5, 1.0 - syntax_errors × 0.15)

score = clamp(score, [0, 1])
```

### Grade Mapping

| Grade | Score Range |
|-------|-----------|
| A | ≥ 0.90 |
| B | [0.80, 0.90) |
| C | [0.70, 0.80) |
| D | [0.50, 0.70) |
| F | < 0.50 |

### Syntax Penalty

Each syntax error multiplies the score by `(1 - 0.15)`, with a floor of 0.5x. This means:
- 1 error: score × 0.85
- 2 errors: score × 0.70
- 3 errors: score × 0.55
- 4+ errors: score × 0.50 (floor)

---

## 12. Root Cause Analysis

**Source**: `src/soma/rca.py`

RCA produces a single plain-English sentence explaining the dominant problem. It runs 5 detectors in parallel, scores them by severity, and returns the highest-scoring finding.

### Detectors

#### 1. Loop Detection (severity: 0.9)
Scans last 12 actions for repeating sequences of 2-3 tools:

```
pattern = tools[-seq_len:]
Count consecutive repetitions scanning backward.
If repetitions ≥ 3 → "stuck in Edit→Bash loop on config.py (3 cycles)"
```

#### 2. Error Cascade (severity: 0.5 + 0.1 per consecutive error)
Counts consecutive errors from the end of the action log:

```
If consecutive_errors ≥ 2:
    "error cascade: {n} consecutive Bash failures (error_rate=40%)"
```

#### 3. Blind Mutation (severity: 0.6 + 0.05 per write)
Counts Write/Edit actions since the last Read:

```
If writes_since_read ≥ 3:
    "blind mutation: 5 writes without reading (foo.py, bar.py)"
```

#### 4. Stall Detection (severity: 0.5)
Checks if 7/8 recent actions are read-only with zero writes:

```
"possible stall: 7/8 recent actions are reads with no writes — may be stuck researching"
```

#### 5. Drift Explanation (severity: 0.4 + 0.5 × drift)
When drift > 0.2, identifies contributing signals:

```
"behavioral drift=0.25 driven by uncertainty=0.30, errors=15%"
```

### Suppression

Returns `None` when `pressure < 0.15` and `level == HEALTHY`.

---

## 13. Agent Fingerprinting

**Source**: `src/soma/fingerprint.py`

### Fingerprint Components

| Field | Type | Description |
|-------|------|-------------|
| `tool_distribution` | `dict[str, float]` | Fraction of actions using each tool |
| `avg_error_rate` | `float` | Historical mean error rate |
| `avg_duration` | `float` | Historical mean action duration |
| `read_write_ratio` | `float` | reads / max(writes, 1) |
| `avg_session_length` | `float` | Mean actions per session |
| `sample_count` | `int` | Number of sessions observed |

### EMA Update

All fingerprint components use EMA with α = 0.1 (slower than baselines, reflecting longer-term patterns):

```
For each scalar:
    fp.value = 0.1 × current + 0.9 × fp.value

For tool distribution:
    For each tool:
        fp.dist[t] = 0.1 × current_dist[t] + 0.9 × fp.dist[t]
```

### Divergence Score

**Source**: `src/soma/fingerprint.py:31-71`

Requires `sample_count ≥ 10` to produce a non-zero divergence.

Three components:

**1. Jensen-Shannon Divergence (tool distribution)** — weight: 2x

```
For each tool t in union(P, Q):
    M(t) = (P(t) + Q(t)) / 2

JS = ½ Σ [P(t) · log₂(P(t)/M(t)) + Q(t) · log₂(Q(t)/M(t))]
```

Smoothing: 0.001 minimum for unseen tools. JS divergence ∈ [0, 1].

**2. Error Rate Delta**

```
err_delta = |current_error_rate - fingerprint_error_rate| / max(fingerprint_error_rate, 0.01)
```

Clamped to [0, 1].

**3. Read/Write Ratio Delta** — weight: 0.5x

```
rw_delta = |current_rw - fingerprint_rw| / max(fingerprint_rw, 0.1)
```

Clamped to [0, 1], then multiplied by 0.5.

**Final score**: `divergence = min(mean(weighted_components), 1.0)`

Divergence > 0.2 triggers an explanation listing the top 3 behavioral shifts.

---

## 14. Task Phase Detection & Scope Drift

**Source**: `src/soma/task_tracker.py`

### Phase Detection

Recent tool usage (last `drift_window` actions) is classified into phases:

| Phase | Tools | Priority |
|-------|-------|----------|
| debug | — | Triggered by error_rate > 30% in window |
| research | Read, Grep, Glob, WebSearch, WebFetch | Count-based |
| implement | Write, Edit, NotebookEdit | Count-based |
| test | Bash | Count-based |

Debug is checked first (error-pattern-based). Others are determined by maximum tool count.

### Scope Drift

After the first 5 file-touching actions establish an `initial_focus` (set of parent directories):

```
recent_dirs = directories touched in last drift_window actions
overlap = recent_dirs ∩ initial_focus
drift = 1.0 - |overlap| / |recent_dirs|
```

Drift > 0.3 triggers an explanation: `"scope expanded to tests/, config/"`.

---

## 15. Drift Mode Classification

**Source**: `src/soma/vitals.py:233-253`

Drift can be DIRECTIVE (contributes to pressure) or INFORMATIONAL (logged but excluded from pressure aggregation).

```
DIRECTIVE if:
    drift > drift_threshold (0.3) AND at least one of:
        - error_rate > error_rate_baseline
        - progress_stalled == True
        - uncertainty > uncertainty_threshold (0.3)

INFORMATIONAL otherwise
```

This prevents exploratory behavior (high drift but low errors/uncertainty) from triggering false escalations. An agent exploring a new part of the codebase without errors is not a problem — only drift accompanied by degradation triggers intervention.

---

## 16. System Constants

### Default Weights

| Constant | Value | Source |
|----------|-------|--------|
| Pressure blend (mean) | 0.70 | `pressure.py:65` |
| Pressure blend (max) | 0.30 | `pressure.py:65` |
| EMA alpha (baseline) | 0.15 | `baseline.py:25` |
| EMA alpha (fingerprint) | 0.10 | `fingerprint.py:102` |
| Min baseline std | 0.10 | `pressure.py:24` |
| Sigmoid center | 3.0 | `vitals.py:23` |
| Sigmoid hard clamp | 6.0 | `vitals.py:21` |
| Ring buffer capacity | 10 | `engine.py:39` |
| Grace period | 10 actions | `baseline.py:25` |
| Graph damping | 0.60 | `graph.py:27` |
| Trust decay rate | 0.05 | `graph.py:28` |
| Trust recovery rate | 0.02 | `graph.py:29` |
| Prediction window | 10 | `predictor.py:45` |
| Prediction horizon | 5 actions | `predictor.py:45` |
| Learning evaluation window | 5 actions | `learning.py:58` |
| Max threshold shift | ±0.10 | `learning.py:63` |
| Quality rolling window | 30 events | `quality.py:39` |
| Drift threshold | 0.30 | `engine.py:262` |
| Uncertainty threshold | 0.30 | `engine.py:262` |

### Escalation Thresholds (Default)

| Transition | Escalate | De-escalate |
|-----------|----------|-------------|
| → CAUTION | 0.25 | 0.20 |
| → DEGRADE | 0.50 | 0.45 |
| → QUARANTINE | 0.75 | 0.70 |
| → RESTART | 0.90 | 0.85 |
| → SAFE_MODE | budget ≤ 0 | budget > 0.10 |

### Pattern Boosts

| Pattern | Boost | Condition |
|---------|-------|-----------|
| error_streak | +0.15 | ≥3 consecutive errors |
| retry_storm | +0.12 | >40% error rate in window |
| blind_writes | +0.10 | ≥2 writes without read |
| thrashing | +0.08 | Same file edited ≥3 times |

### Uncertainty Weights

| Component | Weight |
|-----------|--------|
| retry_rate | 0.30 |
| tool_call_deviation | 0.25 |
| format_deviation | 0.20 |
| entropy_deviation | 0.25 |

---

## 17. Formal Properties

### Boundedness

All outputs are in [0, 1]:
- Sigmoid clamp: domain ℝ → range [0, 1]
- Cosine similarity: clamped by definition
- Resource vitals: `min(x/limit, 1.0)`
- Aggregate pressure: weighted average of [0,1] values ∈ [0,1]

### Monotonicity of Escalation

Let L(t) be the level at time t. For upward transitions:
```
∃ i: pressure ≥ threshold_i → L(t) = max(L(t-1), level_i)
```

For downward transitions:
```
pressure < de_threshold(L(t-1)) → L(t) = L(t-1) - 1
```

Multi-level jumps up, single-step down. This asymmetry protects against acute failures while enabling gradual recovery.

### Convergence of Learning

The learning engine's threshold adjustments are bounded by `[-max_threshold_shift, +max_threshold_shift]`. Signal weight adjustments are bounded by `[min_weight - original_weight, 0]`. Combined with `min_interventions ≥ 3`, the system converges to stable thresholds for any stationary agent behavior distribution.

### Grace Period Guarantee

For `action_count ≤ min_samples` (default 10):
```
effective_pressure = 0.0
level = HEALTHY
```

This holds regardless of signal values, ensuring new agents have time to establish baselines before any intervention.

### Determinism

Given identical:
- Action sequence `[a₁, a₂, ..., aₙ]`
- Budget configuration
- Custom weights/thresholds

The system produces identical:
- Pressure trajectory `[p₁, p₂, ..., pₙ]`
- Level trajectory `[l₁, l₂, ..., lₙ]`
- Learning adjustments

No randomness, no external state, no time dependencies (except action duration, which is an input).
