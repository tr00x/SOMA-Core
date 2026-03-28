<p align="center">
  <h1 align="center">SOMA Core</h1>
</p>

<p align="center">
  <strong>AI agents are blind to themselves. SOMA fixes that.</strong>
</p>

<p align="center">
  <a href="https://github.com/tr00x/SOMA-Core/actions/workflows/ci.yml"><img src="https://github.com/tr00x/SOMA-Core/actions/workflows/ci.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://github.com/tr00x/SOMA-Core/issues"><img src="https://img.shields.io/github/issues/tr00x/SOMA-Core" alt="GitHub issues"></a>
  <img src="https://img.shields.io/badge/status-v0.2.0--beta-orange.svg" alt="Beta">
</p>

<p align="center">
  <b>SOMA</b> — <b>S</b>ystem of <b>O</b>versight and <b>M</b>onitoring for <b>A</b>gents<br>
  <sub><i>soma</i> (Greek: <i>body</i>) — the cell body of a neuron. Receives signals, integrates them, decides whether to fire.</sub>
</p>

<br>

> SOMA watches how your AI agent **behaves** — not just how much it spends. When an agent starts struggling, SOMA notices, computes **pressure**, and **physically cuts** what the agent can see and do. If you have multiple agents, pain **spreads** through a trust graph. Budget hits zero — everything stops. You choose the level of control. And SOMA **learns from itself**.
>
> One line to set up: `client = soma.wrap(your_client)`

<br>

---

<br>

## The Problem Is One Problem &nbsp; <img src="https://img.shields.io/badge/proprioception-missing-red" alt="">

Everyone treats agent failures as separate issues. They aren't. They're all the same disease.

<table>
<tr>
<td width="50%">

**Agents have no proprioception.** A human knows when they're confused. An agent doesn't. It loops, drifts, burns money, corrupts its own context — with zero awareness that anything is wrong.

Every tool on the market treats this as a logging problem. Record what happened. Alert after the fact. That's treating symptoms.

</td>
<td width="50%">

**Four symptoms, one disease:**

- **Compound error** — broken output feeds back, compounds
- **Context half-life** — goals drift as context fills
- **Semantic cascade** — one agent's garbage poisons the pipeline
- **Coordination tax** — more agents = more failure surface

</td>
</tr>
</table>

<br>

---

<br>

## SOMA Is Not a Monitor &nbsp; <img src="https://img.shields.io/badge/role-controller-18FFFF" alt="">

<table>
<tr><td>

**SOMA is a controller.** It sits above your agents. They don't get a vote.

| | |
|:--|:--|
| **Measures behavior** | Uncertainty, drift, error rate, response time |
| **Computes pressure** | Sigmoid z-scores, 70/30 aggregate, burn rate |
| **Propagates** | Trust-weighted graph, multi-pass convergence |
| **Acts** | Truncates context. Blocks tools. Quarantines. Restarts. |
| **Learns** | Adjusts thresholds from its own intervention outcomes |

*The soma doesn't ask the muscle if it wants to contract.*
*SOMA doesn't ask the agent if it wants to be quarantined.*

</td></tr>
</table>

<br>

---

<br>

## Quick Start &nbsp; <img src="https://img.shields.io/badge/one_line-integration-58a6ff" alt="">

<table>
<tr>
<td width="50%">

**Wrap your API client**

```python
import anthropic
import soma

client = soma.wrap(
    anthropic.Anthropic(),
    budget={"tokens": 50000},
)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)

print(client.soma_level)     # Level.HEALTHY
print(client.soma_pressure)  # 0.03
```

</td>
<td width="50%">

**Or use the engine directly**

```python
import soma

engine = soma.quickstart(
    budget={"tokens": 50000},
    agents=["my-agent"],
)

result = engine.record_action(
    "my-agent",
    soma.Action(
        tool_name="search",
        output_text="Found 3 results",
        token_count=150,
    ),
)

print(result.level)    # Level.HEALTHY
print(result.pressure) # 0.03
```

</td>
</tr>
</table>

```bash
# Open the TUI dashboard
soma
```

<br>

---

<br>

## Escalation Ladder &nbsp; <img src="https://img.shields.io/badge/6_levels-hysteresis-22c55e" alt="">

```
  HEALTHY ──── CAUTION ──── DEGRADE ──── QUARANTINE ──── RESTART ──── SAFE_MODE
   < 25%       25-50%       50-75%        75-90%         > 90%       budget = 0
  normal     20% trimmed  50% trimmed   calls blocked   full reset   hard stop
```

<details>
<summary><b>Level details</b></summary>

| Level | Pressure | What SOMA does |
|:------|:---------|:---------------|
| **HEALTHY** | < 25% | Normal operation |
| **CAUTION** | 25-50% | Trims 20% oldest context |
| **DEGRADE** | 50-75% | Trims 50%, blocks expensive tools |
| **QUARANTINE** | 75-90% | Clears context, minimal tools, blocks API calls |
| **RESTART** | > 90% | Complete reset |
| **SAFE_MODE** | Budget = 0 | Everything stops |

Grace period: first 10 actions are penalty-free.
Hysteresis: -5pt de-escalation offset prevents oscillation.

</details>

<br>

---

<br>

## Multi-Agent Pressure Graph &nbsp; <img src="https://img.shields.io/badge/trust-dynamics-ff9100" alt="">

> **This is what makes SOMA different from every other monitoring tool.**
> In a multi-agent system, agents depend on each other. When one agent starts failing, every agent downstream is at risk. No other tool models these dependencies. SOMA does — with live trust that adapts in real time.

**The problem every orchestrator has:** Agent A produces output. Agent B consumes it. If A is confused, B gets garbage input — but B has no way to know. It trusts A blindly. The pipeline fails silently.

**SOMA's solution:** A trust-weighted pressure graph. Every agent-to-agent dependency is an edge with a trust score. When the source struggles, trust drops. Pressure flows downstream. The receiver knows not to blindly consume.

```python
engine.add_edge("researcher", "writer", trust_weight=0.9)
engine.add_edge("writer", "reviewer", trust_weight=0.7)

# Researcher starts failing:
#   → trust(researcher→writer) decays: 0.9 → 0.85 → 0.80...
#   → writer's effective pressure rises (feels upstream pain)
#   → reviewer sees it too through writer
#
# Researcher recovers:
#   → trust recovers slowly: 0.80 → 0.82 → 0.84...
#   → one bad output costs more than ten good ones earn back
```

<details>
<summary><b>Trust dynamics in detail</b></summary>

| What happens | Effect on trust |
|:-------------|:----------------|
| Source agent has high uncertainty | Trust **decays** at 0.05 per action |
| Source agent stabilizes | Trust **recovers** at 0.02 per action |
| Trust reaches 0 | Incoming pressure completely ignored |
| Trust at 1.0 | Full pressure transmitted (damped by 0.6x) |

**Formula:** `effective_pressure = max(own_pressure, 0.6 * weighted_avg_incoming)`

An agent's own problems always dominate. But upstream failures can't be ignored.

**Multi-pass propagation:** In a chain A→B→C, one propagation cycle is enough. No stale data, no second-pass surprises.

**Why this matters for orchestrators:** CrewAI, AutoGen, LangGraph, OpenClaw — all run multi-agent pipelines. None of them track trust between agents. When one agent in the crew goes bad, the orchestrator finds out when the whole pipeline produces garbage. SOMA catches it at the source and propagates the warning before damage spreads.

</details>

<br>

---

<br>

## Autonomy Modes &nbsp; <img src="https://img.shields.io/badge/3_modes-configurable-7c3aed" alt="">

<table>
<tr>
<td align="center" width="33%">
<br>
<b>Fully Autonomous</b><br><br>
<sub>SOMA decides everything.<br>QUARANTINE, RESTART — no human needed.</sub>
<br><br>
</td>
<td align="center" width="33%">
<br>
<b>Human-in-the-Loop</b><br><br>
<sub>Up to DEGRADE — automatic.<br>QUARANTINE+ — waits for <code>soma approve</code>.</sub>
<br><br>
</td>
<td align="center" width="33%">
<br>
<b>Human-on-the-Loop</b><br><br>
<sub>Everything automatic, but human<br>sees all and can <code>soma release</code>.</sub>
<br><br>
</td>
</tr>
</table>

```toml
# soma.toml
[agents.default]
autonomy = "human_in_the_loop"
```

<br>

---

<br>

## CLI

<table>
<tr>
<td width="50%">

**Monitoring**
```
soma                    TUI dashboard
soma agents             List all agents
soma status             Quick text status
```

**Control**
```
soma quarantine <id>    Block agent
soma release <id>       Unblock agent
soma reset <id>         Reset baseline
soma approve <id>       Approve escalation
```

</td>
<td width="50%">

**Configuration**
```
soma init               Setup wizard
soma config show        View soma.toml
soma config set k v     Change setting
soma setup-claude       Install Claude hooks
```

**Session**
```
soma export             Export to JSON
soma replay <file>      Replay session
soma daemon             Run daemon
soma version            Version info
```

</td>
</tr>
</table>

<br>

---

<br>

## Integrations

| Integration | Status | Where |
|:---|:---|:---|
| **Claude Code** | Built-in | `src/soma/hooks/claude_code.py` |
| **Anthropic / OpenAI SDK** | Built-in | `soma.wrap(client)` |
| **Paperclip** | Separate repo | [SOMA-Paperclip](https://github.com/tr00x/SOMA-Paperclip) |
| **OpenClaw** | Planned | Community |
| **LangChain** | Planned | [help wanted](https://github.com/tr00x/SOMA-Core/issues/4) |
| **CrewAI** | Planned | [help wanted](https://github.com/tr00x/SOMA-Core/issues/5) |

<details>
<summary><b>25+ frameworks that need connectors</b></summary>

**Top tier:** `soma-openclaw` `soma-langchain` `soma-langgraph` `soma-crewai` `soma-openai-agents` `soma-autogen`

**Major:** `soma-llama-index` `soma-semantic-kernel` `soma-haystack` `soma-dspy` `soma-pydantic-ai` `soma-rasa`

**Orchestrators:** `soma-magentic-one` `soma-smolagents` `soma-camel-ai` `soma-fastagency`

**Platforms:** `soma-agno` `soma-julep` `soma-letta` `soma-composio` `soma-e2b` `soma-lindy` `soma-dify`

</details>

<br>

---

<br>

## Architecture

```
Action ──→ Vitals ──→ Baseline ──→ Pressure ──→ Graph ──→ Ladder ──→ Control
             │                        │            │                     │
        uncertainty              sigmoid z       trust-weighted      truncate
           drift                70/30 aggregate   propagation       block tools
        error rate              burn rate signal   multi-pass        quarantine
       response time           learning weights    trust decay         restart
```

<br>

---

<br>

<details>
<summary><b>Why existing tools are fundamentally wrong</b></summary>

<br>

A [benchmark of 34 agent tasks](https://arxiv.org/html/2508.13143v1) found ~50% completion rate. [1,642 multi-agent traces](https://arxiv.org/html/2602.13855v1) showed 41-86.7% failure rates. Real incidents include [agents deleting production databases](https://arxiv.org/html/2602.16666v1).

The [AgentOps survey](https://arxiv.org/html/2508.02121v1) breaks monitoring into four stages: monitoring, detection, root cause, resolution. **Most tools only cover stage one.**

[SentinelAgent](https://arxiv.org/abs/2505.24201) proved graph-based anomaly detection works. But it's research — not a library you can `pip install`. SOMA is.

**Research:** [Agent Reliability](https://arxiv.org/html/2602.16666v1) | [SentinelAgent](https://arxiv.org/abs/2505.24201) | [Why Agents Fail](https://arxiv.org/html/2508.13143v1) | [AgentOps Survey](https://arxiv.org/html/2508.02121v1) | [Multi-Agent Risks](https://arxiv.org/abs/2502.14143)

</details>

<details>
<summary><b>The biology is not a metaphor</b></summary>

<br>

| Biology | SOMA |
|:--------|:-----|
| Sensory neurons (dendrites) | Vitals: uncertainty, drift, error rate, response time |
| Soma (cell body) | Pressure: sigmoid clamp, weighted aggregate, baseline |
| Axons | Graph: trust-weighted edges, multi-pass propagation |
| Motor neurons | Control: truncate, block, quarantine, restart |
| Proprioception | What agents lack. What SOMA provides. |
| Pain | Pressure escalation. Not optional. |

</details>

<br>

---

<br>

## Documentation

| | Doc | For |
|:--|:----|:----|
| **Start here** | [Getting Started](docs/guide.md) | Everyone |
| **Deep dive** | [Technical Reference](docs/reference.md) | Engineers |
| **API** | [API Reference](docs/api.md) | Developers |
| **Future** | [Roadmap](ROADMAP.md) | Contributors |
| **Changes** | [Changelog](CHANGELOG.md) | Everyone |
| **Contribute** | [Contributing](CONTRIBUTING.md) | Contributors |

<br>

---

<br>

<table>
<tr>
<td align="center">

**371 tests** | **37 modules** | **100% core coverage** | **15 CLI commands** | **3,449 lines of docs**

v0.2.0-beta | [Roadmap](ROADMAP.md) | MIT License

</td>
</tr>
</table>

<br>

---

<sub>Built by Tim Hunt ([@tr00x](https://github.com/tr00x)) with Claude Code. Monitored by SOMA.</sub>
