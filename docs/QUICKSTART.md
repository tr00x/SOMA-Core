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

Add hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "type": "command", "command": "soma-hook" }
    ],
    "PostToolUse": [
      { "type": "command", "command": "soma-hook" }
    ],
    "Stop": [
      { "type": "command", "command": "soma-hook" }
    ]
  }
}
```

Or run the wizard:

```bash
soma setup-claude
```

## What happens

SOMA runs on every tool call. Here's what you'll see:

**When the agent is healthy (pressure < 15%):** Nothing. Complete silence. SOMA monitors but does not interfere.

**When pressure rises (errors, retries, drift):** Session context appears in tool responses:

```
--- session context ---
actions: 14 | errors: 4/6
pattern: same cmd repeated 3x
last_successful: action #8 (Read)
---
```

The agent sees this as part of the tool output — not as a warning from an external system. It processes the facts and adjusts its behavior.

**Status line** (always visible in Claude Code):

```
SOMA observe ░░░░░░░░░░  3% | #12 | quality A
SOMA guide   ███░░░░░░░ 32% | d:0.45 | #87 | quality B
SOMA warn    ██████░░░░ 62% | e:0.38 | #130 | quality D
```

## Configuration

Create `soma.toml` in your project root (optional — defaults work well):

```toml
[thresholds]
guide = 0.40    # Start soft suggestions (stderr)
warn = 0.60     # Insistent warnings
block = 0.80    # Block destructive ops only

[weights]
uncertainty = 1.2
drift = 1.5
error_rate = 2.5
cost = 1.0
token_usage = 0.6

[mirror]
semantic_enabled = true
semantic_provider = "auto"
semantic_threshold = 0.40

[hooks]
validate_python = true
lint_python = true
quality = true
predict = true
```

## Semantic mode (optional)

For LLM-powered behavioral observation at high pressure (>=40%), provide an API key:

```bash
# Gemini — free tier, recommended
export GEMINI_API_KEY=your_key

# Or Anthropic
export ANTHROPIC_API_KEY=your_key

# Or OpenAI
export OPENAI_API_KEY=your_key
```

Priority: Gemini > Anthropic > OpenAI. Auto-detected from env vars.

Semantic mode produces observations like:
```
--- session context ---
actions: 18 | errors: 7/10
Last 4 edits targeted test files. Original task was fixing engine.py.
---
```

## Verify it works

```bash
# Clean state
rm -f ~/.soma/engine_state.json

# Simulate 5 errors — run in a single script so PPID is consistent
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

## Next steps

- [Architecture](ARCHITECTURE.md) — how the pipeline works
- [Research](RESEARCH.md) — academic foundations
- [CHANGELOG](../CHANGELOG.md) — version history
