# SOMA

The nervous system for AI agents. Monitors behavior, predicts problems, and intervenes before things go wrong.

```
uv tool install soma-ai
soma setup-claude
```

That's it. Your Claude Code now has a nervous system.

## Quick start

```bash
# Install (pick one)
uv tool install soma-ai          # recommended (uv)
pipx install soma-ai             # alternative (pipx)
pip install soma-ai              # if you manage PATH yourself

# Connect to Claude Code (installs hooks, status line, slash commands)
soma setup-claude

# Check it's working
soma status
```

After setup, SOMA runs automatically. Every tool call is monitored. You'll see a status line at the bottom of Claude Code:

```
SOMA + healthy  2% · #42 · quality A
```

## Slash commands

Use these inside Claude Code:

| Command | What it does |
|---------|-------------|
| `/soma:status` | Live status — pressure, quality, vitals, budget, tips |
| `/soma:config` | Settings — modes, thresholds, budget, toggles |
| `/soma:config mode strict` | Strict mode — low thresholds, verbose |
| `/soma:config mode relaxed` | Relaxed (default) — balanced monitoring |
| `/soma:config mode autonomous` | Minimal monitoring for trusted runs |
| `/soma:control quarantine` | Force agent to quarantine (blocks tools) |
| `/soma:control release` | Release from quarantine |
| `/soma:control reset` | Reset behavioral baseline |
| `/soma:help` | Full command reference |

## Terminal commands

```
soma                  # live TUI dashboard
soma status           # quick text summary
soma mode             # show/switch operating mode
soma agents           # list monitored agents
soma setup-claude     # install hooks into Claude Code
soma config show      # print soma.toml
soma export           # export session to JSON
```

## Operating modes

Switch with `soma mode <name>` or `/soma:config mode <name>`:

| Mode | Autonomy | Quarantine at | Verbosity |
|------|----------|---------------|-----------|
| **strict** | human-in-the-loop | 60% | verbose |
| **relaxed** (default) | human-on-the-loop | 80% | normal |
| **autonomous** | fully autonomous | 95% | minimal |

## What it monitors

**5 behavioral signals** per action:
- **Uncertainty** — retries, output chaos, tool diversity
- **Drift** — deviation from established patterns
- **Error rate** — syntax errors, failed commands
- **Cost** — token/dollar burn rate
- **Quality** — A-F grade (syntax, lint, bash success)

**Predicts** problems ~5 actions before they happen.

**Restricts** progressively as pressure rises:

```
HEALTHY (0-24%)  →  CAUTION (25%)  →  DEGRADE (50%)  →  QUARANTINE (75%)  →  RESTART (90%)
   all allowed       warn on writes     bash blocked      read-only           full stop
```

**Explains** in plain English:
- "stuck in Edit→Bash loop on config.py (4 cycles)"
- "3 consecutive Bash failures (error_rate=40%)"
- "scope expanded to tests/, config/"

## How it works

```
Tool call → PreToolUse (can block) → Tool executes → PostToolUse (record + validate)
                                                           │
                                                 Compute vitals → Pressure → Level
                                                           │
                             UserPromptSubmit ← Prediction + RCA + Quality + Tips
```

4 hooks, all configurable:
- **PreToolUse** — blocks dangerous actions under pressure
- **PostToolUse** — records action, validates code, computes vitals
- **UserPromptSubmit** — injects actionable feedback into agent context
- **Stop** — saves state, updates fingerprint, shows session summary

Everything is deterministic. No LLM calls. No network requests. Pure math.

## Configuration

`soma.toml` controls everything:

```toml
[hooks]
verbosity = "normal"      # minimal, normal, verbose
validate_python = true    # syntax check after Write
lint_python = true        # ruff check after Write
predict = true            # anomaly prediction
quality = true            # A-F quality grading

[thresholds]
caution = 0.40
degrade = 0.60
quarantine = 0.80

[weights]
uncertainty = 1.2
drift = 1.5
error_rate = 2.5
```

## Claude Code plugin

SOMA is also available as a Claude Code plugin:

```
/install tr00x/soma-core
```

This auto-registers hooks and adds `/soma:*` slash commands.

## Requirements

- Python >= 3.11
- Claude Code (for hook integration)
- Optional: `ruff` for lint validation, `node` for JS validation

## License

MIT
