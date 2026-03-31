# SOMA API Reference — Version 0.5.0

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

Methods:
| Method | Description |
|--------|------------|
| register_agent(agent_id, autonomy?, system_prompt?, tools?) | Add agent |
| record_action(agent_id, action) → ActionResult | Main pipeline (22 steps) |
| get_level(agent_id) → ResponseMode | Current mode |
| get_snapshot(agent_id) → dict | Full state snapshot |
| add_edge(source, target, trust_weight?) | Connect agents in trust graph |
| export_state(path?) | Write state to JSON |
| from_config(config?) → SOMAEngine | Create from soma.toml |
| quickstart(budget?, agents?) → SOMAEngine | Convenience factory |

record_action pipeline steps (brief): ring buffer → task complexity → initial signature → uncertainty → drift → time anomaly → resources → drift mode → baseline update → signal pressure → floors → classification → goal coherence → baseline integrity → half-life → burn rate → weight adjustment → upstream influence → aggregate → propagation → grace period → trust dynamics → reliability → mode determination → ActionResult

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
Frozen dataclass with slots.

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
ResponseMode.OBSERVE  # 0
ResponseMode.GUIDE    # 1
ResponseMode.WARN     # 2
ResponseMode.BLOCK    # 3
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
```

### PressureVector
```python
from soma.types import PressureVector
pv = PressureVector(uncertainty=0.3, drift=0.1, error_rate=0.8, cost=0.0)
pv.to_dict()    # {"uncertainty": 0.3, ...}
PressureVector.from_dict(d)
```

### AutonomyMode
```python
from soma import AutonomyMode
AutonomyMode.FULLY_AUTONOMOUS
AutonomyMode.HUMAN_ON_THE_LOOP   # default
AutonomyMode.HUMAN_IN_THE_LOOP
```

## Client Wrapper
```python
from anthropic import Anthropic
from soma import wrap
client = wrap(Anthropic(), budget={"tokens": 50000})
# Use normally — SOMA monitors every API call
response = client.messages.create(model="claude-sonnet-4-20250514", messages=[...], max_tokens=100)
```
Works with Anthropic and OpenAI. Raises SomaBlocked or SomaBudgetExhausted.

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

## Framework Adapters

### LangChain
```python
from soma.sdk.langchain import SomaLangChainCallback
callback = SomaLangChainCallback(engine, "my-agent")
chain.invoke(input, config={"callbacks": [callback]})
```
Hooks: on_llm_start, on_llm_end, on_llm_error, on_tool_start, on_tool_end, on_tool_error

### CrewAI
```python
from soma.sdk.crewai import SomaCrewObserver
observer = SomaCrewObserver(engine)
observer.attach(crew)
```
Patches all agents' execute_task(). Uses agent.role as agent_id.

### AutoGen
```python
from soma.sdk.autogen import SomaAutoGenMonitor
monitor = SomaAutoGenMonitor(engine)
monitor.attach(agent)
```
Wraps generate_reply(). Uses agent.name as agent_id.

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

# From file
pe = PolicyEngine.from_file("rules.yaml")   # YAML or TOML
pe = PolicyEngine.from_dict({"rules": [...]})
pe = PolicyEngine.from_url("https://...")

# Evaluate
actions = pe.evaluate(vitals_snapshot, pressure=0.65)
for a in actions:
    a.action   # "warn", "block", "guide", "log"
    a.message  # str
```

Supported fields: pressure, uncertainty, drift, error_rate, token_usage, cost, calibration_score
Supported operators: >=, <=, >, <, ==, !=

## Guardrail Decorator
```python
from soma import guardrail
@guardrail(engine, "agent-1", threshold=0.8)
def risky_operation():
    ...  # Raises SomaBlocked when pressure >= 0.8
# Works with async functions too
```

## Guidance
```python
from soma.guidance import pressure_to_mode, evaluate, is_destructive_bash, is_sensitive_file

mode = pressure_to_mode(0.60)  # ResponseMode.WARN
mode = pressure_to_mode(0.60, thresholds={"guide": 0.40, "warn": 0.60, "block": 0.80})

response = evaluate(pressure=0.80, tool_name="Bash",
    tool_input={"command": "rm -rf /tmp"}, action_log=[...])
response.allow       # False (destructive at BLOCK)
response.message     # "SOMA blocked: destructive command: rm -rf /tmp (p=80%)"
response.mode        # ResponseMode.BLOCK
response.suggestions # list[str]
```
Default thresholds: guide=0.25, warn=0.50, block=0.75

## Uncertainty Classification
```python
from soma.vitals import classify_uncertainty
classify_uncertainty(uncertainty=0.5, task_entropy=0.2)   # "epistemic"
classify_uncertainty(uncertainty=0.5, task_entropy=0.8)   # "aleatoric"
classify_uncertainty(uncertainty=0.1, task_entropy=0.2)   # None (below 0.3)
classify_uncertainty(uncertainty=0.5, task_entropy=0.5)   # None (middle zone)
```

## Reliability Metrics
```python
from soma.reliability import compute_calibration_score, detect_verbal_behavioral_divergence, compute_hedging_rate

score = compute_calibration_score(hedging_rate=0.5, error_rate=0.0)  # 0.75
divergent = detect_verbal_behavioral_divergence(hedging_rate=0.1, pressure=0.8)  # True
rate = compute_hedging_rate(actions)  # float [0, 1]
```

## Half-Life Functions
```python
from soma.halflife import compute_half_life, predict_success_rate, predict_actions_to_threshold, generate_handoff_suggestion

hl = compute_half_life(avg_session_length=90.0, avg_error_rate=0.15)  # 76.5
p = predict_success_rate(action_count=45, half_life=hl)  # 0.67
remaining = predict_actions_to_threshold(action_count=45, half_life=hl)  # 31
msg = generate_handoff_suggestion("agent-1", 45, hl, p)
```

## Persistence
```python
from soma import save_engine_state, load_engine_state
save_engine_state(engine, "state.json")  # Atomic write (fcntl + fsync + rename)
engine = load_engine_state("state.json")
```

## Budget
```python
engine.budget.spend(tokens=100, cost_usd=0.01)
engine.budget.health()          # min remaining ratio across dimensions
engine.budget.remaining()       # {"tokens": 99900, ...}
engine.budget.is_exhausted()    # True when health <= 0
engine.budget.burn_rate("tokens")  # spend per second
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
pred.dominant_reason    # "trend", "error_streak", "blind_writes", "thrashing", "retry_storm"
pred.confidence         # float [0, 1]
pred.actions_ahead      # int
```

## Quality Tracker
```python
from soma.quality import QualityTracker
qt = QualityTracker(window=30)
qt.record_write(had_syntax_error=False, had_lint_issue=True)
qt.record_bash(error=True)
report = qt.get_report()
report.grade    # "A"-"F"
report.score    # float [0, 1]
report.issues   # list[str]
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
ctx = tt.get_context()
ctx.phase          # "implement"
ctx.focus_files    # ["auth.py"]
ctx.scope_drift    # float [0, 1]
eff = tt.get_efficiency()
eff["context_efficiency"]  # read-to-write ratio
eff["success_rate"]        # 1.0 - error_rate
eff["focus"]               # 1.0 - scope_drift
```

## Root Cause Analysis
```python
from soma.rca import diagnose
result = diagnose(action_log, vitals_dict, pressure, level_name, action_count)
# "stuck in Edit->Bash loop on config.py (4 cycles)" or None
```

## Patterns
```python
from soma.patterns import analyze
results = analyze(action_log, workflow_mode="execute")
# Returns: list[PatternResult] (max 3, sorted by severity)
for r in results:
    r.kind       # "blind_edits", "bash_failures", etc.
    r.severity   # "positive", "info", "warning", "critical"
    r.action     # what to do
    r.detail     # context
```

## Findings
```python
from soma.findings import collect
findings = collect(action_log, vitals_dict, pressure, "WARN", 30, hook_config)
for f in findings:
    f.priority   # 0=critical, 1=important, 2=informational
    f.category   # "status", "quality", "predict", "pattern", etc.
    f.message    # what's happening
    f.action     # what to do
```

## Events
```python
engine.events.on("mode_changed", lambda data: print(data))
engine.events.on("half_life_warning", lambda data: print(data))
engine.events.on("verbal_behavioral_divergence", lambda data: print(data))
```
