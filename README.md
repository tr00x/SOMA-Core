# SOMA

Behavioral monitoring and guidance system for AI agents.

SOMA observes agent actions in real-time, computes behavioral pressure from vital signals, and injects corrective guidance before problems escalate. A nervous system for AI agents.

## Install

```
pip install soma-ai
```

or

```
uv add soma-ai
```

Python 3.11+

## Quick Start

### Claude Code hooks (zero-code)

```bash
soma install
```

Sets up pre/post tool-use hooks. Works automatically from that point on — no code changes needed.

### SDK wrapper (any LLM client)

```python
import soma
import anthropic

client = soma.wrap(anthropic.Anthropic())

# All API calls are now monitored.
# SOMA injects guidance directly into the message stream.
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

## How It Works

```
action → vitals → pressure → guidance → injection
```

Every agent action flows through the pipeline:

1. **Vitals** — uncertainty, drift, error rate, token usage, cost
2. **Pressure** — signals aggregate into a 0-1 scalar via z-score + sigmoid
3. **Guidance** — pressure maps to response modes: OBSERVE → GUIDE → WARN → BLOCK
4. **Injection** — corrective guidance reaches the agent (stdout for hooks, messages for wrap)

## Guidance Patterns

SOMA ships 9 guidance patterns, ranked by priority:

| # | Pattern | What it catches |
|---|---------|----------------|
| 1 | `cost_spiral` | Accelerating spend combined with high error rate |
| 2 | `budget` | Budget below 20% remaining |
| 3 | `bash_retry` | Bash followed by Bash after a failure |
| 4 | `retry_storm` | 3+ consecutive same-tool failures |
| 5 | `error_cascade` | 3+ consecutive errors across different tools |
| 6 | `blind_edit` | Edit/Write without a prior Read of the file |
| 7 | `entropy_drop` | Tool tunnel vision (monotool usage), with panic escalation via velocity |
| 8 | `context` | Context window more than 80% full |
| 9 | `drift` | Behavioral drift from initial tool-use patterns |

### Healing Transitions

Data-backed tool suggestions injected when patterns are detected:

- Bash → Read (reduces error rate by 7%)
- Edit → Read (reduces error rate by 5%)
- Write → Grep (reduces error rate by 5%)

### Cross-Session Lessons

SOMA stores lessons from past sessions and matches them to current situations using trigram similarity. Same error type with a different path still gets caught.

## CLI

```bash
soma status       # Show current monitoring state
soma install      # Set up Claude Code hooks
soma config       # View/edit configuration
soma analytics    # Query the analytics DB
soma replay       # Replay a recorded session
soma doctor       # Diagnose issues
```

Interactive TUI dashboard:

```bash
soma              # Launches the dashboard
```

### Entry Points

| Command | Purpose |
|---------|---------|
| `soma` | Main CLI and TUI dashboard |
| `soma-hook` | Hook dispatcher for Claude Code |
| `soma-statusline` | Status line formatter |

## License

MIT
