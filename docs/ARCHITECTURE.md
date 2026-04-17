# SOMA Architecture

Behavioral monitoring for AI agents. Observes actions, computes pressure from vital signals, injects corrective guidance before problems escalate.

## Pipeline

```
action --> vitals --> pressure --> guidance --> injection
  |          |          |            |            |
  |  uncertainty   z-score +    OBSERVE      stderr (pre)
  |  drift         sigmoid     GUIDE         stdout (post)
  |  error_rate    mean+max    WARN          messages (SDK)
  |  token_usage   aggregate   BLOCK
  |  cost
  v
analytics.db
```

Every agent action flows through this pipeline. The engine computes five vital signals, derives aggregate pressure (0-1 scalar), maps pressure to a response mode, and injects guidance into the agent's context.

## Integration Paths

### 1. Hooks (Claude Code)

```
Claude Code
  |
  |  CLAUDE_HOOK=PreToolUse
  v
soma-hook (dispatcher)
  |
  +--> pre_tool_use.py ---> stderr (pre-action guidance)
  |
  |  CLAUDE_HOOK=PostToolUse
  |
  +--> post_tool_use.py --> stdout (injected into tool response)
  |
  +--> stop.py -----------> session teardown
  +--> notification.py ---> notification handling
```

The dispatcher (`hooks/claude_code.py`) routes by `CLAUDE_HOOK` env var. PreToolUse writes guidance to stderr. PostToolUse records the action, evaluates contextual guidance, and writes to stdout where Claude Code appends it to the tool response. Hooks never crash -- all exceptions are caught and suppressed.

### 2. wrap() (SDK)

```python
client = soma.wrap(anthropic.Anthropic())
```

Returns a `WrappedClient` proxy that intercepts all LLM calls, applies engine rules, and emits events. Raises `SomaBlocked` when pressure exceeds thresholds, `SomaBudgetExhausted` when a budget dimension is spent.

## Core Modules

```
src/soma/
  |
  +-- engine.py              SOMAEngine orchestrates the full pipeline
  |     |                    ActionResult, _AgentState
  |     |
  |     +-- vitals.py        compute_uncertainty, compute_drift,
  |     |                    compute_error_rate, compute_resource_vitals
  |     |
  |     +-- pressure.py      z-score via sigmoid, blended mean+max aggregate
  |     |
  |     +-- baseline.py      EMA baseline with cold-start blending
  |     |
  |     +-- guidance.py      pressure_to_mode() -> OBSERVE/GUIDE/WARN/BLOCK
  |     |
  |     +-- budget.py        MultiBudget (spend/replenish/health/burn_rate)
  |     |
  |     +-- graph.py         PressureGraph -- inter-agent pressure propagation
  |     |
  |     +-- learning.py      LearningEngine -- adaptive threshold adjustment
  |     |
  |     +-- lessons.py       LessonStore -- trigram similarity matching
  |     |
  |     +-- analytics.py     SQLite analytics, source-tagged, soma_version
  |
  +-- contextual_guidance.py 10 pattern-based guidance messages
  |                          cooldowns, severity ranking, healing transitions
  |
  +-- context.py             Session context (GSD mode, action count)
  +-- findings.py            Aggregate findings from subsystems
  +-- recorder.py            SessionRecorder, RecordedAction
  +-- persistence.py         Atomic state save/load with file locking
  +-- wrap.py                WrappedClient proxy for SDK integration
  +-- types.py               Action, VitalsSnapshot, AgentConfig, ResponseMode
  +-- errors.py              SOMAError, AgentNotFound, NoBudget
  |
  +-- hooks/
  |     +-- claude_code.py   Dispatcher (routes by CLAUDE_HOOK)
  |     +-- pre_tool_use.py  Pre-action guidance -> stderr
  |     +-- post_tool_use.py Post-action recording + guidance -> stdout
  |     +-- stop.py          Session teardown
  |     +-- notification.py  Notification handling
  |     +-- statusline.py    Status bar formatter
  |     +-- common.py        Shared state utilities
  |
  +-- cli/
        +-- main.py          Argparse router, 20+ subcommands
        +-- hub.py           Textual TUI dashboard
        +-- config_loader.py soma.toml parser with fallback defaults
        +-- tabs/            Dashboard tab modules
```

## Data Flow

```
                   +------------------+
                   |   Agent Action   |
                   +--------+---------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
     action_log (memory)          analytics.db (SQLite)
     list of dicts per session    source-tagged, versioned
              |
              v
   ContextualGuidance.evaluate()
              |
              v
      GuidanceMessage
              |
     +--------+--------+
     |                  |
     v                  v
  stdout             messages
  (hooks)            (SDK wrap)
```

### State Persistence

```
~/.soma/
  +-- engine_state.json    Engine state (atomic write: tmp -> fsync -> rename)
  +-- state.json           Session state
  +-- analytics.db         SQLite action log
```

Engine state uses file locking to prevent concurrent corruption. Subsystem state (quality tracker, predictor, fingerprint engine) loads lazily via `state.py` getters.

## Key Types

| Type | Kind | Purpose |
|------|------|---------|
| `Action` | frozen dataclass | Immutable record of a single agent action |
| `VitalsSnapshot` | frozen dataclass | Point-in-time behavioral health metrics |
| `AgentConfig` | mutable dataclass | Per-agent configuration |
| `ResponseMode` | ordered enum | OBSERVE / GUIDE / WARN / BLOCK |
| `ActionResult` | dataclass | Engine response after processing an action |
| `GuidanceMessage` | dataclass | Contextual guidance with pattern, severity, cooldown |

## Pressure Model

Five vital signals feed the pressure computation:

1. **Uncertainty** -- entropy of recent action distribution
2. **Drift** -- deviation from established behavioral baseline
3. **Error rate** -- ratio of failed/errored actions
4. **Token usage** -- resource consumption rate
5. **Cost** -- monetary spend rate

Each signal is compared against its EMA baseline (with cold-start blending to avoid false positives in early sessions). The deviation is converted to a 0-1 pressure via z-score through a sigmoid function. Aggregate pressure is a blended mean+max of individual signal pressures.

Pressure maps to response modes via configurable thresholds:

```
0.00 - 0.25  OBSERVE   silent, metrics only
0.25 - 0.50  GUIDE     suggest corrections
0.50 - 0.75  WARN      alert, flag destructive ops
0.75 - 1.00  BLOCK     restrict destructive operations
```

## Entry Points

| Entry point | Source | Trigger |
|-------------|--------|---------|
| `soma` | `cli/main.py` | User runs CLI |
| `soma-hook` | `hooks/claude_code.py` | Claude Code dispatches hook |
| `soma-statusline` | `hooks/statusline.py` | Status bar update |
| `soma.quickstart()` | `__init__.py` | Programmatic setup |
| `soma.wrap(client)` | `wrap.py` | SDK integration |
| `SOMAEngine()` | `engine.py` | Direct engine use |
