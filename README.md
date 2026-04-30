<div align="center">

<img src=".github/soma-banner.gif" alt="SOMA — behavioural monitoring for autonomous agents" width="100%" />

# SOMA

### *A nervous system for autonomous LLM agents.*

**Most AI-safety tooling grades the transcript *after* the agent finishes.<br>
SOMA changes the transcript *while* the agent is writing it.**

<br>

[![PyPI](https://img.shields.io/pypi/v/soma-ai.svg?style=for-the-badge&label=pypi&color=ff0080&labelColor=0a0a0a)](https://pypi.org/project/soma-ai/)
[![Python](https://img.shields.io/pypi/pyversions/soma-ai.svg?style=for-the-badge&color=ff0080&labelColor=0a0a0a)](https://pypi.org/project/soma-ai/)
[![License](https://img.shields.io/badge/license-MIT-ff0080.svg?style=for-the-badge&labelColor=0a0a0a)](LICENSE)
[![CalVer](https://img.shields.io/badge/calver-2026.6.2-ff0080.svg?style=for-the-badge&labelColor=0a0a0a)](#)

<br>

```
 18,106  ─  agent actions
    505  ─  sessions
    313  ─  guidance firings
     85  ─  A/B outcomes
```

<sub>All numbers from continuous production use on my own Claude Code workflow.</sub>

</div>

---

I built SOMA to monitor LLM agents the way `htop` monitors processes — continuous, in-process, with a feedback loop. Five vital signs derived from the action stream collapse into a single pressure scalar; once that scalar crosses a threshold, corrective guidance is injected straight into the agent's next-turn context.

```python
import soma, anthropic

client = soma.wrap(anthropic.Anthropic())
client.messages.create(...)   # SOMA observes, scores, intervenes.
```

> [!TIP]
> Already on Claude Code? `pip install soma-ai && soma init` wires the hooks into `.claude/settings.json`. Zero code changes.

<br>

<p align="center">
  <img src="docs/screenshots/overview.png" alt="SOMA dashboard — live agent vitals, pressure timeline, guidance feed" width="100%" />
  <br>
  <sub><i>The live dashboard. Open with <code>soma dashboard</code>.</i></sub>
</p>

---

## How it works

### Five vital signs → one pressure

Each action updates a per-signal exponential moving average per agent. Cold-start blending keeps the first few actions in a session from triggering false positives.

| Signal         | What it captures                                |
|----------------|-------------------------------------------------|
| `uncertainty`  | hedge density and semantic hesitation in output |
| `drift`        | divergence from the session intent vector       |
| `error_rate`   | windowed tool-call failure ratio                |
| `token_usage`  | tokens-per-action velocity                      |
| `cost`         | dollars-per-action velocity                     |

Each raw signal is normalized into a per-signal pressure through a **shifted, clamped sigmoid**:

```math
\text{signal\_pressure} = \sigma_{clamp}\!\left(\frac{\text{current} - \text{baseline}}{\sigma}\right)
```

```
σ_clamp(x) = 0                  if x ≤ 0
           = 1                  if x > 6
           = 1 / (1 + e^(3−x))  otherwise
```

> The shift by 3 is intentional — a raw z-score around zero shouldn't register pressure. A signal has to be *visibly* above baseline before it counts. `signal_pressure < 0.5` until `z > 3`.

The five aggregate into a single scalar:

```math
\text{pressure} = 0.7 \cdot \overline{\text{signals}} + 0.3 \cdot \max(\text{signals})
```

> Pure mean lets one screaming signal hide behind four calm ones. Pure max over-reacts to a single noisy sensor. The 70/30 blend was tuned on early sessions; the constant should eventually be learned per-agent.

`pressure ∈ [0, 1]` maps to a response mode:

| Range          | Mode      | Behaviour                                     |
|:---------------|:----------|:----------------------------------------------|
| `0.00 – 0.25`  | `OBSERVE` | Silent. Metrics only.                         |
| `0.25 – 0.50`  | `GUIDE`   | Soft course-correction in the agent context.  |
| `0.50 – 0.75`  | `WARN`    | Insistent, blocking-adjacent.                 |
| `0.75 – 1.00`  | `BLOCK`   | Refuse destructive operations.                |

### Pipeline

```mermaid
flowchart LR
    A([Agent action]) --> V[Vitals]
    V --> S[Per-signal<br/>pressures]
    S --> P[Aggregate<br/>pressure]
    P --> M{Response<br/>mode}
    M -->|GUIDE / WARN| G[Pattern engine]
    G --> H[Healing<br/>suggestion]
    H --> I[Context<br/>injection]
    I --> A
    M -->|BLOCK| X([Refuse<br/>destructive op])

    classDef sig fill:#1a1a1a,stroke:#ff0080,color:#fff
    classDef act fill:#0a0a0a,stroke:#fff,color:#fff
    class V,S,P,G,H,I sig
    class A,X,M act
```

---

## Guidance — experimental, in active testing

> [!IMPORTANT]
> The vitals pipeline is **stable**. The intervention layer on top of it is **a live experiment**.
> Patterns are instrumented end-to-end so I can tell whether a message *changed* agent behaviour or only *correlated* with a change that was already happening.

Six patterns ship today:

| Pattern              |   n  | Status                                           |
|:---------------------|-----:|:-------------------------------------------------|
| `bash_retry`         |   57 | **Primary signal** — 91 % helped, ~46 % drop     |
| `budget`             |   56 | In active iteration                              |
| `blind_edit`         |   55 | In active iteration                              |
| `bash_error_streak`  |    2 | New — sampling                                   |
| `cost_spiral`        |    1 | New — sampling                                   |
| `error_cascade`      |    0 | Active — awaiting first firing                   |

`bash_retry` is the strongest pattern in production: when the agent enters a retry storm, surfacing the loop back into its own context breaks it out 91 % of the time. Other patterns run with full instrumentation while their messages are iterated on outcome data.

<details>
<summary><b>How outcomes are measured</b></summary>

<br>

Every active pattern runs **block-randomized A/B**: per-firing assignment to treatment vs. control, randomization keyed on `firing_id` (not `session_id`) so there is no intra-session bleed. Outcomes are recorded at three horizons (`h=1`, `h=5`, `h=10` actions ahead) into a SQLite `ab_outcomes` table.

Release gate per pattern:

```
n ≥ 30 paired observations,
two-tailed test, α = 0.05
```

The methodology is the durable part. Patterns get refined, replaced, or retired as data comes in. The system is built so I can swap a message tomorrow and trust the next thirty firings to tell me whether it worked.

</details>

<br>

<table>
<tr>
<td width="50%"><img src="docs/screenshots/agent-detail.png" alt="Agent detail view" /><br><sub align="center"><i>Per-agent detail — vital signs, baselines, pressure history.</i></sub></td>
<td width="50%"><img src="docs/screenshots/roi.png" alt="Pattern ROI dashboard" /><br><sub align="center"><i>Pattern ROI — helped %, pressure delta, sample size per pattern.</i></sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/screenshots/sessions.png" alt="Sessions view" /><br><sub align="center"><i>Sessions — per-session pressure timeline and guidance log.</i></sub></td>
<td width="50%"><img src="docs/screenshots/settings.png" alt="Settings view" /><br><sub align="center"><i>Settings — thresholds, mode boundaries, pattern toggles.</i></sub></td>
</tr>
</table>

---

## Install

```bash
pip install soma-ai
```

<sub>Python 3.11 / 3.12 / 3.13. No external services required. Optional OpenTelemetry export via `pip install soma-ai[otel]`.</sub>

### Two integration paths

<table>
<tr>
<td valign="top" width="50%">

**Hooks** — zero code, for Claude Code

```bash
soma init      # write hooks into
               # .claude/settings.json

soma status    # live vitals in
               # the terminal
```

</td>
<td valign="top" width="50%">

**SDK wrapper** — any LLM client

```python
import soma, anthropic

client = soma.wrap(
    anthropic.Anthropic(),
    agent_id="research",
)
client.messages.create(...)
```

</td>
</tr>
</table>

`soma status` in the terminal:

```
SOMA v2026.6.2 — 3 agents monitored

  cc-34596      OBSERVE       p=0.14  u=0.23  d=0.03  e=0.01   #2
  cc-1384       OBSERVE       p=0.16  u=0.23  d=0.05  e=0.01   #2
  cc-63890      OBSERVE       p=0.00  u=0.05  d=0.05  e=0.01   #0

  Budget: 55% (tokens: 552/999)
```

---

## What's next

1. **Drive three more patterns to gate** (n ≥ 30 paired). Roughly three weeks of session data at the current rate.
2. **Per-agent calibration of global constants** — the 0.7 / 0.3 mean–max blend, the sigmoid shift, and the mode boundaries should each derive from the agent's own history.
3. **Forecast `cost_spiral`.** Right now the pattern fires *after* the spike. The trajectory should predict it.
4. **A learned aggregator.** Replace the hand-tuned blend with a small online model that adjusts signal weights to per-agent error feedback.

---

<div align="center">

<sub>Built by <a href="https://github.com/tr00x">@tr00x</a> · MIT · CalVer</sub>

</div>
