<p align="center">
  <img src="docs/screenshots/overview.png" alt="SOMA Dashboard" width="700">
</p>

<h1 align="center">SOMA</h1>

<p align="center">
  <strong>Behavioral monitoring and guidance for AI agents</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/v/soma-ai?color=f43f5e&label=PyPI" alt="PyPI"></a>
  <a href="https://github.com/tr00x/SOMA-Core"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://github.com/tr00x/SOMA-Core/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"></a>
  <a href="https://github.com/tr00x/SOMA-Core"><img src="https://img.shields.io/badge/tests-1438%20passing-brightgreen" alt="Tests"></a>
</p>

<p align="center">
  SOMA observes agent actions in real-time, computes behavioral pressure<br>
  from vital signals, and injects corrective guidance before problems escalate.<br>
  <em>A nervous system for AI agents.</em>
</p>

---

## Why SOMA?

AI agents fail in predictable ways: they retry the same broken command, spiral into error cascades, burn tokens on dead-end approaches, and edit files they never read. Human operators catch these patterns — eventually. SOMA catches them in real-time and tells the agent what to do instead.

**SOMA doesn't just monitor. It treats.**

| Problem | What happens without SOMA | What SOMA does |
|:--------|:--------------------------|:---------------|
| Agent retries failing Bash 5x | Burns tokens, gets same error | Intercepts after 1st failure, suggests `Read` instead |
| Error cascade across tools | 10+ wasted actions before human notices | Breaks the chain at action 3 with specific fix |
| Monotool tunnel vision | Agent stuck in one tool forever | Detects low entropy, prescribes tool switch |
| Cost spiraling with errors | $5 wasted before anyone checks | Detects spend + error correlation, warns immediately |

---

## Install

```
pip install soma-ai
```

Python 3.11+ &mdash; no other dependencies required.

---

## Quick Start

### Option A: Claude Code (zero-code)

```bash
soma install
```

Done. SOMA hooks into every tool call automatically.

### Option B: Any LLM SDK

```python
import soma
import anthropic

client = soma.wrap(anthropic.Anthropic())

# Every API call is now monitored.
# SOMA injects guidance directly into the message stream.
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

---

## How It Works

```
action  ──>  vitals  ──>  pressure  ──>  guidance  ──>  injection
              │                            │               │
        uncertainty              OBSERVE / GUIDE      stdout (hooks)
        drift                    WARN / BLOCK         messages (SDK)
        error_rate
        token_usage
        cost
```

Every action flows through the pipeline. Five vital signals are computed, aggregated into a 0&ndash;1 pressure scalar via EMA baselines + z-score sigmoid, then mapped to a response mode. When pressure is high enough, SOMA injects specific, actionable guidance into the agent's context.

---

## 9 Guidance Patterns

Ranked by priority. Higher patterns override lower ones when multiple match.

| # | Pattern | Detects | Action |
|:-:|:--------|:--------|:-------|
| 1 | **cost_spiral** | Accelerating spend + high error rate | Warn about cost, suggest cheaper approach |
| 2 | **budget** | Budget below 20% remaining | Budget status + conservation tips |
| 3 | **bash_retry** | Bash followed by Bash after failure | "Read the error first" + healing transition |
| 4 | **retry_storm** | 3+ same-tool consecutive failures | Break the loop, suggest alternative tool |
| 5 | **error_cascade** | 3+ errors across different tools | Stop, diagnose root cause |
| 6 | **blind_edit** | Edit/Write without prior Read | "Read before you edit" |
| 7 | **entropy_drop** | Monotool usage (low Shannon entropy) | Diversify approach + panic escalation |
| 8 | **context** | Context window >80% full | Compaction warning |
| 9 | **drift** | Behavioral deviation from baseline | Pattern drift alert |

### Healing Transitions

Data-backed prescriptions from 17K+ production actions:

```
Bash failed  ──>  Read next     (reduces pressure 7%)
Edit failed  ──>  Read first    (reduces pressure 5%)
Write stuck  ──>  Grep/Glob     (reduces pressure 5%)
```

These aren't opinions &mdash; they're measured effect sizes from real agent sessions.

### Cross-Session Memory

Errors are stored with trigram similarity matching. If the agent hit a similar error last session (even with different file paths), SOMA surfaces the fix that worked before.

---

## ROI Dashboard

```bash
soma dashboard
```

Opens a browser dashboard answering one question: **"Is SOMA worth it?"**

<p align="center">
  <img src="docs/screenshots/overview.png" alt="SOMA Dashboard" width="600">
</p>

- **Health Score** &mdash; 0-100 from live vitals
- **Tokens Saved** &mdash; estimated from broken error cascades
- **Cascades Broken** &mdash; error chains stopped early
- **Guidance Precision** &mdash; % of interventions the agent followed
- **Pattern Performance** &mdash; which patterns fire, which get followed

---

## CLI

```bash
soma status          # Current pressure, vitals, budget
soma install         # Set up Claude Code hooks
soma config show     # View active configuration
soma doctor          # Diagnose issues
soma analytics       # Query session analytics
soma replay          # Replay a recorded session
soma dashboard       # Launch web dashboard
```

---

## Configuration

`soma.toml` in your project root. Defaults work out of the box.

```toml
[budget]
tokens = 100000
cost_usd = 5.0

[thresholds]
guide = 0.4
warn = 0.7
block = 0.9
```

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full technical breakdown.

**Key design decisions:**
- Core is platform-agnostic &mdash; no Claude Code imports in `soma.*`
- Hooks never crash &mdash; all exceptions caught and suppressed
- State persistence uses atomic writes (tmp &rarr; fsync &rarr; rename) with file locking
- Guidance cooldowns prevent alert fatigue &mdash; each pattern has an independent cooldown
- Analytics are source-tagged (hook/wrap/unknown) for honest measurement

---

## License

[MIT](LICENSE) &mdash; free forever.
