# Getting Started with SOMA Core

## What is SOMA?

SOMA watches your AI agents while they run and detects when something is going wrong. It measures signals like confusion, repeated behavior, and error rate, then assigns a health level to each agent in real time. When an agent's health drops far enough, SOMA blocks the next API call so the problem cannot spiral into wasted money or corrupted output.

**Why you need it:** Without monitoring, your AI agent can waste $50 in tokens looping on a broken task and you won't know until it's too late.

---

## Install

```
pip install soma-core
```

Requires Python 3.11 or later.

Install the dashboard too (optional but recommended):

```
pip install soma-core[dashboard]
```

Verify the install worked:

```python
python -c "import soma; print(soma.__version__)"
```

You should see `0.1.0`.

---

## Your First Monitor (step by step)

You will do four things: create an engine, register an agent, record actions, and read the result.

### Step 1: Create an engine

The engine is the brain of SOMA. You give it a budget so it knows when your agent has spent too much.

```python
import soma

engine = soma.quickstart(budget={"tokens": 50000}, agents=["my-agent"])
```

`budget={"tokens": 50000}` means: stop the agent if it uses more than 50,000 tokens.

### Step 2: Register an agent

`quickstart` already did this for you when you passed `agents=["my-agent"]`. If you want to add more agents later, call:

```python
engine.register_agent("another-agent")
```

### Step 3: Record actions

Every time your agent does something (calls a tool, gets a response), tell SOMA about it.

```python
result = engine.record_action("my-agent", soma.Action(
    tool_name="search",
    output_text="Found 3 results",
    token_count=150,
))
```

`record_action` runs the full monitoring pipeline and returns the agent's current status.

### Step 4: Check the result

```python
print(result.level)     # Level.HEALTHY
print(result.pressure)  # 0.03  (a number from 0.0 to 1.0)
```

`pressure` is how far the agent is from normal behavior. Low is good. High means something is wrong.

### Full working example

Copy and run this:

```python
import soma

# Create engine with a 50,000 token budget
engine = soma.quickstart(budget={"tokens": 50000}, agents=["my-agent"])

# Simulate 15 agent actions
for i in range(15):
    result = engine.record_action("my-agent", soma.Action(
        tool_name="search",
        output_text=f"Search result number {i}",
        token_count=200,
    ))
    print(f"Action {i+1}: level={result.level.name}  pressure={result.pressure:.3f}")
```

Expected output (abbreviated):

```
Action 1: level=HEALTHY  pressure=0.000
Action 2: level=HEALTHY  pressure=0.000
...
Action 11: level=HEALTHY  pressure=0.012
```

The first 10 actions show `pressure=0.000`. That is the grace period. SOMA waits for enough data before making judgments. After 10 actions it starts evaluating normally.

---

## Wrap Your API Client (the easy way)

If you use Anthropic's Python SDK or the OpenAI SDK, there is a faster path. One line and SOMA monitors every API call automatically.

### What soma.wrap() does

`soma.wrap()` takes your API client and returns a new version of it. The new version looks and works exactly the same, but SOMA intercepts every call in the background. It records what the agent did, updates the health level, and blocks the next call if the agent is in trouble.

Think of it like a guard who stands between your code and the API. Normal calls go through. Dangerous calls get stopped.

### Full example with a mock client

This example works without a real API key. It shows exactly what SOMA does.

```python
import soma
from soma.wrap import SomaBlocked

# A fake API client so you can try this without any keys
class MockMessages:
    def create(self, **kwargs):
        class Response:
            class usage:
                input_tokens = 100
                output_tokens = 50
            content = []
        return Response()

class MockClient:
    messages = MockMessages()

# Wrap the client
client = soma.wrap(MockClient(), budget={"tokens": 5000}, agent_id="my-agent")

# Use the client normally
for i in range(5):
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(f"Call {i+1}: level={client.soma_level.name}  pressure={client.soma_pressure:.3f}")
```

After each call you can check `client.soma_level` and `client.soma_pressure` to see the current status.

### What happens when SOMA blocks a call

When the agent reaches QUARANTINE level, SOMA raises `SomaBlocked` before the API call goes out. No tokens are spent. Handle it like this:

```python
from soma.wrap import SomaBlocked, SomaBudgetExhausted

try:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": "Hello"}],
    )
except SomaBlocked as e:
    print(f"SOMA stopped the agent: level={e.level.name}, pressure={e.pressure:.3f}")
    # Investigate what went wrong before continuing
except SomaBudgetExhausted as e:
    print(f"Budget exhausted: {e.dimension}")
    # You have run out of tokens or money
```

---

## The Dashboard

### How to open it

In your terminal, run:

```
soma
```

The first time you run it, SOMA will walk you through a short setup wizard and create a `soma.toml` file.

The dashboard requires the `dashboard` extra:

```
pip install soma-core[dashboard]
```

### What you see

The dashboard has four main areas:

**Agent cards** — one card per agent you are monitoring. Each card shows the agent's name, current level, and four numbers: pressure, uncertainty, drift, and error rate.

**Budget bars** — progress bars at the bottom showing how much of your token budget and cost budget you have used.

**Event log** — a scrolling list of level-change events. Every time an agent moves from one level to another, a line appears here with the agent name, old level, new level, and pressure at the time.

**Footer** — keyboard shortcuts. Press `q` to quit.

### How to read the cards

Each card shows:

- **Level** — the current health level (see the next section)
- **Pressure** — a number from `0.000` to `1.000`. Below `0.25` is normal. Above `0.75` is serious.
- **Uncertainty** — how confused or repetitive the agent's output looks
- **Drift** — how much the agent's behavior has changed from its normal pattern
- **Error Rate** — what fraction of recent actions ended in errors

### What the colors mean

The border color of each card tells you the level at a glance:

| Color | Level |
|---|---|
| Green | HEALTHY |
| Yellow | CAUTION |
| Orange | DEGRADE |
| Red | QUARANTINE |
| Purple | RESTART |
| White on red background | SAFE_MODE (budget gone) |

---

## Levels Explained

SOMA uses six levels. They go from best to worst.

### HEALTHY (green)

**What it means:** Everything is normal. Pressure is below 0.25.

**What SOMA does:** Nothing. It keeps watching.

**When to worry:** You do not need to worry.

---

### CAUTION (yellow)

**What it means:** Something is a little off. Pressure is between 0.25 and 0.50. The agent is behaving differently than usual, but not badly enough to act on yet.

**What SOMA does:** Watches more closely. No action is taken.

**When to worry:** If it stays here for a long time without recovering, check what the agent is doing.

---

### DEGRADE (orange)

**What it means:** A real problem has been detected. Pressure is between 0.50 and 0.75. The agent is showing significant uncertainty, drift, or errors.

**What SOMA does:** Flags the agent. If you are using `soma.wrap()`, expensive or risky tool calls may be restricted depending on your config.

**When to worry:** Yes, check the event log to see what changed.

---

### QUARANTINE (red)

**What it means:** The agent is in serious trouble. Pressure is above 0.75.

**What SOMA does:** If you are using `soma.wrap()`, SOMA blocks the next API call and raises `SomaBlocked`. The agent cannot make any more calls until pressure drops.

**When to worry:** Investigate immediately. Look at the agent's recent output and the event log.

---

### RESTART (purple)

**What it means:** Pressure is above 0.90. The agent needs to be reset.

**What SOMA does:** Same as QUARANTINE — blocks calls.

**When to worry:** The agent has almost certainly gone off the rails. Stop it and restart from a clean state.

---

### SAFE_MODE (white/red)

**What it means:** The budget is exhausted. Tokens or money have run out completely.

**What SOMA does:** Blocks all further calls. Raises `SomaBudgetExhausted`.

**When to worry:** This is a hard stop. Increase your budget or wait for the next session.

---

## Settings (soma.toml)

`soma.toml` lives in your project directory. SOMA reads it on startup. If the file does not exist, SOMA uses defaults.

Create it interactively:

```
soma init
```

Or create it manually. Here is a fully commented example:

```toml
[soma]
version = "0.1.0"

[budget]
tokens = 100000      # max tokens before SAFE_MODE
cost_usd = 5.0       # max dollar spend before SAFE_MODE

[agents.default]
autonomy = "human_on_the_loop"   # see below
sensitivity = "balanced"         # aggressive, balanced, or relaxed

[thresholds]
# Pressure values that trigger each level.
# Lower numbers = more sensitive = fires sooner.
caution    = 0.25
degrade    = 0.50
quarantine = 0.75
restart    = 0.90

[weights]
# How much each signal contributes to pressure.
# Higher number = that signal matters more.
uncertainty = 2.0
drift       = 1.8
error_rate  = 1.5
cost        = 1.0
token_usage = 0.8
```

### How to change sensitivity

Three presets exist. Pick one under `[agents.default]`:

| Preset | Caution | Degrade | Quarantine | Use when |
|---|---|---|---|---|
| `aggressive` | 0.15 | 0.35 | 0.55 | Agent touches production data; you want early warning |
| `balanced` | 0.25 | 0.50 | 0.75 | Default; works for most cases |
| `relaxed` | 0.35 | 0.60 | 0.85 | Agent is noisy by nature; too many false alarms |

### autonomy options

- `human_on_the_loop` — SOMA monitors and alerts; it does not pause the agent waiting for human input (default)
- `human_in_the_loop` — at QUARANTINE or above, SOMA requires human approval before the agent continues
- `fully_autonomous` — SOMA monitors but never requires approval

### Example: tight budget, high sensitivity

For a production agent that should not spend more than $1:

```toml
[budget]
tokens = 20000
cost_usd = 1.0

[agents.default]
sensitivity = "aggressive"
```

### Example: development / testing

For a local development agent where false alarms are annoying:

```toml
[budget]
tokens = 500000
cost_usd = 20.0

[agents.default]
sensitivity = "relaxed"
```

---

## Common Problems

**"Why is my agent showing DEGRADE right at startup?"**

SOMA has a grace period of 10 actions. During those first 10 actions, pressure is held at zero so early noise does not trigger false alarms. If you see DEGRADE before action 10, it is because errors are happening immediately (error rate is treated as objectively bad even during cold start). After the grace period, SOMA learns what is normal for your agent and becomes less reactive.

If this keeps happening, check that your agent is not returning errors on its very first calls.

**"How do I reset SOMA completely?"**

Delete the SOMA state directory:

```
rm -rf ~/.soma/
```

This removes all stored state, learned baselines, and session history. The next run starts fresh.

**"My dashboard is empty / shows 'No agents registered'"**

The dashboard reads state from `~/.soma/state.json`. That file is written automatically when you use `soma.wrap()` (because `auto_export=True` by default). If you are using the engine directly without `soma.wrap()`, call `engine.export_state()` after each `record_action` call so the dashboard has data to display.

```python
result = engine.record_action("my-agent", action)
engine.export_state()   # write state so the dashboard can read it
```

**"SOMA is not blocking calls even though the level is QUARANTINE"**

Blocking only happens when you use `soma.wrap()`. The raw `SOMAEngine` just returns results — it never raises exceptions. Wrap your client to get automatic blocking.

**"I am getting SomaBudgetExhausted but I have tokens left"**

If you set `cost_usd` in the budget, SOMA tracks dollar spend as well as tokens. Either the cost limit was hit, or the `dimension` field on the exception will tell you which limit was reached.

---

## Next Steps

### Multi-agent monitoring

Register multiple agents and connect them with edges. When one agent struggles, its pressure flows downstream to agents that depend on it.

```python
import soma

engine = soma.quickstart(budget={"tokens": 200000})
engine.register_agent("orchestrator")
engine.register_agent("sub-agent")

# sub-agent feeds results into orchestrator
engine.add_edge("sub-agent", "orchestrator", trust_weight=0.9)
```

If `sub-agent` starts failing, `orchestrator` will also feel rising pressure — even before it has any errors of its own.

### Session replay

SOMA can record a session to a file and replay it later. Useful for debugging or comparing behavior across runs.

```python
from soma.recorder import SessionRecorder

recorder = SessionRecorder()
recorder.record("my-agent", action)
recorder.export("session.json")
```

Replay from the CLI:

```
soma replay session.json
```

### Testing with pytest

`soma.testing.Monitor` is a context manager designed for pytest. It auto-registers agents and gives you built-in assertions.

```python
from soma.testing import Monitor
from soma.types import Action, Level

def test_agent_stays_healthy():
    with Monitor(budget={"tokens": 10000}) as mon:
        for i in range(15):
            mon.record(
                "planner",
                Action(tool_name="search", output_text=f"result {i}", token_count=100),
            )

    mon.assert_healthy()              # final level must be HEALTHY
    mon.assert_below(Level.DEGRADE)   # must never have reached DEGRADE
```

Use `mon.checkpoint()` after a warm-up phase to reset the test history without losing the learned baseline.

### Contributing

See `CONTRIBUTING.md` in the repository root. The test suite runs with:

```
pytest
```

The project uses `hatchling` for packaging. Source lives in `src/soma/`.
