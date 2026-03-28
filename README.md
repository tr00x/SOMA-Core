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

---

## The Problem Is One Problem

Everyone treats agent failures as separate issues: loops, drift, budget overruns, cascading errors. They aren't separate. They're all the same disease.

**Agents have no proprioception.**

A human knows when they're confused. An agent doesn't. It loops, drifts, burns money, corrupts its own context — with zero awareness that anything is wrong. It's a brain without a nervous system.

Every tool on the market — LangSmith, AgentOps, Arize — treats this as a logging problem. Record what happened. Alert when something looks wrong. Show a dashboard after the fact. That's treating symptoms, not the disease.

The disease is that agents can't feel themselves failing. Here's how it manifests:

**Compound error** — agent makes a small mistake, then reasons about its own broken output, then compounds. By action 20 the context is poisoned. Nobody intervenes because nobody is measuring behavioral pressure.

**Context half-life** — the longer an agent runs, the less it remembers why it started. Old instructions compress. The agent's effective goal drifts. Not a bug — physics. But nobody detects it because drift is behavioral, not a resource metric.

**Semantic cascade** — in multi-agent systems, one confused agent doesn't fail alone. Its garbage output becomes input for the next agent. One failure poisons the entire pipeline.

**Coordination tax** — every agent adds failure surface. Monitoring cost should scale sub-linearly. Every existing tool scales linearly or not at all.

One root cause. Four symptoms. One fix.

---

## SOMA Is Not a Monitor

SOMA is a **controller**. It sits above your agents. They don't get a vote.

| What SOMA does | How |
|:---------------|:----|
| **Measures behavior** | Uncertainty (confusion, repetition, entropy), drift (cosine distance from baseline), error rate, response time |
| **Computes pressure** | Sigmoid-clamped z-scores, 70/30 weighted mean/max aggregate, burn rate feedback |
| **Propagates pressure** | Trust-weighted directed graph. Multi-pass convergence. Trust decays under uncertainty, recovers when stable. |
| **Acts directively** | Truncates context. Blocks tools. Quarantines agents. Blocks API calls. Restarts. Not advisory — physical. |
| **Learns** | Tracks whether its own interventions worked. Adjusts thresholds and weights. Safety-bounded. |

The soma doesn't ask the muscle if it wants to contract. SOMA doesn't ask the agent if it wants to be quarantined.

---

## The Biology Is Not a Metaphor

SOMA is architecturally modeled on the biological nervous system. This isn't branding.

| Biology | SOMA |
|:--------|:-----|
| Sensory neurons (dendrites) | Vitals: uncertainty, drift, error rate, response time |
| Soma (cell body) — integrates, decides | Pressure: sigmoid clamp, weighted aggregate, baseline comparison |
| Axons — transmit between neurons | Graph: trust-weighted edges, multi-pass propagation |
| Motor neurons — cause action | Control: truncate, block, quarantine, restart |
| Proprioception — body awareness | What agents lack. What SOMA provides. |
| Pain — forces reaction | Pressure escalation. Not optional. |

---

## Why Existing Tools Are Fundamentally Wrong

A [benchmark of 34 agent tasks](https://arxiv.org/html/2508.13143v1) found ~50% completion rate. [1,642 multi-agent traces](https://arxiv.org/html/2602.13855v1) showed 41-86.7% failure rates. Real incidents include [agents deleting production databases and making unauthorized purchases](https://arxiv.org/html/2602.16666v1).

The [AgentOps survey](https://arxiv.org/html/2508.02121v1) breaks monitoring into four stages: monitoring, detection, root cause, resolution. **Most tools only cover stage one.** They record. They don't detect. They don't diagnose. They definitely don't intervene.

[SentinelAgent](https://arxiv.org/abs/2505.24201) proved that graph-based anomaly detection catches multi-agent failures that single-agent monitoring misses. But it's research — not a library you can `pip install`.

SOMA is.

<details>
<summary><b>Full research bibliography</b></summary>

- [Towards a Science of AI Agent Reliability](https://arxiv.org/html/2602.16666v1)
- [SentinelAgent: Graph-based Anomaly Detection](https://arxiv.org/abs/2505.24201)
- [Exploring Autonomous Agents: Why They Fail](https://arxiv.org/html/2508.13143v1)
- [A Survey on AgentOps](https://arxiv.org/html/2508.02121v1)
- [Multi-Agent Risks from Advanced AI](https://arxiv.org/abs/2502.14143)

</details>

---

## How It Works (Simple Version)

Your AI agent does something. SOMA watches.

**Step 1:** SOMA measures how the agent is behaving right now — is it repeating itself? Making errors? Taking too long? Acting differently from usual?

**Step 2:** SOMA compares that to what "normal" looks like for this agent. If the agent is acting weird, a number called **pressure** goes up. Pressure is a percentage: 0% = fine, 100% = disaster.

**Step 3:** When pressure crosses a threshold, SOMA **does something about it**:
- 25%+ → trims old conversation history
- 50%+ → blocks expensive tools
- 75%+ → stops the agent from making API calls
- 90%+ → full reset
- budget gone → everything stops

**Step 4:** If there are multiple agents connected, pressure from a struggling agent **spreads** to agents that depend on it. Like pain traveling through a nervous system.

**Step 5:** SOMA remembers whether its interventions worked. If stopping an agent at 75% didn't help, next time it waits until 77%. If it helped, it keeps the threshold. It learns.

One line of code to set up: `client = soma.wrap(your_client)`

---

## Quick Start

```python
import anthropic
import soma

# One line. SOMA controls everything.
client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000})

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)

print(client.soma_level)     # Level.HEALTHY
print(client.soma_pressure)  # 0.03
```

If pressure hits QUARANTINE, the next call raises `SomaBlocked`. The agent is stopped.

```python
# Or use the engine directly
engine = soma.quickstart(budget={"tokens": 50000}, agents=["my-agent"])
result = engine.record_action("my-agent", soma.Action(
    tool_name="search", output_text="Found 3 results", token_count=150,
))
```

```bash
# Open the TUI dashboard
soma
```

---

## Escalation

```
  HEALTHY ──── CAUTION ──── DEGRADE ──── QUARANTINE ──── RESTART ──── SAFE_MODE
   < 25%       25-50%       50-75%        75-90%         > 90%       budget = 0
  normal     20% trimmed  50% trimmed   calls blocked   full reset   hard stop
```

Grace period: first 10 actions are penalty-free. Hysteresis: -5pt de-escalation offset prevents oscillation.

---

## Multi-Agent

```python
engine.add_edge("sub_agent", "orchestrator", trust_weight=0.9)
```

Pressure propagates. Trust decays under uncertainty (0.05/step), recovers when stable (0.02/step). Multi-pass propagation — chains converge in one cycle.

---

## Autonomy Modes

Who decides when SOMA intervenes? You choose per-agent or globally via `soma.toml`:

| Mode | What happens |
|:-----|:-------------|
| **`fully_autonomous`** | SOMA decides everything. QUARANTINE, RESTART — no human needed. |
| **`human_in_the_loop`** | Up to DEGRADE — automatic. QUARANTINE and above — waits for `soma approve <agent>`. |
| **`human_on_the_loop`** | Everything automatic, but human sees everything and can override with `soma release <agent>`. |

Configure in `soma.toml`:
```toml
[agents.default]
autonomy = "human_in_the_loop"
```

Or per-agent in code:
```python
from soma.types import AutonomyMode
engine.register_agent("critical-agent", autonomy=AutonomyMode.HUMAN_IN_THE_LOOP)
engine.register_agent("background-worker", autonomy=AutonomyMode.FULLY_AUTONOMOUS)
```

---

## Integrations

| Integration | Status | Where |
|:---|:---|:---|
| **Claude Code** | Built-in | `src/soma/hooks/claude_code.py` |
| **Any Anthropic/OpenAI SDK** | Built-in | `soma.wrap(client)` |
| **Paperclip** | Separate repo | [SOMA-Paperclip](https://github.com/tr00x/SOMA-Paperclip) |
| **OpenClaw** | Planned | Community |
| **LangChain** | Planned | [help wanted](https://github.com/tr00x/SOMA-Core/issues/4) |
| **CrewAI** | Planned | [help wanted](https://github.com/tr00x/SOMA-Core/issues/5) |

<details>
<summary>25+ frameworks that need connectors</summary>

**Top tier:** `soma-openclaw` `soma-langchain` `soma-langgraph` `soma-crewai` `soma-openai-agents` `soma-autogen`

**Major:** `soma-llama-index` `soma-semantic-kernel` `soma-haystack` `soma-dspy` `soma-pydantic-ai` `soma-rasa`

**Orchestrators:** `soma-magentic-one` `soma-smolagents` `soma-camel-ai` `soma-fastagency`

**Platforms:** `soma-agno` `soma-julep` `soma-letta` `soma-composio` `soma-e2b` `soma-lindy` `soma-dify`

</details>

---

## Architecture

```
Action ──→ Vitals ──→ Baseline ──→ Pressure ──→ Graph ──→ Ladder ──→ Control
             │                        │            │                     │
        uncertainty              sigmoid z       trust-weighted      truncate
           drift                70/30 aggregate   propagation       block tools
        error rate              burn rate signal   multi-pass        quarantine
       response time           learning weights    trust decay         restart
```

---

## Documentation

| Doc | Audience |
|:----|:---------|
| **[Getting Started](docs/guide.md)** | Everyone |
| **[Technical Reference](docs/reference.md)** | Engineers |
| **[API Reference](docs/api.md)** | Developers |
| **[Roadmap](ROADMAP.md)** | Contributors |
| **[Changelog](CHANGELOG.md)** | Everyone |
| **[Contributing](CONTRIBUTING.md)** | Contributors |

---

## Status: v0.2.0-beta

| Metric | Value |
|:-------|:------|
| Source files | 37 |
| Tests | 371 passing |
| Core coverage | 100% |
| Documentation | 3,449 lines |
| CLI commands | 6 |

---

## License

MIT. See [LICENSE](LICENSE).

---

<sub>Built by Tim Hunt ([@tr00x](https://github.com/tr00x)) with Claude Code. Monitored by SOMA.</sub>
