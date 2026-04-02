# SOMA Technical Reference — Version 0.6.0 | April 2026

This document is the formal technical specification for the SOMA behavioral monitoring system. It specifies every formula, constant, algorithm, and system property. All values are verified from source code and represent the canonical reference for implementation behavior.

---

## 1. System Overview

SOMA is a discrete event monitoring system that observes AI agent actions in real-time, computes behavioral pressure from multiple vital signals, detects failure patterns, enforces safety reflexes, and injects proprioceptive feedback into the agent's environment.

**Computational model:**

- Discrete event model, O(n) per action where n = ring buffer size (default 10)
- Deterministic: same action sequence produces identical output
- All signals and pressures bounded to [0, 1]
- Grace period linearly ramps pressure for the first 10 actions (cold-start protection)
- Core computation is sub-millisecond per action, no network requests
- Mirror SEMANTIC mode optionally calls external LLM (~$0.001/call, 3s timeout)

---

## 2. Core Pipeline

The `record_action()` method executes a sequential pipeline for each action:

| Step | Operation | Description |
|------|-----------|-------------|
| 1 | Tool tracking | Append `action.tool_name` to `known_tools` if new |
| 2 | Ring buffer append | Push action into fixed-capacity ring buffer (capacity=10) |
| 3 | Action count increment | Increment `action_count` and update `_last_active` timestamp |
| 4 | Task complexity capture | On first action, estimate task complexity from output text if not already set from system prompt |
| 5 | Initial task vector capture | At `warmup_actions` (default 5), snapshot `initial_known_tools` and compute `initial_task_vector` |
| 6 | Uncertainty computation | Composite from retry rate, tool call deviation, format deviation, entropy deviation |
| 7 | Drift computation | Cosine distance from baseline behavior vector; update baseline vector every 10 actions |
| 8 | Time anomaly boost | If action duration exceeds 2σ above mean, boost uncertainty (capped at +0.3) |
| 9 | Duration baseline update | Update EMA baseline for action duration |
| 10 | Resource vitals | Compute error_rate, token_usage, cost from budget state and ring buffer |
| 11 | Drift mode determination | Classify drift as DIRECTIVE or INFORMATIONAL based on confirmatory signals |
| 12 | Baseline updates | Update EMA baselines for uncertainty, drift, error_rate, tool_calls, entropy |
| 13 | Per-signal pressure | Z-score-based sigmoid pressure for each signal; apply absolute floors |
| 14 | Uncertainty classification | Classify as epistemic/aleatoric; apply pressure modulation |
| 15 | Goal coherence | After warmup, cosine similarity to initial task vector → divergence pressure |
| 16 | Context exhaustion | Sigmoid of cumulative token ratio |
| 17 | Burn rate pressure | If budget health < 1.0, compute projected overshoot |
| 18 | Learning weight adjustment | Apply cumulative weight adjustments from learning engine |
| 19 | Upstream vector influence | Boost per-signal pressures from upstream agents (damped) |
| 20 | Aggregate pressure | Blend weighted mean (0.7) and max (0.3); apply error-rate floor |
| 21 | Grace period ramp | Linear scale: `pressure × (action_count / min_samples)` |
| 22 | Graph propagation | Set internal pressure/vector, propagate through trust-weighted graph |
| 23 | Trust dynamics | Decay trust when uncertainty > 0.5; recover when ≤ 0.5 |
| 24 | Reliability metrics | Hedging rate, calibration score, VBD detection |
| 25 | Task complexity adjustment | Lower thresholds by up to 0.20 for complex tasks |
| 26 | Mode determination | Map effective pressure to ResponseMode; emit events; evaluate learning; auto-export |

---

## 3. Signal Computation

### 3.1 Uncertainty

Composite uncertainty score in [0, 1]:

```
U = 0.30 × retry_rate
  + 0.25 × sigmoid_clamp(tool_call_deviation)
  + 0.20 × format_deviation
  + 0.25 × sigmoid_clamp(entropy_deviation)
```

Components:

- `retry_rate = retried_actions / total_actions` (0.0 for empty)
- `tool_call_deviation = |len(actions) − baseline_avg| / baseline_std` (0 if std = 0)
- `format_deviation = missing_expected_lines / total_expected_lines` (0 if no expected format)
- `entropy_deviation = |current_entropy − baseline_entropy| / baseline_entropy_std` (0 if std = 0)

### 3.2 Output Entropy

Normalized Shannon entropy over character bigrams:

```
bigrams = [text[i:i+2] for i in range(len(text) − 1)]
H = −sum(p_i × log₂(p_i)) / log₂(total_bigrams)
```

Returns 0.0 for text shorter than 2 characters.

### 3.3 Behavioral Drift

```
D = 1 − cosine_similarity(current_vector, baseline_vector)
```

Behavior vector dimensions:

| Index | Feature | Normalization |
|-------|---------|---------------|
| 0 | avg_tool_calls | Always 1.0 |
| 1 | avg_output_len | `mean(len(output_text)) / 1000.0` |
| 2 | avg_response_time | `mean(duration_sec)` |
| 3 | pattern_entropy | Shannon entropy over tool name frequencies |
| 4..n | tool_distribution | Fraction of actions using each known tool |

Baseline vector updated every 10 actions. Cosine similarity returns 0.0 for zero-magnitude vectors.

### 3.4 Drift Mode

Returns `DIRECTIVE` when ALL of:
- `drift > 0.3`
- At least one confirmatory signal: `error_rate > baseline`, OR `uncertainty > 0.3`, OR `progress_stalled`

Otherwise returns `INFORMATIONAL`. In INFORMATIONAL mode, the drift weight is zeroed in aggregate pressure.

### 3.5 Resource Vitals

```
error_rate = errors_in_window / actions_in_window    [0, 1]
token_usage = tokens_used / token_limit              [0, 1]
cost = cost_spent / cost_budget                      [0, 1]
```

### 3.6 Goal Coherence

Captured at `warmup_actions` (5):

```
initial_task_vector = compute_behavior_vector(actions, initial_known_tools)
```

Each subsequent action:

```
coherence = cosine_similarity(current_vector, initial_task_vector)
goal_coherence_divergence = 1 − coherence
```

Uses `initial_known_tools` (frozen at capture) for consistent vector dimensionality.

### 3.7 Context Exhaustion

```
context_exhaustion = sigmoid((cumulative_tokens / context_window − 0.5) / 0.15)
```

Fires when context window is >50% consumed, with steep sigmoid transition.

---

## 4. Normalization

### 4.1 Sigmoid Clamp

```
sigmoid_clamp(x):
    if x ≤ 0:  return 0.0
    if x > 6:   return 1.0
    else:        return 1 / (1 + exp(−x + 3))
```

Center at x = 3, effective transition range [0, 6].

### 4.2 Signal Pressure

```
z = (current − baseline_mean) / max(baseline_std, 0.05)
signal_pressure = sigmoid_clamp(z)
```

Minimum standard deviation floor of 0.05 prevents extreme z-scores when variance is near zero.

---

## 5. Pressure Aggregation

### 5.1 Blend Formula

```
P = 0.7 × (Σ(w_i × p_i) / Σ(w_i)) + 0.3 × max(p_i)
```

Only signals with weight > 0 included. Returns 0.0 if no signals have positive weight. Drift weight zeroed when drift mode is INFORMATIONAL.

### 5.2 Error-Rate Aggregate Floor

Linear ramp preventing baseline normalization of errors. When error_rate pressure `er_p ∈ [0.20, 1.00]`:

```
floor = 0.10 + 0.60 × (er_p − 0.20) / 0.80
P = max(P, floor)
```

Floor mapping:

| Error Pressure | Floor | Typical Mode |
|---------------|-------|--------------|
| 0.20 | 0.10 | OBSERVE |
| 0.40 | 0.25 | GUIDE entry |
| 0.60 | 0.40 | GUIDE |
| 0.80 | 0.55 | WARN |
| 1.00 | 0.70 | WARN (capped) |

This replaces the v0.5.0 step function (onset at 0.50, floor=0.40) that caused bimodal pressure distributions.

### 5.3 Signal-Level Floors

Applied before aggregation:

- `error_rate > 0.3`: `error_pressure = max(error_pressure, error_rate)`
- `retry_rate > 0.3`: `uncertainty_pressure = max(uncertainty_pressure, retry_rate)`

### 5.4 Signal Weights

| Signal | Weight |
|--------|--------|
| uncertainty | 2.0 |
| drift | 1.8 |
| error_rate | 1.5 |
| goal_coherence | 1.5 |
| context_exhaustion | 1.5 |
| cost | 1.0 |
| token_usage | 0.8 |

---

## 6. Baseline Learning (EMA)

### 6.1 Update Rules

```
mean:     μ_{t+1} = 0.15 × x_t + 0.85 × μ_t
variance: v_{t+1} = 0.15 × (x_t − μ_t)² + 0.85 × v_t
```

Alpha = 0.15. Effective half-life ≈ 4.3 observations. First observation initializes mean directly; variance initialized to 0.0.

### 6.2 Cold-Start Blending

```
blend = min(count / 10, 1.0)
result = blend × computed + (1 − blend) × default
```

| Signal | Default |
|--------|---------|
| uncertainty | 0.05 |
| drift | 0.05 |
| error_rate | 0.01 |
| cost | 0.01 |
| token_usage | 0.01 |

### 6.3 Standard Deviation

```
get_std() = max(sqrt(variance), 1e-9)
```

Returns 0.1 for uninitialized signals.

### 6.4 Grace Period

For the first `min_samples` (10) actions, effective pressure is linearly ramped:

```
effective_pressure = computed_pressure × (action_count / min_samples)
```

This replaces the v0.5.0 behavior of forcing pressure to 0.0, which caused a cliff at action 11. The linear ramp ensures graduated pressure escalation: OBSERVE → GUIDE → WARN transitions happen smoothly.

Baselines are inherited across sessions — new sessions get a warm start from the most active prior session.

---

## 7. Guidance System

### 7.1 Default Thresholds

| Threshold | Default | Claude Code |
|-----------|---------|-------------|
| guide | 0.25 | 0.40 |
| warn | 0.50 | 0.60 |
| block | 0.75 | 0.80 |

### 7.2 Mode Mapping

```
OBSERVE:  pressure < guide
GUIDE:    guide ≤ pressure < warn
WARN:     warn ≤ pressure < block
BLOCK:    pressure ≥ block
```

BLOCK mode only prevents destructive operations. Normal Read/Write/Edit/Bash/Agent actions remain allowed.

### 7.3 Destructive Patterns

**9 bash patterns:** `rm -rf`, `rm --recursive`, `rm --force --recursive`, `git reset --hard`, `git push --force` (or `-f`), `git clean -f`, `git checkout .`, `chmod 777`, `kill -9`

**5 sensitive file patterns:** `.env`, `credentials`, `.pem`, `.key`, `secret`

### 7.4 Behavioral Suggestions

Built from last 10 actions:

- **File thrashing:** same file edited ≥ 3 times
- **Bash failures:** ≥ 2 consecutive Bash errors
- **Agent spam:** ≥ 3 Agent calls (suppressed when GSD workflow is active)

---

## 8. Uncertainty Classification

| Parameter | Value |
|-----------|-------|
| min_uncertainty | 0.3 |
| low_entropy_threshold | 0.35 |
| high_entropy_threshold | 0.65 |

- `uncertainty ≤ 0.3`: None
- `task_entropy < 0.35`: epistemic (agent lacks knowledge) → pressure × 1.3
- `task_entropy > 0.65`: aleatoric (inherent ambiguity) → pressure × 0.7
- Otherwise: None

---

## 9. Multi-Agent Pressure Propagation

### 9.1 Graph Structure

- `_Node`: agent_id, internal_pressure, effective_pressure, internal/effective pressure vectors
- `_Edge`: source, target, trust_weight

### 9.2 Scalar Propagation

```
effective = max(internal, damping × weighted_avg(upstream_effective))
```

| Parameter | Value |
|-----------|-------|
| damping | 0.6 |
| max_iterations | 3 |
| convergence_epsilon | 1e-6 |

### 9.3 Vector Propagation (PRS-01)

Each PressureVector field (uncertainty, drift, error_rate, cost) propagated independently:

```
effective_field = max(own_field, damping × weighted_avg(upstream_field))
```

### 9.4 Coordination SNR (PRS-02)

```
snr = confirmed_error_pressure / max(total_incoming_pressure, 0.001)
```

Isolation: if `total_incoming > 0.05` AND `snr < 0.5`, use only internal pressure.

### 9.5 Trust Dynamics

**Decay** (uncertainty > 0.5): `trust -= 0.05 × uncertainty`
**Recovery** (uncertainty ≤ 0.5): `trust += 0.02 × (1 − uncertainty)`

Clamped [0, 1]. Decay:recovery ratio = 2.5:1.

---

## 10. Predictive Model

| Parameter | Value |
|-----------|-------|
| window | 10 |
| horizon | 5 |

**Linear trend:** OLS slope on last 10 pressure readings, extrapolated by horizon.

**Pattern boosts:**

| Pattern | Boost | Trigger |
|---------|-------|---------|
| error_streak | +0.15 | 3+ consecutive errors |
| retry_storm | +0.12 | Error rate > 40% |
| blind_writes | +0.10 | 2+ writes without Read |
| thrashing | +0.08 | Same file edited 3+ times |

**Confidence:**

```
c = 0.6 × min(n / W, 1.0) + 0.4 × max(R², 0.0)
```

R² requires ≥ 3 observations. Warning fires when `c > 0.3` AND `predicted ≥ next_threshold`.

**Cross-session matching:** Loads past trajectories from `history.jsonl`, matches via cosine similarity. Blends 60% current trend + 40% historical match.

---

## 11. Mirror: Proprioceptive Feedback

### 11.1 Mode Selection

| Condition | Mode | Cost |
|-----------|------|------|
| pressure < 0.15 | None (silence) | $0 |
| 0.15 ≤ pressure < 0.40, pattern match | PATTERN | $0 |
| 0.15 ≤ pressure < 0.40, no pattern | STATS | $0 |
| pressure ≥ 0.40 + drift/VBD | SEMANTIC | ~$0.001 |

### 11.2 PATTERN Mode

Lookup in pattern_db by current behavior key. Reuse cached context if `success_rate ≥ 60%` and `attempts ≥ 2`.

### 11.3 STATS Mode

Format raw numbers: action count, error count/total, reads-before-writes ratio, top pressure signals. Pure data, no interpretation. ~40 tokens, wrapped in `--- session context ---` markers.

### 11.4 SEMANTIC Mode

External LLM call (Gemini Flash / Haiku / GPT-4o-mini). ~80 token budget, 3s timeout. Generates 1–2 sentence factual behavioral observation. Fallback to PATTERN/STATS on failure.

### 11.5 Self-Learning

```
inject context → track_injection(key, text, pressure)
    ...3 actions...
evaluate_pending():
    pressure dropped ≥ IMPROVEMENT_RATIO × pressure_at_injection?
        YES → success, cache in pattern_db
        NO  → failure, prune if success_rate < 0.30 after 5 attempts
```

Pattern DB persisted at `~/.soma/patterns.json`.

### 11.6 Delivery

stdout = tool response content (agent sees as environment data). stderr = system diagnostics (operator sees). Claude Code hooks route stdout into the conversation. This is the key mechanism: LLMs ignore instructions but process environmental data.

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
multiplier = 1.0 + 2.0 × max(0, ratio − 0.5)
```

Max effective multiplier = 3.0 (at 100% same-type).

### 12.3 On Failure (3+ same-transition failures)

- Threshold: `+step` (capped at max_threshold_shift)
- Weights: `−0.05` per triggering signal (floored at min_weight)

### 12.4 On Success (3+ same-transition successes)

- Threshold: `−step × 0.5` (capped at −max_threshold_shift)
- Weights: `+0.025` per previously-reduced signal

---

## 13. Quality Scoring

**Window:** 30 events.

```
Q = (write_fraction × write_score + bash_fraction × bash_score) × max(0.5, 1 − 0.15 × syntax_errors)
```

- `write_score = clean_writes / total_writes`
- `bash_score = 1 − bash_failures / total_bashes`
- Syntax error penalty floors at 0.5

**Validation:** Python via py_compile + ruff (F rules). JavaScript via node --check.

| Grade | Threshold |
|-------|-----------|
| A | ≥ 0.90 |
| B | ≥ 0.80 |
| C | ≥ 0.70 |
| D | ≥ 0.50 |
| F | < 0.50 |

---

## 14. Root Cause Analysis

| Detector | Trigger | Severity |
|----------|---------|----------|
| Loop | 2-3 tool sequences repeating ≥ 3 times | 0.90 |
| Error cascade | ≥ 2 consecutive errors | `0.50 + 0.10 × count` (cap 1.0) |
| Blind mutation | ≥ 3 writes without Read | `0.60 + 0.05 × count` |
| Stall | 7/8 reads with 0 writes | 0.50 |
| Drift | drift ≥ 0.2 | `0.40 + 0.50 × drift` |

RCA returns None when pressure < 0.15 and level is OBSERVE.

---

## 15. Agent Fingerprinting

**EMA alpha:** 0.1.

**Divergence:**

```
divergence = weighted_mean(JSD(tool_dist) × 2, error_delta × 1, rw_ratio_delta × 0.5)
```

- JSD = Jensen-Shannon divergence over tool distributions (base-2, [0, 1])
- `error_delta = |current − baseline| / max(baseline, 0.01)` (cap 1.0)
- `rw_ratio_delta = |current − baseline| / max(baseline, 0.1) × 0.5` (cap 1.0)

Requires ≥ 10 sessions. Alert threshold: divergence ≥ 0.2.

---

## 16. Half-Life Temporal Modeling

```
P(t) = exp(−ln(2) × t / half_life)
```

**Half-life estimation:**

```
half_life = max(min_hl, avg_session_length × max(0.3, 1 − avg_error_rate))
```

| Parameter | Default |
|-----------|---------|
| min_half_life | 10.0 actions |
| half_life_min_samples | 3 sessions |
| half_life_lookahead_actions | 10 |
| half_life_success_threshold | 0.5 |

---

## 17. Reliability Metrics

**Calibration:** `cal = (1 − error_rate) × (0.5 + 0.5 × hedging_rate)` [0, 1]

**VBD (Verbal-Behavioral Divergence):** Fires when `(pressure − hedging_rate) > 0.4`. Forces ResponseMode to at least GUIDE.

**27 hedging phrases:** "maybe", "might", "could", "unclear", "unsure", "uncertain", "depends", "possibly", "perhaps", "ambiguous", "probably", "roughly", "approximately", "not sure", "i think", "i believe", "seems like", "appears to", "might be", "not certain", "hard to say", "difficult to determine", "it's possible", "it may", "not clear", "may be", "could be".

---

## 18. Policy Engine

**Rule structure:** `Rule(name, [PolicyCondition(field, op, value)], PolicyAction(action, message))`

**Operators:** `>=`, `<=`, `>`, `<`, `==`, `!=`

**Fields:** pressure, uncertainty, drift, error_rate, token_usage, cost, calibration_score

All conditions AND-joined. All matching rules fire.

**Guardrail decorator:**

```python
@guardrail(engine, agent_id, threshold=0.5)
```

Blocks sync/async functions when pressure ≥ threshold. Raises `SomaBlocked`.

---

## 19. Task Complexity

```
score = 0.40 × length_score + 0.35 × ambiguity_score + 0.25 × dependency_score
```

- `length_score = min(1.0, log1p(len(text)) / log1p(2000))`
- `ambiguity_score = min(1.0, marker_hits / max(len(words), 1) × 20)`
- `dependency_score = min(1.0, dep_count / 5.0)`

**13 ambiguity markers.** **10 dependency markers.**

**Threshold reduction** (when score > 0.5):

```
reduction = 0.4 × (score − 0.5)    # up to 0.20
```

Applied to guide, warn, block thresholds (each floored at 0.10).

---

## 20. Pattern Detection

### 20.1 Negative Patterns

| Pattern | Trigger | Severity | Suppressed In |
|---------|---------|----------|---------------|
| blind_edits | ≥ 3 edits without Read (last 30) | warning | — |
| bash_failures | ≥ 2 consecutive Bash errors | warning | — |
| error_rate | ≥ 30% in last 5+ actions | warning | — |
| thrashing | Same file ≥ 3 edits in last 10 | warning | — |
| agent_spam | ≥ 3 Agent calls in last 10 | info | plan, discuss |
| research_stall | 7/8 reads, 0 writes in last 8 | info | plan, discuss |
| no_checkin | 30+ actions, 15+ mutations, 0 user interactions | info | execute, plan |

### 20.2 Positive Patterns

| Pattern | Trigger |
|---------|---------|
| good_read_edit | 3+ read-before-edit pairs in last 20 |
| good_clean_streak | 10+ error-free actions |

Max 3 results, sorted by severity. Workflow-aware suppression.

---

## 21. Findings Collector

| Priority | Category | Trigger |
|----------|----------|---------|
| 0 | status | WARN or BLOCK mode |
| 0 | quality | Grade D or F (≥ 3 events) |
| 1 | predict | Escalation predicted (confidence > 0.3) |
| 1 | pattern | Negative patterns detected |
| 1 | scope | Scope drift ≥ 0.7 |
| 1 | rca | Root cause when not OBSERVE |
| 2 | positive | Positive patterns |
| 2 | fingerprint | Divergence ≥ 0.3 |
| 2 | scope | Scope drift ≥ 0.5 |
| 2 | quality | Grade C |
| 2 | rca | Root cause in OBSERVE |

---

## 22. Task Tracking

**Phase detection** (tool patterns over last 10 actions):
- Research: Read, Grep, Glob, WebSearch, WebFetch
- Implement: Write, Edit, NotebookEdit
- Test: Bash
- Debug: error rate > 30%

**Scope drift:** After 5 file touches, initial focus captured. Subsequent actions compared via set overlap. Score [0, 1].

---

## 23. Subagent Monitoring

Logs at `~/.soma/subagents/{parent_id}/{sub_id}.jsonl`.

**Cascade risk:**

```
if max_subagent_error_rate > 0.3:
    risk = (max_error − 0.3) / 0.7
else:
    risk = 0.0
```

Propagates to parent pressure via PressureGraph.

---

## 24. Budget

**MultiBudget** dimensions: tokens, cost_usd.

```
spend(**kwargs)          → add to spent, clamp at limit
remaining(dim)           → limit − spent
utilization(dim)         → spent / limit
health()                 → min(remaining/limit) across all dims
burn_rate(dim)           → spent / elapsed_seconds
projected_overshoot()    → (spend_per_step × total) − limit
is_exhausted()           → health() == 0
```

Default budget: 100,000 tokens. Exhaustion raises `SomaBudgetExhausted`.

---

## 25. Persistence

**Atomic write:** serialize → acquire exclusive lock (fcntl.LOCK_EX) → write temp → fsync → atomic rename → release lock.

**Load:** shared lock (fcntl.LOCK_SH) → parse JSON → rebuild engine + agents.

Fallback to direct write on non-POSIX systems.

---

## 26. Hook Pipeline

| Hook | When | Exit Codes |
|------|------|------------|
| PreToolUse | Before tool executes | 0=allow, 2=block |
| PostToolUse | After tool executes | 0 (always) |
| Notification | On mode change | 0 |
| Stop | Session end | 0 |
| Statusline | Real-time UI update | 0 |

**Platform adapters:** ClaudeCodeAdapter (native), CursorAdapter, WindsurfAdapter (HOOK-01 protocol).

---

## 27. Exporters

**OpenTelemetry** (optional `otel` extra):
- Gauges: pressure, uncertainty, drift, error_rate, context_usage
- Counters: actions.total, actions.errors
- Spans: `soma.action.{tool_name}`
- Local providers, never touches global state. No-op if SDK not installed.

**Webhooks:** Fire-and-forget HTTP POST on WARN/BLOCK/policy/budget/context events. Daemon threads, 3s timeout, retry once.

**Session reports:** Markdown to `~/.soma/reports/`. Quality = 100 − error_rate% − mode_penalty (OBSERVE=0, GUIDE=10, WARN=25, BLOCK=50).

---

## 28. System Constants

| Constant | Value | Location |
|----------|-------|----------|
| Ring buffer capacity | 10 | engine.py |
| EMA alpha (baseline) | 0.15 | baseline.py |
| EMA alpha (fingerprint) | 0.1 | fingerprint.py |
| Baseline min_samples | 10 | baseline.py |
| Baseline min_std | 0.05 | pressure.py |
| Baseline default std (uninitialized) | 0.1 | baseline.py |
| Sigmoid clamp center | 3.0 | vitals.py |
| Sigmoid clamp upper bound | 6.0 | vitals.py |
| Aggregate blend: mean weight | 0.70 | pressure.py |
| Aggregate blend: max weight | 0.30 | pressure.py |
| Error floor onset | 0.20 | pressure.py |
| Error floor base | 0.10 | pressure.py |
| Error floor range | 0.60 | pressure.py |
| Error floor cap | 0.70 | pressure.py |
| Signal floor: error_rate threshold | 0.3 | engine.py |
| Signal floor: retry_rate threshold | 0.3 | engine.py |
| Weight: uncertainty | 2.0 | pressure.py |
| Weight: drift | 1.8 | pressure.py |
| Weight: error_rate | 1.5 | pressure.py |
| Weight: goal_coherence | 1.5 | pressure.py |
| Weight: context_exhaustion | 1.5 | pressure.py |
| Weight: cost | 1.0 | pressure.py |
| Weight: token_usage | 0.8 | pressure.py |
| Threshold: guide (default) | 0.25 | guidance.py |
| Threshold: warn (default) | 0.50 | guidance.py |
| Threshold: block (default) | 0.75 | guidance.py |
| Threshold: guide (Claude Code) | 0.40 | hooks |
| Threshold: warn (Claude Code) | 0.60 | hooks |
| Threshold: block (Claude Code) | 0.80 | hooks |
| Graph damping | 0.6 | graph.py |
| Graph max_iterations | 3 | graph.py |
| Graph convergence epsilon | 1e-6 | graph.py |
| Graph SNR threshold | 0.5 | graph.py |
| Trust decay rate | 0.05 | graph.py |
| Trust recovery rate | 0.02 | graph.py |
| Predictor window | 10 | predictor.py |
| Predictor horizon | 5 | predictor.py |
| Prediction confidence threshold | 0.3 | predictor.py |
| Pattern boost: error_streak | 0.15 | predictor.py |
| Pattern boost: retry_storm | 0.12 | predictor.py |
| Pattern boost: blind_writes | 0.10 | predictor.py |
| Pattern boost: thrashing | 0.08 | predictor.py |
| Learning: evaluation_window | 5 | learning.py |
| Learning: threshold_adj_step | 0.02 | learning.py |
| Learning: weight_adj_step | 0.05 | learning.py |
| Learning: min_weight | 0.2 | learning.py |
| Learning: max_threshold_shift | 0.10 | learning.py |
| Learning: min_interventions | 3 | learning.py |
| Quality window | 30 | quality.py |
| Quality syntax penalty | 0.15/error | quality.py |
| Quality penalty floor | 0.5 | quality.py |
| Mirror silence threshold | 0.15 | mirror.py |
| Mirror semantic threshold | 0.40 | mirror.py |
| Mirror eval window | 3 actions | mirror.py |
| Mirror pattern prune threshold | 0.30 | mirror.py |
| Mirror min attempts for prune | 5 | mirror.py |
| Mirror pattern reuse threshold | 0.60 | mirror.py |
| RCA loop severity | 0.90 | rca.py |
| RCA error cascade base | 0.50 | rca.py |
| RCA blind mutation base | 0.60 | rca.py |
| RCA stall severity | 0.50 | rca.py |
| Fingerprint min sessions | 10 | fingerprint.py |
| Fingerprint divergence alert | 0.2 | fingerprint.py |
| Half-life min | 10.0 actions | halflife.py |
| VBD threshold | 0.4 | reliability.py |
| Hedging phrases | 27 | reliability.py |
| Calibration min_samples | 3 | engine.py |
| Epistemic multiplier | 1.3 | engine.py |
| Aleatoric multiplier | 0.7 | engine.py |
| Goal coherence warmup | 5 actions | engine.py |
| Task complexity onset | 0.5 | engine.py |
| Task complexity max reduction | 0.20 | engine.py |
| Threshold floor | 0.10 | engine.py |
| Subagent cascade threshold | 0.3 | subagent_monitor.py |
| Agent eviction TTL | 3600s | engine.py |
| Default budget: tokens | 100,000 | engine.py |
| Webhook timeout | 3s | webhook.py |
| Semantic LLM timeout | 3s | mirror.py |

---

## 29. Formal Properties

**Boundedness.** All signals, pressures, and scores are in [0, 1]. Sigmoid clamp guarantees this for derived values. Resource vitals explicitly clamped. Aggregate pressure clamped via `min(1.0, result)`.

**Determinism.** Same action sequence + same engine configuration = identical output. No randomness in any computation. Timestamps affect only agent eviction.

**Monotonic escalation.** A single action can escalate multiple levels (OBSERVE → BLOCK) if pressure crosses multiple thresholds in one step.

**Graceful de-escalation.** Mode mapping is stateless — depends only on current pressure. Pressure drops can cross multiple thresholds downward in one step.

**Graduated cold-start.** Linear ramp during grace period ensures smooth escalation from silence to monitoring. No cliff behavior at min_samples boundary.

**Convergence.** Graph propagation converges within 3 iterations: damping (0.6 < 1.0) and max operator guarantee strictly decreasing marginal changes.

**Bounded adaptation.** Learning engine capped at ±0.10 threshold shift, weight floor at 0.2. Prevents permanent silence or permanent alarm.

**Non-blocking.** Hook failures never disrupt the host environment. All exceptions caught and logged. Exporters run in daemon threads. Mirror SEMANTIC mode has 3s timeout with fallback.
