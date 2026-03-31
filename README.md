<p align="center">
  <img src=".github/soma-banner.gif" alt="SOMA" />
</p>

<h1 align="center">SOMA</h1>

<p align="center">
  <strong>System of Oversight and Monitoring for Agents</strong><br/>
  <em>The nervous system for AI agents.</em><br/>
  Real-time behavioral monitoring. Predictive guidance. Autonomous safety.
</p>

<p align="center">
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/v/soma-ai?style=for-the-badge&color=blue&label=PyPI" alt="PyPI" /></a>&nbsp;
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/pyversions/soma-ai?style=for-the-badge" alt="Python" /></a>&nbsp;
  <a href="https://github.com/tr00x/SOMA-Core/blob/main/LICENSE"><img src="https://img.shields.io/github/license/tr00x/SOMA-Core?style=for-the-badge" alt="License" /></a>&nbsp;
  <a href="#test-results"><img src="https://img.shields.io/badge/tests-735%20passed-brightgreen?style=for-the-badge" alt="Tests" /></a>
</p>

<p align="center">
  <a href="docs/PAPER.md">Research Paper</a> &bull;
  <a href="docs/TECHNICAL.md">Technical Reference</a> &bull;
  <a href="docs/guide.md">User Guide</a> &bull;
  <a href="docs/api.md">API Reference</a> &bull;
  <a href="docs/INTEGRATION-TEST-REPORT.md">Integration Tests</a> &bull;
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

SOMA is a **closed-loop behavioral guidance system**. It watches every action an AI agent takes, computes behavioral pressure from multiple signals, and injects corrective feedback directly into the agent's context — before problems escalate.

| | What | How |
|:--|:-----|:----|
| **Watch** | 6 behavioral signals per action | Uncertainty, drift, error rate, goal coherence, cost, token usage |
| **Classify** | Epistemic vs. aleatoric uncertainty | Output entropy analysis — knowledge gaps escalate, inherent ambiguity dampens |
| **Guide** | Injects specific advice into agent context | `"3 writes without a Read — Read the target file first"` |
| **Warn** | Escalating warnings as pressure rises | Insistent guidance with increasing urgency |
| **Block** | Blocks ONLY destructive operations | `rm -rf`, `git push --force`, `.env` writes — never blocks normal tools |
| **Predict** | Warns ~5 actions before escalation | Trend extrapolation + pattern detection (error streaks, thrashing, blind writes) |
| **Learn** | Adapts thresholds to each agent | Tracks intervention outcomes, tunes over time |
| **Model** | Predicts agent degradation over time | Half-life temporal modeling — warns before reliability drops |

### What SOMA Catches

Real messages injected into the agent's context:

```
[do] Read main.py and config.py before editing — 3 writes without a Read
[do] STOP retrying, try a different approach — 4 consecutive Bash failures
[do] Read the file, plan ALL changes, then make ONE edit — edited app.py 5x
[do] Start writing code — 7 reads, 0 writes in last 10 actions
[predict] escalation in ~5 actions (error_streak) — stop retrying the failing approach
[scope]   scope expanded to tests/, config/ — is this intentional? If not, refocus
[quality] grade=D (2 syntax errors, 3/8 bash commands failed)
[✓] good — read before writing, clean edits
```

The agent reads these and **changes its behavior**. That's the feedback loop.

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

Status line appears immediately:

```
SOMA: #42 [implement] ctx=73% focused
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
<tr>
<td>

**Framework Adapters**

```python
# LangChain
from soma.sdk.langchain import SomaLangChainCallback
chain.invoke(input, config={
    "callbacks": [SomaLangChainCallback(engine, "agent")]
})

# CrewAI
from soma.sdk.crewai import SomaCrewObserver
SomaCrewObserver(engine).attach(crew)

# AutoGen
from soma.sdk.autogen import SomaAutoGenMonitor
SomaAutoGenMonitor(engine).attach(agent)
```

</td>
<td>

**Context Manager** (universal)

```python
import soma

engine = soma.quickstart()

with soma.track(engine, "my-agent", "Bash") as t:
    result = run_something()
    t.set_output(result)
    t.set_tokens(150)

print(t.result.pressure)  # 0.12
print(t.result.mode)      # OBSERVE
```

</td>
</tr>
</table>

---

## Why SOMA?

AI agents loop, drift, edit files blind, retry failing commands endlessly. In multi-agent pipelines, one confused agent cascades failures across the entire system.

**Existing solutions don't close the loop:**

| Approach | Observes behavior? | Tells the agent? | Guides actions? | Adapts? | Multi-agent? |
|----------|:-:|:-:|:-:|:-:|:-:|
| Guardrails (NeMo, Lakera) | Prompt-level only | No | Content filter | No | No |
| Observability (LangSmith, Helicone) | Yes | **No** | **No** | No | Partial |
| Rate limiters | No | No | Token cap | No | No |
| **SOMA** | **6 signals** | **7 pattern warnings** | **4-mode guidance** | **Self-learning** | **Trust graph** |

---

## The Guidance System

SOMA doesn't block tools. It **guides** — progressively increasing urgency as pressure rises, blocking only destructive operations at extreme levels.

```
  0%          25%         50%           75%          budget=0
  │           │           │             │               │
  ▼           ▼           ▼             ▼               ▼
OBSERVE      GUIDE       WARN         BLOCK          SAFE_MODE
metrics    suggestions  insistent   destructive ops   budget gone
+ [✓]      never blocks never blocks only             read-only
```

| Mode | Pressure | What Happens |
|:-----|:---------|:------------|
| **OBSERVE** | 0–24% | Silent monitoring. Status line shows vitals. Positive feedback: `[✓] good — read before writing`. |
| **GUIDE** | 25–49% | Soft suggestions injected into context. `"Read before every Write/Edit."` Never blocks anything. |
| **WARN** | 50–74% | Insistent warnings. `"Pressure is high — slow down and verify."` Still never blocks. |
| **BLOCK** | 75%+ | Blocks ONLY destructive operations: `rm -rf`, `git push --force`, `.env` writes. All other tools work. |

Agents respond to guidance. You don't need to block `Edit` to stop blind writes — you tell the agent to read first, and it does.

---

## The Pipeline

Every action flows through 22 steps in `record_action()`:

```
Action received
  │
  ├─ 1. Ring buffer (last 10 actions)
  ├─ 2. Task complexity estimation (from system prompt)
  ├─ 3. Initial task signature capture (at action #5)
  │
  ├─ 4. Uncertainty = 0.30·retry + 0.25·tool_dev + 0.20·format + 0.25·entropy
  ├─ 5. Drift = 1 - cosine(current_vector, baseline_vector)
  ├─ 6. Time anomaly boost (duration > 2σ from baseline)
  ├─ 7. Resource vitals (error_rate, cost, token_usage)
  ├─ 8. Drift mode classification (INFORMATIONAL vs DIRECTIVE)
  │
  ├─ 9. EMA baseline update (α=0.15, half-life ~4.3 actions)
  ├─ 10. Per-signal pressure via z-score → sigmoid (min_std=0.05)
  ├─ 11. Error rate floor (>30% errors → pressure ≥ error_rate)
  ├─ 12. Retry rate floor (>30% retries → uncertainty ≥ retry_rate)
  │
  ├─ 13. Uncertainty classification (epistemic 1.3x / aleatoric 0.7x)
  ├─ 14. Goal coherence scoring (cosine to initial task vector)
  ├─ 15. Baseline integrity check (vs fingerprint history)
  ├─ 16. Half-life prediction (exponential decay modeling)
  ├─ 17. Burn rate pressure (budget overshoot projection)
  │
  ├─ 18. Learning weight adjustment (adaptive, bounded ±0.10)
  ├─ 19. Upstream vector influence (PressureVector through trust graph)
  ├─ 20. Aggregate = 0.7·weighted_mean + 0.3·max + error-rate floor
  ├─ 21. Graph propagation (damping=0.6, SNR isolation)
  ├─ 22. Grace period (first 10 actions → pressure forced to 0)
  │
  ├─ Trust decay/recovery (0.05/0.02 rates)
  ├─ Reliability metrics (calibration score + verbal-behavioral divergence)
  ├─ Task complexity → threshold reduction (complex tasks escalate faster)
  └─ Mode determination → ActionResult
```

---

## Uncertainty Classification

SOMA distinguishes **why** an agent is uncertain:

| Type | Condition | Meaning | Pressure Effect |
|:-----|:----------|:--------|:---------------|
| **Epistemic** | High uncertainty + low output entropy | Agent lacks knowledge — stuck, repeating same failures | **1.3x** multiplier (escalate faster) |
| **Aleatoric** | High uncertainty + high output entropy | Task is inherently ambiguous — varied attempts expected | **0.7x** dampening (don't over-react) |
| **Unclassified** | Uncertainty ≤ 0.3, or entropy in middle zone | Not enough signal to classify | No modulation |

Thresholds: `min_uncertainty=0.3`, `low_entropy=0.35`, `high_entropy=0.65`. All configurable.

---

## Multi-Agent Systems

### Vector Pressure Propagation

Pressure propagates per-signal through a trust-weighted directed graph. Downstream agents know **why** upstream is struggling, not just how much.

```python
engine = soma.quickstart()
engine.register_agent("planner")
engine.register_agent("coder")
engine.register_agent("reviewer")

engine.add_edge("planner", "coder", trust_weight=0.8)
engine.add_edge("coder", "reviewer", trust_weight=0.6)
```

When the planner's error_rate spikes, a `PressureVector(uncertainty=0.1, drift=0.0, error_rate=0.8, cost=0.0)` propagates to the coder — damped by 0.6, weighted by trust. The coder's effective error_rate pressure rises specifically, enabling targeted guidance.

### Coordination SNR

Signal-to-noise ratio isolation prevents noisy upstream agents from polluting downstream. If upstream pressure isn't backed by real errors (SNR < 0.5), the influence is zeroed out.

### Trust Dynamics

Trust decays 2.5x faster than it recovers:
- **Decay**: `trust -= 0.05 × uncertainty` (when upstream uncertainty > 0.5)
- **Recovery**: `trust += 0.02 × (1 - uncertainty)` (when upstream is stable)

A sub-agent that spirals quickly loses influence. Rebuilding trust requires sustained good behavior.

---

## Policy Engine

Declarative rules that fire alongside built-in guidance:

```yaml
rules:
  - name: high-error-alert
    when:
      error_rate: {">": 0.5}
    do:
      action: warn
      message: "Error rate above 50% — review recent changes"

  - name: combined-stress
    when:
      pressure: {">=": 0.6}
      error_rate: {">=": 0.3}
    do:
      action: block
      message: "Combined stress — pause and reassess"
```

```python
from soma import PolicyEngine

pe = PolicyEngine.from_file("rules.yaml")
actions = pe.evaluate(vitals_snapshot, pressure=0.65)
```

### Guardrail Decorator

```python
from soma import guardrail

@guardrail(engine, "agent-1", threshold=0.8)
def deploy_to_production():
    ...  # Raises SomaBlocked if pressure >= 0.8

@guardrail(engine, "agent-1", threshold=0.8)
async def deploy_async():
    ...  # Works with async too
```

---

## Reliability Metrics

### Calibration Score

Measures how well the agent's verbal confidence matches actual performance:

```
calibration = (1 - error_rate) × (0.5 + 0.5 × hedging_rate)
```

| Hedging | Errors | Score | Meaning |
|:--------|:-------|:------|:--------|
| High | Low | **High** | Cautious and competent |
| High | High | Low | Cautious but still failing |
| Low | Low | Medium | Confident and correct |
| Low | High | **Low** | Overconfident and failing — most dangerous |

### Verbal-Behavioral Divergence

Detects when an agent sounds confident but is actually struggling. Fires when `(pressure - hedging_rate) > 0.4`. When detected, SOMA forces minimum GUIDE mode regardless of pressure level.

---

## Half-Life Temporal Modeling

Models agent reliability decay over session length:

```
P(success at t) = exp(-ln(2) × t / half_life)
```

| Profile | Error Rate | Half-Life | P(success@25) | P(success@50) |
|:--------|:-----------|:----------|:--------------|:--------------|
| Junior agent | 20% | 16 actions | 33.9% | 11.5% |
| Mid-level | 10% | 36 actions | 61.8% | 38.2% |
| Senior | 4% | 67 actions | 77.3% | 59.7% |
| Expert | 1% | 119 actions | 86.4% | 74.7% |

When predicted success rate drops below 50%, SOMA suggests checkpointing and handing off to fresh context.

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

Adaptive step size scales with outcome consistency (1x at 50/50, up to 2x at 100% same outcome). Threshold shifts bounded to ±0.10. Signal weights adjust independently — floored at 0.2 so no signal is ever fully silenced.

---

## The Math

No neural networks. No black boxes. Every formula is documented and tested.

| Formula | What It Does |
|:--------|:------------|
| `P = 0.7·mean(wᵢpᵢ) + 0.3·max(pᵢ)` | Aggregate pressure — catches both gradual and acute failures |
| Error-rate floor: `0.40 + 0.40·(er-0.50)/0.50` | Prevents weighted mean from diluting dominant error signals |
| `z = (x - μ) / max(σ, 0.05)` → `sigmoid(z)` | Signal normalization — adapts to each agent's baseline |
| `μₜ = 0.15·x + 0.85·μₜ₋₁` | EMA baseline — half-life of ~4.3 observations |
| `U = 0.30·retry + 0.25·tool + 0.20·fmt + 0.25·entropy` | Composite uncertainty from 4 behavioral components |
| `D = 1 - cos(v_current, v_baseline)` | Drift via cosine distance on behavior vectors |
| `P(t) = exp(-ln(2)·t/half_life)` | Temporal reliability decay |
| `cal = (1-err)·(0.5 + 0.5·hedge)` | Calibration score — verbal/behavioral alignment |

---

## Test Results

<table>
<tr>
<td>

**735 tests. 0 failures. ~1 second.**

Every formula, threshold, edge case, and integration path is covered.

16 stress scenarios validate behavior under extreme conditions.

**[Integration Test Report](docs/INTEGRATION-TEST-REPORT.md)** — 4 scenarios, 231 actions, full pipeline: healthy session (zero false positives), degrading session (OBSERVE→BLOCK in 16 actions), multi-agent trust graph, and policy engine live evaluation.

</td>
<td>

```
test_engine.py         ✓ Core pipeline (22 steps)
test_pressure.py       ✓ Aggregation, sigmoid, floors
test_vitals.py         ✓ All 6 signals + classification
test_baseline.py       ✓ EMA, cold-start blending
test_guidance.py       ✓ Mode transitions, destructive blocking
test_learning.py       ✓ Threshold adaptation
test_predictor.py      ✓ Trend + pattern prediction
test_halflife.py       ✓ Temporal decay modeling
test_reliability.py    ✓ Calibration + divergence
test_policy.py         ✓ Policy engine + guardrail
test_quality.py        ✓ A-F grading
test_rca.py            ✓ Root cause analysis
test_fingerprint.py    ✓ JSD behavioral signatures
test_graph.py          ✓ Vector propagation + SNR
test_budget.py         ✓ Budget + SAFE_MODE
test_wrap.py           ✓ Anthropic + OpenAI wrapper
test_sdk.py            ✓ LangChain, CrewAI, AutoGen
test_stress.py         ✓ 16 stress scenarios
test_claude_code_*.py  ✓ Full hook integration
test_hooks_*.py        ✓ All 4 lifecycle hooks
```

</td>
</tr>
</table>

---

## Architecture

```
src/soma/                     59 modules, ~10,000 lines
├── engine.py                Core pipeline — 22-step record_action()
├── types.py                 Action, VitalsSnapshot, PressureVector, ResponseMode
├── pressure.py              Aggregate pressure (weighted mean + max + error-rate floor)
├── vitals.py                6 signals + uncertainty classification + task complexity
├── baseline.py              EMA baselines (α=0.15) with cold-start blending
├── guidance.py              4-mode system (OBSERVE/GUIDE/WARN/BLOCK)
├── graph.py                 Trust graph + vector propagation + SNR isolation
├── policy.py                Declarative YAML/TOML rules + @guardrail decorator
├── reliability.py           Calibration score + verbal-behavioral divergence
├── halflife.py              Temporal success rate modeling (exponential decay)
├── learning.py              Self-tuning thresholds + weight adaptation
├── predictor.py             ~5-action-ahead pressure prediction
├── quality.py               A-F code quality grading
├── rca.py                   Root cause analysis (5 detectors, plain English)
├── patterns.py              7 behavioral pattern detectors
├── findings.py              Prioritized findings collector
├── context.py               Workflow awareness + session context
├── fingerprint.py           Agent behavioral signatures (JSD divergence)
├── budget.py                Multi-dimensional budget tracking
├── wrap.py                  Universal client wrapper (Anthropic + OpenAI)
├── persistence.py           Atomic state persistence (fcntl + fsync + rename)
├── recorder.py              Session recording + replay
├── sdk/
│   ├── track.py             soma.track() context manager
│   ├── langchain.py         SomaLangChainCallback
│   ├── crewai.py            SomaCrewObserver
│   └── autogen.py           SomaAutoGenMonitor
├── hooks/                   Claude Code lifecycle hooks
│   ├── pre_tool_use.py      Guidance (allow/block destructive ops)
│   ├── post_tool_use.py     Record action + validate code + feedback
│   ├── notification.py      Inject findings into agent context
│   ├── stop.py              Save state + session summary
│   └── statusline.py        Real-time status bar
└── cli/                     Terminal UI + commands
```

3 runtime dependencies: `rich` + `tomli-w` + `textual`. Everything else is stdlib.

---

## Configuration

`soma.toml` in your project root:

```toml
[hooks]
verbosity = "normal"      # minimal | normal | verbose
validate_python = true    # py_compile after Write/Edit
lint_python = true        # ruff check after Write/Edit
predict = true            # predictive warnings
quality = true            # A-F quality grading

[budget]
tokens = 1_000_000
cost_usd = 50.0

[thresholds]
guide = 0.25
warn = 0.50
block = 0.75

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
goal_coherence = 1.5
cost = 1.0
token_usage = 0.8
```

---

## Requirements

- Python >= 3.11
- Claude Code (for hook integration) — optional
- `ruff` (for lint validation) — optional

**No API keys. No accounts. No telemetry. No network requests.**

## License

MIT — forever.

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
