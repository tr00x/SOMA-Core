# SOMA Core

Behavioral monitoring and control for AI agents. SOMA watches what your agent does — not just what it spends — and intervenes when things go wrong.

```
pip install soma-core
soma setup-claude
```

That's it. Your Claude Code now has a nervous system.

## What it does

SOMA runs as hooks inside Claude Code. Every tool call goes through SOMA:

**Monitors** 5 behavioral signals per action:
- Uncertainty (retries, output chaos)
- Drift (deviation from normal patterns)
- Error rate
- Token/cost burn
- Output quality (syntax, lint)

**Predicts** problems before they happen:
- Linear trend extrapolation + pattern-based boosters
- Warns the agent ~5 actions before escalation

**Restricts** progressively when pressure rises:
- HEALTHY: everything allowed
- CAUTION: Write/Edit blocked without prior Read
- DEGRADE: Bash/Agent blocked
- QUARANTINE: read-only

**Explains** in plain English:
- "stuck in Edit->Bash loop on config.py (4 cycles)"
- "3 consecutive Bash failures (error_rate=40%)"
- "scope expanded to tests/, config/"

**Learns** across sessions:
- Baseline inheritance (new sessions start warm)
- Agent fingerprinting (detect behavior shifts)
- Adaptive threshold tuning (fewer false positives over time)

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

Run `soma setup-claude` to generate defaults optimized for Claude Code.

## Commands

```
soma                  # live TUI dashboard
soma status           # quick text summary
soma setup-claude     # install hooks into Claude Code
soma replay           # replay recorded sessions
```

## How it works

```
Tool call -> PreToolUse (can block) -> Tool executes -> PostToolUse (record + validate)
                                                              |
                                                    Compute vitals -> Pressure -> Level
                                                              |
                              UserPromptSubmit <- Prediction + RCA + Quality + Tips
```

4 hooks, all configurable:
- **PreToolUse**: blocks dangerous actions under pressure
- **PostToolUse**: records action, validates code, computes vitals, predicts
- **UserPromptSubmit**: injects actionable feedback into agent context
- **Stop**: saves state, updates fingerprint, shows session summary

## The engine

The core is a signal processing pipeline:

1. **Record** action (tool, output, error, duration)
2. **Compute** behavioral vitals (uncertainty, drift, error rate)
3. **Aggregate** into pressure (weighted mean + max, 0-1)
4. **Propagate** through trust graph (multi-agent)
5. **Evaluate** against adaptive thresholds
6. **Learn** from intervention outcomes (success/failure)

Everything is deterministic. No LLM calls. No network requests. Pure math.

## Intelligence features (v0.3)

| Feature | What it does |
|---------|-------------|
| Anomaly prediction | Warns ~5 actions before escalation |
| Root cause analysis | "stuck in Edit->Bash loop" not "drift=0.40" |
| Agent fingerprinting | Detects when behavior diverges from learned profile |
| Adaptive tuning | Thresholds self-adjust based on intervention outcomes |
| Task tracking | Detects scope drift from initial focus area |
| Quality scoring | A-F grade based on syntax errors, lint, bash failures |

## Requirements

- Python >= 3.11
- Claude Code (for hook integration)
- Optional: `ruff` for lint validation, `node` for JS validation

## License

MIT
