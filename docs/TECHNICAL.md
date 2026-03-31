# SOMA Technical Reference -- Version 0.5.0 | March 2026

This document is the formal technical specification for the SOMA behavioral monitoring system. It specifies every formula, constant, algorithm, and system property. All values are verified from source code and represent the canonical reference for implementation behavior.

---

## 1. System Overview

SOMA is a discrete event monitoring system that observes AI agent actions in real-time, computes behavioral pressure from five core vital signals, and injects corrective guidance before problems escalate.

**Computational model:**

- Discrete event model, O(n) per action where n = ring buffer size (default 10)
- Deterministic: same action sequence produces identical output
- All signals and pressures bounded to [0, 1]
- Grace period suppresses pressure for the first 10 actions (cold-start protection)
- No network requests, no LLM inference, sub-millisecond computation per action

---

## 2. Core Pipeline

The `record_action()` method executes a 22-step pipeline for each action. Steps execute sequentially within a single synchronous call.

| Step | Operation | Description |
|------|-----------|-------------|
| 1 | Tool tracking | Append `action.tool_name` to `known_tools` if not already present |
| 2 | Ring buffer append | Push action into fixed-capacity ring buffer (capacity=10) |
| 3 | Action count increment | Increment `action_count` and update `_last_active` timestamp |
| 4 | Task complexity capture | On first action, estimate task complexity from output text if not already set from system prompt |
| 5 | Initial task vector capture | At `warmup_actions` (default 5), snapshot `initial_known_tools` and compute `initial_task_vector` |
| 6 | Uncertainty computation | Compute composite uncertainty from retry rate, tool call deviation, format deviation, entropy deviation |
| 7 | Drift computation | Compute behavioral drift as `1 - cosine_similarity(current_vector, baseline_vector)`; update baseline vector every 10 actions |
| 8 | Time anomaly boost | If action duration exceeds 2 standard deviations above mean, boost uncertainty proportionally (capped at +0.3) |
| 9 | Duration baseline update | Update EMA baseline for action duration |
| 10 | Resource vitals computation | Compute error_rate, token_usage, and cost from budget state and ring buffer |
| 11 | Drift mode determination | Classify drift as DIRECTIVE or INFORMATIONAL based on confirmatory signals |
| 12 | Baseline updates | Update EMA baselines for uncertainty, drift, error_rate, tool_calls, and entropy |
| 13 | Per-signal pressure computation | Compute z-score-based sigmoid pressure for each signal; apply absolute floors for error_rate and retry_rate |
| 14 | Uncertainty classification | Classify uncertainty as epistemic, aleatoric, or None; apply pressure modulation (epistemic x1.3, aleatoric x0.7) |
| 15 | Goal coherence computation | After warmup, compute cosine similarity to initial task vector; invert to divergence and feed into signal pressures |
| 16 | Burn rate pressure | If budget health < 1.0, compute projected overshoot and add burn_rate signal |
| 17 | Learning weight adjustment | Apply cumulative weight adjustments from learning engine on top of base weights |
| 18 | Upstream vector influence | Boost per-signal pressures from upstream agents' effective pressure vectors (damped) |
| 19 | Aggregate pressure computation | Blend weighted mean (0.7) and max (0.3); apply error-rate floor |
| 20 | Graph propagation | Set internal pressure and vector, propagate through trust-weighted graph, extract effective pressure; zero during grace period |
| 21 | Trust dynamics | Decay trust when uncertainty > 0.5; recover trust when uncertainty <= 0.5 |
| 22 | Mode determination and events | Map effective pressure to ResponseMode; apply VBD override; apply task-complexity threshold reduction; emit level_changed events; evaluate learning outcomes; auto-export state |

---

## 3. Signal Computation

### 3.1 Uncertainty

Composite uncertainty score in [0, 1]:

```
U = 0.30 * retry_rate
  + 0.25 * sigmoid_clamp(tool_call_deviation)
  + 0.20 * format_deviation
  + 0.25 * sigmoid_clamp(entropy_deviation)
```

Component definitions:

- `retry_rate = retried_actions / total_actions` (0.0 for empty)
- `tool_call_deviation = |len(actions) - baseline_avg| / baseline_std` (returns 0 if std = 0)
- `format_deviation = missing_expected_lines / total_expected_lines` (returns 0 if no expected format)
- `entropy_deviation = |current_entropy - baseline_entropy| / baseline_entropy_std` (returns 0 if std = 0)

Final score is clamped to [0, 1].

### 3.2 Output Entropy

Normalized Shannon entropy over character bigrams:

```
bigrams = [text[i:i+2] for i in range(len(text) - 1)]
H = -sum(p_i * log2(p_i)) / log2(total_bigrams)
```

Where `p_i = count(bigram_i) / total_bigrams`.

Returns 0.0 for text shorter than 2 characters. Normalization denominator is `log2(total_bigrams)` when `total_bigrams > 1`, else 1.0.

### 3.3 Behavioral Drift

```
D = 1 - cosine_similarity(current_vector, baseline_vector)
```

Behavior vector dimensions:

| Index | Feature | Normalization |
|-------|---------|---------------|
| 0 | avg_tool_calls | Always 1.0 (each action is a tool call) |
| 1 | avg_output_len | `mean(len(output_text)) / 1000.0` |
| 2 | avg_response_time | `mean(duration_sec)` |
| 3 | pattern_entropy | Shannon entropy over tool name frequencies |
| 4..n | tool_distribution | Fraction of actions using each known tool |

Baseline vector is updated every 10 actions or on first computation.

Cosine similarity returns 0.0 for zero-magnitude vectors.

### 3.4 Drift Mode

Returns `DIRECTIVE` when ALL of:

- `drift > 0.3`
- At least one confirmatory signal:
  - `error_rate > error_rate_baseline`, OR
  - `uncertainty > 0.3`, OR
  - `progress_stalled` is True

Otherwise returns `INFORMATIONAL`. In INFORMATIONAL mode, the drift weight is zeroed in the aggregate pressure computation.

### 3.5 Resource Vitals

```
error_rate = errors_in_window / actions_in_window    clamped [0, 1]
token_usage = tokens_used / token_limit              clamped [0, 1]
cost = cost_spent / cost_budget                      clamped [0, 1]
```

Zero denominators yield 0.0.

---

## 4. Normalization

### 4.1 Sigmoid Clamp

```
sigmoid_clamp(x):
    if x <= 0:  return 0.0
    if x > 6:   return 1.0
    else:        return 1 / (1 + exp(-x + 3))
```

Center at x = 3, effective transition range [0, 6].

### 4.2 Signal Pressure

```
z = (current - baseline_mean) / max(baseline_std, 0.05)
signal_pressure = sigmoid_clamp(z)
```

The minimum standard deviation floor of 0.05 prevents extreme z-scores during cold start when variance is near zero.

---

## 5. Pressure Aggregation

### 5.1 Blend Formula

```
P = 0.7 * (sum(w_i * p_i) / sum(w_i)) + 0.3 * max(p_i)
```

Only signals with weight > 0 are included in both the weighted mean and the max. Returns 0.0 if no signals have positive weight.

If drift mode is INFORMATIONAL, the drift weight is set to 0 before aggregation.

### 5.2 Error-Rate Aggregate Floor

When `er_p >= 0.50` AND error_rate weight > 0:

```
floor = 0.40 + 0.40 * (er_p - 0.50) / 0.50
P = max(P, floor)
```

Floor mapping to response mode thresholds:

| Error Pressure | Floor | Mode Entry |
|---------------|-------|------------|
| 0.50 | 0.40 | GUIDE |
| 0.75 | 0.60 | WARN |
| 1.00 | 0.80 | BLOCK |

### 5.3 Signal-Level Floors

Applied before aggregation to prevent baseline adaptation from normalizing objectively bad behavior:

- `error_rate > 0.3`: `error_pressure = max(error_pressure, error_rate)`
- `retry_rate > 0.3`: `uncertainty_pressure = max(uncertainty_pressure, retry_rate)`

### 5.4 DEFAULT_WEIGHTS

| Signal | Weight |
|--------|--------|
| uncertainty | 2.0 |
| drift | 1.8 |
| error_rate | 1.5 |
| goal_coherence | 1.5 |
| cost | 1.0 |
| token_usage | 0.8 |

---

## 6. Baseline Learning (EMA)

### 6.1 Update Rules

Exponential moving average with variance tracking:

```
mean:     mu_{t+1}  = 0.15 * x_t + 0.85 * mu_t
variance: v_{t+1}   = 0.15 * (x_t - mu_t)^2 + 0.85 * v_t
```

Alpha = 0.15. Effective half-life approximately 4.3 observations.

First observation initializes mean directly from value; variance initialized to 0.0.

### 6.2 Cold-Start Blending

```
blend = min(count / 10, 1.0)
result = blend * computed + (1 - blend) * default
```

Default values by signal:

| Signal | Default |
|--------|---------|
| uncertainty | 0.05 |
| drift | 0.05 |
| error_rate | 0.01 |
| cost | 0.01 |
| token_usage | 0.01 |

Signals not in the defaults table return 0.0 as default.

### 6.3 Standard Deviation

```
get_std() = max(sqrt(variance), 1e-9)
```

Returns 0.1 when the signal has never been observed (uninitialized).

### 6.4 Grace Period

For the first `min_samples` (10) actions:

- Effective pressure forced to 0.0
- All graph pressures (internal and effective) zeroed
- Pressure vector reset to zero vector
- `get_snapshot()` returns 0.0 pressure during this window

---

## 7. Guidance System

### 7.1 Default Thresholds

| Threshold | Value |
|-----------|-------|
| guide | 0.25 |
| warn | 0.50 |
| block | 0.75 |

### 7.2 Mode Mapping

```
OBSERVE:  pressure < guide
GUIDE:    guide <= pressure < warn
WARN:     warn <= pressure < block
BLOCK:    pressure >= block
```

### 7.3 Destructive Patterns

**9 bash patterns:**

1. `rm -rf` (rm with -r flag combination)
2. `rm --recursive`
3. `rm --force --recursive`
4. `git reset --hard`
5. `git push --force` (or `-f`)
6. `git clean -f`
7. `git checkout .`
8. `chmod 777`
9. `kill -9`

**5 sensitive file patterns:**

1. `.env` (dotenv files)
2. `credentials`
3. `.pem`
4. `.key`
5. `secret`

BLOCK mode only prevents destructive operations. Normal Read/Write/Edit/Bash/Agent actions remain allowed.

### 7.4 Behavioral Suggestions

Built from the last 10 actions:

- **File thrashing:** same file edited >= 3 times in last 10 actions
- **Bash failures:** >= 2 consecutive Bash errors at end of action log
- **Agent spam:** >= 3 Agent calls in last 10 actions (suppressed when GSD workflow is active)

---

## 8. Uncertainty Classification

Default thresholds:

| Parameter | Value |
|-----------|-------|
| min_uncertainty | 0.3 |
| low_entropy_threshold | 0.35 |
| high_entropy_threshold | 0.65 |

Classification logic:

- `uncertainty <= 0.3`: None (too low to classify)
- `task_entropy < 0.35`: "epistemic" (agent lacks knowledge)
- `task_entropy > 0.65`: "aleatoric" (task inherently ambiguous)
- Otherwise: None (entropy in ambiguous zone)

Pressure modulation:

- Epistemic: `uncertainty_pressure * 1.3` (capped at 1.0)
- Aleatoric: `uncertainty_pressure * 0.7`

---

## 9. Goal Coherence

Captured at `warmup_actions` (default 5):

```
initial_task_vector = compute_behavior_vector(actions, initial_known_tools)
```

Computed on each subsequent action:

```
coherence = cosine_similarity(current_vector, initial_task_vector)    in [0, 1]
```

Inverted for pressure:

```
goal_coherence_divergence = 1 - coherence
```

High divergence produces high pressure. Feeds into `signal_pressures["goal_coherence"]` through the standard z-score path with baseline tracking.

Uses `initial_known_tools` (frozen at capture time) to ensure consistent vector dimensionality across the session.

---

## 10. Multi-Agent Pressure Propagation

### 10.1 Graph Structure

Directed graph with typed internal structures:

- `_Node`: `agent_id`, `internal_pressure`, `effective_pressure`, `internal_pressure_vector`, `effective_pressure_vector`
- `_Edge`: `source`, `target`, `trust_weight`

Edges stored as adjacency lists keyed by target (incoming) and source (outgoing).

### 10.2 Scalar Propagation

```
effective = max(internal, damping * weighted_avg(upstream_effective))
```

| Parameter | Value |
|-----------|-------|
| damping | 0.6 |
| max_iterations | 3 |
| convergence_epsilon | 1e-6 |

Propagation terminates early if no node's effective pressure changes by more than epsilon in an iteration.

### 10.3 Vector Propagation (PRS-01)

Each `PressureVector` field (uncertainty, drift, error_rate, cost) is propagated independently:

```
effective_field = max(own_field, damping * weighted_avg(upstream_field))
```

This preserves signal-level causality across agents: downstream agents react to the specific cause of upstream pressure, not just its magnitude.

### 10.4 Coordination SNR (PRS-02)

Signal-to-noise ratio for incoming pressure:

```
snr = confirmed_error_pressure / max(total_incoming_pressure, 0.001)
```

Isolation rule: if `total_incoming > 0.05` AND `snr < snr_threshold` (0.5), use only internal pressure. This prevents noisy upstream signals from contaminating a healthy agent.

### 10.5 Trust Dynamics

**Decay** (when `uncertainty > 0.5`):

```
trust -= 0.05 * uncertainty
```

**Recovery** (when `uncertainty <= 0.5`):

```
trust += 0.02 * (1 - uncertainty)
```

Both clamped to [0.0, 1.0]. Decay-to-recovery ratio = 2.5:1, reflecting that trust is harder to rebuild than to lose.

---

## 11. Predictive Model

| Parameter | Value |
|-----------|-------|
| window | 10 |
| horizon | 5 |

**Linear trend:** OLS slope on last 10 pressure readings, extrapolated by horizon steps.

**Pattern boosts:**

| Pattern | Boost | Trigger |
|---------|-------|---------|
| error_streak | +0.15 | 3+ consecutive errors at end |
| retry_storm | +0.12 | Error rate > 40% in window |
| blind_writes | +0.10 | 2+ writes without a Read |
| thrashing | +0.08 | Same file edited 3+ times |

**Confidence:**

```
c = 0.6 * min(n / W, 1.0) + 0.4 * max(R_squared, 0.0)
```

Where n = number of pressure readings, W = window size. R-squared requires at least 3 observations; below that, fit confidence is 0.

Warning fires only when `c > 0.3` AND `predicted_pressure >= next_threshold`.

---

## 12. Self-Learning Engine

### 12.1 Parameters

| Parameter | Value |
|-----------|-------|
| evaluation_window | 5 |
| threshold_adj_step | 0.02 |
| weight_adj_step | 0.05 |
| min_weight | 0.2 |
| max_threshold_shift | 0.10 |
| min_interventions | 3 |

### 12.2 Adaptive Step

```
multiplier = 1.0 + 2.0 * max(0, ratio - 0.5)
```

Where ratio = same-type outcomes / total outcomes for the transition key. Maximum effective multiplier = 3.0 (at 100% same-type). Minimum = 1.0 (at 50/50).

### 12.3 On Failure

Requires `min_interventions` (3) same-transition failures before adjustments fire.

- Threshold: `+step` (capped at `max_threshold_shift`)
- Weights: `-0.05` per triggering signal (floored so effective weight >= `min_weight`)

### 12.4 On Success

Requires `min_interventions` (3) same-transition successes before adjustments fire.

- Threshold: `-step * 0.5` (capped at `-max_threshold_shift`)
- Weights: `+0.025` per previously-reduced signal (half recovery rate, only if currently negative)

---

## 13. Quality Scoring

**Window:** 30 events.

```
Q = (write_fraction * write_score + bash_fraction * bash_score) * max(0.5, 1 - 0.15 * syntax_errors)
```

Where:

- `write_score = clean_writes / total_writes` (1.0 if no writes)
- `bash_score = 1 - bash_failures / total_bashes` (1.0 if no bashes)
- `write_fraction = total_writes / (total_writes + total_bashes)`
- `bash_fraction = total_bashes / (total_writes + total_bashes)`
- Syntax error penalty multiplier floors at 0.5

**Grade boundaries:**

| Grade | Threshold |
|-------|-----------|
| A | >= 0.90 |
| B | >= 0.80 |
| C | >= 0.70 |
| D | >= 0.50 |
| F | < 0.50 |

---

## 14. Root Cause Analysis

5 detectors, highest-severity returned:

| Detector | Trigger | Severity |
|----------|---------|----------|
| Loop | 2-3 tool sequences repeating >= 3 times | 0.90 |
| Error cascade | >= 2 consecutive errors | `0.50 + 0.10 * error_count` (capped at 1.0) |
| Blind mutation | >= 3 writes without Read | `0.60 + 0.05 * write_count` |
| Stall | 7/8 reads with 0 writes | 0.50 |
| Drift explanation | drift >= 0.2 | `0.40 + 0.50 * drift` |

RCA returns None when `pressure < 0.15` and level is OBSERVE.

---

## 15. Agent Fingerprinting

**EMA alpha:** 0.1 (slow learning for detecting genuine behavioral shifts).

**Divergence computation:**

```
divergence = weighted_mean(JSD(tool_dist) * 2, error_delta * 1, rw_ratio_delta * 0.5)
```

Where:

- JSD = Jensen-Shannon divergence over tool distributions (base-2, normalized to [0, 1])
- `error_delta = |current - baseline| / max(baseline, 0.01)` (capped at 1.0)
- `rw_ratio_delta = |current - baseline| / max(baseline, 0.1) * 0.5` (capped at 1.0)

Requires >= 10 sessions (`sample_count`). Alert threshold: divergence >= 0.2.

---

## 16. Half-Life Temporal Modeling

**Success rate decay:**

```
P(t) = exp(-ln(2) * t / half_life)
```

Where t = action count. Returns 1.0 at t=0, 0.5 at t=half_life, approaching 0 asymptotically.

**Half-life estimation:**

```
half_life = max(min_hl, avg_session_length * max(0.3, 1 - avg_error_rate))
```

| Parameter | Default |
|-----------|---------|
| min_half_life | 10.0 actions |
| half_life_min_samples | 3 sessions |
| half_life_lookahead_actions | 10 |
| half_life_success_threshold | 0.5 |

---

## 17. Reliability Metrics

**Calibration score:**

```
cal = (1 - error_rate) * (0.5 + 0.5 * hedging_rate)
```

Result in [0, 1]. High calibration indicates verbal caution paired with good execution.

**Verbal-Behavioral Divergence (VBD):**

```
fires when: (pressure - hedging_rate) > 0.4
```

When VBD fires, ResponseMode is forced to at least GUIDE regardless of computed pressure.

**Hedging phrases:** 27 markers detected, including: "maybe", "might", "could", "unclear", "unsure", "uncertain", "depends", "possibly", "perhaps", "ambiguous", "probably", "roughly", "approximately", "not sure", "i think", "i believe", "seems like", "appears to", "might be", "not certain", "hard to say", "difficult to determine", "it's possible", "it may", "not clear", "may be", "could be".

---

## 18. Policy Engine

**Rule structure:** `Rule(name, [PolicyCondition(field, op, value)], PolicyAction(action, message))`

**Operators:** `>=`, `<=`, `>`, `<`, `==`, `!=`

**Fields:** `pressure`, `uncertainty`, `drift`, `error_rate`, `token_usage`, `cost`, `calibration_score`

**Evaluation:** `evaluate(vitals: VitalsSnapshot, pressure: float) -> list[PolicyAction]`

All conditions within a rule are AND-joined. All matching rules return their actions.

**Guardrail decorator:**

```python
@guardrail(engine, agent_id, threshold=0.5)
```

Blocks synchronous and asynchronous functions when agent pressure >= threshold. Raises `SomaBlocked`.

---

## 19. Task Complexity Estimation

```
score = 0.40 * length_score + 0.35 * ambiguity_score + 0.25 * dependency_score
```

**Components:**

- `length_score = min(1.0, log1p(len(text)) / log1p(2000))`
- `ambiguity_score = min(1.0, marker_hits / max(len(words), 1) * 20)`
- `dependency_score = min(1.0, dep_count / 5.0)`

**13 ambiguity markers:** "maybe", "might", "could", "unclear", "unsure", "uncertain", "depends", "possibly", "perhaps", "ambiguous", "complex", "complicated", "not sure".

**10 dependency markers:** "depends on", "requires", "need to", "need a", "first ", "after ", "before ", "prerequisite", "blocked by", "waiting for".

**Threshold reduction:** When `score > 0.5`:

```
reduction = 0.4 * (score - 0.5)    # up to 0.20
```

Applied to guide, warn, and block thresholds (each floored at 0.10).

---

## 20. Pattern Detection

### 20.1 Negative Patterns

| # | Pattern | Trigger | Severity | Suppressed In |
|---|---------|---------|----------|---------------|
| 1 | blind_edits | >= 3 edits without Read in context (checks last 30 actions for reads) | warning | -- |
| 2 | bash_failures | >= 2 consecutive Bash errors at end | warning | -- |
| 3 | error_rate | >= 30% in last 5+ actions | warning | -- |
| 4 | thrashing | Same file >= 3 edits in last 10 | warning | -- |
| 5 | agent_spam | >= 3 Agent calls in last 10 | info | plan, discuss |
| 6 | research_stall | 7/8 reads, 0 writes in last 8 | info | plan, discuss |
| 7 | no_checkin | 30+ actions, 15+ mutations, 0 user interactions in last 30 | info | execute, plan |

### 20.2 Positive Patterns

| Pattern | Trigger |
|---------|---------|
| good_read_edit | 3+ read-before-edit pairs in last 20 actions |
| good_clean_streak | 10+ error-free actions |

Positive patterns only emitted when no negative patterns are detected.

**Output:** Maximum 3 results, sorted by severity. Workflow-aware suppression via `workflow_mode` parameter.

---

## 21. Findings Collector

Priority levels and their sources:

| Priority | Category | Trigger |
|----------|----------|---------|
| 0 | status | WARN or BLOCK mode active |
| 0 | quality | Grade D or F (with >= 3 events) |
| 1 | predict | Escalation predicted with confidence > 0.3 |
| 1 | pattern | Negative behavioral patterns detected |
| 1 | scope | Scope drift >= 0.7 with explanation |
| 1 | rca | Root cause analysis when not in OBSERVE |
| 2 | positive | Positive behavioral patterns |
| 2 | fingerprint | Fingerprint divergence >= 0.3 |
| 2 | scope | Scope drift >= 0.5 with explanation |
| 2 | quality | Grade C |
| 2 | rca | Root cause analysis while in OBSERVE |

Results sorted by priority (critical first).

---

## 22. System Constants Table

| Constant | Value | Location |
|----------|-------|----------|
| Ring buffer capacity | 10 | `engine.py` |
| EMA alpha (baseline) | 0.15 | `baseline.py` |
| EMA alpha (fingerprint) | 0.1 | `fingerprint.py` |
| Baseline min_samples | 10 | `baseline.py` |
| Baseline min_std | 0.05 | `pressure.py` |
| Baseline default std (uninitialized) | 0.1 | `baseline.py` |
| Baseline default: uncertainty | 0.05 | `baseline.py` |
| Baseline default: drift | 0.05 | `baseline.py` |
| Baseline default: error_rate | 0.01 | `baseline.py` |
| Baseline default: cost | 0.01 | `baseline.py` |
| Baseline default: token_usage | 0.01 | `baseline.py` |
| Sigmoid clamp center | 3.0 | `vitals.py` |
| Sigmoid clamp upper bound | 6.0 | `vitals.py` |
| Aggregate blend: mean weight | 0.70 | `pressure.py` |
| Aggregate blend: max weight | 0.30 | `pressure.py` |
| Error-rate floor onset | 0.50 | `pressure.py` |
| Error-rate floor base | 0.40 | `pressure.py` |
| Error-rate floor scale | 0.40 | `pressure.py` |
| Signal floor: error_rate threshold | 0.3 | `engine.py` |
| Signal floor: retry_rate threshold | 0.3 | `engine.py` |
| Weight: uncertainty | 2.0 | `pressure.py` |
| Weight: drift | 1.8 | `pressure.py` |
| Weight: error_rate | 1.5 | `pressure.py` |
| Weight: goal_coherence | 1.5 | `pressure.py` |
| Weight: cost | 1.0 | `pressure.py` |
| Weight: token_usage | 0.8 | `pressure.py` |
| Threshold: guide | 0.25 | `guidance.py` |
| Threshold: warn | 0.50 | `guidance.py` |
| Threshold: block | 0.75 | `guidance.py` |
| Graph damping | 0.6 | `graph.py` |
| Graph max_iterations | 3 | `graph.py` |
| Graph convergence epsilon | 1e-6 | `graph.py` |
| Graph SNR threshold | 0.5 | `graph.py` |
| Trust decay rate | 0.05 | `graph.py` |
| Trust recovery rate | 0.02 | `graph.py` |
| Trust decay:recovery ratio | 2.5:1 | `graph.py` |
| Predictor window | 10 | `predictor.py` |
| Predictor horizon | 5 | `predictor.py` |
| Prediction confidence threshold | 0.3 | `predictor.py` |
| Pattern boost: error_streak | 0.15 | `predictor.py` |
| Pattern boost: retry_storm | 0.12 | `predictor.py` |
| Pattern boost: blind_writes | 0.10 | `predictor.py` |
| Pattern boost: thrashing | 0.08 | `predictor.py` |
| Learning: evaluation_window | 5 | `learning.py` |
| Learning: threshold_adj_step | 0.02 | `learning.py` |
| Learning: weight_adj_step | 0.05 | `learning.py` |
| Learning: min_weight | 0.2 | `learning.py` |
| Learning: max_threshold_shift | 0.10 | `learning.py` |
| Learning: min_interventions | 3 | `learning.py` |
| Learning: success recovery multiplier | 0.5 | `learning.py` |
| Learning: adaptive step max multiplier | 3.0 | `learning.py` |
| Quality window | 30 | `quality.py` |
| Quality syntax error penalty | 0.15 per error | `quality.py` |
| Quality penalty floor | 0.5 | `quality.py` |
| Grade A threshold | 0.90 | `quality.py` |
| Grade B threshold | 0.80 | `quality.py` |
| Grade C threshold | 0.70 | `quality.py` |
| Grade D threshold | 0.50 | `quality.py` |
| RCA loop severity | 0.90 | `rca.py` |
| RCA error cascade base severity | 0.50 | `rca.py` |
| RCA error cascade increment | 0.10 per error | `rca.py` |
| RCA blind mutation base severity | 0.60 | `rca.py` |
| RCA blind mutation increment | 0.05 per write | `rca.py` |
| RCA stall severity | 0.50 | `rca.py` |
| RCA drift base severity | 0.40 | `rca.py` |
| RCA drift scale | 0.50 | `rca.py` |
| Fingerprint min sessions for divergence | 10 | `fingerprint.py` |
| Fingerprint divergence alert threshold | 0.2 | `fingerprint.py` |
| Fingerprint JSD weight | 2.0 | `fingerprint.py` |
| Fingerprint error_delta weight | 1.0 | `fingerprint.py` |
| Fingerprint rw_ratio_delta weight | 0.5 | `fingerprint.py` |
| Half-life min_half_life | 10.0 | `halflife.py` |
| Half-life error penalty floor | 0.3 | `halflife.py` |
| VBD threshold | 0.4 | `reliability.py` |
| Hedging phrase count | 27 | `reliability.py` |
| Calibration min_samples | 3 | `engine.py` |
| Uncertainty classification: min_uncertainty | 0.3 | `vitals.py` |
| Uncertainty classification: low_entropy_threshold | 0.35 | `vitals.py` |
| Uncertainty classification: high_entropy_threshold | 0.65 | `vitals.py` |
| Epistemic pressure multiplier | 1.3 | `engine.py` |
| Aleatoric pressure multiplier | 0.7 | `engine.py` |
| Goal coherence warmup_actions | 5 | `engine.py` |
| Task complexity: weight_length | 0.40 | `vitals.py` |
| Task complexity: weight_ambiguity | 0.35 | `vitals.py` |
| Task complexity: weight_dependency | 0.25 | `vitals.py` |
| Task complexity: length reference | 2000 chars | `vitals.py` |
| Task complexity: dependency normalization | 5.0 | `vitals.py` |
| Task complexity: ambiguity scale | 20.0 | `vitals.py` |
| Task complexity: threshold reduction onset | 0.5 | `engine.py` |
| Task complexity: max threshold reduction | 0.20 | `engine.py` |
| Task complexity: threshold floor | 0.10 | `engine.py` |
| Ambiguity markers count | 13 | `vitals.py` |
| Dependency markers count | 10 | `vitals.py` |
| Destructive bash patterns count | 9 | `guidance.py` |
| Sensitive file patterns count | 5 | `guidance.py` |
| Baseline integrity: min_samples | 10 | `engine.py` |
| Baseline integrity: error_ratio | 2.0 | `engine.py` |
| Baseline integrity: min_error_rate | 0.20 | `engine.py` |
| Agent eviction TTL | 3600 seconds | `engine.py` |
| Default budget: tokens | 100,000 | `engine.py` |

---

## 23. Formal Properties

**Boundedness.** All signals, pressures, and scores are in [0, 1]. The sigmoid clamp guarantees this for derived values. Resource vitals are explicitly clamped. Aggregate pressure is clamped via `min(1.0, result)`.

**Determinism.** The same action sequence fed to the same engine configuration produces identical vitals, pressures, and mode transitions. No randomness is used in any computation. Timestamps affect only agent eviction, not behavioral signals.

**Monotonic escalation.** A single action can escalate the response mode by multiple levels (e.g., OBSERVE to BLOCK) if pressure crosses multiple thresholds in one step. There is no single-step escalation limit.

**Graceful de-escalation.** Mode drops one level at a time as pressure decreases, governed by the continuous mapping of `pressure_to_mode()`. A sudden pressure drop can cross multiple thresholds downward in one step (the mode mapping is stateless -- it depends only on current pressure, not previous mode).

**Convergence.** The learning engine is bounded by `max_threshold_shift` (+/-0.10) for threshold adjustments. Signal weight adjustments are floored at `min_weight` (0.2). These bounds prevent the system from learning itself into permanent silence or permanent alarm.

**Stability.** Graph propagation converges within 3 iterations due to the damping factor (0.6 < 1.0) and the epsilon threshold (1e-6). Each iteration can only increase effective pressure (max operation), and the damped upstream contribution is strictly less than the source, guaranteeing convergence.
