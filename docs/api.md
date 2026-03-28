# SOMA Core API Reference

> Auto-generated from source. All signatures verified against `src/soma/` as of 2026-03-27.

---

## soma (top-level)

The top-level `soma` package re-exports the most commonly used symbols and provides two convenience entry points.

---

### `quickstart`

```python
def quickstart(budget=None, agents=None) -> SOMAEngine
```

Fastest way to create a configured engine with one or more agents pre-registered.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `budget` | `dict[str, float] \| None` | `{"tokens": 100_000}` | Budget limits keyed by dimension name. |
| `agents` | `list[str] \| None` | `["default"]` | Agent IDs to pre-register on the engine. |

**Returns** `SOMAEngine`

**Example**

```python
import soma
engine = soma.quickstart(budget={"tokens": 50000}, agents=["agent-1", "agent-2"])
```

---

### `wrap`

```python
def wrap(
    client: Any,
    budget: dict[str, float] | None = None,
    agent_id: str = "default",
    auto_export: bool = True,
    block_at: Level = Level.QUARANTINE,
) -> WrappedClient
```

Wrap an API client with SOMA monitoring and control. See [soma.wrap](#somawrap) for full detail.

**Example**

```python
client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000})
```

---

### `save_engine_state`

```python
def save_engine_state(engine: SOMAEngine, path: str | None = None) -> None
```

Persist full engine state to a JSON file. See [soma.persistence](#somapersistence).

---

### `load_engine_state`

```python
def load_engine_state(path: str | None = None) -> SOMAEngine | None
```

Restore an engine from a previously saved state file. Returns `None` if no file exists. See [soma.persistence](#somapersistence).

---

### `replay_session`

```python
def replay_session(
    recording: SessionRecorder,
    budget: dict | None = None,
    edges: list[tuple] | None = None,
) -> list[ActionResult]
```

Replay all recorded actions through a fresh engine. See [soma.replay](#somareplay--replay_session).

---

## soma.types

Shared data types and enumerations used throughout SOMA.

---

### `Level`

```python
class Level(Enum)
```

Escalation levels ordered by severity. Supports `<`, `<=`, `>`, `>=` comparisons.

| Member | Value | Description |
|---|---|---|
| `HEALTHY` | `0` | Agent is operating normally. |
| `CAUTION` | `1` | Early warning signs detected. |
| `DEGRADE` | `2` | Agent is operating in a degraded state. |
| `QUARANTINE` | `3` | Agent is isolated; calls are blocked at this level by default. |
| `RESTART` | `4` | Agent should be restarted. |
| `SAFE_MODE` | `5` | Budget exhausted; agent is locked down. |

**Example**

```python
from soma.types import Level
if result.level >= Level.CAUTION:
    print("Pressure rising.")
```

---

### `AutonomyMode`

```python
class AutonomyMode(Enum)
```

Controls how human oversight interacts with escalation.

| Member | Value |
|---|---|
| `FULLY_AUTONOMOUS` | `"fully_autonomous"` |
| `HUMAN_IN_THE_LOOP` | `"human_in_the_loop"` |
| `HUMAN_ON_THE_LOOP` | `"human_on_the_loop"` |

---

### `DriftMode`

```python
class DriftMode(Enum)
```

Controls whether drift signal contributes to aggregate pressure.

| Member | Value | Description |
|---|---|---|
| `INFORMATIONAL` | `"informational"` | Drift is tracked but given zero weight in pressure calculation. |
| `DIRECTIVE` | `"directive"` | Drift contributes fully to aggregate pressure. |

---

### `InterventionOutcome`

```python
class InterventionOutcome(Enum)
```

Result of a recorded human intervention.

| Member | Value |
|---|---|
| `SUCCESS` | `"success"` |
| `FAILURE` | `"failure"` |
| `PENDING` | `"pending"` |

---

### `Action`

```python
@dataclass(frozen=True, slots=True)
class Action
```

A single agent action recorded by SOMA. Immutable.

**Fields**

| Name | Type | Default | Description |
|---|---|---|---|
| `tool_name` | `str` | _(required)_ | Name of the tool or API method called. |
| `output_text` | `str` | _(required)_ | Text output produced by the action. |
| `token_count` | `int` | `0` | Number of tokens consumed. |
| `cost` | `float` | `0.0` | Estimated cost in USD. |
| `error` | `bool` | `False` | Whether the action raised an exception. |
| `retried` | `bool` | `False` | Whether the action was a retry. |
| `duration_sec` | `float` | `0.0` | Wall-clock duration of the action in seconds. |
| `timestamp` | `float` | `0.0` | Unix timestamp when the action occurred. |
| `metadata` | `dict[str, Any]` | `{}` | Arbitrary key-value metadata. |

**Example**

```python
action = Action(tool_name="bash", output_text="ok", token_count=120, cost=0.0001)
```

---

### `VitalsSnapshot`

```python
@dataclass(frozen=True, slots=True)
class VitalsSnapshot
```

All vitals captured at one point in time. Returned inside `ActionResult`.

**Fields**

| Name | Type | Default | Description |
|---|---|---|---|
| `uncertainty` | `float` | `0.0` | Behavioural uncertainty score `[0, 1]`. |
| `drift` | `float` | `0.0` | Cosine distance from baseline behaviour vector. |
| `drift_mode` | `DriftMode` | `DriftMode.INFORMATIONAL` | Whether drift is in directive or informational mode. |
| `token_usage` | `float` | `0.0` | Fraction of token budget consumed `[0, 1]`. |
| `cost` | `float` | `0.0` | Fraction of cost budget consumed `[0, 1]`. |
| `error_rate` | `float` | `0.0` | Error rate in the recent action window `[0, 1]`. |

---

### `AgentConfig`

```python
@dataclass
class AgentConfig
```

Configuration for a monitored agent. Created automatically by `SOMAEngine.register_agent`.

**Fields**

| Name | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | _(required)_ | Unique identifier for the agent. |
| `autonomy` | `AutonomyMode` | `AutonomyMode.HUMAN_ON_THE_LOOP` | Oversight mode. |
| `system_prompt` | `str` | `""` | The agent's system prompt (used for drift detection). |
| `tools_allowed` | `list[str]` | `[]` | Whitelist of tool names the agent may use. |
| `expensive_tools` | `list[str]` | `[]` | Tools considered expensive (informational). |
| `minimal_tools` | `list[str]` | `[]` | Minimal tool set for degraded operation. |

---

## soma.engine

The central SOMA pipeline. All pressure computation, level evaluation, and event emission flow through `SOMAEngine`.

---

### `SOMAEngine`

```python
class SOMAEngine
```

Main SOMA pipeline. Records actions, computes vitals, aggregates pressure, and evaluates escalation levels.

---

#### `__init__`

```python
def __init__(self, budget: dict[str, float] | None = None) -> None
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `budget` | `dict[str, float] \| None` | `{"tokens": 100_000}` | Budget dimension names and their limits. |

**Example**

```python
engine = SOMAEngine(budget={"tokens": 50000, "cost_usd": 2.0})
```

---

#### `register_agent`

```python
def register_agent(
    self,
    agent_id: str,
    autonomy: AutonomyMode = AutonomyMode.HUMAN_ON_THE_LOOP,
    system_prompt: str = "",
    tools: list[str] | None = None,
) -> None
```

Register a new agent with the engine. Also adds the agent as a node in the pressure graph.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | _(required)_ | Unique agent identifier. |
| `autonomy` | `AutonomyMode` | `AutonomyMode.HUMAN_ON_THE_LOOP` | Human oversight mode. |
| `system_prompt` | `str` | `""` | Agent system prompt. |
| `tools` | `list[str] \| None` | `None` | Allowed tool names; `None` means unrestricted. |

**Returns** `None`

**Example**

```python
engine.register_agent("planner", autonomy=AutonomyMode.FULLY_AUTONOMOUS, tools=["bash", "read"])
```

---

#### `add_edge`

```python
def add_edge(self, source: str, target: str, trust_weight: float = 1.0) -> None
```

Add a directed trust edge in the pressure graph so that `source`'s pressure propagates to `target`.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | _(required)_ | Source agent ID. |
| `target` | `str` | _(required)_ | Target agent ID. |
| `trust_weight` | `float` | `1.0` | Edge weight controlling propagation strength `[0, 1]`. |

**Returns** `None`

**Example**

```python
engine.add_edge("orchestrator", "worker", trust_weight=0.8)
```

---

#### `record_action`

```python
def record_action(self, agent_id: str, action: Action) -> ActionResult
```

Run the full SOMA pipeline for one action: vitals, pressure, graph propagation, ladder evaluation, events.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | _(required)_ | The agent that performed the action. |
| `action` | `Action` | _(required)_ | The action to record. |

**Returns** `ActionResult` — level, pressure, and vitals snapshot.

**Raises** `AgentNotFound` if `agent_id` has not been registered.

**Example**

```python
result = engine.record_action("agent-1", Action(tool_name="bash", output_text="done"))
print(result.level)  # Level.HEALTHY
```

---

#### `get_level`

```python
def get_level(self, agent_id: str) -> Level
```

Return the current escalation level for an agent without running the pipeline.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | _(required)_ | The agent to query. |

**Returns** `Level`

**Raises** `AgentNotFound` if `agent_id` has not been registered.

**Example**

```python
level = engine.get_level("agent-1")
```

---

#### `get_snapshot`

```python
def get_snapshot(self, agent_id: str) -> dict[str, Any]
```

Return a dictionary summary of the agent's current state.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | _(required)_ | The agent to query. |

**Returns** `dict` with keys: `level`, `pressure`, `vitals` (dict), `action_count`, `budget_health`.

**Raises** `AgentNotFound` if `agent_id` has not been registered.

**Example**

```python
snap = engine.get_snapshot("agent-1")
print(snap["budget_health"])  # 0.87
```

---

#### `export_state`

```python
def export_state(self, path: str | None = None) -> None
```

Write current state to a JSON file for dashboard polling. Also calls `save_engine_state` for restart recovery.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `path` | `str \| None` | `~/.soma/state.json` | Destination path. Defaults to `~/.soma/state.json`. |

**Returns** `None`

**Example**

```python
engine.export_state("/tmp/soma_state.json")
```

---

#### `events` _(property)_

```python
@property
def events(self) -> EventBus
```

The engine's `EventBus`. Subscribe to `"level_changed"` events here.

**Example**

```python
engine.events.on("level_changed", lambda d: print(d["new_level"]))
```

---

#### `budget` _(property)_

```python
@property
def budget(self) -> MultiBudget
```

The engine's `MultiBudget` instance. Use to inspect or modify spend tracking.

**Example**

```python
print(engine.budget.health())  # 0.95
```

---

### `ActionResult`

```python
@dataclass(frozen=True, slots=True)
class ActionResult
```

Returned by `SOMAEngine.record_action`. Immutable.

**Fields**

| Name | Type | Description |
|---|---|---|
| `level` | `Level` | Current escalation level after processing this action. |
| `pressure` | `float` | Effective aggregate pressure `[0, 1]` after graph propagation. |
| `vitals` | `VitalsSnapshot` | Full vitals computed for this action. |

---

## soma.wrap

Provides a transparent proxy that wraps any Anthropic or OpenAI client, intercepting every LLM call through the SOMA pipeline.

---

### `wrap`

```python
def wrap(
    client: Any,
    budget: dict[str, float] | None = None,
    agent_id: str = "default",
    auto_export: bool = True,
    block_at: Level = Level.QUARANTINE,
) -> WrappedClient
```

Wrap an API client with SOMA monitoring and control. Creates a new `SOMAEngine` internally.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `client` | `Any` | _(required)_ | An Anthropic or OpenAI client instance. |
| `budget` | `dict[str, float] \| None` | `{"tokens": 100_000}` | Budget limits (e.g., `{"tokens": 50000, "cost_usd": 1.0}`). |
| `agent_id` | `str` | `"default"` | Name for this agent in SOMA tracking. |
| `auto_export` | `bool` | `True` | Write `~/.soma/state.json` after each API call. |
| `block_at` | `Level` | `Level.QUARANTINE` | Escalation level at which API calls are blocked. |

**Returns** `WrappedClient`

**Example**

```python
import anthropic, soma
client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000}, agent_id="my-agent")
response = client.messages.create(model="claude-opus-4-5", max_tokens=1024,
                                   messages=[{"role": "user", "content": "Hello"}])
print(client.soma_level)     # Level.HEALTHY
print(client.soma_pressure)  # 0.03
```

---

### `WrappedClient`

```python
class WrappedClient
```

Proxy around an API client. Intercepts all LLM calls, runs SOMA checks, and proxies all other attribute access to the underlying client.

---

#### `__init__`

```python
def __init__(
    self,
    client: Any,
    engine: SOMAEngine,
    agent_id: str = "default",
    auto_export: bool = True,
    block_at: Level = Level.QUARANTINE,
) -> None
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `client` | `Any` | _(required)_ | The underlying API client. |
| `engine` | `SOMAEngine` | _(required)_ | A pre-configured `SOMAEngine`. |
| `agent_id` | `str` | `"default"` | Agent identifier for SOMA tracking. |
| `auto_export` | `bool` | `True` | Export state after each call. |
| `block_at` | `Level` | `Level.QUARANTINE` | Level at which calls are blocked. |

---

#### `soma_level` _(property)_

```python
@property
def soma_level(self) -> Level
```

The current escalation level for this agent.

---

#### `soma_pressure` _(property)_

```python
@property
def soma_pressure(self) -> float
```

The current effective pressure for this agent.

---

#### `engine` _(property)_

```python
@property
def engine(self) -> SOMAEngine
```

The underlying `SOMAEngine`.

---

#### `recorder` _(property)_

```python
@property
def recorder(self) -> SessionRecorder
```

The `SessionRecorder` capturing all actions made through this client.

---

### `SomaBlocked`

```python
class SomaBlocked(Exception)
```

Raised when SOMA blocks an API call because the agent's level is at or above `block_at`.

**Constructor parameters**: `agent_id: str`, `level: Level`, `pressure: float`

**Attributes**: `.agent_id`, `.level`, `.pressure`

**Example**

```python
try:
    response = client.messages.create(...)
except soma.SomaBlocked as e:
    print(f"Blocked at {e.level.name}, pressure={e.pressure:.3f}")
```

---

### `SomaBudgetExhausted`

```python
class SomaBudgetExhausted(Exception)
```

Raised when SOMA blocks an API call because the budget is fully exhausted.

**Constructor parameters**: `dimension: str`

**Attributes**: `.dimension`

**Example**

```python
try:
    response = client.messages.create(...)
except soma.SomaBudgetExhausted as e:
    print(f"Budget exhausted on dimension: {e.dimension}")
```

---

## soma.budget

---

### `MultiBudget`

```python
class MultiBudget
```

Tracks spending across multiple named resource dimensions (e.g., `tokens`, `cost_usd`).

---

#### `__init__`

```python
def __init__(self, limits: dict[str, float]) -> None
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `limits` | `dict[str, float]` | Maximum allowed spend per dimension. |

**Example**

```python
budget = MultiBudget({"tokens": 100000, "cost_usd": 5.0})
```

---

#### `spend`

```python
def spend(self, **kwargs: float) -> None
```

Add to spent amounts. Each dimension is clamped at its limit.

**Parameters**: keyword arguments where each key is a dimension name and value is the amount to add.

**Raises** `KeyError` if a dimension name is unknown.

**Example**

```python
budget.spend(tokens=500, cost_usd=0.0005)
```

---

#### `replenish`

```python
def replenish(self, dimension: str, amount: float) -> None
```

Reduce the spent amount for a dimension (floored at 0).

**Parameters**

| Name | Type | Description |
|---|---|---|
| `dimension` | `str` | Dimension to replenish. |
| `amount` | `float` | Amount to subtract from spent. |

**Raises** `KeyError` if the dimension is unknown.

---

#### `remaining`

```python
def remaining(self, dimension: str) -> float
```

Return the remaining budget for a dimension (`limit - spent`).

---

#### `utilization`

```python
def utilization(self, dimension: str) -> float
```

Return the fraction spent for a dimension (`spent / limit`). Returns `1.0` if limit is zero.

---

#### `health`

```python
def health(self) -> float
```

Return the minimum `(remaining / limit)` across all dimensions. Returns `1.0` for an empty budget.

**Returns** `float` in `[0, 1]`.

**Example**

```python
print(budget.health())  # 0.72
```

---

#### `burn_rate`

```python
def burn_rate(self, dimension: str) -> float
```

Return the average spend per second since the `MultiBudget` was created.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `dimension` | `str` | The dimension to measure. |

**Returns** `float` — spend per second.

---

#### `projected_overshoot`

```python
def projected_overshoot(
    self,
    dimension: str,
    estimated_total_steps: int,
    current_step: int,
) -> float
```

Estimate overshoot (`projected_total_spend - limit`) at `estimated_total_steps`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `dimension` | `str` | The dimension to project. |
| `estimated_total_steps` | `int` | Total number of steps expected. |
| `current_step` | `int` | Steps completed so far. |

**Returns** `float` — positive means over-budget, negative means headroom.

---

#### `is_exhausted`

```python
def is_exhausted(self) -> bool
```

Return `True` when `health() <= 0` (at least one dimension fully spent).

---

#### `to_dict`

```python
def to_dict(self) -> dict[str, Any]
```

Serialise to a dictionary containing `"limits"` and `"spent"` keys.

---

#### `from_dict`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> MultiBudget
```

Restore a `MultiBudget` from a dictionary previously produced by `to_dict`.

**Example**

```python
budget2 = MultiBudget.from_dict(budget.to_dict())
```

---

## soma.baseline

---

### `Baseline`

```python
class Baseline
```

Exponential moving average (EMA) baseline with cold-start blending. During the cold-start period (fewer than `min_samples` observations) the EMA is blended toward sensible signal-specific defaults so early readings do not over-trigger escalation.

---

#### `__init__`

```python
def __init__(self, alpha: float = 0.15, min_samples: int = 10) -> None
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `alpha` | `float` | `0.15` | EMA smoothing factor. Higher values make the baseline react faster. |
| `min_samples` | `int` | `10` | Number of observations required to exit cold-start blending. |

---

#### `update`

```python
def update(self, signal: str, value: float) -> None
```

Apply one EMA step for `signal` with the given `value`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `signal` | `str` | Signal name (e.g., `"uncertainty"`, `"error_rate"`). |
| `value` | `float` | The new observed value. |

**Example**

```python
baseline.update("error_rate", 0.1)
```

---

#### `get`

```python
def get(self, signal: str) -> float
```

Return the blended baseline for `signal`. During cold-start the EMA is blended toward the built-in default; after `min_samples` observations the raw EMA is returned.

**Returns** `float`

---

#### `get_std`

```python
def get_std(self, signal: str) -> float
```

Return the standard deviation derived from the EMA variance estimate. Returns `0.1` if no observations have been recorded.

**Returns** `float`

---

#### `get_count`

```python
def get_count(self, signal: str) -> int
```

Return the number of observations recorded for `signal`.

**Returns** `int`

---

#### `to_dict`

```python
def to_dict(self) -> dict[str, Any]
```

Serialise the baseline to a dictionary.

---

#### `from_dict`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> Baseline
```

Restore a `Baseline` from a previously serialised dictionary.

**Example**

```python
b2 = Baseline.from_dict(b.to_dict())
```

---

## soma.pressure

---

### `sigmoid_clamp`

```python
def sigmoid_clamp(x: float) -> float
```

*(Re-exported from `soma.vitals`.)* Maps any real number through a modified sigmoid such that values `<= 0` return `0.0` and positive values return a value in `(0, 1)`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `x` | `float` | Input value (typically a z-score). |

**Returns** `float` in `[0, 1)`.

**Example**

```python
from soma.pressure import sigmoid_clamp
print(sigmoid_clamp(0.0))   # 0.0
print(sigmoid_clamp(3.0))   # ~0.95
```

---

### `compute_signal_pressure`

```python
def compute_signal_pressure(current: float, baseline: float, std: float) -> float
```

Compute pressure for a single signal via a sigmoid-clamped z-score.

Result = `sigmoid_clamp((current - baseline) / max(std, 1e-9))`.
Values at or below the baseline return `0.0`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `current` | `float` | Current observed value. |
| `baseline` | `float` | EMA baseline for this signal. |
| `std` | `float` | Standard deviation estimate for this signal. |

**Returns** `float` in `[0, 1)`.

**Example**

```python
p = compute_signal_pressure(current=0.4, baseline=0.1, std=0.05)
```

---

### `compute_aggregate_pressure`

```python
def compute_aggregate_pressure(
    signal_pressures: dict[str, float],
    drift_mode: DriftMode,
    weights: dict[str, float] | None = None,
) -> float
```

Combine individual signal pressures into a single aggregate pressure value.

Formula: `0.7 * weighted_mean + 0.3 * max_pressure` across all signals with positive weight.
If `drift_mode` is `INFORMATIONAL`, the `"drift"` signal weight is set to zero.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `signal_pressures` | `dict[str, float]` | _(required)_ | Map of signal name to pressure value. |
| `drift_mode` | `DriftMode` | _(required)_ | Controls whether drift contributes. |
| `weights` | `dict[str, float] \| None` | `DEFAULT_WEIGHTS` | Override the default signal weights. |

Default weights: `uncertainty=2.0`, `drift=1.8`, `error_rate=1.5`, `cost=1.0`, `token_usage=0.8`.

**Returns** `float` in `[0, 1]`.

**Example**

```python
pressure = compute_aggregate_pressure(
    {"uncertainty": 0.6, "error_rate": 0.3},
    DriftMode.DIRECTIVE,
)
```

---

## soma.graph

---

### `PressureGraph`

```python
class PressureGraph
```

Directed graph that propagates internal agent pressure along trust-weighted edges. Used by `SOMAEngine` to model inter-agent influence.

---

#### `__init__`

```python
def __init__(
    self,
    damping: float = 0.6,
    decay_rate: float = 0.05,
    recovery_rate: float = 0.02,
) -> None
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `damping` | `float` | `0.6` | Fraction of incoming pressure applied to a node's effective pressure. |
| `decay_rate` | `float` | `0.05` | Rate at which trust decays per unit of uncertainty. |
| `recovery_rate` | `float` | `0.02` | Rate at which trust recovers per unit of stability. |

---

#### `add_agent`

```python
def add_agent(self, agent_id: str) -> None
```

Add a node for `agent_id`. No-op if the agent is already registered.

---

#### `add_edge`

```python
def add_edge(self, source: str, target: str, trust: float = 1.0) -> None
```

Add a directed edge from `source` to `target`. Both nodes are created if they do not exist.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | _(required)_ | Source agent ID. |
| `target` | `str` | _(required)_ | Target agent ID. |
| `trust` | `float` | `1.0` | Initial trust weight `[0, 1]`. |

---

#### `set_internal_pressure`

```python
def set_internal_pressure(self, agent_id: str, pressure: float) -> None
```

Set the internally computed pressure for `agent_id` (before propagation).

---

#### `get_effective_pressure`

```python
def get_effective_pressure(self, agent_id: str) -> float
```

Return the effective pressure for `agent_id` after the last propagation pass.

**Returns** `float`

---

#### `propagate`

```python
def propagate(self, max_iterations: int = 3) -> None
```

Run multi-pass pressure propagation until convergence or `max_iterations` is reached. Each node's effective pressure becomes `max(internal, damping * weighted_avg_incoming)`.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `max_iterations` | `int` | `3` | Maximum number of propagation passes. |

---

#### `decay_trust`

```python
def decay_trust(self, source: str, uncertainty: float) -> None
```

Reduce the trust weight on all outgoing edges from `source` by `decay_rate * uncertainty`.

---

#### `recover_trust`

```python
def recover_trust(self, source: str, uncertainty: float) -> None
```

Increase the trust weight on all outgoing edges from `source` by `recovery_rate * (1 - uncertainty)`.

---

#### `get_trust`

```python
def get_trust(self, source: str, target: str) -> float
```

Return the current trust weight for the edge from `source` to `target`.

**Returns** `float`

**Raises** `KeyError` if no edge exists between the two agents.

**Example**

```python
graph.add_edge("a", "b", trust=0.9)
print(graph.get_trust("a", "b"))  # 0.9
```

---

#### `to_dict`

```python
def to_dict(self) -> dict[str, Any]
```

Serialise the full graph (nodes, edges, and configuration) to a dictionary.

---

## soma.ladder

---

### `Ladder`

```python
class Ladder
```

Stateful escalation ladder that maps (pressure, budget_health) to a `Level`. Implements hysteresis to prevent rapid oscillation between levels.

---

#### `__init__`

```python
def __init__(self) -> None
```

Initialises the ladder at `Level.HEALTHY`.

---

#### `current` _(property)_

```python
@property
def current(self) -> Level
```

The current escalation level.

---

#### `evaluate`

```python
def evaluate(self, pressure: float, budget_health: float) -> Level
```

Compute and record the new escalation level.

Priority rules:
1. `budget_health <= 0` → enter `SAFE_MODE` (latches).
2. While in `SAFE_MODE`, exit only when `budget_health > 0.10`.
3. Manual `force_level` override applies after safe-mode check.
4. Escalate to the highest level whose threshold is exceeded by `pressure`.
5. De-escalate by exactly one level when `pressure` drops below the current level's de-escalation threshold (hysteresis).

**Parameters**

| Name | Type | Description |
|---|---|---|
| `pressure` | `float` | Current aggregate pressure `[0, 1]`. |
| `budget_health` | `float` | Current budget health `[0, 1]`. |

**Returns** `Level`

**Example**

```python
level = ladder.evaluate(pressure=0.6, budget_health=0.8)  # Level.DEGRADE
```

---

#### `evaluate_with_adjustments`

```python
def evaluate_with_adjustments(
    self,
    pressure: float,
    budget_health: float,
    threshold_adjustments: dict[str, float] | None = None,
) -> Level
```

Like `evaluate()`, but applies learned threshold shifts before checking. Keys in `threshold_adjustments` take the form `"OLD_LEVEL->NEW_LEVEL"` (e.g., `"HEALTHY->CAUTION"`); the value is added to both the escalation and de-escalation threshold for that transition.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `pressure` | `float` | _(required)_ | Current aggregate pressure. |
| `budget_health` | `float` | _(required)_ | Current budget health. |
| `threshold_adjustments` | `dict[str, float] \| None` | `None` | Learned threshold shifts keyed by transition string. |

**Returns** `Level`

---

#### `requires_approval`

```python
def requires_approval(self, level: Level, autonomy: AutonomyMode) -> bool
```

Return `True` if this level + autonomy combination requires human approval. Only `HUMAN_IN_THE_LOOP` mode blocks on `QUARANTINE`, `RESTART`, or `SAFE_MODE`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `level` | `Level` | The level to check. |
| `autonomy` | `AutonomyMode` | The agent's oversight mode. |

**Returns** `bool`

**Example**

```python
ladder.requires_approval(Level.QUARANTINE, AutonomyMode.HUMAN_IN_THE_LOOP)  # True
```

---

#### `force_level`

```python
def force_level(self, level: Level | None) -> None
```

Manually override the current level. Pass `None` to clear the override and return to normal evaluation.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `level` | `Level \| None` | The level to force, or `None` to clear. |

**Example**

```python
ladder.force_level(Level.CAUTION)   # lock at CAUTION
ladder.force_level(None)            # restore normal evaluation
```

---

## soma.events

---

### `EventBus`

```python
class EventBus
```

Simple synchronous publish/subscribe event bus. All handlers are called synchronously in subscription order.

---

#### `__init__`

```python
def __init__(self) -> None
```

---

#### `on`

```python
def on(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None
```

Subscribe `handler` to `event`. The handler receives a single `dict` payload.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `event` | `str` | Event name (e.g., `"level_changed"`). |
| `handler` | `Callable[[dict], None]` | Callback to invoke when the event fires. |

**Example**

```python
engine.events.on("level_changed", lambda d: print(d["new_level"].name))
```

---

#### `off`

```python
def off(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None
```

Unsubscribe `handler` from `event`. No-op if the handler is not subscribed.

---

#### `emit`

```python
def emit(self, event: str, data: dict[str, Any]) -> None
```

Fire all handlers registered for `event` with `data`. Handlers are called in subscription order.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `event` | `str` | Event name. |
| `data` | `dict[str, Any]` | Payload passed to each handler. |

---

**Built-in engine events**

| Event | Payload keys | Description |
|---|---|---|
| `"level_changed"` | `agent_id`, `old_level`, `new_level`, `pressure` | Emitted whenever an agent's escalation level changes. |

---

## soma.testing

---

### `Monitor`

```python
class Monitor
```

Lightweight context manager wrapping a `SOMAEngine` for use in tests. Auto-registers agents on first use.

**Example**

```python
from soma.testing import Monitor
from soma.types import Action, Level

with Monitor(budget={"tokens": 10000}) as mon:
    for _ in range(20):
        mon.record("agent", Action(tool_name="bash", output_text="ok"))
mon.assert_healthy()
mon.assert_below(Level.CAUTION)
```

---

#### `__init__`

```python
def __init__(self, budget: dict[str, float] | None = None) -> None
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `budget` | `dict[str, float] \| None` | `{"tokens": 100_000}` | Budget limits for the internal engine. |

---

#### `record`

```python
def record(self, agent_id: str, action: Action) -> ActionResult
```

Record `action` for `agent_id`, auto-registering the agent if needed.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `agent_id` | `str` | Agent performing the action. |
| `action` | `Action` | The action to record. |

**Returns** `ActionResult`

**Raises** `RuntimeError` if called outside a `with` block.

---

#### `assert_healthy`

```python
def assert_healthy(self) -> None
```

Raise `AssertionError` if the most recent level is not `HEALTHY`. Uses `current_level` (not `max_level`) so transient cold-start escalation does not fail tests.

---

#### `assert_below`

```python
def assert_below(self, level: Level) -> None
```

Raise `AssertionError` if `max_level >= level`. Uses `max_level` so any transient escalation is caught.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `level` | `Level` | The level that must not be reached. |

---

#### `checkpoint`

```python
def checkpoint(self) -> None
```

Reset history, `total_actions`, and `total_cost` without resetting the underlying engine. Use after a warm-up phase so assertions reflect only post-checkpoint behaviour.

---

#### `max_level` _(property)_

```python
@property
def max_level(self) -> Level
```

Highest escalation level observed across all recorded results. Returns `Level.HEALTHY` if no actions have been recorded.

---

#### `current_level` _(property)_

```python
@property
def current_level(self) -> Level
```

Escalation level from the most recently recorded action. Returns `Level.HEALTHY` if no actions have been recorded.

---

#### `total_actions` _(property)_

```python
@property
def total_actions(self) -> int
```

Total number of actions recorded across all agents since the last `checkpoint`.

---

#### `total_cost` _(property)_

```python
@property
def total_cost(self) -> float
```

Cumulative `action.cost` across all recorded actions since the last `checkpoint`.

---

#### `history` _(property)_

```python
@property
def history(self) -> list[ActionResult]
```

All `ActionResult` objects in recording order since the last `checkpoint`.

---

## soma.recorder

---

### `SessionRecorder`

```python
class SessionRecorder
```

Records agent actions during a session and supports export to / load from a JSON file.

---

#### `__init__`

```python
def __init__(self) -> None
```

Creates an empty recorder. `recorder.actions` is an empty list.

---

#### `record`

```python
def record(self, agent_id: str, action: Action) -> None
```

Append a new `RecordedAction` to the session.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `agent_id` | `str` | The agent that performed the action. |
| `action` | `Action` | The action to record. |

**Example**

```python
recorder.record("agent-1", action)
```

---

#### `export`

```python
def export(self, path: str | Path) -> None
```

Write the session as a versioned JSON file to `path`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `path` | `str \| Path` | Destination file path. |

**Example**

```python
recorder.export("/tmp/session.json")
```

---

#### `load`

```python
@classmethod
def load(cls, path: str | Path) -> SessionRecorder
```

Read a JSON session file and return a populated `SessionRecorder`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `path` | `str \| Path` | Path to a session JSON file produced by `export`. |

**Returns** `SessionRecorder`

**Example**

```python
recorder = SessionRecorder.load("/tmp/session.json")
```

---

## soma.persistence

---

### `save_engine_state`

```python
def save_engine_state(engine: SOMAEngine, path: str | None = None) -> None
```

Persist full engine state (agents, baselines, budget, graph, learning engine) to a JSON file.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `engine` | `SOMAEngine` | _(required)_ | The engine to persist. |
| `path` | `str \| None` | `~/.soma/engine_state.json` | Destination path. Parent directories are created if needed. |

**Returns** `None`

**Example**

```python
from soma.persistence import save_engine_state
save_engine_state(engine, "/backups/soma_state.json")
```

---

### `load_engine_state`

```python
def load_engine_state(path: str | None = None) -> SOMAEngine | None
```

Restore an engine from a previously saved state file. Returns `None` if the file does not exist or cannot be parsed.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `path` | `str \| None` | `~/.soma/engine_state.json` | Path to the state file. |

**Returns** `SOMAEngine | None`

**Example**

```python
from soma.persistence import load_engine_state
engine = load_engine_state() or soma.quickstart()
```

---

## soma.replay

---

### `replay_session`

```python
def replay_session(
    recording: SessionRecorder,
    budget: dict | None = None,
    edges: list[tuple] | None = None,
) -> list[ActionResult]
```

Replay all recorded actions through a fresh `SOMAEngine`. Agents are auto-registered in the order they first appear. Useful for debugging, analysis, and regression testing.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `recording` | `SessionRecorder` | _(required)_ | A populated session recorder. |
| `budget` | `dict \| None` | `None` | Budget for the fresh engine. |
| `edges` | `list[tuple] \| None` | `None` | Graph edges as `(source, target)` or `(source, target, trust_weight)` tuples. |

**Returns** `list[ActionResult]` — one result per recorded action, in order.

**Example**

```python
recording = SessionRecorder.load("session.json")
results = replay_session(recording, budget={"tokens": 100000})
print(results[-1].level)
```
