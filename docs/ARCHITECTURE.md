# SOMA Architecture

SOMA is a closed-loop behavioral monitoring system. Actions produce vitals, vitals produce pressure, pressure produces feedback, feedback changes actions.

This document describes the complete system architecture as implemented in v0.6.0 (90 modules, 19k lines, Python 3.11+).

See also: [Technical Reference](TECHNICAL.md) for exact formulas and constants, [Research](RESEARCH.md) for academic foundations, [Paper](PAPER.md) for the full academic treatment, [Guide](guide.md) for practical usage, [API Reference](api.md) for programmatic interface.

## System overview

```
Tool Call ──────────────────────────────────────────────> Tool Execution
     │                                                         │
     ▼                                                         ▼
┌─ SOMA Engine ─────────────────────────────────────────────────────┐
│                                                                   │
│  PRE-TOOL                                 POST-TOOL               │
│  ┌──────────────┐                     ┌──────────────────┐        │
│  │   Skeleton    │ hard blocks,       │  Sensor Layer    │        │
│  │   (Reflexes)  │ retry dedup,       │  vitals →        │        │
│  │              │ blind write warn    │  baselines →     │        │
│  └──────────────┘                     │  pressure (0→1)  │        │
│                                       └────────┬─────────┘        │
│                                                │                  │
│                                       ┌────────▼─────────┐        │
│                                       │ Pattern Detection │        │
│                                       │ retry, thrash,    │        │
│                                       │ blind edit, stall │        │
│                                       └────────┬─────────┘        │
│                                                │                  │
│                                       ┌────────▼─────────┐        │
│                                       │     Mirror       │        │
│                                       │ PATTERN → STATS  │        │
│                                       │ → SEMANTIC       │        │
│                                       │ (→ tool response)│        │
│                                       └────────┬─────────┘        │
│                                                │                  │
│  ┌──────────────┐                     ┌────────▼─────────┐        │
│  │ PressureGraph│◄────────────────────│   Multi-Agent    │        │
│  │ (propagation)│ trust-weighted      │   Coordination   │        │
│  └──────────────┘ edges               └──────────────────┘        │
│                                                                   │
│  ┌────────────────────────────────────────────────────────┐       │
│  │ Memory: fingerprints │ sessions │ patterns │ predictor │       │
│  └────────────────────────────────────────────────────────┘       │
│                                                                   │
│  ┌────────────────────────────────────────────────────────┐       │
│  │ Exporters: OTel │ Webhooks │ Reports │ Audit log       │       │
│  └────────────────────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────────────┘

Escalation: OBSERVE (silent) → GUIDE (suggestions) → WARN (insistent) → BLOCK (destructive ops only)
Delivery:   stdout → tool response (agent sees)  |  stderr → system diagnostics (operator sees)
```

## The action pipeline

Every tool call flows through `SOMAEngine.record_action()`. Here is the full step-by-step sequence:

1. **Track tool** — add to agent's known_tools if new
2. **Append to ring buffer** (capacity 10) — increment action_count
3. **Capture task complexity** on first action from output text
4. **Capture initial task signature** after 5 actions (behavior vector snapshot for goal coherence)
5. **Compute behavioral vitals** — uncertainty, drift, error rate, goal coherence, context exhaustion
6. **Update baselines** — EMA with alpha=0.15, cold-start blending over first 10 samples
7. **Compute per-signal pressures** — sigmoid-clamped z-scores, each signal independently
8. **Apply upstream vector influence** — graph propagation from parent/dependency agents
9. **Aggregate pressure** — 0.7 × weighted mean + 0.3 × max, with error floor
10. **Grace period ramp** — linear scale during first N actions to prevent false spikes
11. **Budget spend** — track tokens, cost_usd via MultiBudget
12. **Trust decay/recovery** — adjust trust based on uncertainty > 0.5
13. **Reliability metrics** — hedging rate, calibration score, verbal-behavioral divergence
14. **Task complexity adjustment** — lower thresholds by up to 0.20 for complex tasks
15. **Mode determination** — `pressure_to_mode(effective_pressure, thresholds)`
16. **Learning evaluation** — check pending interventions, record outcomes
17. **Emit events** — `action_recorded`, `level_changed` to event bus
18. **Auto-export state** — atomic write to `~/.soma/engine_state.json`
19. **Return ActionResult** — mode, pressure, vitals, context_action, pressure_vector, handoff suggestion

## Sensor layer

### Vitals

Signals computed per action from the ring buffer of recent actions:

| Signal | Source | What it measures |
|--------|--------|-----------------|
| **uncertainty** | Weighted composite of retry rate, tool call deviation, format deviation, entropy deviation | How unpredictable the agent's behavior is |
| **drift** | Cosine distance from baseline behavior vector (phase-aware) | How much the tool usage pattern has changed |
| **error_rate** | Errors / total actions in sliding window | Raw failure frequency |
| **goal_coherence** | 1 − cosine similarity(current vector, initial task vector) | Deviation from the original task objective |
| **context_exhaustion** | sigmoid((cumulative_tokens / context_window − 0.5) / 0.15) | How fast the context window is being consumed |
| **token_usage** | Tokens spent / token limit | Token budget utilization |
| **cost** | Cost spent / cost budget | Dollar budget utilization |

**Uncertainty decomposition:**

```
uncertainty = w0·retry_rate + w1·sigmoid(tool_call_deviation) + w2·format_deviation + w3·sigmoid(entropy_deviation)
```

Where entropy deviation is normalized Shannon entropy over character bigrams of the output. Uncertainty is classified as:
- **Epistemic** (low entropy + high uncertainty): the agent doesn't know → 1.3× multiplier
- **Aleatoric** (high entropy + high uncertainty): inherent randomness → 0.7× multiplier

**Behavior vector** (used for drift and goal coherence):

```
[avg_tool_calls, avg_output_len, avg_response_time, pattern_entropy] + tool_distribution_per_known_tool
```

### Pressure computation

Each signal is converted to a 0–1 pressure via sigmoid-clamped z-score:

```
z = (current − baseline_mean) / max(baseline_std, 0.05)
signal_pressure = sigmoid_clamp(z)

where sigmoid_clamp(x) = 0 if x ≤ 0, 1 if x > 6, else 1/(1 + exp(−x + 3))
```

Aggregate pressure blends mean and max:

```
aggregate = 0.7 × weighted_mean + 0.3 × max_pressure

weighted_mean = Σ(weight_i × pressure_i) / Σ(weight_i)
```

**Signal weights:**

| Signal | Weight |
|--------|--------|
| uncertainty | 2.0 |
| drift | 1.8 |
| error_rate | 1.5 |
| goal_coherence | 1.5 |
| context_exhaustion | 1.5 |
| cost | 1.0 |
| token_usage | 0.8 |

**Error floor:** High error rates cannot be normalized away by healthy baselines. When error_rate pressure is in [0.20, 1.00], a floor is applied:

```
floor = 0.10 + 0.60 × (error_pressure − 0.20) / 0.80
aggregate = max(aggregate, floor)
```

This guarantees proportional aggregate pressure whenever error rate is elevated, regardless of other signals.

**Drift mode:** When uncertainty and error rate are both low, drift is classified as INFORMATIONAL and its weight is zeroed — the agent is exploring safely.

### Baseline

Exponential moving average (EMA) per signal with cold-start blending:

```
new_value = α × value + (1 − α) × old_value
new_variance = α × (value − old)² + (1 − α) × old_variance

α = 0.15 (15% weight to new observation)
min_samples = 10 (cold-start window)
```

During cold start:

```
blend = min(count / min_samples, 1.0)
effective = blend × computed_ema + (1 − blend) × signal_default
```

Signal defaults: uncertainty=0.05, drift=0.05, error_rate=0.01, token_usage=0.01, cost=0.01.

**Grace period:** During the first min_samples actions, effective pressure is linearly ramped: `pressure × (action_count / min_samples)`. This prevents the cliff behavior that caused bimodal pressure distributions in earlier versions.

Baselines are inherited across sessions — new sessions get a warm start from the most active prior session.

## Escalation modes

| Mode | Pressure | Behavior |
|------|----------|----------|
| OBSERVE | 0–25% | Silent. Metrics recorded. |
| GUIDE | 25–50% | Soft suggestions on stderr. Mirror active. |
| WARN | 50–75% | Insistent warnings. Predictions shown. |
| BLOCK | 75–100% | Destructive ops blocked. Normal tools always allowed. |

Claude Code defaults are higher (40/60/80) to reduce noise. Thresholds are configurable in `soma.toml`.

**Task complexity adjustment:** For complex tasks (complexity > 0.5), thresholds are lowered by up to 0.20 — the system is more sensitive when the task is harder.

## Reflex system

Pre-tool hard blocks that fire before the tool executes. Independent from pressure — they fire at any level when the specific pattern is detected.

| Reflex | Trigger | Action |
|--------|---------|--------|
| retry_dedup | 2+ identical Bash commands | Block (exit code 2) |
| blind_edit | 3+ Edit/Write without prior Read | Block |
| bash_failures | 2+ consecutive Bash errors | Warning |
| commit_gate | `git commit` when quality grade D/F | Block |
| destructive_ops | `rm -rf`, `git push -f`, `git reset --hard`, `chmod 777`, `kill -9`, `git clean -f`, `git checkout .` | Block at BLOCK mode |
| sensitive_files | `.env`, `.pem`, `.key`, `credentials`, `secret` | Warning |

**Operating modes:**
- **observe** — no blocking, no guidance. Pure monitoring.
- **guide** — guidance on stderr, injection reflexes (soft nudges), no blocking.
- **reflex** — full blocking for dangerous patterns + guidance.

**Exit codes:** 0 = allow (with optional stderr message), 2 = block (Claude Code prevents the tool call).

## Pattern detection

Detected from the action log (last 10–30 actions):

| Pattern | Trigger | Used by |
|---------|---------|---------|
| retry_loop | 2+ identical Bash commands | Reflexes, Predictor (+0.12 boost) |
| blind_edit | Writes without prior Read | Reflexes, Predictor (+0.10 boost) |
| error_cascade | 3+ errors in last 5 actions | Predictor (+0.15 boost) |
| thrashing | 3+ edits to same file | Guidance suggestions, Predictor (+0.08) |
| agent_spam | 3+ Agent spawns in 10 actions | Guidance suggestions |
| research_stall | 7+ reads, 0 writes in 8 actions | Findings |

## Mirror

Proprioceptive feedback via environment augmentation. Mirror injects factual observations about the agent's behavior into tool responses via stdout.

### Mode selection

```
pressure < 0.15           → None (silence)
0.15 ≤ pressure < 0.40    → PATTERN or STATS
pressure ≥ 0.40 AND
  (no pattern match OR
   goal drift OR
   VBD detected)          → SEMANTIC (fallback: PATTERN/STATS)
```

**PATTERN (free):** Matches current behavior against known patterns. If a pattern exists in the pattern database with success_rate ≥ 60% and ≥ 2 attempts, its cached context is reused.

**STATS (free):** When no pattern matches but pressure is elevated, Mirror formats raw numbers: action count, error count, reads-before-writes ratio, top pressure signals. Pure data, no interpretation.

**SEMANTIC (~$0.001):** At high pressure (≥40%) combined with goal drift or verbal-behavioral divergence, Mirror calls a cheap LLM (Gemini Flash / Haiku / GPT-4o-mini) to generate a 1–2 sentence factual observation.

**Output format:** Wrapped in `--- session context ---` markers, max 3 lines, ~40 tokens.

### Self-learning

```
Mirror.generate() → inject context
    ↓
track_injection(pattern_key, context_text, pressure_at_injection)
    ↓
...3 actions pass...
    ↓
Mirror.evaluate_pending()
    ↓
pressure dropped ≥ 10%?
  YES → record_outcome(helped=True), cache in pattern_db
  NO  → record_outcome(helped=False), prune if success_rate < 30% after 5 attempts
```

Pattern database persisted at `~/.soma/patterns.json`. Effective contexts are reused across sessions.

### Verbal-behavioral divergence (VBD)

The agent's last Edit/Write targets a file that hasn't been Read within the last 5 actions. This suggests the agent is modifying code it hasn't recently examined — a common precursor to errors.

## Multi-agent: PressureGraph

Directed graph modeling inter-agent dependencies with trust-weighted edges and per-signal pressure propagation.

### Structure

- **Nodes:** One per registered agent. Each has internal_pressure, effective_pressure, and PressureVector (uncertainty, drift, error_rate, cost).
- **Edges:** Directed from source to target with trust weight. Trust decays at 0.05/action when upstream uncertainty > 0.5, recovers at 0.02/action otherwise.

### Propagation algorithm

Runs after each action (max 3 iterations until convergence):

For each node with incoming edges:

1. **Compute coordination SNR (signal-to-noise ratio):**
   ```
   snr = confirmed_signals / total_incoming
   ```
   If SNR < 0.5 and total_incoming > 0.05 → node is **isolated**, uses only internal pressure.

2. **Scalar propagation:**
   ```
   weighted_avg = Σ(trust × upstream_effective) / Σ(trust)
   effective = max(internal, damping × weighted_avg)
   ```
   Damping = 0.6 (downstream gets 60% of upstream pressure).

3. **Vector propagation** (per signal):
   ```
   each signal = max(own_signal, damping × weighted_avg_of_upstream_signal)
   ```

This means if a parent agent's error rate spikes, child agents' effective error_rate pressure rises proportionally — they know *why* upstream is struggling.

## Predictions and forecasting

The predictor estimates future pressure and warns before escalations happen.

### Algorithm

1. **Linear trend extrapolation** via OLS regression on last 10 pressure readings:
   ```
   slope = Σ((x − x̄)(y − ȳ)) / Σ((x − x̄)²)
   trend_prediction = current + slope × horizon
   ```
   Default horizon = 5 actions ahead.

2. **Pattern boosts** (additive):
   | Pattern | Boost | Trigger |
   |---------|-------|---------|
   | error_streak | +0.15 | 3+ consecutive errors |
   | blind_writes | +0.10 | 2+ writes without read |
   | thrashing | +0.08 | Same file edited 3+ times |
   | retry_storm | +0.12 | Error rate > 40% |

3. **Confidence:**
   ```
   sample_conf = min(n_samples / window, 1.0)
   fit_conf = max(r², 0.0) if n ≥ 3 else 0.0
   confidence = 0.6 × sample_conf + 0.4 × fit_conf
   ```

4. **Escalation:** `will_escalate = predicted ≥ next_threshold AND confidence > 0.3`

### Cross-session trajectory matching

The predictor loads past session trajectories from `history.jsonl` and matches the current trajectory against historical patterns using cosine similarity. Final prediction blends 60% current trend + 40% historical match.

## Quality tracking

Rolling window (default 30 events) of write and bash outcomes.

**Events tracked:**
- Write/Edit: syntax_error flag, lint_issue flag (validated via py_compile, ruff, node --check)
- Bash: success/failure

**Scoring:**

```
write_score = clean_writes / total_writes
bash_score = 1 − (failures / total_bashes)
score = weighted_average(write_score, bash_score)

syntax_penalty = max(0.5, 1.0 − syntax_errors × 0.15)
final_score = score × syntax_penalty, clamped [0, 1]
```

**Grades:** A (≥0.9), B (≥0.8), C (≥0.7), D (≥0.5), F (<0.5).

The commit gate reflex blocks `git commit` when quality is D or F.

## Behavioral fingerprinting

Cross-session behavioral identity tracking per agent.

**Fingerprint:**

```
tool_distribution: dict[tool → fraction]
avg_error_rate: float
avg_duration: float
read_write_ratio: float
avg_session_length: float
sample_count: int
```

Updated via EMA (alpha=0.1) after each session.

**Divergence detection** (Jensen-Shannon + deltas):

```
1. Tool distribution: JS divergence (weighted 2.0)
   kl_sum = Σ(p × log₂(p/m) + q × log₂(q/m))
   js = min(kl_sum / 2, 1.0)

2. Error rate delta: |current − baseline| / max(baseline, 0.01) (weighted 1.0)

3. Read/write ratio delta: |current − baseline| / max(baseline, 0.1) (weighted 0.5)

final_divergence = mean(weighted_scores), clamped [0, 1]
```

Requires sample_count ≥ 10. Detects behavioral mode shifts, identity corruption, and tool distribution drift across sessions.

## Budget and resources

**MultiBudget** tracks spending across named dimensions (tokens, cost_usd):

```
spend(**kwargs)     → add to spent, clamp at limit
remaining(dim)      → limit − spent
utilization(dim)    → spent / limit [0, 1]
health()            → min(remaining / limit) across all dimensions
burn_rate(dim)      → spent / elapsed_seconds
projected_overshoot → (spend_per_step × total_steps) − limit
is_exhausted()      → health() == 0
```

When budget is exhausted, `WrappedClient` raises `SomaBudgetExhausted` — the API call is prevented.

**Half-life estimation:** Based on context burn rate and token consumption, SOMA estimates how many actions until the agent becomes ineffective. When half-life is critical, a handoff suggestion is included in the ActionResult.

## Task tracking

Per-session phase detection and scope drift monitoring.

**Phase detection** (from tool patterns over last 10 actions):
- **Research:** Read, Grep, Glob, WebSearch, WebFetch
- **Implement:** Write, Edit, NotebookEdit
- **Test:** Bash
- **Debug:** High error rate (>30% of window)

**Scope drift:** After 5 file-touching actions, the initial focus (files and directories) is captured. Subsequent actions are compared against this initial focus via set overlap. Drift score is [0, 1] with an explanation string.

## Adaptive learning

The learning engine adjusts thresholds and signal weights based on intervention outcomes.

**Workflow:**

1. When mode escalates (e.g., OBSERVE → GUIDE), record an intervention with current signals and pressure
2. After evaluation window (N actions), check if pressure dropped
3. **Success:** pressure decreased — intervention was effective
4. **Failure:** pressure unchanged or increased — threshold may be too sensitive

On accumulated failures:
- Raise escalation threshold by 0.02 (max cumulative shift: 0.10)
- Lower trigger signal weight by 0.05 (floor: 0.2)

This means SOMA adapts its sensitivity to each agent — an agent that consistently recovers on its own gets looser thresholds.

## Subagent monitoring

Tracks spawned child agents with per-subagent action logs at `~/.soma/subagents/{parent_id}/{sub_id}.jsonl`.

**Per-subagent metrics:** action_count, error_count, error_rate, total_tokens, tools_used.

**Cascade risk:**

```
if max_subagent_error_rate > threshold (0.3):
    risk = (max_error − threshold) / (1.0 − threshold)
else:
    risk = 0.0
```

Cascade risk propagates to parent agent's effective pressure via the PressureGraph.

## Session identity

Agent ID = `cc-{PPID}` where PPID is the Claude Code process ID. All hook calls within one Claude Code session share the same PPID, so state accumulates correctly. Recycled PIDs are detected by comparing PPID start times.

## Persistence

### Atomic writes

Engine state uses atomic writes to prevent corruption from concurrent hook calls:

```
1. Serialize engine state to JSON
2. Acquire exclusive file lock (fcntl.LOCK_EX)
3. Write to temp file → os.fsync()
4. Atomic rename (POSIX guarantees)
5. Release lock
```

Reads use shared locks (fcntl.LOCK_SH). Fallback to direct write if atomic path fails (non-POSIX).

### Per-session files (`~/.soma/sessions/{agent_id}/`)

| File | Content |
|------|---------|
| action_log.json | Last 20 actions: tool, error, file, timestamp |
| trajectory.json | Pressure value per action |
| quality.json | QualityTracker state: syntax errors, lint issues, grade |
| predictor.json | Pressure prediction model state |
| task_tracker.json | Current phase, focus files, scope drift |
| bash_history.json | Last 10 commands for retry dedup |

### Global files (`~/.soma/`)

| File | Content |
|------|---------|
| engine_state.json | Full engine: agents, baselines, budget, graph, learning |
| state.json | Dashboard snapshot: agents, pressure, vitals |
| fingerprint.json | Cross-session behavioral fingerprints |
| patterns.json | Mirror self-learning database |
| audit.jsonl | Append-only audit trail of all actions |
| sessions/history.jsonl | Completed session summaries with trajectories |
| reports/ | Generated session report markdown files |

## Exporters

### OpenTelemetry

Optional integration (`pip install soma-ai[otel]`). Creates local tracer and meter providers (never touches global state).

- **Gauges:** pressure, uncertainty, drift, error_rate, context_usage
- **Counters:** actions.total, actions.errors
- **Spans:** `soma.action.{tool_name}` with agent_id, token_count, error attributes

Graceful degradation — becomes no-op if opentelemetry-sdk is not installed.

### Webhooks

Fire-and-forget HTTP POST on mode escalation events. Daemon threads so the engine is never blocked. Retry once on failure, silently drop on second failure. Timeout 3s.

**Events:** warn, block, policy_violation, budget_exhausted, context_critical.

**Payload:**

```json
{
  "event_type": "mode_change_warn",
  "agent_id": "cc-12345",
  "pressure": 0.62,
  "mode": "WARN",
  "timestamp": 1711929600.0,
  "details": {}
}
```

### Session reports

Markdown summaries generated on session end or on demand. Sections: summary, vitals timeline, interventions, reflexes, cost, tool distribution, quality score. Saved to `~/.soma/reports/`.

## Hook pipeline

Integration layer for Claude Code and other platforms.

### Modules

| Module | Responsibility |
|--------|---------------|
| pre_tool_use.py | Reflex evaluation, subagent injection, guidance gate |
| post_tool_use.py | Action recording, validation, Mirror injection, pressure trajectory |
| notification.py | Agent awareness prompt injection and findings formatting (UserPromptSubmit/Notification hooks) |
| stop.py | Session cleanup, report generation |
| statusline.py | Real-time status bar formatting |
| common.py | Shared utilities: get_engine, read_action_log, audit logging |

### Platform adapters

| Adapter | Environment |
|---------|-------------|
| ClaudeCodeAdapter | Native Claude Code (CLAUDE_HOOK env vars) |
| CursorAdapter | Cursor IDE |
| WindsurfAdapter | Windsurf IDE |

All adapters implement the HOOK-01 protocol for consistent behavior.

### Delivery mechanism

Claude Code hooks have two output channels:
- **stdout:** Content appended to the tool response — the agent sees it as part of the tool's output
- **stderr:** System messages displayed in the UI — visible to the human, the agent processes as system context

Session context goes to stdout because:
1. It becomes part of the environment, not an instruction
2. The agent cannot distinguish it from real tool output
3. LLMs ignore instructions but process environmental data
4. It survives context compression (it's in tool results, not system messages)

## Programmatic API

```python
import soma

# Quick start — creates engine with defaults
engine = soma.quickstart()

# Wrap Anthropic client — all calls monitored transparently
client = soma.wrap(anthropic.Anthropic())

# Universal proxy for any framework
proxy = soma.SOMAProxy(engine, "my-agent")
safe_tool = proxy.wrap_tool(my_function)
child = proxy.spawn_subagent("child-agent")
```

**WrappedClient** intercepts `messages.create()` and `messages.stream()`, extracts response data (output_text, token_count, cost), records actions through the engine, and raises `SomaBlocked` or `SomaBudgetExhausted` when the agent should be stopped.

## Findings

The findings module aggregates monitoring insights into a prioritized list:

| Category | Source | Example |
|----------|--------|---------|
| status | Pressure + vitals | "Pressure at 0.62 (WARN)" |
| quality | QualityTracker | "Quality grade: C (0.73)" |
| predict | Predictor | "Likely to escalate to WARN in 3 actions" |
| pattern | Action log analysis | "Detected: error_streak (3 consecutive)" |
| scope | TaskTracker | "Scope drift: 0.45 — working outside initial focus" |
| fingerprint | FingerprintEngine | "Behavioral shift: tool distribution diverged 34%" |
| rca | Diagnose module | "Root cause: repeated failures in test suite" |
| positive | Various | "Error rate recovering — pressure trending down" |

Findings are surfaced in hook output, reports, and the TUI dashboard.

## Comparison with existing tools

| Feature | Langfuse / AgentOps | SOMA |
|---------|---------------------|------|
| Who sees data | Human (dashboard) | Agent (tool response) |
| When | Post-hoc | Real-time |
| Delivery | External UI | Environment augmentation |
| Effect on agent | None | Behavioral self-correction |
| Blocking | No | Reflexes for destructive ops |
| Learning | No | Self-learning pattern cache |
| Multi-agent | Trace visualization | Trust-weighted pressure propagation |
| Cross-session | Log aggregation | Behavioral fingerprinting + trajectory matching |
