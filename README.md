<p align="center">
  <img src=".github/soma-banner.gif" alt="SOMA" />
</p>

<h1 align="center">SOMA</h1>

<p align="center">
  <strong>System of Oversight and Monitoring for Agents</strong><br/>
  <em>The nervous system for AI agents.</em><br/>
  Real-time behavioral monitoring. Predictive intervention. Autonomous safety control.
</p>

<p align="center">
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/v/soma-ai?style=for-the-badge&color=blue&label=PyPI" alt="PyPI" /></a>&nbsp;
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/pyversions/soma-ai?style=for-the-badge" alt="Python" /></a>&nbsp;
  <a href="https://github.com/tr00x/SOMA-Core/blob/main/LICENSE"><img src="https://img.shields.io/github/license/tr00x/SOMA-Core?style=for-the-badge" alt="License" /></a>&nbsp;
  <a href="#-test-results"><img src="https://img.shields.io/badge/tests-524%20passed-brightgreen?style=for-the-badge" alt="Tests" /></a>
</p>

<p align="center">
  <a href="docs/PAPER.md">Research Paper</a> &bull;
  <a href="docs/TECHNICAL.md">Technical Reference</a> &bull;
  <a href="docs/guide.md">User Guide</a> &bull;
  <a href="docs/api.md">API Reference</a> &bull;
  <a href="docs/hooks.md">Hook Reference</a> &bull;
  <a href="ROADMAP.md">Roadmap</a>
</p>

---

> **Your AI agent just burned $200 in a retry loop. Again.**
>
> SOMA stops that. One line of code. Zero config. Sub-millisecond overhead.

```bash
pip install soma-ai
```

---

## Why SOMA?

AI agents are powerful but fragile. They loop. They hallucinate. They edit files blind. They blow budgets. They retry failing commands 15 times. And in multi-agent pipelines, one confused agent can cascade failures across the entire system.

**Existing solutions don't cut it:**

| Approach | Observes behavior? | Intervenes? | Adapts? | Multi-agent? |
|----------|:-:|:-:|:-:|:-:|
| Guardrails (NeMo, Lakera) | Prompt-level only | Content filter | No | No |
| Observability (LangSmith, Helicone) | Yes | **No** | No | Partial |
| Rate limiters | No | Token cap | No | No |
| **SOMA** | **5 behavioral signals** | **6-level escalation** | **Self-learning** | **Trust graph** |

---

## Quick Start

<table>
<tr>
<td>

**Claude Code** (zero code)

```bash
uv tool install soma-ai
soma setup-claude
```

That's it. Status line appears immediately:

```
SOMA + healthy  2% · #42 · quality A
```

</td>
<td>

**Python SDK** (any agent)

```python
import anthropic, soma

client = soma.wrap(
    anthropic.Anthropic(),
    budget={"tokens": 100_000}
)
# Every API call monitored
```

</td>
</tr>
</table>

---

## How It Works

<table>
<tr><td>

```
    Agent Action
         |
         v
  ┌──────────────┐
  │ COMPUTE       │  5 behavioral signals:
  │ VITALS        │  uncertainty · drift · error · cost · tokens
  └──────┬───────┘
         v
  ┌──────────────┐
  │ NORMALIZE     │  z-score → sigmoid clamp → [0, 1]
  └──────┬───────┘
         v
  ┌──────────────┐
  │ AGGREGATE     │  0.7 × weighted_mean + 0.3 × max
  │ PRESSURE      │  → single number: 0-100%
  └──────┬───────┘
         v
  ┌──────────────┐
  │ ESCALATION    │  HEALTHY → CAUTION → DEGRADE →
  │ LADDER        │  QUARANTINE → RESTART → SAFE_MODE
  └──────┬───────┘
         v
  ┌──────────────┐
  │ PREDICT       │  ~5 actions ahead
  │ + LEARN       │  adapt thresholds over time
  └──────────────┘
```

</td><td>

### The 5 Behavioral Signals

| Signal | Detects |
|--------|---------|
| **Uncertainty** | Retries, tool chaos, output entropy |
| **Drift** | Deviation from baseline patterns |
| **Error rate** | Broken code, failed commands |
| **Cost** | Dollar burn rate vs budget |
| **Token usage** | Token consumption vs limit |

Each signal is z-score normalized against the agent's **own baseline** and sigmoid-clamped to [0,1].

No magic numbers. Everything adapts to how *your* agent behaves.

> *Full math in [Technical Reference](docs/TECHNICAL.md)*

</td></tr>
</table>

---

## The Escalation Ladder

SOMA doesn't just alert. It **acts** — progressively restricting capabilities as pressure rises.

```
  0%          25%         50%           75%          90%      budget=0
  │           │           │             │            │           │
  ▼           ▼           ▼             ▼            ▼           ▼
HEALTHY    CAUTION     DEGRADE     QUARANTINE    RESTART    SAFE_MODE
all ok     read first  bash blocked  read-only    full stop   budget gone
```

| Level | Pressure | Intervention |
|:------|:---------|:------------|
| **HEALTHY** | 0-24% | All tools allowed |
| **CAUTION** | 25%+ | Writes require prior Read (prevents blind edits) |
| **DEGRADE** | 50%+ | Bash and Agent tools blocked |
| **QUARANTINE** | 75%+ | Read-only mode |
| **RESTART** | 90%+ | Full stop |
| **SAFE_MODE** | Budget gone | Nothing runs until budget restored |

**Hysteresis** prevents level thrashing (different thresholds for escalation vs de-escalation). **Multi-level jump** up for acute failures, **one-level-at-a-time** down for verified recovery.

---

## Predictive Intervention

SOMA warns you **~5 actions before** problems happen:

| Pattern | Boost | Trigger |
|---------|:-----:|---------|
| `error_streak` | +15% | 3+ consecutive failures |
| `retry_storm` | +12% | >40% error rate in window |
| `blind_writes` | +10% | 2+ writes without reading first |
| `thrashing` | +8% | Same file edited 3+ times |

Linear trend extrapolation + pattern detection. Confidence-weighted. Only warns when R² fit + sample size justify it.

---

## Self-Learning

Static thresholds produce false positives. SOMA eliminates them:

```
Escalation → wait 5 actions → pressure dropped?
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
               YES (helped)             NO (false positive)
            lower threshold             raise threshold
           (catch earlier)             (fewer false alarms)
```

Adaptive step size: more consistent outcomes = faster convergence. Bounds prevent runaway: ±0.10 max shift per transition.

> *After ~15 interventions, SOMA converges to agent-specific thresholds with near-zero false positive rate.*

---

## Enterprise: Multi-Agent Systems

<details>
<summary><strong>Multi-Agent Pressure Propagation</strong> — trust-weighted graph with decay/recovery</summary>

```python
from soma import SOMAEngine

engine = SOMAEngine()
engine.register_agent("planner")
engine.register_agent("coder")
engine.register_agent("reviewer")

# Trust graph: problems propagate downstream
engine.graph.add_edge("planner", "coder", trust=0.8)
engine.graph.add_edge("coder", "reviewer", trust=0.6)
```

- Pressure flows along trust-weighted edges (damping: 0.60)
- Trust decays 2.5x faster than it recovers (asymmetric dynamics)
- Convergence in ≤3 iterations

When your planner spirals, the coder gets restricted **before** the bad outputs arrive.

</details>

<details>
<summary><strong>Budget Management</strong> — multi-dimensional with automatic SAFE_MODE</summary>

```python
client = soma.wrap(client, budget={
    "tokens": 500_000,
    "cost_usd": 25.00,
})
```

- Automatic SAFE_MODE when any budget dimension exhausted
- Burn rate projection detects overspend trajectory early
- Per-agent and per-pipeline tracking

</details>

<details>
<summary><strong>Agent Fingerprinting</strong> — Jensen-Shannon divergence for behavioral shift detection</summary>

Persistent behavioral signature per agent:
- Tool distribution (Read 45%, Edit 30%, Bash 15%, ...)
- Error rate baseline
- Read/write ratios
- Session length norms

**JSD divergence** catches subtle distribution shifts that threshold checks miss. Requires 10+ sessions before alerting (no false alarms from insufficient data).

</details>

<details>
<summary><strong>Root Cause Analysis</strong> — plain English diagnostics, not error codes</summary>

```
"stuck in Edit→Bash→Edit loop on config.py (3 cycles)"
"error cascade: 4 consecutive Bash failures (error_rate=40%)"
"blind mutation: 5 writes without reading (foo.py, bar.py)"
"behavioral drift=0.25 driven by uncertainty=0.30"
```

5 detectors ranked by severity. The agent receives these diagnostics and can self-correct.

</details>

<details>
<summary><strong>Task Phase Detection</strong> — scope drift detection with directory tracking</summary>

SOMA infers the current phase (research → implement → test → debug) and tracks file focus:

```
[scope] scope expanded to tests/, config/    ← wandered off-task
[phase] switched from implement to debug     ← unexpected shift
```

Drift > 30% triggers scope warning in agent context.

</details>

---

## <img src=".github/claude-logo.png" width="20" /> Claude Code Integration

SOMA is a **native Claude Code extension** — 4 lifecycle hooks, status line, and slash commands.

```bash
uv tool install soma-ai && soma setup-claude
```

### Lifecycle Hooks

| Hook | When | What It Does |
|:-----|:-----|:------------|
| **PreToolUse** | Before tool execution | Blocks dangerous tools under pressure |
| **PostToolUse** | After tool completes | Records action, validates code (py_compile + ruff), computes vitals |
| **UserPromptSubmit** | Before agent reasons | Injects pressure, predictions, RCA, and quality diagnostics |
| **Stop** | Session ends | Saves state, updates fingerprint, prints session summary |

### Status Line (always visible)

```
SOMA + healthy  2% · #42 · quality A
```

### Slash Commands

| Command | Description |
|:--------|:-----------|
| `/soma:status` | Live pressure, quality, vitals, budget, tips |
| `/soma:config` | View/change settings in-session |
| `/soma:config mode strict` | Low thresholds, verbose, human-in-loop |
| `/soma:config mode relaxed` | Balanced monitoring (default) |
| `/soma:config mode autonomous` | Minimal monitoring for trusted runs |
| `/soma:control quarantine` | Force quarantine immediately |
| `/soma:control release` | Release from quarantine |
| `/soma:control reset` | Reset behavioral baseline |
| `/soma:help` | Full command reference |

### Operating Modes

| Mode | Quarantine At | Approval Model | Best For |
|:-----|:-------------|:--------------|:--------|
| **strict** | 60% | Human-in-the-loop | Production, sensitive codebases |
| **relaxed** | 80% | Human-on-the-loop | Daily development (default) |
| **autonomous** | 95% | No approvals | Trusted CI/CD pipelines |

> *Full hook documentation in [Hook Reference](docs/hooks.md)*

---

## Configuration

`soma.toml` in your project root — everything is tunable:

```toml
[hooks]
verbosity = "normal"      # minimal | normal | verbose
validate_python = true    # syntax check written Python files
lint_python = true        # ruff check after writes
predict = true            # predictive warnings
quality = true            # A-F quality grading

[budget]
tokens = 1_000_000
cost_usd = 50.0

[thresholds]              # pressure levels for escalation
caution = 0.25
degrade = 0.50
quarantine = 0.75

[weights]                 # signal importance in pressure
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
cost = 1.0
token_usage = 0.8
```

---

## The Math

No neural networks. No black boxes. Every formula is documented and tested.

| Formula | What It Does |
|:--------|:------------|
| `P = 0.7·mean(wᵢpᵢ) + 0.3·max(pᵢ)` | Aggregate pressure — catches both gradual and acute failures |
| `z = (x - μ) / max(σ, 0.1)` → `sigmoid(z)` | Signal normalization — adapts to each agent's baseline |
| `μₜ = 0.15·x + 0.85·μₜ₋₁` | EMA baseline — half-life of ~4.3 observations |
| `P̂ = P + slope·h + boost` | Prediction — linear trend + pattern boosts |
| `Q = (w·Qw + b·Qb) · penalty` | Quality — write/bash success with syntax penalty |

> *Complete derivations in [Technical Reference](docs/TECHNICAL.md). Theoretical foundations in [Research Paper](docs/PAPER.md).*

---

## Terminal Dashboard

```bash
soma              # Full TUI dashboard (4 tabs: status, agents, config, replay)
soma status       # Quick text summary
soma agents       # List monitored agents
soma mode         # Show/switch operating mode
soma export       # Export session to JSON
soma replay       # Replay recorded sessions
```

---

## Test Results

<table>
<tr>
<td>

**524 tests. 0 failures. 0.70 seconds.**

Every formula, threshold, edge case, and integration path is covered.

16 stress scenarios validate behavior under extreme conditions: rapid action sequences, budget exhaustion, pressure spikes, loop detection, and multi-agent propagation.

72KB of Claude Code integration tests simulate complete hook workflows end-to-end.

</td>
<td>

```
test_engine.py         ✓ Core pipeline
test_pressure.py       ✓ Z-score, sigmoid, aggregation
test_vitals.py         ✓ All 5 signals
test_baseline.py       ✓ EMA, cold-start
test_ladder.py         ✓ Escalation, hysteresis
test_learning.py       ✓ Threshold adaptation
test_predictor.py      ✓ Trend, patterns
test_quality.py        ✓ A-F grading
test_rca.py            ✓ Root cause analysis
test_fingerprint.py    ✓ JSD, divergence
test_graph.py          ✓ Multi-agent propagation
test_budget.py         ✓ Budget, SAFE_MODE
test_wrap.py           ✓ Anthropic + OpenAI
test_stress.py         ✓ 16 stress scenarios
test_claude_code_*.py  ✓ Full integration
test_hooks_*.py        ✓ All 4 hooks
test_cli.py            ✓ CLI + TUI
test_modes.py          ✓ Operating modes
```

</td>
</tr>
</table>

---

## Architecture

```
soma/
├── engine.py          Core pipeline — the brain
├── pressure.py        Pressure aggregation (weighted mean + max)
├── vitals.py          5 behavioral signal computations
├── baseline.py        EMA baselines with cold-start blending
├── ladder.py          6-level escalation with hysteresis
├── learning.py        Self-tuning threshold adaptation
├── predictor.py       5-action-ahead pressure prediction
├── quality.py         A-F code quality grading
├── rca.py             Root cause analysis (plain English)
├── task_tracker.py    Task phase and scope drift detection
├── fingerprint.py     Agent behavioral signatures (JSD)
├── graph.py           Multi-agent pressure propagation
├── budget.py          Multi-dimensional budget tracking
├── wrap.py            Universal client wrapper
├── hooks/             Claude Code lifecycle hooks
└── cli/               Terminal UI and commands
```

2 dependencies: `rich` (terminal formatting) + `tomli-w` (config). Everything else is stdlib.

---

## Documentation

| | Document | What's Inside |
|:--|:---------|:-------------|
| :mortar_board: | **[Research Paper](docs/PAPER.md)** | Problem statement, biological/control-theory inspiration, formal models, evaluation, related work, 8 references |
| :triangular_ruler: | **[Technical Reference](docs/TECHNICAL.md)** | Every formula with source file:line references, all constants, formal properties (boundedness, monotonicity, convergence) |
| :book: | **[User Guide](docs/guide.md)** | Setup, pressure model explained, baselines, learning, configuration, CLI commands, file paths |
| :wrench: | **[API Reference](docs/api.md)** | Every class and method with code examples — SOMAEngine, Action, Level, Budget, Predictor, Quality, Fingerprint |
| :electric_plug: | **[Hook Reference](docs/hooks.md)** | All 4 Claude Code hooks — input/output format, configurable features, silence conditions, examples |
| :world_map: | **[Roadmap](ROADMAP.md)** | 6 milestones through 2027 — Foundation (done), Agent Intelligence (done), Real-World Ready, Ecosystem, Intelligence, Platform |

---

## Requirements

- Python >= 3.11
- Claude Code (for hook integration) — optional
- `ruff` (for lint validation) — optional

**No API keys. No accounts. No telemetry. No network requests.**

## License

MIT

---

<p align="center">
  <strong>Stop watching your agents fail. Start governing them.</strong>
</p>

<p align="center">
  <code>pip install soma-ai</code>
</p>

<p align="center">
  <sub>Built for <a href="https://claude.ai/code">Claude Code</a> by <a href="https://github.com/tr00x">tr00x</a></sub>
</p>
