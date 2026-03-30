# SOMA API Reference

## Core

### `SOMAEngine`

The main pipeline. Records actions, computes vitals, manages pressure and modes.

```python
from soma import SOMAEngine

engine = SOMAEngine(
    budget={"tokens": 100000, "cost_usd": 5.0},
    custom_weights={"error_rate": 2.5},
    custom_thresholds={"guide": 0.40},
)
```

#### Methods

| Method | Description |
|--------|------------|
| `register_agent(agent_id, autonomy?, system_prompt?, tools?)` | Add agent to monitoring |
| `record_action(agent_id, action) -> ActionResult` | Main pipeline: action -> vitals -> pressure -> mode |
| `get_level(agent_id) -> ResponseMode` | Current response mode (alias `get_mode`) |
| `get_snapshot(agent_id) -> dict` | Full state: mode, pressure, vitals, action_count, budget_health |
| `add_edge(source, target, trust_weight?)` | Connect agents in trust graph |
| `approve_escalation(agent_id) -> ResponseMode` | Approve pending escalation (HUMAN_IN_THE_LOOP) |
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
8. Map pressure to response mode via `pressure_to_mode()`
9. Emit events (mode_changed, approval_needed)
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
result.mode       # ResponseMode enum (primary)
result.level      # Alias for result.mode (backward compat)
result.pressure   # float [0, 1]
result.vitals     # VitalsSnapshot
result.context_action  # "pass", "truncate_20", etc.
```

### `ResponseMode` enum

```python
from soma import ResponseMode

ResponseMode.OBSERVE  # 0 — silent, metrics only
ResponseMode.GUIDE    # 1 — soft suggestions
ResponseMode.WARN     # 2 — insistent warnings
ResponseMode.BLOCK    # 3 — blocks destructive ops only
```

Legacy alias: `Level = ResponseMode`. The old names (`HEALTHY`, `CAUTION`, `DEGRADE`, `QUARANTINE`, `RESTART`, `SAFE_MODE`) exist as enum aliases and will be removed in 0.5.0.

### `GuidanceResponse`

Returned by `guidance.evaluate()`:

```python
from soma.guidance import GuidanceResponse

response.mode        # ResponseMode
response.allow       # bool — True unless destructive op at BLOCK
response.message     # str | None — human-readable guidance
response.suggestions # list[str] — context-aware suggestions
```

### `AutonomyMode` enum

```python
from soma import AutonomyMode

AutonomyMode.FULLY_AUTONOMOUS   # Never asks for approval
AutonomyMode.HUMAN_ON_THE_LOOP  # Approval only for BLOCK+
AutonomyMode.HUMAN_IN_THE_LOOP  # Approval blocks escalation
```

## Core Modules

### `soma.patterns` — Pattern Analysis

Detects behavioral patterns in agent action logs. Layer-agnostic: returns structured `PatternResult` objects.

#### `PatternResult`

```python
from soma.patterns import PatternResult

PatternResult(
    kind="blind_edits",     # pattern type
    severity="warning",     # "positive", "info", "warning", "critical"
    action="Read before editing (foo.py, bar.py)",  # what agent should do
    detail="you made 4 edits to files you haven't read",
    data={"count": 4, "files": ["foo.py", "bar.py"]},
)
```

Pattern kinds: `blind_edits`, `bash_failures`, `error_rate`, `thrashing`, `agent_spam`, `research_stall`, `no_checkin`, `good_read_edit`, `good_clean_streak`.

#### `analyze()`

```python
from soma.patterns import analyze

results = analyze(action_log, workflow_mode="")
# Returns: list[PatternResult], max 3, sorted by severity
```

Args:
- `action_log`: list of action dicts with keys: `tool`, `error`, `file`, `ts`
- `workflow_mode`: `""` (default), `"plan"`, `"execute"`, `"discuss"`, `"fast"` — suppresses irrelevant patterns per mode

### `soma.findings` — Findings Collector

Gathers all monitoring insights (patterns, quality, predictions, scope drift, fingerprint divergence, RCA) into a structured list. Layers call `collect()` and format the results.

#### `Finding`

```python
from soma.findings import Finding

Finding(
    priority=0,          # 0=critical (always show), 1=important, 2=informational
    category="status",   # "status", "quality", "predict", "pattern", "scope",
                         # "fingerprint", "rca", "positive"
    message="Pressure elevated (p=65%)",
    action="Slow down. Read->Think->Act, not Act->Fix->Retry",
)
```

#### `collect()`

```python
from soma.findings import collect

findings = collect(
    action_log=action_log,
    vitals=vitals_dict,
    pressure=0.65,
    level_name="WARN",        # OBSERVE, GUIDE, WARN, BLOCK
    actions=30,
    hook_config={"quality": True, "predict": True},
)
# Returns: list[Finding], sorted by priority (critical first)
```

### `soma.context` — Session Context

Provides structured context about the agent's working environment. Used by patterns, findings, and layers for context-aware behavior.

#### `SessionContext`

```python
from soma.context import SessionContext

SessionContext(
    cwd="/path/to/project",
    workflow_mode="execute",   # "", "plan", "execute", "discuss", "fast"
    gsd_active=True,           # .planning/ directory exists
    action_count=42,
    pressure=0.30,
)
```

#### `detect_workflow_mode()`

```python
from soma.context import detect_workflow_mode

mode = detect_workflow_mode(cwd="/path/to/project")
# Returns: "" (default), "plan", "execute", "discuss", "fast"
# Reads .planning/STATE.md to infer GSD workflow phase
```

#### `get_session_context()`

```python
from soma.context import get_session_context

ctx = get_session_context(cwd="", action_count=42, pressure=0.30)
# Returns: SessionContext with all fields populated
# cwd defaults to CLAUDE_WORKING_DIRECTORY env var or os.getcwd()
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
from soma import Action, ResponseMode

with Monitor(budget={"tokens": 10000}) as m:
    m.record("agent-1", Action(tool_name="Read", output_text="ok", token_count=10))
    m.record("agent-1", Action(tool_name="Bash", output_text="err", token_count=10, error=True))

    assert m.current_level("agent-1") == ResponseMode.OBSERVE
    m.assert_healthy("agent-1")
    m.assert_below("agent-1", ResponseMode.BLOCK)
```

## Guidance

The guidance module (`soma.guidance`) is the decision point for all tool calls.

```python
from soma.guidance import pressure_to_mode, evaluate, is_destructive_bash, is_sensitive_file

# Map pressure to response mode (with optional custom thresholds)
mode = pressure_to_mode(0.60)  # ResponseMode.WARN
mode = pressure_to_mode(0.60, thresholds={"guide": 0.40, "warn": 0.60, "block": 0.80})

# Full guidance evaluation (used by PreToolUse hook)
response = evaluate(
    pressure=0.80,
    tool_name="Bash",
    tool_input={"command": "rm -rf /tmp/build"},
    action_log=[...],
    thresholds={"guide": 0.40, "warn": 0.60, "block": 0.80},
)
response.allow       # False — destructive bash at BLOCK mode
response.message     # "SOMA blocked: destructive command: rm -rf /tmp/build (p=80%)"

# Utility checks
is_destructive_bash("git push --force origin main")  # True
is_destructive_bash("python main.py")                 # False
is_sensitive_file(".env.production")                   # True
is_sensitive_file("src/main.py")                       # False
```

Default thresholds: `guide=0.25, warn=0.50, block=0.75`.
Claude Code overrides: `guide=0.40, warn=0.60, block=0.80`.

## Events

```python
engine.events.on("mode_changed", lambda data: print(data))
engine.events.on("approval_needed", lambda data: print(data))
```

Event data includes: agent_id, old_mode, new_mode, pressure, autonomy.

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

tt = TaskTracker(drift_window=10, cwd="/path/to/project")
tt.record("Read", "/src/auth.py")
tt.record("Edit", "/src/auth.py")

ctx = tt.get_context()
ctx.phase          # "implement"
ctx.focus_files    # ["auth.py"]
ctx.scope_drift    # 0.0

eff = tt.get_efficiency()
eff["context_efficiency"]  # read-to-write ratio (0-1)
eff["success_rate"]        # 1.0 - error_rate
eff["focus"]               # 1.0 - scope_drift
```

## Root Cause Analysis

```python
from soma.rca import diagnose

result = diagnose(action_log, vitals, pressure, level_name, action_count)
# "stuck in Edit->Bash loop on config.py (4 cycles)"
# or None if nothing notable
```
