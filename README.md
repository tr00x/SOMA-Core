# SOMA Core

[![Tests](https://github.com/tr00x/SOMA-Core/actions/workflows/ci.yml/badge.svg)](https://github.com/tr00x/SOMA-Core/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/tr00x/SOMA-Core)](https://github.com/tr00x/SOMA-Core/issues)
[![Beta](https://img.shields.io/badge/status-beta-orange.svg)]()

> **SOMA** — **S**ystem of **O**versight and **M**onitoring for **A**gents
>
> Also: *soma* (Greek: *body*) — the cell body of a neuron. It receives signals from dendrites, integrates them, and decides whether to fire.

AI agents have no proprioception. They cannot feel themselves failing. They loop, drift, burn money, corrupt their own context — and have zero awareness that anything is wrong. They are brains without a nervous system.

SOMA is that nervous system.

Not a dashboard. Not a logger. Not an alerting layer that tells you the house already burned down. SOMA is a new primitive: continuous behavioral measurement, inter-agent pressure propagation, and directive control over what agents can see and do. It sits above your agents. They don't get a vote.

> v0.2.0-beta — Paperclip plugin, daemon mode, file-based IPC. [Changelog](CHANGELOG.md)

---

## The Four Problems (One Root Cause)

Everyone treats these as separate issues. They aren't.

**Compound Error.** An agent makes a small mistake. Then it reasons about its own broken output. Then it compounds. By action 20 the context is poisoned and every subsequent step makes it worse. Nobody intervenes because nobody is measuring behavioral pressure — only tokens and cost.

**Context Half-Life.** The longer an agent runs, the less it remembers why it started. Context fills up. Old instructions get compressed or dropped. The agent's effective goal drifts. This isn't a bug — it's physics. But no tool detects it because drift is a behavioral signal, not a resource metric.

**Semantic Cascade.** In multi-agent systems, a struggling sub-agent doesn't just fail alone. Its garbage output becomes input for the next agent. And the next. One confused agent can poison an entire pipeline. Nobody builds monitoring that models these dependencies. We do — pressure graphs with trust dynamics.

**Coordination Tax.** Every agent in a multi-agent system adds overhead. More agents means more failure surface, more context to track, more trust relationships to manage. The monitoring cost should scale sub-linearly. Instead, most tools scale linearly or not at all.

**The root cause:** agents lack proprioception. They have no internal sense of "something is wrong with me." SOMA provides that sense from the outside.

---

## What SOMA Does About It

SOMA measures **behavior**, not metadata. It computes **pressure** — how far an agent has deviated from its established baseline. And when pressure rises, it **acts**.

| Capability | How |
|---|---|
| Behavioral vitals | Uncertainty (confusion, repetition, entropy deviation), drift (cosine distance from baseline behavior vector) |
| Pressure graph | Directed trust-weighted edges between agents. Pressure propagates. Trust decays under uncertainty, recovers when stable. |
| Directive control | Not advisory. SOMA physically truncates context, blocks tools, quarantines agents. The agent can't override it. |
| Self-learning | Tracks whether its own interventions worked. Adjusts thresholds and weights automatically. Safety-bounded. |
| One-line integration | `client = soma.wrap(your_client)` — wraps any Anthropic or OpenAI client. |

---

## The Analogy Is Literal

This isn't marketing. SOMA is architecturally modeled on the biological nervous system.

| Biology | SOMA |
|---|---|
| Sensory neurons (dendrites) | Vitals: uncertainty, drift, error rate, response time |
| Soma (cell body) — integrates signals, decides to fire | Pressure calculator: sigmoid clamp, weighted aggregate, baseline comparison |
| Axons — transmit signals between neurons | Pressure graph: trust-weighted edges, multi-pass propagation |
| Motor neurons — cause action | Context control: truncate, block, quarantine, restart |
| Proprioception — sense of body position | What agents lack. What SOMA provides. |
| Pain — forces attention and reaction | Pressure escalation. Not optional. Not advisory. |

The soma doesn't ask the muscle if it wants to contract. SOMA doesn't ask the agent if it wants to be quarantined.

---

## Research That Got Us Here

This project started from a simple question: *what actually hurts in the world of AI agents right now?*

The numbers were bad. A [benchmark of 34 agent tasks](https://arxiv.org/html/2508.13143v1) found ~50% completion rate. An [analysis of ~1,642 multi-agent traces](https://arxiv.org/html/2602.13855v1) showed failure rates from 41% to 86.7%. ["Towards a Science of AI Agent Reliability"](https://arxiv.org/html/2602.16666v1) documented real incidents: coding assistants deleting production databases, agents making unauthorized purchases.

[SentinelAgent](https://arxiv.org/abs/2505.24201) showed graph-based anomaly detection works for multi-agent failures. The [AgentOps survey](https://arxiv.org/html/2508.02121v1) found most tools only cover monitoring — not detection, root cause, or resolution. [Multi-Agent Risks from Advanced AI](https://arxiv.org/abs/2502.14143) mapped coordination failure modes.

Nobody connected the dots. Compound error, half-life, cascade, coordination — four symptoms, one disease: agents can't feel themselves failing. We built the fix.

**Key influences:**
- [Towards a Science of AI Agent Reliability](https://arxiv.org/html/2602.16666v1)
- [SentinelAgent: Graph-based Anomaly Detection](https://arxiv.org/abs/2505.24201)
- [Exploring Autonomous Agents: Why They Fail](https://arxiv.org/html/2508.13143v1)
- [A Survey on AgentOps](https://arxiv.org/html/2508.02121v1)
- [Multi-Agent Risks from Advanced AI](https://arxiv.org/abs/2502.14143)
- EMA-based anomaly detection for behavioral baselines
- Asymmetric trust dynamics (trust decays fast, recovers slowly)
- Directive control theory (degraded agents can't follow advice — constrain them physically)

---

## Quick Start

### Wrap your API client

```python
import anthropic
import soma

client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000})

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)

print(client.soma_level)     # Level.HEALTHY
print(client.soma_pressure)  # 0.03
```

SOMA intercepts every call. If pressure hits QUARANTINE, the next call raises `SomaBlocked`. The agent is stopped. You decide what happens next.

### Or use the engine directly

```python
import soma

engine = soma.quickstart(budget={"tokens": 50000}, agents=["my-agent"])
result = engine.record_action("my-agent", soma.Action(
    tool_name="search", output_text="Found 3 results", token_count=150,
))
```

### Open the dashboard

```
soma
```

---

## Escalation

| Level | Pressure | What happens |
|---|---|---|
| **HEALTHY** | < 25% | Normal operation. |
| **CAUTION** | 25-50% | 20% context trimmed. |
| **DEGRADE** | 50-75% | 50% trimmed. Expensive tools blocked. |
| **QUARANTINE** | 75-90% | Context cleared. Minimal tools. API calls blocked. |
| **RESTART** | > 90% | Complete reset. |
| **SAFE_MODE** | Budget = 0 | Everything stops. |

Grace period: first 10 actions are penalty-free. Hysteresis: -5pt de-escalation offset prevents oscillation.

---

## Multi-Agent

```python
engine.add_edge("sub_agent", "orchestrator", trust_weight=0.9)
```

When `sub_agent` struggles, `orchestrator` feels it. Pressure flows through the graph. Trust decays under uncertainty (0.05/step), recovers when stable (0.02/step). Multi-pass propagation — chains converge in one cycle.

---

## Claude Code

```
soma setup-claude
```

Installs hooks on PreToolUse, PostToolUse, PostMessage, and Stop. SOMA monitors every action. At QUARANTINE, tool calls are blocked. The dashboard shows everything in real time.

---

## Paperclip Plugin

SOMA ships with a first-party [Paperclip](https://github.com/paperclipai/paperclip) plugin for managing AI agent companies.

**Install:** Settings → Plugins → Examples → "SOMA Core — Agent Monitor" → Install

**Features:**
- Dashboard widget with real-time pressure bars for all agents
- Full monitoring page (`/soma`) with vitals, controls, budget management
- Settings page with editable thresholds, budget limits, behavior toggles
- Sidebar entry with status indicator
- Agent detail tab with SOMA vitals
- Control panel: Quarantine/Release/Reset per-agent and bulk
- File-based IPC — no extra servers needed

**How it works:**
```
Agent → Claude Code → PostToolUse hook → ~/.soma/inbox/
                                              ↓
                                       SOMA daemon (1s poll)
                                              ↓
                                       ~/.soma/state.json
                                              ↓
                                       Paperclip plugin (3s poll) → UI
```

Quarantine/Release/Reset commands flow in reverse: Plugin → `~/.soma/commands/` → daemon → engine.

The plugin is in `packages/plugins/examples/plugin-soma-monitor/` if you're running Paperclip from source.

---

## Testing

```python
from soma.testing import Monitor
from soma.types import Action, Level

def test_agent_stays_healthy():
    with Monitor(budget={"tokens": 10000}) as mon:
        for i in range(15):
            mon.record("agent", Action(tool_name="search", output_text=f"r{i}", token_count=200))
    mon.assert_healthy()
```

---

## Architecture

```
Action -> Vitals -> Baseline -> Pressure -> Graph -> Ladder -> Control
            |                      |           |                  |
      uncertainty           sigmoid z-score  trust-weighted   truncate
         drift              70/30 aggregate   propagation    block tools
      error rate           burn rate signal   multi-pass     quarantine
     response time         learning weights   trust decay      restart
```

---

## Documentation

| Doc | Audience |
|---|---|
| [Getting Started](docs/guide.md) | Everyone |
| [Technical Reference](docs/reference.md) | Engineers |
| [API Reference](docs/api.md) | Developers |
| [Roadmap](ROADMAP.md) | Contributors |
| [Changelog](CHANGELOG.md) | Everyone |

---

## Status: v0.2.0-beta

```
5,800+ lines of code.  399 tests.  100% core coverage.
Paperclip plugin: 1,200+ lines (manifest + worker + UI).
Daemon + command queue + inbox processor.
```

See [ROADMAP.md](ROADMAP.md) for what's next.

---

## Help Wanted

I'm one person. SOMA Core is built, the engine works, the math is verified — but there's a whole world of AI frameworks out there and I can't integrate with all of them alone.

If you've ever watched an AI agent burn $50 on a loop and thought "there should be a way to stop this" — this is your project too.

**What needs building:**

- **Framework connectors** — every agent framework and orchestrator needs a SOMA layer. The list is long and I need help:

  `soma-langchain` / `soma-crewai` / `soma-autogen` / `soma-openai-agents` / `soma-llama-index` / `soma-semantic-kernel` / `soma-haystack` / `soma-dspy` / `soma-pydantic-ai` / `soma-magentic-one` / `soma-langgraph` / `soma-smolagents` / `soma-camel-ai` / `soma-agno` / `soma-julep` / `soma-letta` / `soma-composio` / `soma-e2b` / `soma-superagent` / `soma-fixie` / `soma-promptflow`

  Each one is a thin wrapper — if you use a framework, you already know how its internals work. You can build its SOMA connector. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Async support** — `soma.wrap()` for `AsyncAnthropic` and `AsyncOpenAI`. [Issue #2](https://github.com/tr00x/SOMA-Core/issues/2).
- **Web dashboard** — browser-based alternative to the TUI. [Issue #3](https://github.com/tr00x/SOMA-Core/issues/3).
- **OpenTelemetry export** — push SOMA metrics to Grafana, Datadog, whatever you use. [Issue #7](https://github.com/tr00x/SOMA-Core/issues/7).
- **Progress tracking** — detect when an agent is stuck, not just confused. [Issue #6](https://github.com/tr00x/SOMA-Core/issues/6).
- **Testing in production** — if you run agents, try SOMA and report what breaks. That's the most valuable contribution.

Every AI agent deserves a nervous system. Help me build it for all of them.

Issues marked [`good first issue`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) and [`help wanted`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) are waiting for you.

---

## License

MIT. See [LICENSE](LICENSE).

## Author

Tim Hunt ([@tr00x](https://github.com/tr00x))

Built with Claude Code. Monitored by SOMA.
