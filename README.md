# SOMA Core

The nervous system for AI agents.

---

## What it does

- Watches your AI agents for problems (uncertainty, confusion, loops)
- Stops them before they waste money or go off-track
- Shows you everything on a live dashboard

---

## Install

```
pip install soma-core
```

Requires Python 3.11 or later.

---

## 30-Second Start

```python
import soma

engine = soma.quickstart(budget={"tokens": 50000}, agents=["my-agent"])

# Record what your agent does
result = engine.record_action("my-agent", soma.Action(
    tool_name="search",
    output_text="Found 3 results",
    token_count=150,
))

print(result.level)    # Level.HEALTHY
print(result.pressure) # 0.03
```

Every call to `record_action` runs SOMA's full monitoring pipeline and returns the current health status of your agent.

---

## One-Line Integration

If you are using Anthropic's Python SDK, wrap your client with `soma.wrap()`. One line and you are done.

```python
import anthropic
import soma

# One line. SOMA controls everything.
client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000})

# Use your client normally. SOMA monitors every call.
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)

# SOMA blocks the call if the agent is in trouble
print(client.soma_level)     # Level.HEALTHY
print(client.soma_pressure)  # 0.03
```

SOMA intercepts every API call in the background. If the agent reaches a dangerous state, SOMA blocks the next call automatically.

---

## Dashboard

Start the live dashboard with:

```
soma
```

<!-- screenshot placeholder -->

The dashboard shows every agent, their current health level, pressure score, and a timeline of escalation events.

---

## What SOMA Monitors

| Signal | What it means |
|---|---|
| Uncertainty | Agent is confused or repeating itself |
| Drift | Agent changed behavior from its normal pattern |
| Error Rate | Agent is failing |
| Pressure | Combined score (0-100%) |

SOMA computes these signals from your agent's recent actions, not from metadata. It detects problems before they surface as errors or unexpected API calls.

---

## What SOMA Does About It

When pressure rises, SOMA escalates through levels automatically. Each level restricts what the agent can do.

| Level | What happens |
|---|---|
| HEALTHY (green) | Everything is fine |
| CAUTION (yellow) | Something is off — watching closely |
| DEGRADE (orange) | Problem detected — restricting agent |
| QUARANTINE (red) | Agent stopped — too risky to continue |

SOMA de-escalates automatically once pressure drops back down.

---

## Multi-Agent

Register multiple agents and connect them with edges. Pressure from a struggling sub-agent flows up to the orchestrator that depends on it.

```python
import soma
from soma.types import Action

engine = soma.quickstart(budget={"tokens": 200000})
engine.register_agent("orchestrator")
engine.register_agent("sub_agent")

# sub_agent feeds into orchestrator
engine.add_edge("sub_agent", "orchestrator", trust_weight=0.9)

# Record actions for each agent independently
engine.record_action("sub_agent", Action(tool_name="search", output_text="result", token_count=300))
engine.record_action("orchestrator", Action(tool_name="write", output_text="done", token_count=500))
```

If `sub_agent` starts struggling, its pressure propagates to `orchestrator` — so SOMA can intervene before the whole pipeline fails.

---

## Testing

SOMA ships with `soma.testing.Monitor`, a context manager that wraps the engine and exposes assertions for use with pytest.

```python
from soma.testing import Monitor
from soma.types import Action, Level

def test_planner_stays_healthy():
    with Monitor(budget={"tokens": 10000}) as mon:
        for i in range(10):
            mon.record(
                "planner",
                Action(tool_name="search", output_text=f"result {i}", token_count=200),
            )

    mon.assert_healthy()             # current level is HEALTHY
    mon.assert_below(Level.DEGRADE)  # never reached DEGRADE during the test
```

`Monitor` registers agents automatically on first use. Call `mon.checkpoint()` after a warm-up phase to reset history without resetting the engine's learned baseline.

---

## Claude Code Users

One command to set up SOMA in your Claude Code project:

```
soma setup-claude
```

This creates:
- `soma.toml` with default settings
- `CLAUDE.md` entry with SOMA instructions
- `/soma-status` slash command for Claude Code

Then open a second terminal and run `soma` to watch your agents.

---

## CLI

```
soma                  Start the live dashboard
soma init             Interactive setup wizard
soma status           Show current agent levels
soma replay FILE      Replay a recorded session
soma setup-claude     Set up SOMA for Claude Code
soma version          Show version
```

---

## License

MIT. See [LICENSE](LICENSE).

---

## Author

Tim Hunt ([@tr00x](https://github.com/tr00x))
