# SOMA CLI + TUI Hub — Design Spec

## Summary

Replace the demo dashboard with a real CLI tool. When you type `soma`, you get a full control panel. When you type `soma init`, a smart wizard sets up your project.

## Commands

```
soma              Open TUI Hub (4 tabs)
soma init         Smart wizard -> soma.toml
soma status       Quick text status (no TUI, for CI/scripts)
soma replay FILE  Replay a session file
soma version      Show version
```

## TUI Hub (4 tabs, switch with 1/2/3/4)

### Tab 1: Dashboard
- Agent cards with live vitals (pressure, uncertainty, drift, errors)
- Event log at bottom
- Budget bar
- Same concept as current dashboard but reads from state file

### Tab 2: Agents
- List of all registered agents
- Status of each (level, pressure, action count)
- Actions: kill (K), heal (H), add (A), remove (D)
- Per-agent action history (last 10)

### Tab 3: Replay
- Load a session.json file
- Step through actions one by one (arrow keys)
- Or auto-play at configurable speed
- Show "what if" — change thresholds and see different outcomes

### Tab 4: Config
- Live editor for soma.toml values
- Change thresholds, weights, budget in real time
- Preview effect on current agents
- Save to soma.toml

## Smart Wizard (soma init)

Step 1: "What type of project?"
  a) Claude Code plugin
  b) Python SDK (standalone)
  c) CI/CD testing

Step 2 (adapts):
  Claude Code: asks about budget, sensitivity
  Python SDK: asks about agents, connections, budget
  CI Testing: asks about thresholds, pass/fail criteria

Step 3: Generates:
  - soma.toml
  - Integration code snippet (printed to terminal)

No LLM calls. Pure branching logic. Fast.

## soma.toml Format

```toml
[soma]
version = "0.1.0"
store = "~/.soma/state.json"

[budget]
tokens = 100000
cost_usd = 5.0

[agents.default]
autonomy = "human_on_the_loop"
sensitivity = "balanced"

[thresholds]
caution = 0.25
degrade = 0.50
quarantine = 0.75
restart = 0.90

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
cost = 1.0
token_usage = 0.8

[graph]
damping = 0.6
trust_decay_rate = 0.05
trust_recovery_rate = 0.02
```

## soma status (text output)

```
SOMA v0.1.0 — 3 agents monitored

Agent 1    HEALTHY     p=0.03  u=0.11  d=0.00  e=0.00   #42
Agent 2    CAUTION     p=0.31  u=0.28  d=0.05  e=0.10   #38
Agent 3    HEALTHY     p=0.02  u=0.09  d=0.00  e=0.00   #41

Budget: 73% (tokens: 27,000/100,000)
```

## State File (~/.soma/state.json)

Written by layers, read by CLI. Contains:
- All agent states (vitals, baseline, level)
- Budget state
- Pressure graph
- Action history (last 100 per agent)
- Learning state

## Architecture

```
src/soma/cli/
├── __init__.py
├── main.py          # Entry point, argparse
├── hub.py           # TUI Hub (Textual App with tabs)
├── wizard.py        # soma init wizard
├── status.py        # soma status text output
├── replay_cli.py    # soma replay CLI mode
├── config_loader.py # Read/write soma.toml
└── tabs/
    ├── __init__.py
    ├── dashboard.py  # Tab 1
    ├── agents.py     # Tab 2
    ├── replay.py     # Tab 3
    └── config.py     # Tab 4
```
