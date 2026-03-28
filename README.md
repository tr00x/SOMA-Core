# SOMA Core

[![Tests](https://github.com/tr00x/SOMA-Core/actions/workflows/ci.yml/badge.svg)](https://github.com/tr00x/SOMA-Core/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/tr00x/SOMA-Core)](https://github.com/tr00x/SOMA-Core/issues)
[![Beta](https://img.shields.io/badge/status-beta-orange.svg)]()

**System of Oversight and Monitoring for Agents**

*The nervous system for AI agents.*

Named after the **soma** — the cell body of a neuron. In biology, the soma receives signals from dendrites, processes them, and decides whether to fire. SOMA Core does the same for AI agents: receives behavioral signals, computes pressure, and decides whether to intervene.

> v0.1.0-beta — First public release. Core engine stable. Paperclip plugin available. Community layers coming.

---

## The Problem

AI agents are black boxes. You give them a task, they burn through tokens, make API calls, spawn sub-agents — and you have no idea what's happening until something breaks. Or until you get a $200 bill for an agent that spent 3 hours stuck in a retry loop.

Every existing tool (LangSmith, AgentOps, Arize) monitors what happened *after the fact*. They log tokens, cost, latency. They tell you the house burned down. They don't stop the fire.

## What SOMA Does

SOMA monitors agent *behavior* in real time and intervenes before problems compound.

- **Behavioral signals** — measures uncertainty (is the agent confused?), drift (did it go off-task?), and error patterns. Not just tokens and cost.
- **Pressure graph** — in multi-agent systems, pressure propagates between connected agents. If a sub-agent struggles, the orchestrator feels it.
- **Directive control** — SOMA doesn't just alert. It physically modifies what the agent sees: truncating context, blocking expensive tools, or stopping the agent entirely.
- **One-line integration** — `client = soma.wrap(your_client)` and you're done.

## How We Got Here

This project started from a simple question: *what actually hurts in the world of AI agents right now?*

We read the research. Papers on agent reliability, multi-agent coordination failures, context window degradation. We talked to developers running agents in production — burning money on loops, debugging ghost behaviors, watching agents drift off-task with no way to intervene.

The existing tools treat AI agents like web services: log the requests, alert on errors. But agents aren't web services. They have *behavior*. They get confused. They lose track of what they're doing. They change strategy mid-task and nobody notices until the budget is gone.

SOMA was built to close that gap. Not another dashboard. A nervous system — something that feels when an agent is in trouble and acts on it.

**Key influences:**
- Research on behavioral drift detection in autonomous systems
- EMA-based anomaly detection (exponential moving averages for establishing behavioral baselines)
- Trust dynamics in multi-agent systems (asymmetric trust decay/recovery)
- Directive control theory — the idea that a degraded agent can't be trusted to follow advisory recommendations, so the system must physically constrain it

---

## Current Status: v0.1.0-beta

This is the first public release. What works:

| Component | Status |
|---|---|
| Core engine (vitals, pressure, baseline, ladder, graph, learning) | Stable. 399 tests. 100% coverage on core. |
| CLI (`soma`, `soma init`, `soma status`, `soma replay`) | Stable. |
| TUI Dashboard (4 tabs) | Working. Reads from state file. |
| `soma.wrap()` — universal API client wrapper | Stable. Anthropic + OpenAI SDKs. |
| Paperclip plugin | Installed. Monitoring cost events. |
| Session recording + replay | Stable. |
| pytest-soma (testing framework) | Stable. |
| State persistence | Stable. Survives restarts. |

What's coming:
- PyPI publish (`pip install soma-core`)
- Web dashboard (browser-based alternative to TUI)
- More framework integrations
- Progress tracking (detect when agent is stuck, not just confused)
- Async client support

---

## Who This Is For

**You run AI agents in production** and want to know when they're struggling before they waste your budget.

**You build multi-agent systems** and need visibility into how agents affect each other.

**You test AI agent behavior** and want to assert that agents stay within acceptable parameters.

**You use Claude Code, LangChain, CrewAI, AutoGen, or any framework** that makes LLM API calls.

---

## Install

```
pip install soma-core
```

Requires Python 3.11+.

---

## Quick Start

### Option 1: Wrap your API client (recommended)

```python
import anthropic
import soma

# One line. SOMA monitors and controls everything.
client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000})

# Use your client normally.
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)

# Check agent health
print(client.soma_level)     # Level.HEALTHY
print(client.soma_pressure)  # 0.03
```

If pressure reaches QUARANTINE, SOMA blocks the next API call and raises `SomaBlocked`. Your agent can't ignore it.

### Option 2: Use the engine directly

```python
import soma

engine = soma.quickstart(budget={"tokens": 50000}, agents=["my-agent"])

result = engine.record_action("my-agent", soma.Action(
    tool_name="search",
    output_text="Found 3 results",
    token_count=150,
))

print(result.level)    # Level.HEALTHY
print(result.pressure) # 0.03
```

### Option 3: Open the dashboard

```
soma
```

Four tabs: Dashboard (live monitoring), Agents (manage), Replay (analyze sessions), Config (tune settings).

First time? SOMA runs an interactive setup wizard automatically.

---

## What SOMA Monitors

| Signal | What it detects |
|---|---|
| Uncertainty | Agent is confused, repeating itself, or producing unusual output entropy |
| Drift | Agent's behavior pattern changed from its established baseline |
| Error rate | Agent is failing (with absolute floor — errors never become "normal") |
| Response time | Agent suddenly takes much longer than usual |
| Budget burn | Agent is spending faster than sustainable |

All signals are computed from the **last 10 actions** in a rolling window. SOMA establishes each agent's behavioral baseline using exponential moving averages and flags deviations.

---

## Escalation Levels

| Level | Pressure | What SOMA does |
|---|---|---|
| **HEALTHY** | < 25% | Nothing. Agent operates normally. |
| **CAUTION** | 25-50% | Trims oldest 20% of message history. Increased logging. |
| **DEGRADE** | 50-75% | Trims 50% of history. Blocks expensive tools. |
| **QUARANTINE** | 75-90% | Clears message history. Minimal tool set only. Blocks API calls via `soma.wrap()`. |
| **RESTART** | > 90% | Fresh context. Complete reset. |
| **SAFE_MODE** | Budget = 0 | All agents stopped. Waiting for budget replenishment or human decision. |

Levels use **hysteresis** — an agent won't oscillate between CAUTION and HEALTHY on the boundary. De-escalation thresholds are 5 points below escalation thresholds.

The first 10 actions are a **grace period** — SOMA learns the baseline without penalizing cold-start noise.

---

## Multi-Agent Pressure Graph

```python
engine = soma.quickstart(budget={"tokens": 200000})
engine.register_agent("researcher")
engine.register_agent("writer")
engine.add_edge("researcher", "writer", trust_weight=0.9)

# When researcher struggles, writer feels the pressure
engine.events.on("level_changed", lambda e:
    print(f"{e['agent_id']}: {e['old_level'].name} -> {e['new_level'].name}")
)
```

Pressure propagates through directed, trust-weighted edges. Trust decays when an agent shows high uncertainty and recovers when it stabilizes. Multi-pass propagation ensures chains (A->B->C) converge in one cycle.

---

## Testing Your Agents

```python
from soma.testing import Monitor
from soma.types import Action, Level

def test_agent_stays_healthy():
    with Monitor(budget={"tokens": 10000}) as mon:
        for i in range(15):
            mon.record("agent", Action(
                tool_name="search",
                output_text=f"result {i}",
                token_count=200,
            ))
    mon.assert_healthy()
    mon.assert_below(Level.DEGRADE)
```

---

## Claude Code Integration

```
soma setup-claude
```

Creates `soma.toml`, adds SOMA instructions to `CLAUDE.md`, creates a `/soma-status` slash command.

---

## Paperclip Integration

SOMA ships as a Paperclip plugin that monitors all LLM providers. Subscribes to `cost_event.created` — every API call, every provider, every agent.

Dashboard widget shows per-agent pressure bars, token counts, and escalation levels in the Paperclip UI.

---

## CLI

```
soma                  Live dashboard (4 tabs)
soma init             Interactive setup wizard
soma status           Quick text status
soma replay FILE      Replay a recorded session with rich table
soma setup-claude     Set up for Claude Code
soma version          Show version
```

---

## Self-Learning

SOMA learns from its own interventions. After each escalation, it checks: did pressure actually drop? If not, it adjusts:

- **Threshold shifts** — if escalations at a level consistently fail, the threshold rises (up to +0.10)
- **Weight adjustments** — if a signal triggered bad escalations, its weight decreases (floor at 0.2)
- **Safety bounds** — minimum 3 interventions before any adjustment. System can't "unlearn" how to escalate.

---

## Documentation

| Document | For whom | What it covers |
|---|---|---|
| [Getting Started Guide](docs/guide.md) | Everyone | Step-by-step setup, examples, FAQ |
| [Technical Reference](docs/reference.md) | Engineers | Every formula, parameter, edge case |
| [API Reference](docs/api.md) | Developers | Every class, method, signature |
| [Contributing](CONTRIBUTING.md) | Contributors | How to build layers and contribute |

---

## Architecture

```
Agent Action
     |
  Vitals (uncertainty, drift, error_rate, response_time)
     |
  Baseline (EMA rolling mean + std, cold start blending)
     |
  Pressure (sigmoid z-score per signal, 70/30 mean/max aggregate)
     |
  Graph (trust-weighted multi-pass propagation)
     |
  Ladder (6 levels, hysteresis, learning threshold adjustments)
     |
  Context Control (directive: truncate, block tools, restart)
```

---

## Project Stats

```
Production code:   5,261 lines (43 files)
Test code:         4,976 lines (28 files)
Tests:             399 passing
Core coverage:     100%
Documentation:     3,449 lines
```

---

## License

MIT. See [LICENSE](LICENSE).

---

## Author

Tim Hunt ([@tr00x](https://github.com/tr00x))

Built with Claude Code. Monitored by SOMA.
