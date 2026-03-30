# SOMA Guide

## Quick Start

```bash
pip install soma-ai
soma setup-claude
```

This installs 4 hooks into Claude Code and creates `~/.soma/` for state.

## What happens after setup

Every tool call in Claude Code now flows through SOMA:

```
You type a command
  -> PreToolUse evaluates guidance: observe, suggest, warn, or block destructive ops
  -> Tool executes (or gets blocked if destructive at high pressure)
  -> PostToolUse records the action, validates code, computes pressure
  -> Next prompt: UserPromptSubmit injects feedback into agent context
  -> Session ends: Stop saves state, updates fingerprint
```

SOMA is always present after 3 actions. The notification module is a thin formatter -- all intelligence lives in the core modules (`patterns.py`, `findings.py`, `context.py`).

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

Pressure maps to response modes:

| Mode | Pressure Range | What happens |
|------|---------------|-------------|
| OBSERVE | 0-25% | Silent. Metrics collected, no intervention. |
| GUIDE | 25-50% | Soft suggestions when patterns detected. Never blocks. |
| WARN | 50-75% | Insistent warnings with alternatives. Never blocks. |
| BLOCK | 75-100% | Blocks ONLY destructive operations (rm -rf, git push --force, .env writes). |

Write, Edit, Bash, and Agent are **never blocked**. Only genuinely destructive operations are stopped, and only at 75%+ pressure.

## Baselines and learning

SOMA uses exponential moving averages (EMA, alpha=0.15) to learn what's "normal":

- First 10 actions: grace period (zero pressure)
- Actions 10-20: baselines blend from defaults to observed values
- After 20: baselines reflect actual agent behavior

The learning engine tracks intervention outcomes:
- If intervention helped (pressure dropped) -> lower threshold slightly
- If intervention didn't help (pressure stayed) -> raise threshold
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

SOMA infers what phase you're in (research/implement/test/debug) and tracks which files/directories you're focused on. If you drift to unrelated areas, it flags scope drift. The task tracker accepts a `cwd` parameter and `get_efficiency()` returns `context_efficiency`, `success_rate`, and `focus` metrics.

### Quality scoring

Every Write/Edit gets syntax-checked (Python: py_compile, JS: node --check) and linted (Python: ruff). Session quality is graded A-F based on syntax errors, lint issues, and bash failure rate.

### Pattern analysis

Core pattern detection (`soma.patterns`) analyzes the last 10 actions for:
- Edits without prior Reads (blind edits)
- Consecutive Bash failures
- High error rate (>30%)
- File thrashing (same file edited 3+ times)
- Agent spam (3+ agent spawns)
- Research stall (7+ reads, 0 writes)
- No user check-in (15+ mutations without asking)
- Positive patterns: read-before-edit maintained, clean streaks

Patterns are workflow-aware: agent spam and research stall are suppressed during plan/discuss phases; scope drift and no-checkin are suppressed during execute/plan.

### Session context

`soma.context` detects the working environment:
- GSD workflow mode (plan, execute, discuss, fast)
- Working directory from `CLAUDE_WORKING_DIRECTORY` env var
- Session action count and pressure level

## Configuration

All settings live in `soma.toml`. Old config keys (e.g. `caution`, `degrade`, `quarantine`) auto-migrate on load.

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
tokens = 1000000             # token limit
cost_usd = 50.0              # cost limit

[thresholds]
guide = 0.25                 # pressure for GUIDE mode
warn = 0.50                  # pressure for WARN mode
block = 0.75                 # pressure for BLOCK mode

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
soma doctor           # Check SOMA installation health (hooks, config, state)
soma agents           # List all monitored agents
soma replay <file>    # Replay a recorded session
soma init             # Create soma.toml interactively
soma version          # Print version
soma stop             # Disable SOMA hooks in Claude Code
soma start            # Re-enable SOMA hooks in Claude Code
soma uninstall-claude # Remove SOMA from Claude Code completely
soma reset <id>       # Reset agent baseline
soma config show      # View current config
soma config set k v   # Change config value
soma mode <name>      # Switch operating mode (strict/relaxed/autonomous)
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

## Disabling and uninstalling

```bash
soma stop               # Disable hooks (keep config, easy re-enable with soma start)
soma uninstall-claude   # Remove hooks from Claude Code entirely
rm -rf ~/.soma          # Remove all state
```
