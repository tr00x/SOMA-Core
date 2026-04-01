# SOMA v1.0 — From Monitor to Nervous System

**Date:** 2026-04-01
**Status:** Design approved
**Author:** Claude + Tim

---

## Problem

SOMA has a 22-step pipeline computing 5 vitals, pressure, predictions, patterns, half-life, fingerprints, trust graphs, quality grades, budget tracking, and root cause analysis. All of it produces numbers that nobody reads. The only thing that actually DOES something is blocking `rm -rf` at high pressure.

We built a Ferrari engine but forgot to attach wheels.

## Vision

SOMA becomes a real nervous system: **sense → decide → act**. Not "sense → compute → display". Every signal the engine produces must either trigger an action or be removed. No vanity metrics.

## Design

### 1. Three Operating Modes

Users pick their level of intervention in `soma.toml`:

```toml
[soma]
mode = "reflex"  # "observe" | "guide" | "reflex"
```

**OBSERVE** — Current monitoring. Statusline, audit log, vitals. Zero intervention. For users who just want visibility.

**GUIDE** — Current behavior. Suggestions injected into context via notification hook. Agent can ignore. For experienced users who want hints.

**REFLEX** — New. Hard interventions. SOMA blocks bad actions, forces good ones, auto-checkpoints, auto-rollbacks. Agent cannot override unless explicitly configured. For production, for teams, for anyone who wants SOMA to actually work.

Each mode inherits from the previous. REFLEX includes everything GUIDE does, GUIDE includes everything OBSERVE does.

### 2. Reflex System

Reflexes are automatic actions triggered by patterns and signals. They use the existing PreToolUse hook (exit code 2 = block) but expand what triggers a block.

#### 2.1 Pattern Reflexes (from existing 7 detectors)

| Pattern | Trigger | Reflex Action | Block Message |
|---------|---------|---------------|---------------|
| blind_edits | 3+ Edit/Write without Read on target file | Block Edit, require Read first | "Read {file} first — you haven't seen its current state" |
| bash_failures | 3+ consecutive Bash errors | Block identical command, allow modified | "Same command failed {N}x. Change something before retrying." |
| thrashing | 3+ edits to same file in 10 actions | Block Edit on file for 3 actions, force Read | "You've edited {file} {N}x. Read it, plan ALL changes, one edit." |
| error_rate | >50% errors in last 10 actions | Require plan comment before next action | "Error rate {N}% — explain your approach before continuing." |
| research_stall | 7+ reads, 0 writes in last 10 | Allow but inject strong nudge | "You've read {N} files. Start writing code." |
| agent_spam | 3+ agents spawned in 10 actions | Allow but inject warning | "Check agent results before spawning more." |
| retry_dedup | Exact same Bash command repeated | Block exact duplicate | "Identical command. Change arguments or try different approach." |

#### 2.2 Signal Reflexes (from existing engine signals)

| Signal | Trigger | Reflex Action |
|--------|---------|---------------|
| Pressure predicted to escalate | Predictor says escalation in ≤3 actions | Auto `git stash push -m "soma-checkpoint-{N}"` |
| Half-life degradation | Predicted success rate < 40% | Inject: "Context degrading. Run /clear or hand off to fresh agent." |
| Drift > 0.4 | Cosine distance from task baseline | Inject original task into context: "Your task: {X}. You're doing: {Y}. Refocus." |
| Budget > 80% | Budget health < 0.2 | Reduce max_tokens suggestion, inject remaining budget |
| Budget exhausted | Budget health = 0 | Block all API calls (existing SAFE_MODE) |
| Context > 80% | Context window usage > 80% | Inject: "Context {N}% full. Checkpoint your work." |
| Context > 95% | Context window usage > 95% | Force checkpoint: auto-commit + summary |
| Quality grade D/F | Code quality grader returns D or F | Block `git commit`, require fixes |
| Anomaly detected | Fingerprint JSD divergence > threshold | Alert: "Behavioral anomaly — agent pattern changed significantly." |

#### 2.3 Agent Notification on Block

Every block includes:
1. **What** was blocked ("Edit on main.py blocked")
2. **Why** ("3 edits without reading — high chance of regression")
3. **How to proceed** ("Read main.py first, then edit")
4. **Pressure context** ("Current pressure: 56%, mode: WARN")
5. **Override** (if configured): "Add 'SOMA override' to your message to bypass"

Format injected into agent context:
```
[SOMA BLOCKED] Edit on main.py
Reason: 3 edits without reading current state (blind_edits pattern)
Fix: Read main.py first, then make your edit
Pressure: 56% (WARN) | Error rate: 40% | Drift: 0.12
```

### 3. Extracting Value from Existing Modules

#### 3.1 RCA → Diagnosis Injection (from `rca.py`)

Currently: RCA runs, produces finding, nobody sees it.
New: When error_rate > 30%, inject root cause into agent context.

```
[SOMA DIAGNOSIS] Root cause: ImportError in action #12 cascading to all subsequent Bash calls.
The module 'jwt' is not installed. Run: pip install PyJWT
```

This is the difference between "error rate high" (useless) and "you need pip install PyJWT" (actionable).

#### 3.2 Predictor → Preemptive Action (from `predictor.py`)

Currently: Predicts escalation, shows in findings.
New: When prediction confidence > 70% and escalation within 3 actions:
- GUIDE mode: inject warning with predicted trigger
- REFLEX mode: auto-checkpoint (git stash), inject warning

#### 3.3 Half-life → Handoff Protocol (from `halflife.py`)

Currently: Computes decay curve, shows in report.
New: When predicted success rate drops below threshold:
- Generate session summary (what was done, what's left, key files)
- Inject into context: "Your reliability is dropping. Here's a handoff summary for a fresh agent."
- In multi-agent graph: reduce trust weight for this agent

#### 3.4 Fingerprint → Anomaly Detection (from `fingerprint.py`)

Currently: Computes JSD divergence, stores in state.
New: When JSD divergence spikes > 2x baseline:
- Alert: behavioral pattern changed significantly
- Could indicate: prompt injection, hallucination spiral, or legitimate task change
- Log event for audit trail

#### 3.5 Graph → Circuit Breaker (from `graph.py`)

Currently: Propagates pressure vectors between agents.
New: When agent pressure > BLOCK threshold for > 5 consecutive actions:
- Circuit breaker opens: reduce trust weight to 0.1
- Downstream agents see minimal influence from degraded agent
- Alert: "Agent {X} quarantined — sustained high pressure"
- Recovery: 10 consecutive OBSERVE actions → circuit closes, trust rebuilds

#### 3.6 Quality → Commit Gate (from `quality.py`)

Currently: Grades code A-F.
New:
- Grade F: block git commit with "Code quality F — fix critical issues first"
- Grade D: warn but allow, inject issues list
- Grade C: inject "consider reviewing before commit"
- Grade A/B: positive reinforcement "[✓] clean code"

#### 3.7 Learning → Personal Thresholds (from `learning.py`)

Currently: Adjusts thresholds based on intervention outcomes.
New: Cross-session persistence means SOMA learns each agent's patterns:
- Agent that always recovers from high error rate → higher error_rate threshold
- Agent that spirals → lower thresholds, earlier intervention
- Per-task learning: "when doing refactors, this agent needs more guidance"

#### 3.8 Session Store → Experience Memory (from `session_store.py`)

Currently: Stores session records as JSON Lines.
New: Before starting similar task, check session history:
- "Last time you worked on auth.py, approach X worked after 3 failed attempts with approach Y"
- Inject relevant experience into context at session start

### 4. New Capabilities (built on core)

#### 4.1 Auto-Checkpoint

When: Predictor forecasts escalation OR before risky operation detected.
Action: `git stash push -m "soma-checkpoint-{timestamp}"` or `git add -A && git stash`
Rollback: If next 3 actions all fail → `git stash pop` and inject "rolled back to checkpoint"

#### 4.2 Smart Throttle

As pressure rises, progressively reduce suggested max_tokens:
- OBSERVE: no limit
- GUIDE: inject "keep responses focused"
- WARN: inject "max 500 tokens per response"
- BLOCK: inject "one sentence answers only"

Forces agent to think more carefully when under pressure.

#### 4.3 Scope Guardian

When drift > threshold:
1. Retrieve original task from session context
2. List files agent has touched vs files in original scope
3. Inject: "Task: {original}. Out-of-scope files touched: {list}. Refocus or confirm scope change."

#### 4.4 Retry Deduplication

Track last 5 Bash commands. If exact same command (ignoring whitespace) is submitted:
- Block with: "Identical command. Change arguments or approach."
- Show diff if command is slightly different: "Only whitespace changed. The error will be the same."

#### 4.5 Platform Adapters for Reflexes

Reflexes work through hooks. Each platform has different hook mechanisms:

| Platform | Block Mechanism | Inject Mechanism |
|----------|----------------|-----------------|
| Claude Code | PreToolUse exit(2) | Notification stdout |
| Cursor | Rules file injection | Rules file injection |
| Windsurf | Event handler return | Event context injection |
| SDK (wrap) | Raise SomaBlocked | System prompt injection |
| Any agent | record_action return | ActionResult.context_action |

The reflex engine is platform-agnostic. Adapters translate reflex decisions into platform-specific actions.

### 5. Configuration

```toml
[soma]
mode = "reflex"  # observe | guide | reflex

[reflexes]
blind_edits = true        # block edit without read
bash_retry_block = true   # block identical failed commands
thrashing_lock = true     # lock thrashed files
error_plan_required = false  # require plan at high error rate (aggressive)
auto_checkpoint = true    # git stash before predicted escalation
auto_rollback = false     # auto rollback on cascade failure (dangerous)
commit_gate = true        # block commit on quality grade D/F
retry_dedup = true        # block exact duplicate commands
scope_guardian = true     # inject task when drift detected
override_allowed = true   # allow "SOMA override" bypass

[reflexes.thresholds]
blind_edit_count = 3      # edits before block
bash_failure_count = 3    # failures before block
thrash_count = 3          # same-file edits before lock
error_rate_trigger = 0.5  # error rate for plan requirement
drift_trigger = 0.4       # drift for scope guardian
budget_warn = 0.8         # budget % for throttle
context_warn = 0.8        # context % for warning
halflife_handoff = 0.4    # success rate for handoff suggestion
```

### 6. Architecture

```
Agent Action
    │
    ▼
┌──────────────┐
│ PreToolUse   │◄── Reflex Engine checks patterns + signals
│ Hook         │    Returns: allow | block + message
└──────┬───────┘
       │ (if allowed)
       ▼
┌──────────────┐
│ Engine       │── 22-step pipeline (existing)
│ record_action│   Computes vitals, pressure, predictions
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ PostToolUse  │── Record action, update state
│ Hook         │   Check quality, update learning
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Notification │── Inject findings + reflex feedback
│ Hook         │   Agent sees: what happened, why, what to do
└──────────────┘
```

The Reflex Engine is a new module (`src/soma/reflexes.py`) that:
1. Receives tool_name, tool_input, action_log, engine snapshot
2. Checks all enabled reflexes against current state
3. Returns: allow/block decision + message + suggested action
4. Is called by PreToolUse hook (for blocking) and Notification hook (for injection)

### 7. Success Metrics

This design succeeds if:

1. **Benchmark proof**: Reflex mode reduces errors by >30% on retry_storm and degrading_session scenarios
2. **Real agent proof**: Claude Code with SOMA reflex mode completes tasks with fewer errors than without
3. **Zero false blocks on healthy sessions**: Healthy session benchmark shows 0 reflex activations
4. **User adoption signal**: Users keep reflex mode enabled (don't turn it off after trying)

### 8. What We Don't Build

- No web dashboard (Phase 14)
- No ML/neural anything (statistical methods only)
- No SaaS/cloud features
- No changes to core pipeline math (it works fine)
- No new vitals or signals (we have enough sensing, we need actuation)

### 9. Implementation Priority

**Wave 1 — Core Reflexes** (highest impact, proves the concept):
- Reflex engine module (`reflexes.py`)
- 3 modes in config (observe/guide/reflex)
- Pattern reflexes: blind_edits block, retry_dedup, bash_failure block
- Agent notification on every block (what/why/how)
- Benchmark: re-run all scenarios with reflex mode

**Wave 2 — Signal Reflexes** (leverage existing pipeline):
- Predictor → auto-checkpoint
- Drift → scope guardian injection
- Half-life → handoff suggestion
- RCA → diagnosis injection
- Quality → commit gate

**Wave 3 — Advanced** (nice-to-have):
- Graph circuit breaker
- Session memory injection
- Smart throttle
- Fingerprint anomaly detection
- Context overflow management

---

*This design transforms SOMA from a monitoring dashboard into a real nervous system. Every module we've built gets a purpose. Every number triggers an action.*
