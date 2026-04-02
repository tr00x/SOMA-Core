# Architecture

SOMA is a closed-loop behavioral monitoring system. Actions produce vitals, vitals produce pressure, pressure produces feedback, feedback changes actions.

## Data flow

```
Agent decides to use a tool
         |
         v
+---------------------------+
| PreToolUse hook           |
|                           |
| 1. Load engine state      |
| 2. Check reflexes:        |
|    - retry_dedup          |
|    - blind_edit           |
|    - bash_failures        |
|    - commit_gate          |
| 3. If blocked: exit(2)    |
| 4. Evaluate guidance      |
|    pressure -> mode       |
+---------------------------+
         |
   Tool executes normally
         |
         v
+---------------------------+
| PostToolUse hook          |
|                           |
| 1. Parse tool response    |
| 2. Validate (syntax/lint) |
| 3. Record action:         |
|    compute_uncertainty()  |
|    compute_drift()        |
|    compute_error_rate()   |
|    compute_signal_pressure|
|    aggregate_pressure()   |
|    pressure_to_mode()     |
| 4. Mirror.evaluate_pending|
| 5. Mirror.generate()     |
|    -> stdout (agent sees) |
| 6. Proprioceptive stderr  |
| 7. Save state             |
+---------------------------+
         |
         v
Agent sees tool response
+ session context (if any)
```

## Mirror

Mirror is the output layer. It decides what the agent should see about its own behavior.

### Three modes

**PATTERN (0 cost):** Matches current behavior against known patterns — retry loops, blind edits, error cascades. If a pattern is recognized and has a cached effective context in `pattern_db`, that cached context is reused. This is the cheapest and fastest mode.

**STATS (0 cost):** When no pattern matches but pressure is elevated, Mirror formats raw numbers: action count, error count, reads-before-writes ratio, top pressure signals. Pure data, no interpretation.

**SEMANTIC (~$0.001 per call):** At high pressure (>=40%) combined with goal drift or verbal-behavioral divergence, Mirror calls a cheap LLM (Gemini Flash / Haiku / GPT-4o-mini) to generate a 1-2 sentence factual observation. Only triggered when patterns and stats are insufficient.

### Mode selection

```
pressure < 0.15           -> None (silence)
0.15 <= pressure < 0.40   -> PATTERN or STATS
pressure >= 0.40 AND
  (no pattern match OR
   goal drift OR
   VBD detected)          -> SEMANTIC (fallback: PATTERN/STATS)
```

### Self-learning cycle

```
Mirror.generate()
    |
    +-> track_injection(pattern_key, context, pressure)
    |
    ...3 actions pass...
    |
Mirror.evaluate_pending()
    |
    +-> pressure dropped >= 10%?
    |     YES -> record_outcome(helped=True)
    |             cache context in pattern_db
    |     NO  -> record_outcome(helped=False)
    |             prune if success_rate < 30% after 5 attempts
```

Pattern DB is persisted at `~/.soma/patterns.json`. Effective contexts are reused across sessions.

### VBD detection

Verbal-behavioral divergence: the agent's last Edit/Write targets a file that hasn't been Read within the last 5 actions. This suggests the agent is modifying code it hasn't recently examined — a common precursor to errors.

## Sensor layer

### Vitals

Five primary signals, computed from the ring buffer of recent actions:

| Signal | Source | What it measures |
|--------|--------|-----------------|
| uncertainty | Output entropy, retry rate, baseline deviation | How unpredictable the agent's behavior is |
| drift | Cosine distance from baseline behavior vector | How much the tool usage pattern has changed |
| error_rate | Errors / total actions in window | Raw failure rate |
| cost | Budget spent / budget limit | Resource consumption |
| token_usage | Tokens used / token limit | Token budget health |

Extended signals: goal_coherence (deviation from initial task), context_exhaustion (context window fill), calibration_score (confidence vs performance).

### Pressure computation

Each signal is converted to a 0-1 pressure via sigmoid-clamped z-score:

```
signal_pressure = sigmoid((current - baseline_mean) / max(baseline_std, 0.05))
```

Aggregate pressure blends mean and max:

```
aggregate = 0.7 * weighted_mean + 0.3 * max_pressure
```

Weights: uncertainty=2.0, drift=1.8, error_rate=1.5, cost=1.0, token_usage=0.8.

Error rate has a continuous floor: high error pressure maps to guaranteed minimum aggregate pressure regardless of other signals being healthy.

### Baseline

Exponential moving average (EMA) per signal with cold-start blending. During the first N actions (grace period), pressure ramps linearly from 0 to prevent false spikes before the baseline has enough data.

Baselines are inherited across sessions — new sessions get a warm start from the most active prior session.

### Pattern detection

Detected from the action log (last 10-30 actions):

| Pattern | Trigger | Severity |
|---------|---------|----------|
| retry_loop | 2+ identical Bash commands | Blocking (reflex mode) |
| blind_edit | 3+ Edit/Write without prior Read | Blocking (reflex mode) |
| bash_failures | 2+ consecutive Bash errors | Warning |
| thrashing | 3+ edits to same file | Warning |
| error_cascade | 3+ errors in last 5 actions | Warning |
| agent_spam | 3+ Agent spawns in 10 actions | Info |
| research_stall | 7+ reads, 0 writes in 8 actions | Info |

## Delivery mechanism

### Why stdout, not stderr

Claude Code hooks have two output channels:
- **stdout:** content appended to the tool response — the agent sees it as part of the tool's output
- **stderr:** system messages displayed in the UI — visible to the human, but the agent processes them as system context

Session context goes to stdout because:
1. It becomes part of the environment, not an instruction
2. The agent cannot distinguish it from real tool output
3. LLMs ignore instructions but process environmental data
4. It survives context compression (it's in tool results, not system messages)

### Reflex blocking

Separate from Mirror. Pattern-based hard blocks for irreversible operations. PreToolUse hook returns exit code 2 = Claude Code prevents the tool call.

Three operating modes:
- **observe:** No blocking, no guidance. Pure monitoring.
- **guide:** Guidance messages on stderr. Injection reflexes (soft nudges). No blocking.
- **reflex:** Full blocking for dangerous patterns + guidance.

## Memory and persistence

### Per-session (`~/.soma/sessions/{agent_id}/`)

| File | Content |
|------|---------|
| action_log.json | Last 20 actions: tool, error, file, timestamp |
| trajectory.json | Pressure value per action |
| quality.json | QualityTracker: syntax errors, lint issues, grade |
| predictor.json | Pressure prediction model state |
| task_tracker.json | Current phase, scope drift |
| bash_history.json | Last 10 commands for retry dedup |

### Global (`~/.soma/`)

| File | Content |
|------|---------|
| engine_state.json | Full engine: agents, baselines, budget, graph, learning |
| state.json | Dashboard snapshot: agents, pressure, vitals |
| fingerprint.json | Cross-session behavioral fingerprints |
| patterns.json | Mirror self-learning database |
| audit.jsonl | Append-only audit trail |
| sessions/history.jsonl | Completed session summaries |

Engine state uses atomic writes (temp file -> fsync -> rename) with file locking to prevent corruption from concurrent hook calls.

### Session identity

Agent ID = `cc-{PPID}` where PPID is the Claude Code process ID. All hook calls within one Claude Code session share the same PPID, so state accumulates correctly. Recycled PIDs are detected by comparing PPID start times.

## Escalation modes

| Mode | Pressure | Behavior |
|------|----------|----------|
| OBSERVE | 0-25% | Silent. Metrics recorded. |
| GUIDE | 25-50% | Soft suggestions on stderr. Mirror active. |
| WARN | 50-75% | Insistent warnings. Predictions shown. |
| BLOCK | 75-100% | Destructive ops blocked. Normal tools allowed. |

Thresholds are configurable in `soma.toml`. Claude Code defaults are higher (40/60/80) to reduce noise.

## Multi-agent

PressureGraph models inter-agent dependencies. When a child agent's pressure rises, it propagates to the parent via trust-weighted edges with damping. Per-signal PressureVector propagation lets downstream agents know *why* upstream is struggling (error rate vs drift vs cost).

## Comparison with existing tools

| Feature | Langfuse/AgentOps | SOMA |
|---------|-------------------|------|
| Who sees data | Human (dashboard) | Agent (tool response) |
| When | Post-hoc | Real-time |
| Delivery | External UI | Environment augmentation |
| Effect on agent | None | Behavioral self-correction |
| Blocking | No | Reflexes for destructive ops |
| Learning | No | Self-learning pattern cache |
