# SOMA API Reference — Version 0.6.0

## Core

### SOMAEngine

```python
from soma import SOMAEngine

engine = SOMAEngine(
    budget={"tokens": 100000, "cost_usd": 5.0},
    custom_weights={"error_rate": 2.5},
    custom_thresholds={"guide": 0.40},
)
```

| Method | Description |
|--------|------------|
| `register_agent(agent_id, autonomy?, system_prompt?, tools?)` | Add agent to monitoring |
| `record_action(agent_id, action) → ActionResult` | Main pipeline — compute vitals, pressure, mode |
| `get_level(agent_id) → ResponseMode` | Current escalation mode |
| `get_snapshot(agent_id) → dict` | Full state snapshot for dashboard/export |
| `add_edge(source, target, trust_weight?)` | Connect agents in PressureGraph |
| `export_state(path?)` | Write engine state to JSON (atomic) |
| `from_config(config?) → SOMAEngine` | Create from soma.toml |
| `quickstart(budget?, agents?) → SOMAEngine` | Convenience factory with defaults |

### Action

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

Frozen dataclass with slots. All fields optional except `tool_name`.

### ActionResult

```python
result = engine.record_action(agent_id, action)

result.mode              # ResponseMode (OBSERVE/GUIDE/WARN/BLOCK)
result.pressure          # float [0, 1]
result.vitals            # VitalsSnapshot
result.context_action    # "pass", "guide", "warn", "block_destructive"
result.pressure_vector   # PressureVector | None
result.handoff_suggestion # str | None (half-life warning)
result.level             # Alias for result.mode
```

### ResponseMode

```python
from soma import ResponseMode

ResponseMode.OBSERVE  # 0 — silent monitoring
ResponseMode.GUIDE    # 1 — soft suggestions
ResponseMode.WARN     # 2 — insistent warnings
ResponseMode.BLOCK    # 3 — blocks destructive ops only
```

### VitalsSnapshot

```python
from soma import VitalsSnapshot

# All fields (frozen dataclass):
uncertainty: float = 0.0
drift: float = 0.0
drift_mode: DriftMode = DriftMode.INFORMATIONAL
token_usage: float = 0.0
cost: float = 0.0
error_rate: float = 0.0
goal_coherence: float | None = None          # None during warmup (<5 actions)
baseline_integrity: bool = True
uncertainty_type: str | None = None           # "epistemic", "aleatoric", or None
task_complexity: float | None = None
predicted_success_rate: float | None = None
half_life_warning: bool = False
calibration_score: float | None = None        # None during warmup (<3 actions)
verbal_behavioral_divergence: bool = False
context_usage: float = 0.0                    # Context window utilization
context_burn_rate: float = 0.0                # Tokens per action
```

### PressureVector

```python
from soma.types import PressureVector

pv = PressureVector(uncertainty=0.3, drift=0.1, error_rate=0.8, cost=0.0)
pv.to_dict()              # {"uncertainty": 0.3, ...}
PressureVector.from_dict(d)
```

Per-signal pressure for multi-agent propagation — downstream agents see *why* upstream is struggling.

### AutonomyMode

```python
from soma import AutonomyMode

AutonomyMode.FULLY_AUTONOMOUS
AutonomyMode.HUMAN_ON_THE_LOOP   # default
AutonomyMode.HUMAN_IN_THE_LOOP
```

---

## Client Wrapper

### wrap()

```python
from anthropic import Anthropic
from soma import wrap

client = wrap(Anthropic(), budget={"tokens": 50000})
response = client.messages.create(model="claude-sonnet-4-20250514", messages=[...], max_tokens=100)
```

Works with both Anthropic and OpenAI clients. Intercepts `messages.create()`, `messages.stream()` (Anthropic) and `chat.completions.create()` (OpenAI). Supports sync and async.

Raises `SomaBlocked` at BLOCK mode or `SomaBudgetExhausted` when budget is spent.

### Streaming

```python
# Anthropic streaming (context manager)
with client.messages.stream(model=..., messages=..., max_tokens=100) as stream:
    for text in stream.text_stream:
        print(text)
# Action recorded automatically on exit

# OpenAI streaming (iterator)
stream = client.chat.completions.create(model=..., messages=..., stream=True)
for chunk in stream:
    print(chunk.choices[0].delta.content)
```

---

## SOMAProxy — Universal Tool Wrapper

For any framework (LangChain, CrewAI, AutoGen, custom agents):

```python
from soma import SOMAProxy

proxy = SOMAProxy(engine, "my-agent")

# Wrap individual tools
safe_tool = proxy.wrap_tool(my_function)
result = safe_tool(args)  # Monitored, blocked if reflex fires

# Wrap a list of tools (LangChain-compatible)
safe_tools = proxy.wrap_tools([tool1, tool2, tool3])

# Wrap an entire agent object
safe_agent = proxy.wrap_agent(my_agent)

# Spawn monitored child agent
child = proxy.spawn_subagent("child-agent")
child_tool = child.wrap_tool(child_function)
```

Raises `SOMABlockError` when reflexes block a tool call.

---

## Context Manager

```python
from soma import track

with track(engine, "agent-1", "Bash") as t:
    result = run_something()
    t.set_output(result)
    t.set_error(False)
    t.set_tokens(150)
    t.set_cost(0.01)

print(t.result.pressure)
```

---

## Framework Adapters

### LangChain

```python
from soma.sdk.langchain import SomaLangChainCallback

callback = SomaLangChainCallback(engine, "my-agent")
chain.invoke(input, config={"callbacks": [callback]})
```

Hooks: on_llm_start, on_llm_end, on_llm_error, on_tool_start, on_tool_end, on_tool_error.

### CrewAI

```python
from soma.sdk.crewai import SomaCrewObserver

observer = SomaCrewObserver(engine)
observer.attach(crew)
```

Patches all agents' execute_task(). Uses `agent.role` as agent_id.

### AutoGen

```python
from soma.sdk.autogen import SomaAutoGenMonitor

monitor = SomaAutoGenMonitor(engine)
monitor.attach(agent)
```

Wraps generate_reply(). Uses `agent.name` as agent_id.

---

## Mirror — Proprioceptive Feedback

```python
from soma.mirror import Mirror

mirror = Mirror(engine, "agent-1")

# Generate context for current behavioral state
context = mirror.generate(pressure=0.45, vitals=vitals, action_log=log)
# Returns: "--- session context ---\nerrors: 3/8 | error_rate: 0.41\n---"

# Track injection for self-learning
mirror.track_injection(pattern_key="error_rate", context_text=context, pressure=0.45)

# Evaluate after 3 actions — did the context help?
mirror.evaluate_pending(current_pressure=0.30)

# Record outcome manually
mirror.record_outcome(pattern_key="error_rate", helped=True)
```

Three modes: PATTERN ($0), STATS ($0), SEMANTIC (~$0.001). Not in main `__init__.py` — import directly.

---

## Policy Engine

```python
from soma import PolicyEngine
from soma.policy import Rule, PolicyCondition, PolicyAction

# From code
rules = [
    Rule("high-error",
         [PolicyCondition("error_rate", ">=", 0.5)],
         PolicyAction("warn", "Error rate above 50%")),
]
pe = PolicyEngine(rules)

# From file (YAML or TOML)
pe = PolicyEngine.from_file("rules.yaml")
pe = PolicyEngine.from_dict({"rules": [...]})
pe = PolicyEngine.from_url("https://...")

# Evaluate
actions = pe.evaluate(vitals_snapshot, pressure=0.65)
for a in actions:
    a.action   # "warn", "block", "guide", "log"
    a.message  # str
```

Fields: pressure, uncertainty, drift, error_rate, token_usage, cost, calibration_score.
Operators: `>=`, `<=`, `>`, `<`, `==`, `!=`. Conditions within a rule are AND-joined.

---

## Guardrail Decorator

```python
from soma import guardrail

@guardrail(engine, "agent-1", threshold=0.8)
def risky_operation():
    ...  # Raises SomaBlocked when pressure >= 0.8

# Works with async functions too
@guardrail(engine, "agent-1", threshold=0.8)
async def async_risky():
    ...
```

---

## Guidance

```python
from soma.guidance import pressure_to_mode, evaluate, is_destructive_bash, is_sensitive_file

mode = pressure_to_mode(0.60)  # ResponseMode.WARN
mode = pressure_to_mode(0.60, thresholds={"guide": 0.40, "warn": 0.60, "block": 0.80})

response = evaluate(
    pressure=0.80,
    tool_name="Bash",
    tool_input={"command": "rm -rf /tmp"},
    action_log=[...],
)
response.allow       # False (destructive at BLOCK)
response.message     # "SOMA blocked: destructive command: rm -rf /tmp (p=80%)"
response.mode        # ResponseMode.BLOCK
response.suggestions # list[str]

is_destructive_bash("rm -rf /")      # True
is_sensitive_file(".env.production")  # True
```

---

## Predictor

```python
from soma.predictor import PressurePredictor

p = PressurePredictor(window=10, horizon=5)
p.update(pressure=0.15, action_entry={"tool": "Read", "error": False})

pred = p.predict(next_threshold=0.40)
pred.will_escalate      # bool
pred.predicted_pressure # float
pred.dominant_reason    # "trend", "error_streak", "blind_writes", "thrashing", "retry_storm"
pred.confidence         # float [0, 1]
pred.actions_ahead      # int (default 5)
```

---

## Quality Tracker

```python
from soma.quality import QualityTracker

qt = QualityTracker(window=30)
qt.record_write(had_syntax_error=False, had_lint_issue=True)
qt.record_bash(error=True)

report = qt.get_report()
report.grade    # "A", "B", "C", "D", "F"
report.score    # float [0, 1]
report.issues   # list[str]
report.syntax_errors   # int
report.lint_issues     # int
report.bash_failures   # int
```

---

## Fingerprint Engine

```python
from soma.fingerprint import FingerprintEngine

fe = FingerprintEngine(alpha=0.1)
fe.update_from_session("agent-1", action_log)

div, explanation = fe.check_divergence("agent-1", current_log)
# div=0.45, explanation="Bash +30%, Read -25%"
```

---

## Task Tracker

```python
from soma.task_tracker import TaskTracker

tt = TaskTracker(drift_window=10, cwd="/path/to/project")
tt.record("Read", "/src/auth.py")

ctx = tt.get_context()
ctx.phase          # "research", "implement", "test", "debug", "unknown"
ctx.focus_files    # ["auth.py"]
ctx.focus_dirs     # ["/src"]
ctx.scope_drift    # float [0, 1]
ctx.drift_explanation  # str

eff = tt.get_efficiency()
eff["context_efficiency"]  # read-to-write ratio
eff["success_rate"]        # 1.0 - error_rate
eff["focus"]               # 1.0 - scope_drift
```

---

## Root Cause Analysis

```python
from soma.rca import diagnose

result = diagnose(action_log, vitals_dict, pressure, level_name, action_count)
# "stuck in Edit->Bash loop on config.py (4 cycles)" or None
```

---

## Patterns

```python
from soma.patterns import analyze

results = analyze(action_log, workflow_mode="execute")
for r in results:
    r.kind       # "blind_edits", "bash_failures", "thrashing", etc.
    r.severity   # "positive", "info", "warning", "critical"
    r.action     # what to do
    r.detail     # context
```

Max 3 results, sorted by severity. Workflow-aware suppression.

---

## Findings

```python
from soma.findings import collect

findings = collect(action_log, vitals_dict, pressure, "WARN", 30, hook_config)
for f in findings:
    f.priority   # 0=critical, 1=important, 2=informational
    f.category   # "status", "quality", "predict", "pattern", "scope", "fingerprint", "rca", "positive"
    f.message    # what's happening
    f.action     # what to do
```

---

## Uncertainty Classification

```python
from soma.vitals import classify_uncertainty

classify_uncertainty(uncertainty=0.5, task_entropy=0.2)   # "epistemic"
classify_uncertainty(uncertainty=0.5, task_entropy=0.8)   # "aleatoric"
classify_uncertainty(uncertainty=0.1, task_entropy=0.2)   # None (below 0.3)
```

---

## Reliability Metrics

```python
from soma.reliability import compute_calibration_score, detect_verbal_behavioral_divergence, compute_hedging_rate

score = compute_calibration_score(hedging_rate=0.5, error_rate=0.0)  # 0.75
divergent = detect_verbal_behavioral_divergence(hedging_rate=0.1, pressure=0.8)  # True
rate = compute_hedging_rate(actions)  # float [0, 1]
```

---

## Half-Life

```python
from soma.halflife import compute_half_life, predict_success_rate, predict_actions_to_threshold, generate_handoff_suggestion

hl = compute_half_life(avg_session_length=90.0, avg_error_rate=0.15)  # 76.5
p = predict_success_rate(action_count=45, half_life=hl)  # 0.67
remaining = predict_actions_to_threshold(action_count=45, half_life=hl)  # 31
msg = generate_handoff_suggestion("agent-1", 45, hl, p)
```

---

## Budget

```python
engine.budget.spend(tokens=100, cost_usd=0.01)
engine.budget.health()              # min remaining ratio across dimensions
engine.budget.remaining()           # {"tokens": 99900, ...}
engine.budget.utilization("tokens") # float [0, 1]
engine.budget.is_exhausted()        # True when health <= 0
engine.budget.burn_rate("tokens")   # spend per second
engine.budget.replenish("tokens", 5000)
engine.budget.projected_overshoot("tokens", total_steps=100, current_step=50)
```

---

## Persistence

```python
from soma import save_engine_state, load_engine_state

save_engine_state(engine, "state.json")  # Atomic: fcntl lock → temp → fsync → rename
engine = load_engine_state("state.json")
```

---

## Events

```python
engine.events.on("action_recorded", lambda data: print(data))
engine.events.on("level_changed", lambda data: print(data))
engine.events.on("mode_changed", lambda data: print(data))
engine.events.on("half_life_warning", lambda data: print(data))
engine.events.on("verbal_behavioral_divergence", lambda data: print(data))
```

---

## Hook Adapters

```python
from soma.hooks import ClaudeCodeAdapter, CursorAdapter, WindsurfAdapter, HookAdapter, HookInput, HookResult

# Platform adapters implement HookAdapter protocol
adapter = ClaudeCodeAdapter()   # Native Claude Code env vars
adapter = CursorAdapter()       # Cursor IDE
adapter = WindsurfAdapter()     # Windsurf IDE

input_data = adapter.parse_input()  # → HookInput
result = HookResult(allow=True, message="OK")
adapter.send_result(result)
```

---

## Exceptions

```python
from soma import SomaBlocked, SomaBudgetExhausted, SOMABlockError

# SomaBlocked — raised by WrappedClient when pressure >= BLOCK threshold
try:
    client.messages.create(...)
except SomaBlocked as e:
    e.agent_id   # str
    e.level      # ResponseMode
    e.pressure   # float

# SomaBudgetExhausted — raised when a budget dimension is spent
try:
    client.messages.create(...)
except SomaBudgetExhausted as e:
    e.dimension  # "tokens" or "cost_usd"

# SOMABlockError — raised by SOMAProxy when reflexes block a tool
try:
    safe_tool(args)
except SOMABlockError:
    pass
```
