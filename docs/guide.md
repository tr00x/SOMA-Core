# SOMA Guide -- Version 0.6.0

## Quick Start

```bash
pip install soma-ai
soma setup-claude
```

Installs hooks (PreToolUse, PostToolUse, Stop) + status line. Creates `~/.soma/` for state.

## What Happens After Setup

Every tool call flows through SOMA:

- **PreToolUse** -- evaluate reflexes (block destructive ops, retry dedup, blind edit prevention), evaluate guidance
- **PostToolUse** -- record action, validate code (py_compile + ruff + node --check), compute vitals and pressure, Mirror injection (proprioceptive context into tool response)
- **Stop** -- save state, update fingerprint, generate session summary
- **Notification / UserPromptSubmit** -- inject agent awareness prompt on first action, format and deliver findings

SOMA is active after first action. Grace period (first 10 actions) linearly ramps pressure from 0 to prevent false spikes before baselines have enough data.

## The Pressure Model

7 behavioral signals aggregated into a single 0→1 pressure score:

| Signal | What it measures | Weight |
|--------|-----------------|--------|
| uncertainty | Retries, output entropy, tool deviation, format deviation | 2.0 |
| drift | Cosine distance from baseline behavior vector (phase-aware) | 1.8 |
| error_rate | Fraction of errored actions in sliding window | 1.5 |
| goal_coherence | Cosine distance from initial task vector (after 5 actions) | 1.5 |
| context_exhaustion | Context window consumption rate (sigmoid at 50%) | 1.5 |
| cost | Cost budget utilization | 1.0 |
| token_usage | Token budget utilization | 0.8 |

Each signal is converted to pressure via sigmoid-clamped z-score against its EMA baseline. Aggregation:

```
pressure = 0.7 × weighted_mean + 0.3 × max_signal
```

Plus error-rate floor: linear ramp from 0.10 (at 20% error pressure) to 0.70 (at 100%), preventing baseline normalization of errors.

### Escalation Modes

| Mode | Default Range | Claude Code Range | Effect |
|------|--------------|-------------------|--------|
| OBSERVE | 0–25% | 0–40% | Silent. Metrics + positive feedback only. |
| GUIDE | 25–50% | 40–60% | Soft suggestions. Mirror active. Never blocks. |
| WARN | 50–75% | 60–80% | Insistent warnings. Predictions shown. Never blocks. |
| BLOCK | 75–100% | 80–100% | Blocks ONLY destructive ops. Normal tools always allowed. |

Thresholds configurable in `soma.toml`.

## Baselines and Learning

EMA with alpha=0.15 (~4.3 action half-life):

- **Actions 1–10:** Grace period with linear pressure ramp. Cold-start blending from defaults toward observed values.
- **After 10:** Pure EMA tracking. Baselines fully established.

Baselines are inherited across sessions — new sessions warm-start from the most active prior session.

### Adaptive Learning

The learning engine tracks intervention outcomes (mode escalations):

- **Success** (pressure dropped after escalation) — lower threshold to catch earlier next time
- **Failure** (pressure didn't drop) — raise threshold to reduce false alarms
- Consistent outcomes → larger adjustments (up to 3×)
- Bounded: max threshold shift ±0.10, min signal weight 0.2

This means SOMA adapts its sensitivity per agent over time.

## Reflex System

Hard blocks that fire independent of pressure level:

| Reflex | Trigger | Action |
|--------|---------|--------|
| retry_dedup | 2+ identical Bash commands | Block |
| blind_edit | 3+ Write/Edit without prior Read | Block |
| bash_failures | 2+ consecutive Bash errors | Warning |
| commit_gate | git commit when quality grade D/F | Block |
| destructive_ops | rm -rf, git push -f, git reset --hard, chmod 777, kill -9 | Block at BLOCK mode |
| sensitive_files | .env, .pem, .key, credentials, secret | Warning |

Three operating modes: **observe** (no blocking), **guide** (soft nudges), **reflex** (full blocking).

## Mirror — Proprioceptive Feedback

Mirror injects factual observations about the agent's behavior into tool responses via stdout. The agent sees this as environment data and self-corrects.

| Mode | Cost | When | Example |
|------|------|------|---------|
| PATTERN | $0 | Known pattern + cached context | `pattern: same bash cmd repeated 3x` |
| STATS | $0 | Elevated pressure, no pattern | `errors: 3/8 \| error_rate: 0.41` |
| SEMANTIC | ~$0.001 | High pressure + drift/VBD | LLM-generated behavioral observation |

**Self-learning:** After each injection, Mirror watches the next 3 actions. If pressure drops ≥10%, the context helped — it's cached in `~/.soma/patterns.json`. Ineffective patterns are pruned after 5 failures with <30% success rate.

For SEMANTIC mode: `export GEMINI_API_KEY=...` (free tier). Falls back to PATTERN/STATS on failure or timeout (3s).

## Pattern Detection

7 negative patterns detected from recent actions:

| Pattern | Trigger | Suppressed In |
|---------|---------|---------------|
| blind_edits | ≥ 3 edits without Read (checks last 30) | — |
| bash_failures | ≥ 2 consecutive Bash errors | — |
| error_rate | ≥ 30% in last 5+ actions | — |
| thrashing | Same file ≥ 3 edits in last 10 | — |
| agent_spam | ≥ 3 Agent calls in last 10 | plan, discuss |
| research_stall | 7/8 reads, 0 writes | plan, discuss |
| no_checkin | 30+ actions, 15+ mutations, 0 user interactions | execute, plan |

Plus 2 positive patterns: **good_read_edit** (3+ read-before-edit pairs), **good_clean_streak** (10+ error-free actions).

Workflow-aware: patterns suppressed when irrelevant to current phase.

## Uncertainty Classification

Classifies via output entropy (Shannon entropy over character bigrams):

- uncertainty ≤ 0.3 — no classification
- Low entropy (< 0.35) + high uncertainty — **epistemic** (agent lacks knowledge) → 1.3× pressure
- High entropy (> 0.65) + high uncertainty — **aleatoric** (task genuinely ambiguous) → 0.7× pressure

## Goal Coherence

At action #5, SOMA captures the initial task signature (behavior vector). Ongoing cosine similarity between current and initial behavior. Low coherence = agent drifted from original task = higher pressure.

## Multi-Agent Monitoring

### PressureGraph

Directed graph with trust-weighted edges modeling inter-agent dependencies:

```python
engine.add_edge("orchestrator", "worker-1", trust_weight=0.8)
engine.add_edge("orchestrator", "worker-2", trust_weight=0.6)
```

When a child agent's pressure rises, it propagates to the parent via damped trust-weighted edges (damping=0.6). Per-signal PressureVector propagation preserves causality — downstream agents know *why* upstream is struggling.

Trust decays when upstream uncertainty > 0.5, recovers when healthy. Decay:recovery ratio = 2.5:1.

Coordination SNR isolates healthy agents from noisy upstream signals.

### Subagent Monitoring

Tracks spawned child agents at `~/.soma/subagents/{parent_id}/{sub_id}.jsonl`. Computes cascade risk when subagent error rate exceeds 30% threshold.

## Cross-Session Memory

**Persists across sessions:**
- Engine state: baselines, learning adjustments, thresholds, budget, graph
- Agent fingerprints: tool distribution, error rate, read/write ratio (EMA, alpha=0.1)
- Mirror pattern database: learned effective contexts
- Session history: append-only JSONL with trajectories and tool distributions

**Resets per session:**
- Action log, predictor state, quality tracker, task tracker, bash history

### Behavioral Fingerprinting

Detects behavioral shifts via Jensen-Shannon divergence on tool distributions + error rate and read/write ratio deltas. Alert threshold: divergence ≥ 0.2. Requires ≥ 10 sessions.

### Cross-Session Prediction

Loads past session trajectories from `history.jsonl`, matches current trajectory via cosine similarity. Blends 60% current trend + 40% historical match for more accurate escalation predictions.

## Predictive Intervention

Linear trend extrapolation on recent pressure + pattern boosters:

| Pattern | Boost |
|---------|-------|
| error_streak (3+ consecutive) | +15% |
| retry_storm (error rate > 40%) | +12% |
| blind_writes (2+ without Read) | +10% |
| thrashing (same file 3+ edits) | +8% |

Warns only when confidence > 30% AND predicted pressure crosses next threshold.

## Quality Scoring

Every Write/Edit validated: py_compile + ruff (Python), node --check (JavaScript).

```
score = (write_success × bash_success) × syntax_penalty
```

| Grade | Threshold |
|-------|-----------|
| A | ≥ 90% |
| B | ≥ 80% |
| C | ≥ 70% |
| D | ≥ 50% |
| F | < 50% |

Commit gate reflex blocks `git commit` at grade D or F.

## Half-Life Modeling

Models agent reliability decay: `P(t) = exp(−ln(2) × t / half_life)`

Shorter half-life = faster degradation. When projected success rate < 50%, SOMA suggests handoff to human. Half-life estimated from session history and error rates.

## Reliability Metrics

- **Calibration:** `(1 − error_rate) × (0.5 + 0.5 × hedging_rate)` — high score means verbal caution paired with good execution
- **Verbal-behavioral divergence:** fires when `(pressure − hedging_rate) > 0.4` — agent says cautious things but acts recklessly. Forces GUIDE mode.

## Root Cause Analysis

Plain English diagnosis from action patterns:

- "stuck in Edit→Bash→Edit loop on config.py (3 cycles)"
- "error cascade: 4 consecutive Bash failures (error_rate=40%)"
- "blind mutation: 5 writes without reading"
- "possible stall: 7/8 recent actions are reads"

## Programmatic API

```python
import soma

# Quick start
engine = soma.quickstart()

# Wrap API client (Anthropic or OpenAI)
client = soma.wrap(anthropic.Anthropic())

# Universal proxy for any framework
proxy = soma.SOMAProxy(engine, "my-agent")
safe_tool = proxy.wrap_tool(my_function)

# Policy rules
pe = soma.PolicyEngine.from_file("rules.yaml")

# Guardrail decorator
@soma.guardrail(engine, "agent-1", threshold=0.8)
def risky_operation():
    ...
```

See [API Reference](api.md) for the complete programmatic interface.

## Policy Engine

Declarative rules in YAML or TOML:

```yaml
rules:
  - name: high-errors
    when:
      error_rate: {">": 0.5}
    do:
      action: warn
      message: "Error rate above 50%"
```

Load: `PolicyEngine.from_file("rules.yaml")` or `from_dict()` or `from_url()`.

## Configuration

`soma.toml` — everything tunable:

```toml
[hooks]
verbosity = "normal"      # minimal | normal | verbose
validate_python = true
lint_python = true
validate_js = true
predict = true
quality = true
fingerprint = true
task_tracking = true

[budget]
tokens = 1_000_000
cost_usd = 50.0

[thresholds]
guide = 0.25
warn = 0.50
block = 0.75

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
goal_coherence = 1.5
context_exhaustion = 1.5
cost = 1.0
token_usage = 0.8
```

## CLI Commands

```
soma                    # TUI dashboard (interactive)
soma status             # Quick text summary
soma setup-claude       # Install hooks for Claude Code
soma doctor             # Check installation health
soma agents             # List monitored agents
soma replay <file>      # Replay recorded session
soma replay --last      # Replay most recent session
soma init               # Create soma.toml via wizard
soma version            # Print version
soma stop               # Disable hooks
soma start              # Re-enable hooks
soma uninstall-claude   # Remove hooks from Claude Code
soma reset <id>         # Reset agent baseline
soma config show        # View configuration
soma config set k v     # Change configuration value
soma mode <name>        # Switch mode (strict/relaxed/autonomous)
soma policy <pack>      # Manage community policy packs
soma report             # Generate session report
soma analytics          # Show historical analytics
soma benchmark          # Run behavioral benchmarks
soma stats              # Session statistics
```

## Integrations

| Platform | Method | Status |
|----------|--------|--------|
| Claude Code | Hook system (pre/post tool use, stop) | Production |
| Anthropic API | `soma.wrap(client)` — transparent proxy | Production |
| OpenAI API | `soma.wrap(client)` — transparent proxy | Production |
| Any framework | `soma.SOMAProxy` — universal tool wrapper | Production |
| LangChain | `SomaLangChainCallback` | Adapter ready |
| CrewAI | `SomaCrewObserver` | Adapter ready |
| AutoGen | `SomaAutoGenMonitor` | Adapter ready |
| Cursor | `CursorAdapter` hook adapter | Adapter ready |
| Windsurf | `WindsurfAdapter` hook adapter | Adapter ready |
| OpenTelemetry | Metrics export (optional `otel` extra) | Built-in |
| Webhooks | HTTP POST on escalation events | Built-in |

## Files

| Path | Purpose | Scope |
|------|---------|-------|
| `soma.toml` | Project configuration | Project |
| `~/.soma/engine_state.json` | Full engine state (baselines, learning, graph) | Persistent |
| `~/.soma/state.json` | Dashboard snapshot (agents, pressure, vitals) | Persistent |
| `~/.soma/fingerprint.json` | Agent behavioral fingerprints | Persistent |
| `~/.soma/patterns.json` | Mirror self-learning database | Persistent |
| `~/.soma/audit.jsonl` | Append-only audit trail | Persistent |
| `~/.soma/sessions/history.jsonl` | Completed session summaries | Persistent |
| `~/.soma/sessions/{id}/action_log.json` | Recent actions (max 20) | Session |
| `~/.soma/sessions/{id}/trajectory.json` | Pressure values per action | Session |
| `~/.soma/sessions/{id}/quality.json` | Quality tracker state | Session |
| `~/.soma/sessions/{id}/predictor.json` | Prediction model state | Session |
| `~/.soma/sessions/{id}/task_tracker.json` | Phase and scope drift | Session |
| `~/.soma/sessions/{id}/bash_history.json` | Last 10 commands (retry dedup) | Session |
| `~/.soma/subagents/{parent}/{sub}.jsonl` | Subagent action logs | Session |
| `~/.soma/reports/` | Generated session reports | Persistent |

## Web Dashboard

SOMA includes a real-time web dashboard built on FastAPI + Server-Sent Events:

```bash
python -m soma.dashboard.server
```

Runs on port 7777. Six tabs:

| Tab | Purpose |
|-----|---------|
| Overview | Live pressure gauges, behavioral insights, findings |
| Deep Dive | Per-agent pressure timeline, vitals breakdown, baseline report |
| Analytics | Cross-session trends, tool usage distribution, mirror effectiveness |
| Logs | Filterable action log with tool names, pressure, errors, timing |
| Sessions | Session history with cross-session trend comparison |
| Settings | Mode selection, thresholds, weights, budget, policy configuration |

The dashboard reads from `~/.soma/` state files and provides live updates.

## Disabling

```bash
soma stop               # Pause (resume with soma start)
soma uninstall-claude   # Remove hooks from Claude Code
rm -rf ~/.soma          # Remove all state
```
