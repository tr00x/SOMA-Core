# SOMA API Reference

## Core

### `SOMAEngine`

The main pipeline. Records actions, computes vitals, manages pressure and levels.

```python
from soma import SOMAEngine

engine = SOMAEngine(
    budget={"tokens": 100000, "cost_usd": 5.0},
    custom_weights={"error_rate": 2.5},
    custom_thresholds={"caution": 0.40},
)
```

#### Methods

| Method | Description |
|--------|------------|
| `register_agent(agent_id, autonomy?, system_prompt?, tools?)` | Add agent to monitoring |
| `record_action(agent_id, action) -> ActionResult` | Main pipeline: action -> vitals -> pressure -> level |
| `get_level(agent_id) -> Level` | Current escalation level |
| `get_snapshot(agent_id) -> dict` | Full state: level, pressure, vitals, action_count, budget_health |
| `add_edge(source, target, trust_weight?)` | Connect agents in trust graph |
| `approve_escalation(agent_id) -> Level` | Approve pending escalation (HUMAN_IN_THE_LOOP) |
| `export_state(path?)` | Write state to JSON |
| `from_config(config?) -> SOMAEngine` | Create from soma.toml |

#### `record_action` pipeline

1. Compute uncertainty (retry rate, tool deviation, entropy, format)
2. Compute drift (cosine similarity to baseline behavior vector)
3. Compute resource vitals (token usage, cost, error rate)
4. Update baselines (EMA)
5. Compute per-signal pressure (z-score, sigmoid-clamped)
6. Aggregate pressure (0.7 * weighted mean + 0.3 * max)
7. Propagate through trust graph
8. Evaluate ladder (with learning adjustments)
9. Emit events (level_changed, approval_needed)
10. Learn from outcomes

### `Action`

```python
from soma import Action

action = Action(
    tool_name="Bash",
    output_text="output here",
    token_count=100,
    cost=0.001,
    error=False,
    retried=False,
    duration_sec=0.5,
)
```

### `ActionResult`

Returned by `record_action()`:

```python
result.level      # Level enum
result.pressure   # float [0, 1]
result.vitals     # VitalsSnapshot
result.context_action  # "pass", "truncate_20", "quarantine", etc.
```

### `Level` enum

```python
from soma import Level

Level.HEALTHY     # 0
Level.CAUTION     # 1
Level.DEGRADE     # 2
Level.QUARANTINE  # 3
Level.RESTART     # 4
Level.SAFE_MODE   # 5
```

### `AutonomyMode` enum

```python
from soma import AutonomyMode

AutonomyMode.FULLY_AUTONOMOUS   # Never asks for approval
AutonomyMode.HUMAN_ON_THE_LOOP  # Approval only for QUARANTINE+
AutonomyMode.HUMAN_IN_THE_LOOP  # Approval blocks escalation
```

## Client Wrapper

```python
from anthropic import Anthropic
from soma import wrap

client = wrap(Anthropic(), budget={"tokens": 50000})

# Use normally — SOMA monitors every API call
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=100,
)
```

Works with both Anthropic and OpenAI clients. Raises `SomaBlocked` or `SomaBudgetExhausted` when limits hit.

## Persistence

```python
from soma import save_engine_state, load_engine_state

save_engine_state(engine, "path/to/state.json")
engine = load_engine_state("path/to/state.json")
```

Full engine state serialized: agents (baselines, levels), budget, graph, learning.

## Testing

```python
from soma.testing import Monitor
from soma import Action

with Monitor(budget={"tokens": 10000}) as m:
    m.record("agent-1", Action(tool_name="Read", output_text="ok", token_count=10))
    m.record("agent-1", Action(tool_name="Bash", output_text="err", token_count=10, error=True))

    assert m.current_level("agent-1") == Level.HEALTHY
    m.assert_healthy("agent-1")
    m.assert_below("agent-1", Level.QUARANTINE)
```

## Events

```python
engine.events.on("level_changed", lambda data: print(data))
engine.events.on("approval_needed", lambda data: print(data))
```

Event data includes: agent_id, old_level, new_level, pressure, autonomy.

## Budget

```python
engine.budget.spend(tokens=100)
engine.budget.health()          # min utilization across all dimensions
engine.budget.remaining()       # {"tokens": 99900}
engine.budget.is_exhausted()    # True when health <= 0
engine.budget.replenish("tokens", 5000)
```

## Predictor

```python
from soma.predictor import PressurePredictor

p = PressurePredictor(window=10, horizon=5)
p.update(pressure=0.15, action_entry={"tool": "Read", "error": False})
pred = p.predict(next_threshold=0.40)

pred.will_escalate      # bool
pred.predicted_pressure # float
pred.dominant_reason    # "trend", "error_streak", "blind_writes", "thrashing"
pred.confidence         # float [0, 1]
```

## Quality Tracker

```python
from soma.quality import QualityTracker

qt = QualityTracker()
qt.record_write(had_syntax_error=False, had_lint_issue=True)
qt.record_bash(error=True)

report = qt.get_report()
report.grade    # "A"-"F"
report.score    # float [0, 1]
report.issues   # ["1 lint issue", "1/1 bash commands failed"]
```

## Fingerprint Engine

```python
from soma.fingerprint import FingerprintEngine

fe = FingerprintEngine(alpha=0.1)
fe.update_from_session("agent-1", action_log)

div, explanation = fe.check_divergence("agent-1", current_log)
# div=0.45, explanation="Bash +30%, Read -25%"
```

## Task Tracker

```python
from soma.task_tracker import TaskTracker

tt = TaskTracker(drift_window=10)
tt.record("Read", "/src/auth.py")
tt.record("Edit", "/src/auth.py")

ctx = tt.get_context()
ctx.phase          # "implement"
ctx.focus_files    # ["auth.py"]
ctx.scope_drift    # 0.0
```

## Root Cause Analysis

```python
from soma.rca import diagnose

result = diagnose(action_log, vitals, pressure, level_name, action_count)
# "stuck in Edit->Bash loop on config.py (4 cycles)"
# or None if nothing notable
```
