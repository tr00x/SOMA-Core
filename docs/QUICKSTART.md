# SOMA Quickstart

Three ways to integrate SOMA into your workflow.

## Path 1: Claude Code Hooks (zero-code)

```bash
pip install soma-ai
soma install
```

Done. SOMA monitors all Claude Code tool calls automatically via pre/post hooks.

## Path 2: Anthropic SDK Wrapper

```python
import anthropic
import soma

client = soma.wrap(anthropic.Anthropic())
# All API calls are now monitored
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

SOMA intercepts every LLM call, tracks vitals, and injects guidance when pressure rises.

## Path 3: Engine Direct

```python
import soma

engine = soma.quickstart()
```

Use `engine.register_agent()` and `engine.record_action()` for full control over what gets monitored.

## CLI Commands

| Command | What it does |
|---------|-------------|
| `soma status` | Show current pressure, vitals, and budget |
| `soma install` | Install Claude Code hooks into your project |
| `soma config show` | Display active configuration |
| `soma doctor` | Diagnose configuration and hook health |
| `soma analytics` | Show session analytics and trends |
| `soma replay` | Replay a recorded session for analysis |

## Configuration

SOMA reads from `soma.toml` in your project root. Defaults work out of the box.

```toml
[budget]
tokens = 100000
cost_usd = 5.0

[thresholds]
guide = 0.4
warn = 0.7
block = 0.9
```

## How It Works

1. **Actions** enter the engine (tool calls, API requests)
2. **Vitals** are computed: uncertainty, drift, error rate, token usage, cost
3. **Pressure** is derived from vitals using EMA baselines and z-scores
4. **Guidance** fires when pressure crosses thresholds: OBSERVE -> GUIDE -> WARN -> BLOCK
5. Contextual patterns (retry loops, tool entropy, panic edits) trigger specific advice

The closed loop: actions -> vitals -> pressure -> guidance -> behavior change.
