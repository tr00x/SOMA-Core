<p align="center">
  <img src="docs/screenshots/overview.png" alt="SOMA Dashboard — Overview" width="720">
</p>

<h1 align="center">SOMA</h1>

<p align="center">
  <strong>Behavioral monitoring and real-time guidance for AI agents</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/soma-ai/"><img src="https://img.shields.io/pypi/v/soma-ai?color=f43f5e&label=PyPI" alt="PyPI"></a>
  <a href="https://github.com/tr00x/SOMA-Core"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://github.com/tr00x/SOMA-Core/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"></a>
  <a href="https://github.com/tr00x/SOMA-Core"><img src="https://img.shields.io/badge/tests-1438%20passing-brightgreen" alt="Tests"></a>
</p>

<p align="center">
  SOMA observes agent actions in real-time, computes behavioral pressure<br>
  from five vital signals, and injects corrective guidance before problems<br>
  escalate. Think of it as a nervous system for AI agents.
</p>

---

## Why SOMA?

AI agents fail in predictable ways. They retry the same broken command 10 times. They spiral into error cascades across tools. They burn thousands of tokens on dead-end approaches. They edit files they never read. Human operators catch these patterns — eventually, after the damage is done.

SOMA catches them in real-time and tells the agent exactly what to do instead.

**SOMA doesn't just monitor. It treats.**

| Problem | Without SOMA | With SOMA |
|:--------|:-------------|:----------|
| Agent retries failing Bash 5x | Burns tokens, gets same error every time | Intercepts after 1st failure, suggests `Read` the error output |
| Error cascade across tools | 10+ wasted actions before human notices | Breaks the chain at action 3 with a specific fix |
| Monotool tunnel vision | Agent stuck calling one tool forever | Detects low entropy, prescribes tool diversification |
| Cost spiraling with errors | $5+ wasted before anyone checks | Detects spend + error correlation, warns immediately |
| Editing without reading | Blind edits introduce bugs | Blocks and tells agent to read the file first |
| Context window filling up | Agent runs out of context, loses track | Warns at 80%, suggests compaction strategy |

---

## Install

Pick whichever matches your setup:

```bash
# uv (recommended — isolated tool env, auto-PATH)
uv tool install soma-ai

# pip (if you already have a Python on PATH)
pip install soma-ai

# pipx (same idea as uv tool)
pipx install soma-ai
```

Python 3.11+. No external service dependencies.

Upgrade:

```bash
uv tool upgrade soma-ai     # or: pip install --upgrade soma-ai
```

---

## Two Integration Paths

### Path 1: Claude Code Hooks (zero-code)

```bash
soma install
```

Done. SOMA hooks into every tool call automatically. Guidance appears as part of tool responses — the agent sees it and adjusts behavior without human intervention.

**How it works:** PreToolUse hook writes to stderr (pre-action warnings). PostToolUse hook records the action, evaluates 9 guidance patterns, and writes corrections to stdout where Claude Code appends them to the tool response. Hooks never crash — all exceptions are caught and suppressed.

### Path 2: SDK Wrapper (any LLM client)

```python
import soma
import anthropic

client = soma.wrap(anthropic.Anthropic())

# Every API call is now monitored.
# SOMA injects guidance directly into the message stream
# as system messages when behavioral pressure rises.
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

Works with any client that follows the Anthropic SDK interface. `soma.wrap()` returns a transparent proxy — your code doesn't change. Raises `SomaBlocked` when pressure is critical, `SomaBudgetExhausted` when budget is spent.

---

## The Pipeline

```
action  ──>  vitals  ──>  pressure  ──>  guidance  ──>  injection
               │              │              │              │
         5 signals      EMA baseline    9 patterns      stdout (hooks)
         per action     + z-score       ranked by       messages (SDK)
                        + sigmoid       priority
```

Every agent action flows through this pipeline:

1. **Vitals** — five signals computed per action:
   - **Uncertainty** — entropy of recent action distribution
   - **Drift** — deviation from established behavioral baseline
   - **Error rate** — ratio of failed actions
   - **Token usage** — resource consumption rate
   - **Cost** — monetary spend rate

2. **Pressure** — each signal compared against its EMA baseline (with cold-start blending to avoid false positives in early sessions). Deviation converted to 0–1 via z-score through sigmoid. Aggregate = blended mean + max of individual pressures.

3. **Response Mode** — pressure maps to escalating modes:

   | Range | Mode | Behavior |
   |:------|:-----|:---------|
   | 0.00–0.25 | **OBSERVE** | Silent. Metrics only. |
   | 0.25–0.50 | **GUIDE** | Suggest corrections. |
   | 0.50–0.75 | **WARN** | Alert. Flag destructive operations. |
   | 0.75–1.00 | **BLOCK** | Restrict destructive operations. |

4. **Injection** — corrective guidance reaches the agent context. Hooks write to stdout (appended to tool response). SDK wrapper injects system messages.

---

## 9 Guidance Patterns

Ranked by priority. When multiple patterns match, the highest-priority one fires. Each pattern has an independent cooldown to prevent alert fatigue.

| # | Pattern | What it detects | What it prescribes |
|:-:|:--------|:----------------|:-------------------|
| 1 | **cost_spiral** | Accelerating spend + high error rate | Cost warning + cheaper approach suggestion |
| 2 | **budget** | Budget below 20% remaining | Budget status + conservation strategy |
| 3 | **bash_retry** | Bash immediately after Bash failure | "Read the error output first" + healing transition |
| 4 | **retry_storm** | 3+ consecutive same-tool failures | Break the loop + alternative tool suggestion |
| 5 | **error_cascade** | 3+ consecutive errors across tools | Stop and diagnose root cause |
| 6 | **blind_edit** | Edit/Write without prior Read of file | "Read before you edit" |
| 7 | **entropy_drop** | Monotool usage (low Shannon entropy) | Diversify tools + panic escalation if velocity high |
| 8 | **context** | Context window >80% full | Compaction warning |
| 9 | **drift** | Behavioral drift from initial patterns | Pattern drift alert |

### Healing Transitions

When a pattern fires, SOMA doesn't just say "stop doing that." It tells the agent specifically what to do next, backed by data from 17K+ production actions:

```
Bash failed   →  Read next      (reduces pressure by 7%)
Edit failed   →  Read first     (reduces pressure by 5%)
Write stuck   →  Grep/Glob      (reduces pressure by 5%)
```

These are measured effect sizes, not opinions.

### Panic Detector

The entropy_drop pattern includes a panic escalation mechanism. When SOMA detects both low tool entropy (monotool usage) AND high action velocity (rapid-fire actions), it escalates to critical severity. This catches agents that are stuck in a loop and moving too fast to self-correct.

### Cross-Session Memory

Errors are stored in a `LessonStore` with trigram similarity matching. If the agent hit a similar error in a past session — even with different file paths or slightly different error messages — SOMA surfaces the fix that worked before.

---

## ROI Dashboard

<p align="center">
  <img src="docs/screenshots/roi.png" alt="SOMA ROI Dashboard" width="720">
</p>

```bash
soma dashboard
```

The ROI page answers one question: **"Is SOMA worth it?"**

- **Health Score** — 0-100 composite from live vitals (error rate, uncertainty, drift)
- **Tokens Saved** — estimated from error cascades broken early (each intervention prevents ~3 wasted actions)
- **Cascades Broken** — count of retry_storm, error_cascade, and bash_retry chains stopped
- **Guidance Precision** — percentage of interventions the agent actually followed
- **Pattern Performance** — horizontal bar chart showing which patterns fire most and their follow-through rates

The dashboard also includes an [Overview page](docs/screenshots/overview.png) with live agent cards, pressure gauges, mode distribution, signal averages, resource usage, and recent sessions.

Data comes from `analytics.db` (source-tagged SQLite with every action recorded), circuit files (per-agent followthrough and cooldown state), and `engine_state.json` (current vitals). Auto-refreshes every 5 seconds.

---

## CLI

```bash
soma status          # Current pressure, vitals, and budget
soma install         # Set up Claude Code hooks
soma config show     # View active configuration
soma doctor          # Diagnose configuration and hook health
soma analytics       # Query session analytics
soma replay          # Replay a recorded session
soma dashboard       # Launch web dashboard
```

Three entry points:

| Command | Purpose |
|:--------|:--------|
| `soma` | Main CLI — status, config, install, replay, analytics |
| `soma-hook` | Hook dispatcher for Claude Code (called via CLAUDE_HOOK env var) |
| `soma-statusline` | Status line formatter for terminal status bars |

---

## Configuration

`soma.toml` in your project root. Defaults work out of the box — you don't need this file to get started.

```toml
[budget]
tokens = 100000
cost_usd = 5.0

[thresholds]
guide = 0.4    # pressure above this → suggest corrections
warn = 0.7     # pressure above this → alert, flag destructive ops
block = 0.9    # pressure above this → restrict destructive operations
```

### State Files

SOMA stores state in `~/.soma/`:

| File | Purpose |
|:-----|:--------|
| `engine_state.json` | Engine state (atomic write with file locking) |
| `state.json` | Session state |
| `analytics.db` | SQLite action log (source-tagged, versioned) |
| `circuit_{agent_id}.json` | Per-agent cooldowns, followthrough, signal pressures |

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full technical breakdown.

**Key design decisions:**

- **Platform-agnostic core** — no Claude Code imports in `soma.*`. Hooks are a separate integration layer.
- **Hooks never crash** — all exceptions caught and suppressed. SOMA must never disrupt the agent it monitors.
- **Atomic persistence** — state writes use tmp → fsync → rename with file locking. No partial writes.
- **Independent cooldowns** — each guidance pattern has its own cooldown counter. No alert fatigue.
- **Source-tagged analytics** — every recorded action is tagged with its source (hook/wrap/unknown) for honest measurement.
- **Followthrough tracking** — SOMA measures whether the agent actually followed its guidance, enabling data-driven pattern improvement.

---

## License

[MIT](LICENSE) — free forever, no monetization, no telemetry.
