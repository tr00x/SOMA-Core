# SOMA Guide

## Quick Start

```bash
pip install soma-core
soma setup-claude
```

This installs 4 hooks into Claude Code and creates `~/.soma/` for state.

## What happens after setup

Every tool call in Claude Code now flows through SOMA:

```
You type a command
  -> PreToolUse checks if tool is allowed at current pressure level
  -> Tool executes (or gets blocked)
  -> PostToolUse records the action, validates code, computes pressure
  -> Next prompt: UserPromptSubmit injects feedback into agent context
  -> Session ends: Stop saves state, updates fingerprint
```

## The pressure model

SOMA monitors 5 behavioral signals:

| Signal | What it measures | Weight (Claude Code) |
|--------|-----------------|---------------------|
| uncertainty | Retries, output chaos, tool deviation | 1.2 |
| drift | Cosine distance from baseline behavior vector | 1.5 |
| error_rate | Fraction of actions that failed | 2.5 |
| cost | Budget utilization | 1.0 |
| token_usage | Token budget utilization | 0.6 |

Each signal gets a z-score pressure (sigmoid-clamped), then they're aggregated:

```
pressure = 0.7 * weighted_mean + 0.3 * max_signal
```

Pressure maps to escalation levels:

| Level | Threshold | What happens |
|-------|-----------|-------------|
| HEALTHY | 0.00 | Everything allowed |
| CAUTION | 0.40 | Write/Edit requires prior Read |
| DEGRADE | 0.60 | Bash and Agent blocked |
| QUARANTINE | 0.80 | Only Read/Glob/Grep allowed |
| RESTART | 0.95 | Same as QUARANTINE |
| SAFE_MODE | budget=0 | Budget exhausted, read-only |

Thresholds have hysteresis: CAUTION escalates at 0.40, de-escalates at 0.35.

## Baselines and learning

SOMA uses exponential moving averages (EMA, alpha=0.15) to learn what's "normal":

- First 10 actions: grace period (zero pressure)
- Actions 10-20: baselines blend from defaults to observed values
- After 20: baselines reflect actual agent behavior

The learning engine tracks intervention outcomes:
- If escalation helped (pressure dropped) -> lower threshold slightly
- If escalation didn't help (pressure stayed) -> raise threshold
- Adaptive step: more consistent outcomes = larger adjustments

This means SOMA gets fewer false positives over time.

## Cross-session memory

New sessions inherit baselines from the most active previous session. SOMA doesn't start cold every time.

Agent fingerprints (tool distribution, error rate, read/write ratio) persist across sessions. If behavior suddenly shifts, SOMA flags it.

## Intelligence features

### Anomaly prediction

After each action, SOMA fits a linear trend to recent pressure readings and adds pattern-based boosters (error streaks, blind writes, thrashing). If predicted pressure exceeds the next threshold, it warns the agent ~5 actions before escalation.

### Root cause analysis

Instead of "drift=0.40", SOMA says:
- "stuck in Edit->Bash loop on config.py (4 cycles)"
- "error cascade: 3 consecutive Bash failures (error_rate=40%)"
- "blind mutation: 5 writes without reading (foo.py, bar.py)"
- "possible stall: 7/8 recent actions are reads with no writes"

### Task tracking

SOMA infers what phase you're in (research/implement/test/debug) and tracks which files/directories you're focused on. If you drift to unrelated areas, it flags scope drift.

### Quality scoring

Every Write/Edit gets syntax-checked (Python: py_compile, JS: node --check) and linted (Python: ruff). Session quality is graded A-F based on syntax errors, lint issues, and bash failure rate.

## Configuration

All settings live in `soma.toml`:

```toml
[hooks]
verbosity = "normal"         # minimal (1 line), normal (3-4 lines), verbose (all)
validate_python = true       # py_compile after Write/Edit .py
validate_js = true           # node --check after Write/Edit .js
lint_python = true           # ruff check --select F after Write/Edit .py
predict = true               # anomaly prediction
fingerprint = true           # agent fingerprinting
quality = true               # A-F quality grading
task_tracking = true         # scope drift detection

[budget]
tokens = 1000000             # token limit (SAFE_MODE when exhausted)
cost_usd = 50.0              # cost limit

[thresholds]
caution = 0.40               # pressure level for CAUTION
degrade = 0.60               # pressure level for DEGRADE
quarantine = 0.80            # pressure level for QUARANTINE
restart = 0.95               # pressure level for RESTART

[weights]
uncertainty = 1.2            # signal weight in pressure aggregation
drift = 1.5
error_rate = 2.5
cost = 1.0
token_usage = 0.6
```

## CLI commands

```
soma                  # TUI dashboard (live monitoring)
soma status           # Quick text summary
soma setup-claude     # Install hooks into Claude Code
soma agents           # List all monitored agents
soma replay <file>    # Replay a recorded session
soma init             # Create soma.toml interactively
soma version          # Print version
soma quarantine <id>  # Force agent to QUARANTINE
soma release <id>     # Reset agent to HEALTHY
soma reset <id>       # Reset agent baseline
soma config show      # View current config
soma config set k v   # Change config value
```

## Files

| Path | Purpose |
|------|---------|
| `soma.toml` | Project configuration |
| `~/.soma/engine_state.json` | Full engine state (baselines, learning) |
| `~/.soma/state.json` | Snapshot for dashboard/statusline |
| `~/.soma/action_log.json` | Recent actions (session-scoped) |
| `~/.soma/predictor.json` | Pressure predictor state (session-scoped) |
| `~/.soma/task_tracker.json` | Task context (session-scoped) |
| `~/.soma/quality.json` | Quality tracker (session-scoped) |
| `~/.soma/fingerprint.json` | Agent fingerprints (persists across sessions) |
| `~/.claude/settings.json` | Claude Code hook configuration |

## Uninstalling

```bash
soma uninstall-claude   # Remove hooks from Claude Code
rm -rf ~/.soma          # Remove all state
```
