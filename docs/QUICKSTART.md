# Quick Start

Get SOMA running in 5 minutes.

## Prerequisites

- Python 3.11+
- Claude Code (CLI or IDE extension)

## Install

```bash
pip install soma-ai
```

Or with uv:

```bash
uv tool install soma-ai
```

Verify:

```bash
soma --version
which soma-hook
```

## Configure Claude Code

Run the wizard:

```bash
soma setup-claude
```

Or add hooks manually to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          { "type": "command", "command": "CLAUDE_HOOK=PreToolUse soma-hook", "timeout": 5 }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          { "type": "command", "command": "CLAUDE_HOOK=PostToolUse soma-hook", "timeout": 5 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "CLAUDE_HOOK=Stop soma-hook", "timeout": 10 }
        ]
      }
    ]
  }
}
```

Check installation health:

```bash
soma doctor
```

## What happens

SOMA runs on every tool call:

- **PreToolUse** -- reflex checks (block destructive ops, retry dedup, blind edit prevention)
- **PostToolUse** -- record action, validate code, compute pressure, Mirror injection
- **Stop** -- save state, update fingerprint, generate session summary
- **Notification / UserPromptSubmit** -- inject agent awareness prompt and findings into context

**When the agent is healthy (pressure < 15%):** Silence. SOMA monitors but does not interfere.

**When pressure rises (errors, retries, drift):** Session context appears in tool responses:

```
--- session context ---
actions: 14 | errors: 4/6
pattern: same cmd repeated 3x
last_successful: action #8 (Read)
---
```

The agent sees this as part of the tool output -- not as a warning. It processes the facts and adjusts its behavior.

**Status line** (always visible in Claude Code):

```
SOMA observe ░░░░░░░░░░  3% | #12 | quality A
SOMA guide   ███░░░░░░░ 32% | d:0.45 | #87 | quality B
SOMA warn    ██████░░░░ 62% | e:0.38 | #130 | quality D
```

## Configuration

Create `soma.toml` in your project root (optional -- defaults work well):

```toml
[thresholds]
guide = 0.40    # Start soft suggestions
warn = 0.60     # Insistent warnings
block = 0.80    # Block destructive ops only

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
goal_coherence = 1.5
context_exhaustion = 1.5
cost = 1.0
token_usage = 0.8

[mirror]
semantic_enabled = true
semantic_provider = "auto"
semantic_threshold = 0.40

[hooks]
validate_python = true
lint_python = true
quality = true
predict = true
fingerprint = true
task_tracking = true
```

## Semantic mode (optional)

For LLM-powered behavioral observation at high pressure (>=40%):

```bash
# Gemini -- free tier, recommended
export GEMINI_API_KEY=your_key

# Or Anthropic
export ANTHROPIC_API_KEY=your_key

# Or OpenAI
export OPENAI_API_KEY=your_key
```

Priority: Gemini > Anthropic > OpenAI. Auto-detected from env vars.

## Web Dashboard

SOMA includes a real-time web dashboard built on FastAPI + SSE:

```bash
# Start the dashboard (runs on port 7777)
python -m soma.dashboard.server
```

The dashboard has 6 tabs: Overview, Deep Dive, Analytics, Logs, Sessions, Settings. It reads state from `~/.soma/` and provides live updates via Server-Sent Events.

## Programmatic API

```python
import soma

# Quick start
engine = soma.quickstart()

# Wrap Anthropic or OpenAI client
client = soma.wrap(anthropic.Anthropic())

# Universal proxy for any framework
proxy = soma.SOMAProxy(engine, "my-agent")
safe_tool = proxy.wrap_tool(my_function)
```

See [API Reference](api.md) for the full programmatic interface.

## Verify it works

```bash
soma doctor
soma status
```

Or simulate pressure:

```bash
cat > /tmp/test_soma.sh << 'EOF'
#!/bin/bash
for i in 1 2 3 4 5; do
  echo '{"tool_name":"Bash","tool_input":{"command":"test"},"tool_response":"FAIL","error":true}' \
    | CLAUDE_HOOK=PostToolUse soma-hook 2>/dev/null
done
EOF
bash /tmp/test_soma.sh
```

By action 3-4, you should see `--- session context ---` on stdout.

## CLI commands

```
soma                    # TUI dashboard
soma status             # Quick text summary
soma setup-claude       # Install hooks
soma doctor             # Check installation health
soma agents             # List monitored agents
soma replay <file>      # Replay recorded session
soma init               # Create soma.toml via wizard
soma stop / start       # Disable / re-enable hooks
soma reset <id>         # Reset agent baseline
soma config show/set    # View or change configuration
soma mode <name>        # Switch mode (strict/relaxed/autonomous)
soma report             # Generate session report
soma analytics          # Show historical analytics
soma benchmark          # Run behavioral benchmarks
soma stats              # Session statistics
soma policy             # Manage community policy packs
soma version            # Print version
soma uninstall-claude   # Remove hooks from Claude Code
```

## Next steps

- [Guide](guide.md) -- full user guide
- [Architecture](ARCHITECTURE.md) -- how the pipeline works
- [API Reference](api.md) -- programmatic interface
- [Research](RESEARCH.md) -- academic foundations
- [Technical Reference](TECHNICAL.md) -- every formula and constant
