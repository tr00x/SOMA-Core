# Quickstart

Three integration paths. Pick the one that fits.

---

## Path 1: Claude Code Hooks (zero-code)

```bash
pip install soma-ai
soma install
```

SOMA monitors all tool calls automatically via pre/post hooks. No code changes needed.

**What you get:** real-time guidance injected into Claude Code's context whenever behavioral pressure rises. The agent sees SOMA's advice as part of the tool response.

---

## Path 2: SDK Wrapper (any LLM client)

```python
import anthropic
import soma

client = soma.wrap(anthropic.Anthropic())

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

Every LLM call is intercepted. SOMA tracks vitals and injects guidance messages when pressure rises. Raises `SomaBlocked` if pressure exceeds the block threshold, `SomaBudgetExhausted` if a budget dimension is spent.

---

## Path 3: Engine Direct

```python
import soma

engine = soma.quickstart()
agent_id = engine.register_agent("my-agent")

# Record actions manually
result = engine.record_action(
    agent_id,
    soma.Action(tool_name="Bash", output_text="...", token_count=100)
)

print(result.vitals.pressure)  # 0.0 - 1.0
print(result.mode)             # OBSERVE / GUIDE / WARN / BLOCK
```

Full control over what gets monitored and when.

---

## CLI

| Command | What it does |
|:--------|:-------------|
| `soma status` | Current pressure, vitals, and budget |
| `soma install` | Install Claude Code hooks |
| `soma config show` | Display active configuration |
| `soma doctor` | Diagnose configuration and hook health |
| `soma analytics` | Session analytics and trends |
| `soma replay` | Replay a recorded session |
| `soma dashboard` | Launch web dashboard (ROI page) |

---

## Configuration

SOMA reads from `soma.toml` in your project root. Everything has sensible defaults.

```toml
[budget]
tokens = 100000
cost_usd = 5.0

[thresholds]
guide = 0.4    # pressure above this → suggest corrections
warn = 0.7     # pressure above this → alert + flag destructive ops
block = 0.9    # pressure above this → restrict destructive operations
```

---

## How It Works

```
action ──> vitals ──> pressure ──> guidance ──> injection
```

1. **Actions** enter the engine (tool calls, API requests)
2. **Vitals** computed: uncertainty, drift, error rate, token usage, cost
3. **Pressure** derived from vitals using EMA baselines and z-score sigmoid
4. **Guidance** fires when pressure crosses thresholds: OBSERVE &rarr; GUIDE &rarr; WARN &rarr; BLOCK
5. **Contextual patterns** (retry loops, tool entropy, panic edits) trigger specific prescriptions

The closed loop: **actions &rarr; vitals &rarr; pressure &rarr; guidance &rarr; behavior change.**
