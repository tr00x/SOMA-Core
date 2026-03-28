# SOMA Core Technical Reference

> Version 0.1.0 — authoritative reference for engineers integrating or extending SOMA Core.
> All formulas, defaults, and parameter ranges are derived directly from source.

---

## Architecture Overview

### Pipeline

Every `record_action()` call traverses the following stages in order:

```
Action
  │
  ▼
Vitals Computation
  ├─ Uncertainty  (retry rate, tool-call deviation, format deviation, entropy deviation)
  ├─ Drift        (cosine distance from behavior baseline vector)
  ├─ Drift Mode   (INFORMATIONAL or DIRECTIVE)
  └─ Resource Vitals (token_usage, cost, error_rate)
  │
  ▼
Baseline Update (EMA per signal)
  │
  ▼
Per-Signal Pressure (sigmoid-clamped z-score)
  │
  ▼
Aggregate Pressure  (0.7 × weighted_mean + 0.3 × max)
  │
  ▼
PressureGraph       (trust-weighted multi-agent propagation)
  │
  ▼
Escalation Ladder   (threshold comparison → Level)
  │
  ▼
Context Control     (message trimming, tool restriction)
  │
  ▼
Learning Engine     (intervention recording, threshold/weight adaptation)
```

### Module Dependency Graph

```
engine.py
├── types.py          (Action, Level, VitalsSnapshot, AgentConfig, …)
├── vitals.py         (compute_uncertainty, compute_drift, …)
├── baseline.py       (Baseline — EMA)
├── pressure.py       (compute_signal_pressure, compute_aggregate_pressure)
├── graph.py          (PressureGraph)
├── ladder.py         (Ladder)
├── budget.py         (MultiBudget)
├── learning.py       (LearningEngine)
├── events.py         (EventBus)
└── ring_buffer.py    (RingBuffer)

wrap.py               depends on engine.py, recorder.py, types.py
context_control.py    depends on types.py only
persistence.py        depends on engine.py, baseline.py, budget.py, graph.py, learning.py
testing.py            depends on engine.py, types.py
cli/
  main.py             → status.py, replay_cli.py, wizard.py, setup_claude.py
  config_loader.py    → engine.py, types.py
```

### Data Flow

1. Caller creates an `Action` and passes it to `SOMAEngine.record_action(agent_id, action)`.
2. The engine maintains a `RingBuffer[Action]` (capacity=10) per agent; the new action is appended and the full buffer window drives all vitals.
3. Vitals are computed against per-agent `Baseline` (EMA) values; baselines are updated after computation.
4. Per-signal pressures are z-scored and sigmoid-clamped, then aggregated.
5. The agent's internal pressure is written to `PressureGraph`; multi-pass propagation computes effective pressure.
6. During the grace period (first `min_samples=10` actions) effective pressure is forced to 0.
7. Trust edges are decayed or recovered based on uncertainty.
8. `Ladder.evaluate_with_adjustments()` maps effective pressure + budget health → `Level`.
9. If the level changed, an event is emitted and an `InterventionRecord` is created.
10. `LearningEngine.evaluate()` is called; if an older pending record has matured, it is resolved and adjustments may fire.
11. `ActionResult(level, pressure, vitals)` is returned.

---

## Types

### `Action`

Frozen dataclass (`frozen=True, slots=True`). Represents a single agent action.

| Field | Type | Default | Description |
|---|---|---|---|
| `tool_name` | `str` | required | Name of the tool called (e.g. `"bash"`, `"messages.create"`). |
| `output_text` | `str` | required | Text output from the tool. Used for entropy and format-deviation computation. Capped at 1,000 chars inside `wrap.py`. |
| `token_count` | `int` | `0` | Tokens consumed by this action. |
| `cost` | `float` | `0.0` | Monetary cost in USD for this action. |
| `error` | `bool` | `False` | Whether this action produced an error. |
| `retried` | `bool` | `False` | Whether this action was a retry of a previous attempt. |
| `duration_sec` | `float` | `0.0` | Wall-clock duration in seconds. |
| `timestamp` | `float` | `0.0` | Unix timestamp (caller-supplied; not auto-set). |
| `metadata` | `dict[str, Any]` | `{}` | Arbitrary extra data. Not used by the engine. |

### `Level`

Enum with integer values. Rich comparison operators (`<`, `<=`, `>`, `>=`) are defined via `.value`.

| Name | Value | Meaning |
|---|---|---|
| `HEALTHY` | `0` | Normal operation. |
| `CAUTION` | `1` | Elevated pressure; context trimmed 20%. |
| `DEGRADE` | `2` | High pressure; context trimmed 50%, expensive tools removed. |
| `QUARANTINE` | `3` | Very high pressure; context cleared, minimal tools only. |
| `RESTART` | `4` | Extreme pressure; context cleared, full tools restored. |
| `SAFE_MODE` | `5` | Budget exhausted; minimal everything, latches until replenished. |

Ordering: `HEALTHY < CAUTION < DEGRADE < QUARANTINE < RESTART < SAFE_MODE`.

### `VitalsSnapshot`

Frozen dataclass. Returned inside `ActionResult`.

| Field | Type | Default | Description |
|---|---|---|---|
| `uncertainty` | `float` | `0.0` | Composite uncertainty score, `[0, 1]`. |
| `drift` | `float` | `0.0` | Cosine-distance behavioral drift, `[0, 1]`. |
| `drift_mode` | `DriftMode` | `INFORMATIONAL` | Whether drift is informational or directive. |
| `token_usage` | `float` | `0.0` | Fraction of token budget used, `[0, 1]`. |
| `cost` | `float` | `0.0` | Fraction of cost budget used, `[0, 1]`. |
| `error_rate` | `float` | `0.0` | Fraction of actions in the window that errored, `[0, 1]`. |

### `AgentConfig`

Mutable dataclass. Created internally by `SOMAEngine.register_agent()`.

| Field | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | required | Unique identifier for the agent. |
| `autonomy` | `AutonomyMode` | `HUMAN_ON_THE_LOOP` | Determines approval requirements at high levels. |
| `system_prompt` | `str` | `""` | The agent's system prompt. Preserved unchanged by context control. |
| `tools_allowed` | `list[str]` | `[]` | Full tool list. Passed as initial `known_tools`. |
| `expensive_tools` | `list[str]` | `[]` | Tools dropped at `DEGRADE`. Caller populates via context dict. |
| `minimal_tools` | `list[str]` | `[]` | Tools kept at `QUARANTINE` / `SAFE_MODE`. Caller populates via context dict. |

### `AutonomyMode`

| Value | String key | Behaviour |
|---|---|---|
| `FULLY_AUTONOMOUS` | `"fully_autonomous"` | Never requires human approval. |
| `HUMAN_ON_THE_LOOP` | `"human_on_the_loop"` | Observes but does not require approval. |
| `HUMAN_IN_THE_LOOP` | `"human_in_the_loop"` | Requires approval at `QUARANTINE`, `RESTART`, `SAFE_MODE`. |

### `DriftMode`

| Value | Meaning |
|---|---|
| `INFORMATIONAL` | Drift is noted but does not contribute to pressure. |
| `DIRECTIVE` | Drift contributes its full weight to aggregate pressure. |

### `InterventionOutcome`

| Value | Meaning |
|---|---|
| `PENDING` | Evaluation window not yet reached, or no record exists. |
| `SUCCESS` | Pressure dropped after the intervention. |
| `FAILURE` | Pressure did not drop; adjustments may fire. |

---

## Vitals Computation

### Uncertainty

**File:** `soma/vitals.py :: compute_uncertainty()`

#### Formula

```
uncertainty = clamp(w_retry·retry + w_tool·σ_clamp(tool_dev_z) + w_fmt·fmt_dev + w_entropy·σ_clamp(entropy_z), 0, 1)
```

where `σ_clamp` is `sigmoid_clamp` (defined below).

#### Default weights

```python
weights: tuple[float, float, float, float] = (0.30, 0.25, 0.20, 0.25)
# (w_retry, w_tool, w_fmt, w_entropy)
```

#### Components

**1. Retry rate** (`w_retry = 0.30`)

```
retry = count(actions where action.retried) / len(actions)
```

Range: `[0, 1]`. Returns `0.0` for empty window.

**2. Tool-call deviation** (`w_tool = 0.25`)

```
tool_dev_z = |len(actions) - baseline_tool_calls_avg| / baseline_tool_calls_std
tool_component = sigmoid_clamp(tool_dev_z)
```

Returns `0.0` when `baseline_tool_calls_std == 0`. The z-score is an absolute value (unsigned).

**3. Format deviation** (`w_fmt = 0.20`)

```
fmt_dev = mean over actions of:
    count(expected_format lines missing from action.output_text) / len(expected_format)
```

Returns `0.0` when `expected_format` is empty or `None`. Missing is determined by substring membership (`line not in output`).

**4. Output entropy deviation** (`w_entropy = 0.25`)

```
entropy_z = |current_entropy - baseline_entropy| / baseline_entropy_std
entropy_component = sigmoid_clamp(entropy_z)
```

`current_entropy` is computed over the concatenation of all actions' `output_text` joined by spaces.

#### `output_entropy` — Shannon entropy over character bigrams

```
bigrams = [text[i:i+2] for i in range(len(text) - 1)]
total   = len(bigrams)
H       = -Σ (count/total) · log₂(count/total)   for each unique bigram
max_H   = log₂(total)   if total > 1 else 1.0
output_entropy = H / max_H
```

- n = 2 (character bigrams).
- Returns `0.0` for text shorter than 2 characters.
- Returns `0.0` if `max_H == 0`.
- Result range: `[0, 1]`.

#### `sigmoid_clamp`

```
sigmoid_clamp(x):
    if x <= 0: return 0.0
    if x > 6:  return 1.0
    return 1 / (1 + exp(-x + 3))
```

Verification points:
- x = 1σ → `1/(1+exp(-1+3))` = `1/(1+exp(2))` ≈ **0.119**
- x = 3σ → `1/(1+exp(-3+3))` = `1/(1+1)` = **0.500**
- x = 5σ → `1/(1+exp(-5+3))` = `1/(1+exp(-2))` ≈ **0.881**
- x ≤ 0 → **0.0** (hard floor)
- x > 6 → **1.0** (hard ceiling)

#### Absolute pressure floor (in `engine.py`)

If `retry_rate > 0.3`, the uncertainty pressure is raised to at least `retry_rate`:

```python
if retry_rate > 0.3:
    uncertainty_pressure = max(uncertainty_pressure, retry_rate)
```

Analogue for error rate (see Pressure section).

#### Time anomaly boost (in `engine.py`)

When `action_count > 5` and `duration_sec > 0`:

```
time_deviation = (action.duration_sec - avg_duration) / max(std_duration, 0.1)
if time_deviation > 2.0:
    time_boost = min(sigmoid_clamp(time_deviation) * 0.3, 0.3)
    uncertainty = min(1.0, uncertainty + time_boost)
```

Maximum boost: `0.3`. Triggers only when action is more than 2 std-dev slower than baseline.

---

### Drift

**File:** `soma/vitals.py :: compute_drift()`, `compute_behavior_vector()`

#### Behavior vector

```
v = [avg_tool_calls, avg_output_len, avg_response_time, pattern_entropy, *tool_dist]
```

| Component | Formula | Notes |
|---|---|---|
| `avg_tool_calls` | `1.0` (constant) | Each `Action` IS a tool call. |
| `avg_output_len` | `mean(len(a.output_text) for a in actions) / 1000.0` | Normalized to a 1,000-char reference scale. |
| `avg_response_time` | `mean(a.duration_sec for a in actions)` | Seconds. |
| `pattern_entropy` | `-Σ (count/n)·log₂(count/n)` over tool_name counts | Shannon entropy of the tool-name sequence. Not normalized. |
| `tool_dist[i]` | `tool_counts[known_tools[i]] / n` | Per-tool fraction; one entry per known tool. |

Zero actions → zero vector of length `4 + len(known_tools)`.

#### Cosine distance (drift)

```
cosine_similarity(a, b) = dot(a, b) / (|a| · |b|)
drift = 1 - cosine_similarity(current_vector, baseline_vector)
```

- Returns `0.0` for zero vectors (both magnitude checks).
- Range: `[0, 2]` in theory; in practice stays near `[0, 1]`.

#### Baseline vector update cadence (in `engine.py`)

```python
if s.action_count % 10 == 0 or s.baseline_vector is None:
    s.baseline_vector = current_vec
```

The drift baseline is re-anchored every 10 actions, or immediately on the first action.

#### Drift mode determination

```python
def determine_drift_mode(
    drift, drift_threshold,
    error_rate, error_rate_baseline,
    progress_stalled,
    uncertainty, uncertainty_threshold,
) -> DriftMode:
```

Returns `DIRECTIVE` if and only if:

```
drift > drift_threshold
AND (error_rate > error_rate_baseline
     OR progress_stalled
     OR uncertainty > uncertainty_threshold)
```

Otherwise returns `INFORMATIONAL`.

In `engine.py`, the thresholds used are:

```python
drift_threshold       = 0.3
uncertainty_threshold = 0.3
error_rate_baseline   = s.baseline.get("error_rate")   # EMA value
progress_stalled      = False                          # not yet wired
```

When `drift_mode == INFORMATIONAL`, the drift signal weight is set to `0` in the aggregate pressure computation, so drift pressure does not contribute.

---

### Resource Vitals

**File:** `soma/vitals.py :: compute_resource_vitals()`

All three values are independently clamped to `[0, 1]`:

```
token_usage = clamp(token_used  / token_limit,  0, 1)   if token_limit > 0  else 0.0
cost        = clamp(cost_spent  / cost_budget,  0, 1)   if cost_budget > 0  else 0.0
error_rate  = clamp(errors_in_window / actions_in_window, 0, 1)
              if actions_in_window > 0 else 0.0
```

- `token_used` is read from `budget.spent["tokens"]` (integer cast).
- `errors_in_window` = count of `action.error == True` in the current ring-buffer window (capacity 10).

---

## Baseline (EMA)

**File:** `soma/baseline.py :: Baseline`

### EMA update

```
new_value    = α · value + (1 − α) · old_value
new_variance = α · (value − old_value)² + (1 − α) · old_variance
```

Parameters:
- `alpha` (`α`): `0.15` (default)
- `min_samples`: `10` (default; controls cold-start blend)

On the very first observation for a signal, `_value[signal] = value` and `_variance[signal] = 0.0`.

### Cold-start blending

```
blend   = min(n / min_samples, 1.0)   where n = observation count
returned = blend · computed_EMA + (1 − blend) · default
```

At `n = 0` (no observations): returns the signal's `DEFAULTS` value.
At `n ≥ 10`: blend = 1.0; returns the EMA value unchanged.

### Default baselines

```python
DEFAULTS = {
    "uncertainty": 0.15,
    "drift":       0.10,
    "token_usage": 0.30,
    "cost":        0.20,
    "error_rate":  0.05,
}
```

Signals not in `DEFAULTS` (e.g. `"tool_calls"`, `"entropy"`, `"duration"`) return `0.0` as their default.

### Standard deviation

```
std = max(sqrt(variance), 1e-9)
```

Returns `0.1` if the signal has never been observed (no variance entry exists).

### Grace period

In `engine.py`, the first `min_samples` (10) actions receive `effective_pressure = 0.0` regardless of computed values:

```python
if s.action_count <= s.baseline.min_samples:
    effective = 0.0
```

This prevents cold-start false alarms during baseline warm-up.

---

## Pressure

**File:** `soma/pressure.py`

### Per-signal pressure

```
z = (current − baseline) / max(std, 1e-9)
signal_pressure = sigmoid_clamp(z)
```

Values at or below baseline (`z ≤ 0`) return `0.0` due to `sigmoid_clamp`'s hard floor.

### Absolute floors (in `engine.py`)

**Error rate floor:**
```python
if rv.error_rate > 0.3:
    error_pressure = max(error_pressure, rv.error_rate)
```

**Uncertainty / retry floor:**
```python
if retry_rate > 0.3:
    uncertainty_pressure = max(uncertainty_pressure, retry_rate)
```

These floors prevent the EMA from "normalizing" persistently high error or retry rates.

### Default signal weights

```python
DEFAULT_WEIGHTS = {
    "uncertainty": 2.0,
    "drift":       1.8,
    "error_rate":  1.5,
    "cost":        1.0,
    "token_usage": 0.8,
}
```

`drift` is zeroed out when `drift_mode == INFORMATIONAL`.

### Burn-rate pressure (in `engine.py`)

When `budget.health() < 1.0`, the engine checks each budget dimension:

```python
overshoot = budget.projected_overshoot(dim, estimated_total_steps=100, current_step=action_count)
if overshoot > 0:
    signal_pressures["burn_rate"] = min(overshoot, 1.0)
    break   # only the first overshooting dimension is used
```

`burn_rate` is not in `DEFAULT_WEIGHTS` and thus receives an effective weight of `0.0` in the default aggregate — it only contributes if a custom weight dict includes it.

### Aggregate pressure

```
result = 0.7 · weighted_mean + 0.3 · max_pressure
```

where `weighted_mean` and `max_pressure` are computed only over signals with `effective_weight > 0`:

```
total_weight   = Σ w_i
weighted_mean  = Σ (w_i · p_i) / total_weight
max_pressure   = max(p_i)
```

Returns `0.0` if no signals have positive weight.

### Learning weight adjustments

Before computing aggregate pressure, per-signal weights are adjusted:

```python
adjusted_weight[signal] = max(0.2, DEFAULT_WEIGHTS[signal] + learning_adj[signal])
```

`learning_adj[signal]` is the cumulative adjustment from `LearningEngine` (≤ 0 after failures). The floor of `0.2` prevents any signal from being fully silenced.

---

## Inter-Agent Pressure Graph

**File:** `soma/graph.py :: PressureGraph`

### Structure

- **Nodes** (`_Node`): `agent_id`, `internal_pressure`, `effective_pressure`.
- **Edges** (`_Edge`): directed from `source` to `target` with `trust_weight ∈ [0, 1]`.
- Edges are stored in two indexes: `_edges[target]` (incoming) and `_out_edges[source]` (outgoing).

### Constructor defaults

| Parameter | Default | Description |
|---|---|---|
| `damping` | `0.6` | Fraction of incoming weighted-average pressure propagated. |
| `decay_rate` | `0.05` | Trust reduction per unit of uncertainty on decay. |
| `recovery_rate` | `0.02` | Trust recovery per unit of (1 − uncertainty) on recovery. |

### Propagation formula

For each node on each iteration:

```
if no incoming edges:
    effective = internal

else:
    total_weight  = Σ trust_weight of incoming edges
    weighted_avg  = Σ (trust_weight · source.effective_pressure) / total_weight
    effective     = max(internal, damping · weighted_avg)
```

- Convergence check: `|new_effective − old_effective| > 1e-6` on any node → continue.
- Maximum iterations: `3` (default `max_iterations` parameter).
- Agents with no incoming edges are unaffected by propagation (effective = internal).

### Asymmetry

The formula is `max(internal, damping · weighted_avg)` — pressure only flows **upward** across an edge. A low-pressure agent cannot pull a high-pressure agent's effective pressure down.

### Trust decay

```
trust -= decay_rate · uncertainty
trust = clamp(trust, 0.0, 1.0)
```

Triggered when `uncertainty > 0.5` (engine.py). Applied to **all outgoing edges** of the agent.

### Trust recovery

```
trust += recovery_rate · (1 − uncertainty)
trust = clamp(trust, 0.0, 1.0)
```

Triggered when `uncertainty ≤ 0.5` (engine.py).

---

## Budget

**File:** `soma/budget.py :: MultiBudget`

### Constructor

```python
MultiBudget(limits: dict[str, float])
```

All dimensions start with `spent = 0.0`. The internal clock (`_start_time`) is set at construction time using `time.monotonic()`.

### Health

```
health = min(remaining(dim) / limits[dim]   for each dim)
       = min((limits[dim] - spent[dim]) / limits[dim])
```

- Returns `1.0` for an empty budget (no dimensions).
- Returns `0.0` if `limits[dim] == 0` for any dimension.
- Range: `[0, 1]`.

### Burn rate

```
burn_rate(dim) = spent[dim] / elapsed_seconds
```

`elapsed_seconds` = wall time since construction. Returns `0.0` if elapsed ≤ 0.

### Projected overshoot

```
spend_per_step      = spent[dim] / current_step
projected_total     = spend_per_step · estimated_total_steps
overshoot           = projected_total − limits[dim]
```

Returns `0.0` if `current_step ≤ 0`. Negative result means headroom remains.

### `spend()` behavior

Each dimension is clamped at its limit: `spent[dim] = min(spent[dim] + amount, limits[dim])`. Passing an unknown dimension key raises `KeyError`.

### `replenish()` behavior

`spent[dim] = max(0.0, spent[dim] − amount)`. Floor at 0. Raises `KeyError` for unknown dimensions.

### Default config budget

From `config_loader.py`:

```toml
[budget]
tokens   = 100000
cost_usd = 5.0
```

From `engine.py` / `wrap.py` when no config is present: `{"tokens": 100_000}`.

---

## Escalation Ladder

**File:** `soma/ladder.py :: Ladder`

### Thresholds

```python
THRESHOLDS = [
    (0.00, 0.00),   # HEALTHY     (escalate at p≥0.00, de-escalate below 0.00)
    (0.25, 0.20),   # CAUTION
    (0.50, 0.45),   # DEGRADE
    (0.75, 0.70),   # QUARANTINE
    (0.90, 0.85),   # RESTART
]
```

Each entry is `(escalate_threshold, de_escalate_threshold)`. The de-escalate threshold is always 0.05 lower than the escalate threshold — this is the hysteresis band.

`SAFE_MODE` is not in `THRESHOLDS`; it is triggered by budget, not pressure.

### Escalation logic

1. **SAFE_MODE latch:** if `budget_health ≤ 0.0`, enter `SAFE_MODE`. Stays until `budget_health > 0.10` (`SAFE_MODE_EXIT`). On exit, resets current to `HEALTHY` and falls through to normal evaluation.
2. **Manual override:** `force_level(level)` sets `_forced`; takes precedence after safe-mode check.
3. **Target level:** highest `_ESCALATION_LEVELS[i]` where `pressure ≥ THRESHOLDS[i][0]`.
4. **Escalate:** if `target > current`, jump directly (multi-level spikes allowed).
5. **De-escalate:** if `target < current` AND `pressure < de_escalate_threshold[current_index]`, drop exactly one level.
6. **Hold:** if pressure is between the de-escalate and escalate thresholds, level is unchanged.

### Approval requirement

```python
def requires_approval(level, autonomy) -> bool:
    if autonomy is not HUMAN_IN_THE_LOOP:
        return False
    return level in (QUARANTINE, RESTART, SAFE_MODE)
```

Only `HUMAN_IN_THE_LOOP` mode ever blocks; the other two modes always return `False`.

### Learned threshold adjustments

`evaluate_with_adjustments()` accepts a `threshold_adjustments` dict keyed by `"OLD_LEVEL->NEW_LEVEL"` strings. The shift value is added to both the escalate and de-escalate thresholds for that transition before evaluation:

```python
adjusted_esc = esc + shift
adjusted_de  = de  + shift
```

---

## Learning Engine

**File:** `soma/learning.py :: LearningEngine`

### Parameters and defaults

| Parameter | Default | Description |
|---|---|---|
| `evaluation_window` | `5` | Actions that must elapse before an intervention is evaluated. |
| `threshold_adj_step` | `0.02` | How much to raise the threshold per confirmed failure batch. |
| `weight_adj_step` | `0.05` | How much to lower a signal weight per confirmed failure batch. |
| `min_weight` | `0.2` | Floor for the effective weight of any signal. |
| `max_threshold_shift` | `0.10` | Maximum cumulative threshold shift for any single transition. |
| `min_interventions` | `3` | Minimum failures of the same type before adjustments fire. |

### `InterventionRecord` structure

```python
@dataclass
class _Record:
    agent_id:        str
    old_level:       Level
    new_level:       Level
    pressure:        float           # pressure at the moment of intervention
    trigger_signals: dict[str, float]  # signal_pressures at intervention time
    actions_elapsed: int = 0
```

### Intervention flow

1. **Record:** on level change, `record_intervention(agent_id, old, new, pressure, signals)` appends a `_Record` to `_pending[agent_id]`.
2. **Evaluate:** on every action, `evaluate(agent_id, current_pressure, actions_since=1)` increments `actions_elapsed` on the oldest pending record.
3. **Window check:** if `actions_elapsed < evaluation_window`, return `PENDING`.
4. **Resolution:** `delta = record.pressure - current_pressure`. If `delta > 0` → `SUCCESS`. Otherwise → `FAILURE`.

### Failure response (`_on_failure`)

Only fires when `failure_count[key] >= min_interventions` (safety bound: minimum 3 failures before any adjustment):

**Threshold adjustment (raise escalation threshold):**
```
new_shift = min(current_shift + threshold_adj_step, max_threshold_shift)
```
Cap: `±0.10` cumulative shift for any transition.

**Weight adjustment (lower signal weight):**
```
new_adj   = current_adj - weight_adj_step
floor_adj = min_weight - original_weight
new_adj   = max(new_adj, floor_adj)
```

The floor ensures `original_weight + adj ≥ min_weight`. Weight adjustments accumulate per signal name, not per transition.

---

## Context Control

**File:** `soma/context_control.py :: apply_context_control()`

Takes a context dict and a `Level`; returns a modified copy (original never mutated).

### Context dict schema

```python
context = {
    "messages":       list,        # ordered oldest → newest
    "tools":          list[str],   # currently available tool names
    "system_prompt":  str,         # always preserved unchanged
    "expensive_tools": list[str],  # optional; dropped at DEGRADE
    "minimal_tools":  list[str],   # optional; the restricted set for QUARANTINE/SAFE_MODE
}
```

### Per-level behavior

| Level | Messages | Tools |
|---|---|---|
| `HEALTHY` | Unchanged (pass-through copy). | Unchanged. |
| `CAUTION` | Keep newest 80% (rounded up via `ceil`). | Unchanged. |
| `DEGRADE` | Keep newest 50% (rounded up). | Remove `expensive_tools` from list. |
| `QUARANTINE` | Clear (empty list). | Replace with `minimal_tools` only. |
| `RESTART` | Clear (empty list). | Unchanged (full tool list). |
| `SAFE_MODE` | Clear (empty list). | Replace with `minimal_tools` only. |

### `_keep_newest` formula

```python
keep = math.ceil(total * fraction)
return messages[total - keep:]
```

For `CAUTION` (fraction=0.80): if there are 10 messages, `keep = ceil(8.0) = 8`, the oldest 2 are dropped.
For `DEGRADE` (fraction=0.50): if there are 7 messages, `keep = ceil(3.5) = 4`, the oldest 3 are dropped.

---

## State Persistence

**File:** `soma/persistence.py`

### `save_engine_state(engine, path=None)`

Default path: `~/.soma/engine_state.json` (directory created if absent).

Serialises the following to JSON:

```json
{
  "agents": {
    "<agent_id>": {
      "baseline":        { ... },   // Baseline.to_dict()
      "action_count":    <int>,
      "known_tools":     [...],
      "baseline_vector": [...],
      "level":           "<Level.name>"
    }
  },
  "budget":   { ... },              // MultiBudget.to_dict()
  "graph":    { ... },              // PressureGraph.to_dict()
  "learning": { ... }               // LearningEngine.to_dict()
}
```

**What is NOT saved:** the ring buffer (action history window), event bus subscriptions, and live timing state (`_start_time` of the budget clock).

### `load_engine_state(path=None) -> SOMAEngine | None`

Returns `None` if the file does not exist or is malformed JSON.

Restores in order: budget → graph → learning → agents. Agent levels are restored via `force_level()` so the ladder's `_forced` flag is set.

### `export_state(path=None)` (on `SOMAEngine`)

Writes a lighter `~/.soma/state.json` (for the dashboard) **and then** calls `save_engine_state()` automatically. The state.json format:

```json
{
  "agents": {
    "<id>": {
      "level":        "<name>",
      "pressure":     <float>,
      "vitals":       { "uncertainty": ..., "drift": ..., "error_rate": ... },
      "action_count": <int>
    }
  },
  "budget": {
    "health": <float>,
    "limits": { ... },
    "spent":  { ... }
  }
}
```

---

## `soma.wrap()` Protocol

**File:** `soma/wrap.py`

### `wrap()` signature

```python
def wrap(
    client:      Any,
    budget:      dict[str, float] | None = None,   # default: {"tokens": 100_000}
    agent_id:    str = "default",
    auto_export: bool = True,
    block_at:    Level = Level.QUARANTINE,
) -> WrappedClient
```

Creates a fresh `SOMAEngine` with the given budget and returns a `WrappedClient` that monkey-patches the API client.

### Monkey-patching

Two client patterns are detected and wrapped:

| Client | Method patched |
|---|---|
| Anthropic SDK | `client.messages.create` |
| OpenAI SDK | `client.chat.completions.create` |

The original method is replaced with a closure; all original arguments are forwarded unchanged.

### Per-call lifecycle

1. **Pre-check — level block:**
   ```python
   if level >= block_at:
       raise SomaBlocked(agent_id, level, pressure)
   ```
   Default `block_at = Level.QUARANTINE` means calls are blocked at `QUARANTINE`, `RESTART`, and `SAFE_MODE`.

2. **Pre-check — budget:**
   ```python
   if engine.budget.is_exhausted():
       raise SomaBudgetExhausted("budget")
   ```

3. **Execute original call.** Errors are caught, `error=True` is set, and the exception is re-raised.

4. **Record action** (in `finally` block, always runs):
   - `output_text` is capped at 1,000 characters.
   - `cost` is estimated as `tokens * 0.5 / 1_000_000` (≈ $0.50 / 1M tokens average).
   - `engine.record_action(agent_id, action)` is called.

5. **Export state** (if `auto_export=True`): calls `engine.export_state()`.

### Response parsing

**Anthropic format:**
- `output_text`: concatenated `block.text` for all content blocks with a `.text` attribute, joined by `"\n"`.
- `token_count`: `usage.input_tokens + usage.output_tokens`.

**OpenAI format:**
- `output_text`: `choices[0].message.content`.
- `token_count`: `usage.total_tokens` (if present).

**Fallback token estimate:** if `token_count == 0` and `text` is non-empty: `tokens = len(text) // 4`.

### `SomaBlocked` exception

```python
SomaBlocked(agent_id: str, level: Level, pressure: float)
# .agent_id, .level, .pressure attributes available
```

### `SomaBudgetExhausted` exception

```python
SomaBudgetExhausted(dimension: str)
# .dimension attribute available
```

---

## CLI Commands

Entry point: `soma` (mapped to `soma.cli.main:main`).

### `soma` (no subcommand)

Launches the Textual TUI hub. On first run (no `soma.toml` and no `~/.soma/state.json`), runs the interactive wizard instead.

### `soma init`

Runs the interactive setup wizard (`soma.cli.wizard.run_wizard()`). Prompts for project type, parameters, and writes `soma.toml`. Three project type flows:

| Choice | Flow |
|---|---|
| `1` | Claude Code plugin |
| `2` | Python SDK (multi-agent) |
| `3` | CI/CD testing |

### `soma status`

Reads `~/.soma/state.json` (path configurable via `soma.toml :: soma.store`) and prints a text summary.

Output format per agent row (plain text):

```
  <agent_id>    <LEVEL>      p=0.00  u=0.00  d=0.00  e=0.00   #<n>
```

With Rich installed, `LEVEL` is coloured: green/yellow/dark_orange/red/bold_red/magenta.

Budget line: `  Budget: <pct>% (tokens: <spent>/<limit>)`.

### `soma replay <file>`

Replays a session JSON file through a fresh engine and displays results as a Rich table.

Table columns: `Step`, `Agent`, `Level` (coloured), `Pressure`, `Uncertainty`, `Drift`, `Errors`.

Summary section shows per-agent max level and max pressure.

### `soma setup-claude`

Creates or augments the following files:

| File | Action |
|---|---|
| `CLAUDE.md` | Appends SOMA section if "SOMA" not already present; creates with header if missing. |
| `soma.toml` | Creates with `DEFAULT_CONFIG` if not present; skips if exists. |
| `~/.soma/` | Creates directory. |
| `.claude/commands/soma-status.md` | Creates a `/soma-status` slash command. |

---

## Testing (`soma.testing.Monitor`)

**File:** `soma/testing.py :: Monitor`

### Context manager protocol

```python
with Monitor(budget={"tokens": 10000}) as mon:
    result = mon.record("agent", action)
# assertions outside the with block
mon.assert_healthy()
mon.assert_below(Level.DEGRADE)
```

`__exit__` never suppresses exceptions.

### `record(agent_id, action) -> ActionResult`

Auto-registers the agent on first use. Appends the `ActionResult` to `mon.history` and accumulates `action.cost` into `mon.total_cost`.

### `checkpoint()`

Resets `history`, `total_cost` (and thus `total_actions`, `max_level`, `current_level`) without resetting the underlying engine state. Use after a warm-up phase so that baselines are established but history reflects only post-warm-up behavior.

### Properties

| Property | Type | Description |
|---|---|---|
| `history` | `list[ActionResult]` | All results since last `checkpoint()`. |
| `total_actions` | `int` | `len(history)`. |
| `total_cost` | `float` | Cumulative `action.cost` since last `checkpoint()`. |
| `current_level` | `Level` | Level from the most recent result; `HEALTHY` if no history. |
| `max_level` | `Level` | Highest level seen in `history`; `HEALTHY` if no history. |

### `assert_healthy()`

Checks `current_level == HEALTHY`. Uses the **most recent** result, not `max_level`, to tolerate transient cold-start escalation.

Raises `AssertionError` with message: `Expected current_level HEALTHY but got <X> (max_level=<Y>)`.

### `assert_below(level)`

Checks `max_level < level`. Uses **max_level** so any transient escalation is captured.

Raises `AssertionError` with message: `Expected max_level below <level> but got <max_level>`.

---

## Configuration (`soma.toml`)

**File:** `soma/cli/config_loader.py :: DEFAULT_CONFIG`

### Full schema with defaults

```toml
[soma]
version = "0.1.0"
store   = "~/.soma/state.json"      # path to the live state file polled by the dashboard

[budget]
tokens   = 100000                   # integer; token budget per session
cost_usd = 5.0                      # float; USD cost limit

[agents.default]
autonomy    = "human_on_the_loop"   # "human_on_the_loop" | "human_in_the_loop" | "fully_autonomous"
sensitivity = "balanced"            # "aggressive" | "balanced" | "relaxed" (wizard only)

[thresholds]
caution    = 0.25                   # pressure at which level escalates to CAUTION
degrade    = 0.50                   # pressure at which level escalates to DEGRADE
quarantine = 0.75                   # pressure at which level escalates to QUARANTINE
restart    = 0.90                   # pressure at which level escalates to RESTART

[weights]
uncertainty = 2.0
drift       = 1.8
error_rate  = 1.5
cost        = 1.0
token_usage = 0.8

[graph]
damping             = 0.6
trust_decay_rate    = 0.05
trust_recovery_rate = 0.02
```

### Sensitivity presets

Defined in `soma/cli/wizard.py :: SENSITIVITY_PRESETS`. These replace the `[thresholds]` section entirely:

| Threshold | `aggressive` | `balanced` | `relaxed` |
|---|---|---|---|
| `caution` | `0.15` | `0.25` | `0.35` |
| `degrade` | `0.35` | `0.50` | `0.60` |
| `quarantine` | `0.55` | `0.75` | `0.85` |
| `restart` | `0.75` | `0.90` | `0.95` |

### How config maps to engine parameters

| Config key | Engine parameter |
|---|---|
| `budget.tokens` | `MultiBudget(limits={"tokens": ...})` |
| `budget.cost_usd` | `MultiBudget(limits={"cost_usd": ...})` |
| `agents.default.autonomy` | `engine.register_agent("default", autonomy=...)` |
| `thresholds.*` | `ladder.THRESHOLDS` (currently read from `soma.toml` but not yet wired into `Ladder` at engine construction — thresholds in `ladder.py` are module-level constants; the config values are used by the wizard to write `soma.toml` and inform the user but do not override `Ladder.THRESHOLDS` at runtime in v0.1.0) |
| `graph.damping` | `PressureGraph(damping=...)` |
| `graph.trust_decay_rate` | `PressureGraph(decay_rate=...)` |
| `graph.trust_recovery_rate` | `PressureGraph(recovery_rate=...)` |

`create_engine_from_config()` currently wires `budget` and `agents.default.autonomy`. The `weights` and `graph` sections are stored in `soma.toml` for reference but are not yet passed into the engine constructor in v0.1.0.

---

## Internal Components

### `RingBuffer`

**File:** `soma/ring_buffer.py`

Fixed-capacity FIFO backed by `collections.deque(maxlen=capacity)`. Default capacity: **10** (per-agent window size in `engine.py`).

- Oldest item is silently dropped on overflow.
- `last(n)` returns the most recent `n` items.
- Supports `__getitem__` with int and slice, `__iter__`, `__len__`, `__bool__`.

### `EventBus`

**File:** `soma/events.py`

Synchronous pub/sub. Handlers are called in subscription order. The engine emits one event:

| Event | Payload keys |
|---|---|
| `"level_changed"` | `agent_id`, `old_level` (Level), `new_level` (Level), `pressure` (float) |

### `SessionRecorder`

**File:** `soma/recorder.py`

Records `RecordedAction(agent_id, action, timestamp)` objects. Exports to / loads from JSON with `version: 1` envelope.

Used by `soma replay` and available on `WrappedClient.recorder`.

### Errors

| Exception | Trigger |
|---|---|
| `SOMAError` | Base class. |
| `AgentNotFound` | `engine.get_level()` or `engine.record_action()` for an unregistered `agent_id`. |
| `NoBudget` | Raised if budget is not configured (currently defined but not thrown by default paths). |
| `SomaBlocked` | API call blocked by `wrap()` because `level >= block_at`. |
| `SomaBudgetExhausted` | API call blocked by `wrap()` because budget is exhausted. |

---

## Quick Reference: Key Numeric Constants

| Constant | Value | Location |
|---|---|---|
| EMA alpha | `0.15` | `baseline.py` |
| Cold-start min_samples | `10` | `baseline.py` |
| Ring buffer capacity | `10` | `engine.py` |
| Baseline vector re-anchor cadence | every 10 actions | `engine.py` |
| Grace period | first 10 actions | `engine.py` |
| Uncertainty weights | (0.30, 0.25, 0.20, 0.25) | `vitals.py` |
| sigmoid_clamp domain | (0, 6] → (0, 1) | `vitals.py` |
| Drift DIRECTIVE threshold | `0.30` | `engine.py` |
| Uncertainty DIRECTIVE threshold | `0.30` | `engine.py` |
| Absolute floor threshold | `0.30` | `engine.py` |
| Time anomaly sigma threshold | `2.0` | `engine.py` |
| Time anomaly max boost | `0.30` | `engine.py` |
| Aggregate pressure blend | 0.7 × mean + 0.3 × max | `pressure.py` |
| Damping | `0.6` | `graph.py` |
| Trust decay rate | `0.05` | `graph.py` |
| Trust recovery rate | `0.02` | `graph.py` |
| Graph max iterations | `3` | `graph.py` |
| Trust decay trigger | uncertainty > 0.5 | `engine.py` |
| SAFE_MODE exit threshold | `0.10` | `ladder.py` |
| Learning evaluation window | `5` actions | `learning.py` |
| Learning threshold step | `0.02` | `learning.py` |
| Learning weight step | `0.05` | `learning.py` |
| Learning min weight | `0.2` | `learning.py` |
| Learning max threshold shift | `0.10` | `learning.py` |
| Learning min interventions | `3` | `learning.py` |
| Output text cap in wrap | 1,000 chars | `wrap.py` |
| Cost estimate rate | $0.50 / 1M tokens | `wrap.py` |
| Token fallback estimate | `len(text) // 4` | `wrap.py` |
| Default budget | `{"tokens": 100_000}` | `engine.py`, `wrap.py` |
