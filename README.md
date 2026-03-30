<p align="center">
  <img src=".github/soma-banner.gif" alt="SOMA" />
</p>

<h1 align="center">SOMA</h1>

<p align="center">
  <strong>System of Oversight and Monitoring for Agents</strong><br/>
  <em>The nervous system for AI agents.</em><br/>
  Real-time behavioral monitoring. Predictive guidance. Autonomous safety control.
</p>

<p align="center">
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/v/soma-ai?style=for-the-badge&color=blue&label=PyPI" alt="PyPI" /></a>&nbsp;
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/pyversions/soma-ai?style=for-the-badge" alt="Python" /></a>&nbsp;
  <a href="https://github.com/tr00x/SOMA-Core/blob/main/LICENSE"><img src="https://img.shields.io/github/license/tr00x/SOMA-Core?style=for-the-badge" alt="License" /></a>&nbsp;
  <a href="#-test-results"><img src="https://img.shields.io/badge/tests-524%20passed-brightgreen?style=for-the-badge" alt="Tests" /></a>
</p>

<p align="center">
  <a href="docs/claude-code-layer.md">Claude Code Layer</a> &bull;
  <a href="docs/PAPER.md">Research Paper</a> &bull;
  <a href="docs/TECHNICAL.md">Technical Reference</a> &bull;
  <a href="docs/guide.md">User Guide</a> &bull;
  <a href="docs/api.md">API Reference</a> &bull;
  <a href="docs/hooks.md">Hook Reference</a> &bull;
  <a href="ROADMAP.md">Roadmap</a>
</p>

---

> **Your AI agent just edited 5 files without reading any of them. It's retrying the same failing command for the 8th time. It wandered from your auth module into unrelated config files. And you have no idea until it's too late.**
>
> SOMA sees all of this in real-time — and steers the agent back on track.

```bash
pip install soma-ai
```

---

## What SOMA Does

SOMA is not a dashboard. It's not a logger. It's a **closed-loop behavioral guidance system** that watches every action an AI agent takes, detects problems as they develop, and **injects corrective feedback directly into the agent's context**.

### Watch → Guide → Warn → Block (only destructive ops)

| | What | How |
|:--|:-----|:----|
| **Watch** | 5 behavioral signals per action | Uncertainty, drift, error rate, cost, token usage |
| **Guide** | Injects specific advice into agent context | `"3 writes without a Read — Read the target file first"` |
| **Warn** | Escalating warnings as pressure rises | Insistent guidance with increasing urgency |
| **Block** | Blocks ONLY destructive operations | `rm -rf`, `git push --force`, `.env` writes — never blocks normal tools |
| **Learn** | Adapts thresholds to each agent | Tracks intervention outcomes, tunes over time |
| **Predict** | Warns ~5 actions before escalation | Linear trend + pattern detection (error streaks, thrashing, blind writes) |

### What SOMA Catches

These are real messages SOMA injects into the agent's context:

```
[pattern] 3 writes without a Read (main.py, config.py) — Read the target file first
[pattern] 4 consecutive Bash failures — STOP retrying, try a different approach
[pattern] edited app.py 5x — Read the file, plan ALL changes, then make ONE edit
[pattern] 7 reads, 0 writes in last 10 actions — you may be stuck researching
[pattern] 15 mutations with no user check-in — verify you're still on track
[predict] escalation in ~5 actions (error_streak) — stop retrying the failing approach
[scope]   scope expanded to tests/, config/ — is this intentional? If not, refocus
[quality] grade=D (2 syntax errors, 3/8 bash commands failed)
[status]  WARN 60% — pressure is high, slow down and verify your approach
```

The agent reads these and **changes its behavior**. That's the feedback loop — not a human reading logs after the fact.

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
SOMA + observe  3% · #42 · quality A
```

</td>
<td>

**Python SDK** (any agent)

```python
import anthropic, soma

client = soma.wrap(anthropic.Anthropic())
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[...],
)
# Every API call is monitored
```

</td>
</tr>
</table>

---

## Why SOMA?

AI agents are powerful but fragile. They loop. They edit files blind. They retry failing commands endlessly. They drift from the task. And in multi-agent pipelines, one confused agent cascades failures across the entire system.

**Existing solutions don't close the loop:**

| Approach | Observes behavior? | Tells the agent? | Guides actions? | Adapts? | Multi-agent? |
|----------|:-:|:-:|:-:|:-:|:-:|
| Guardrails (NeMo, Lakera) | Prompt-level only | No | Content filter | No | No |
| Observability (LangSmith, Helicone) | Yes | **No** | **No** | No | Partial |
| Rate limiters | No | No | Token cap | No | No |
| **SOMA** | **5 signals** | **7 pattern warnings** | **4-mode guidance** | **Self-learning** | **Trust graph** |

---

## The Guidance System

SOMA doesn't just alert. It **guides** — progressively increasing urgency as pressure rises, but never blocking your normal workflow.

```
  0%          25%         50%           75%          budget=0
  │           │           │             │               │
  ▼           ▼           ▼             ▼               ▼
OBSERVE      GUIDE       WARN         BLOCK          SAFE_MODE
metrics    suggestions  insistent   destructive ops   budget gone
only       never blocks never blocks only             read-only
```

| Mode | Pressure | What SOMA Does |
|:-----|:---------|:------------|
| **OBSERVE** | 0-24% | All tools allowed. Status line shows vitals. Metrics collected silently. |
| **GUIDE** | 25-49% | Soft suggestions injected into context. *"Read before every Write/Edit."* Never blocks anything. |
| **WARN** | 50-74% | Insistent warnings with increasing urgency. *"Pressure is high — slow down and verify."* Still never blocks normal tools. |
| **BLOCK** | 75%+ | Blocks ONLY destructive operations: `rm -rf`, `git push --force`, `.env` file writes. Write, Edit, Bash, Agent — all still work. |
| **SAFE_MODE** | Budget gone | Nothing runs until budget restored. |

The key insight: **agents respond to guidance**. You don't need to block `Edit` to stop blind writes — you tell the agent to read first, and it does. Blocking normal tools just makes the agent less capable without making it safer.

---

## Predictive Intervention

SOMA warns **~5 actions before** problems happen:

| Pattern | Boost | What It Tells the Agent |
|---------|:-----:|------------------------|
| `error_streak` | +15% | *"stop retrying the failing approach, try something different"* |
| `retry_storm` | +12% | *"investigate the root cause instead of retrying"* |
| `blind_writes` | +10% | *"Read the target files before editing"* |
| `thrashing` | +8% | *"plan the complete change first, then make one clean edit"* |

Linear trend extrapolation + pattern detection. Confidence-weighted — only warns when the data justifies it.

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

Adaptive step size. Bounded +/-0.10 max shift. After ~15 interventions, SOMA converges to agent-specific thresholds.

---

## Enterprise: Multi-Agent Systems

Running 5, 10, 50 agents? SOMA was built for this. Here's what it gives you that nothing else does:

### The Problem at Scale

When a planning agent hallucinates requirements, the coding agent implements them faithfully, the testing agent burns cycles on hallucinated features, and the deployment agent ships it. By the time a human notices, you've burned hours and dollars. **No one is watching the agents watch each other.**

### What SOMA Gives Enterprise Teams

<details>
<summary><strong>Multi-Agent Pressure Propagation</strong> — when one agent spirals, downstream agents get warned before they inherit the chaos</summary>

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
- Trust decays 2.5x faster than it recovers — trust is easy to lose, hard to earn
- When your planner spirals, the coder gets warned **before** the bad outputs arrive
- No manual intervention needed — the graph handles it automatically

**Without SOMA:** planner hallucinates → coder implements garbage → reviewer wastes time → you find out an hour later.
**With SOMA:** planner's pressure rises → coder's effective pressure rises → coder gets guided → pipeline self-corrects.

</details>

<details>
<summary><strong>Agent Fingerprinting</strong> — catches behavioral shifts that simple monitoring misses</summary>

Persistent behavioral signature per agent:
- Tool distribution (Read 45%, Edit 30%, Bash 15%, ...)
- Error rate baseline
- Read/write ratios
- Session length norms

**Jensen-Shannon divergence** catches subtle distribution shifts. Your code-review agent suddenly doing 80% Bash? SOMA flags it instantly.

Use cases: prompt injection detection, model regression, unintended behavioral drift after config changes.

</details>

<details>
<summary><strong>Root Cause Analysis</strong> — plain English diagnostics that agents can act on</summary>

```
"stuck in Edit→Bash→Edit loop on config.py (3 cycles)"
"error cascade: 4 consecutive Bash failures (error_rate=40%)"
"blind mutation: 5 writes without reading (foo.py, bar.py)"
"behavioral drift=0.25 driven by uncertainty=0.30"
```

5 detectors ranked by severity. These go directly into the agent's context — the agent self-corrects without human involvement.

</details>

<details>
<summary><strong>Task Phase Detection</strong> — detects when agents wander off-task</summary>

SOMA infers current phase (research → implement → test → debug) and tracks file focus:

```
[scope] scope expanded to tests/, config/ — is this intentional? If not, refocus
[phase] switched from implement to debug — unexpected shift
```

For enterprise: ensures each agent stays in its lane. A coding agent that starts "researching" unrelated files gets flagged.

</details>

<details>
<summary><strong>Budget Management</strong> — per-agent limits with automatic SAFE_MODE</summary>

```python
client = soma.wrap(client, budget={"tokens": 500_000, "cost_usd": 25.00})
```

- Automatic SAFE_MODE when any budget dimension exhausted
- Burn rate projection detects overspend trajectory early
- Per-agent and per-pipeline tracking

A runaway agent hits its budget limit → SAFE_MODE → pipeline continues with other agents.

</details>

### Why This Matters for Enterprise

| Without SOMA | With SOMA |
|:-------------|:----------|
| Agent loops for 30 minutes before anyone notices | Loop detected at iteration 3, agent guided to change approach |
| $500 API bill from a retry storm overnight | Budget SAFE_MODE after $25, agent stops automatically |
| Planner hallucinates → entire pipeline builds garbage | Planner's pressure propagates, coder gets warned before bad outputs arrive |
| Post-mortem: "the agent edited 47 files it shouldn't have" | Real-time: `"scope expanded to unrelated dirs — is this intentional?"` |
| "Which agent caused the cascade failure?" | RCA: `"error cascade: 4 consecutive failures in coder (error_rate=40%)"` |

---

## <img src=".github/claude-logo.png" width="20" /> Claude Code Integration

SOMA is a **native Claude Code extension** — 4 lifecycle hooks, status line, and slash commands.

```bash
uv tool install soma-ai && soma setup-claude
```

### Lifecycle Hooks

| Hook | When | What It Does |
|:-----|:-----|:------------|
| **PreToolUse** | Before tool execution | Blocks destructive operations under high pressure |
| **PostToolUse** | After tool completes | Records action, validates code (py_compile + ruff), computes vitals |
| **UserPromptSubmit** | Before agent reasons | Injects pressure, predictions, RCA, and quality diagnostics |
| **Stop** | Session ends | Saves state, updates fingerprint, prints session summary |

### Status Line (always visible)

```
SOMA + observe  3% · #42 · quality A
```

### Slash Commands

| Command | Description |
|:--------|:-----------|
| `/soma:status` | Live pressure, quality, vitals, budget, tips |
| `/soma:config` | View/change settings in-session |
| `/soma:config mode strict` | Low thresholds, verbose, human-in-loop |
| `/soma:config mode relaxed` | Balanced monitoring (default) |
| `/soma:config mode autonomous` | Minimal monitoring for trusted runs |
| `/soma:control reset` | Reset behavioral baseline |
| `/soma:help` | Full command reference |

### CLI Commands

```bash
soma setup-claude    # Install hooks + slash commands into Claude Code
soma status          # Show current pressure, mode, quality
soma reset           # Reset baselines to defaults
soma start           # Start SOMA monitoring
soma stop            # Stop SOMA monitoring
soma uninstall-claude # Remove SOMA hooks from Claude Code
```

### Operating Modes

| Mode | Block At | Approval Model | Best For |
|:-----|:---------|:--------------|:--------|
| **strict** | 60% | Human-in-the-loop | Production, sensitive codebases |
| **relaxed** | 80% | Human-on-the-loop | Daily development (default) |
| **autonomous** | 95% | No approvals | Trusted CI/CD pipelines |

> *Full details: [Claude Code Layer deep-dive](docs/claude-code-layer.md) · [Hook Reference](docs/hooks.md)*

---

## Dogfooding

SOMA monitors the agent that builds it. This README, the test suite, the banner, every commit — all produced by Claude Code under SOMA's watch.

Real observations from development sessions:
- **Blind writes caught**: SOMA flagged when the agent edited files without reading them first — the agent stopped and read the file
- **Scope drift detected**: Working on docs, the agent started touching CLI code — SOMA flagged it, agent refocused
- **Bash loops prevented**: Agent retried a failing command — SOMA warned at attempt 2, the agent changed approach
- **Zero false positives**: OBSERVE mode maintained throughout normal work, no unnecessary warnings

The feedback loop works. The agent is measurably more careful when SOMA is watching.

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

[thresholds]              # pressure levels for mode transitions
guide = 0.25
warn = 0.50
block = 0.75

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
| `z = (x - μ) / max(σ, 0.05)` → `sigmoid(z)` | Signal normalization — adapts to each agent's baseline |
| `μₜ = 0.15·x + 0.85·μₜ₋₁` | EMA baseline — half-life of ~4.3 observations |
| `P̂ = P + slope·h + boost` | Prediction — linear trend + pattern boosts |
| `Q = (w·Qw + b·Qb) · penalty` | Quality — write/bash success with syntax penalty |

> *Complete derivations in [Technical Reference](docs/TECHNICAL.md). Theoretical foundations in [Research Paper](docs/PAPER.md).*

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
test_guidance.py       ✓ Mode transitions, blocking
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
├── guidance.py        4-mode guidance system (OBSERVE → GUIDE → WARN → BLOCK)
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

3 dependencies: `rich` + `tomli-w` + `textual`. Everything else is stdlib.

---

## Documentation

| | Document | What's Inside |
|:--|:---------|:-------------|
| :mortar_board: | **[Research Paper](docs/PAPER.md)** | Problem statement, biological/control-theory inspiration, formal models, evaluation, related work, 8 references |
| :triangular_ruler: | **[Technical Reference](docs/TECHNICAL.md)** | Every formula with source file:line references, all constants, formal properties (boundedness, monotonicity, convergence) |
| :book: | **[User Guide](docs/guide.md)** | Setup, pressure model explained, baselines, learning, configuration, CLI commands, file paths |
| :wrench: | **[API Reference](docs/api.md)** | Every class and method with code examples — SOMAEngine, Action, Mode, Budget, Predictor, Quality, Fingerprint |
| :robot: | **[Claude Code Layer](docs/claude-code-layer.md)** | How SOMA integrates with Claude Code — what the agent sees, 7 patterns, code validation, operating modes, Claude's own perspective |
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
  <strong>Stop watching your agents fail. Start guiding them.</strong>
</p>

<p align="center">
  <code>pip install soma-ai</code>
</p>

<p align="center">
  <sub>Built for <a href="https://claude.ai/code">Claude Code</a> by <a href="https://github.com/tr00x">tr00x</a></sub>
</p>
