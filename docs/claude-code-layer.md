# SOMA + Claude Code: The Behavioral Safety Layer

SOMA integrates with Claude Code as a **closed-loop behavioral control system**. It's not a plugin you install and forget — it's a layer that fundamentally changes how the agent operates by giving it real-time awareness of its own behavior.

---

## What the Layer Does

Every action Claude Code takes passes through SOMA:

```
You type a prompt
    │
    ▼
UserPromptSubmit ──► SOMA injects behavioral feedback into agent context
    │                 (pressure, patterns, predictions, quality, scope)
    ▼
Agent reasons (with SOMA's feedback visible)
    │
    ▼
PreToolUse ────────► SOMA checks: is this tool allowed at current pressure?
    │                 (blocks Write without Read, blocks Bash at DEGRADE+)
    ▼
Tool executes
    │
    ▼
PostToolUse ───────► SOMA records action, validates code, computes new pressure
    │                 (py_compile, ruff, error detection, prediction update)
    ▼
Next prompt ───────► cycle repeats
    │
    ...
    ▼
Stop ──────────────► SOMA saves state, updates fingerprint, session summary
```

### The 4 Hooks

| Hook | When | What It Does |
|:-----|:-----|:------------|
| **UserPromptSubmit** | Before agent starts thinking | Injects: pressure %, signal values, pattern warnings, predictions, quality grade, scope drift, RCA diagnostics |
| **PreToolUse** | Before every tool call | Checks escalation level. Blocks dangerous tools if pressure is high. Never blocks Read/Grep/Glob. |
| **PostToolUse** | After every tool call | Records the action. Validates written code (syntax + lint). Updates pressure, predictions, quality. Reports level changes. |
| **Stop** | Session ends | Saves engine state for next session. Updates agent fingerprint. Cleans session files. Prints summary. |

---

## What the Agent Actually Sees

This is the real output SOMA injects into the agent's context before every reasoning step.

### Normal operation (HEALTHY, low pressure)

```
SOMA: p=9% #42 [u=0.03 d=0.12 e=0.00]
```

One line. Pressure, action count, vitals. The agent knows it's being watched but nothing is wrong.

### When patterns emerge

```
SOMA: p=9% #67 [u=0.05 d=0.25 e=0.00]
[pattern] 3 writes without a Read (main.py, config.py) — Read the target file first to understand current state
[scope] scope expanded to tests/, config/ — is this intentional? If not, refocus on the original task
```

The agent sees specific, actionable instructions. Not "pressure is elevated" — but "you wrote 3 files without reading them, here's what to do."

### When things go wrong

```
SOMA: p=35% #89 [u=0.15 d=0.40 e=0.20]
[pattern] 4 consecutive Bash failures — STOP retrying, try a different approach
[predict] escalation in ~5 actions (error_streak) — stop retrying the failing approach
[quality] grade=D (2 syntax errors, 3/8 bash commands failed)
```

The agent receives three separate warnings. Pressure is rising. If it doesn't change behavior, DEGRADE is ~5 actions away.

### At elevated levels

```
SOMA: p=55% #112 [u=0.30 d=0.45 e=0.35]
[status] DEGRADED — Bash/Agent blocked. Focus on reading and planning. Fix the root cause before acting
[why] error cascade: 5 consecutive Bash failures (error_rate=35%)
[quality] grade=F (4 syntax errors, 5/10 bash commands failed)
```

Bash is now blocked. The agent can only Read, Grep, Glob, Edit (with prior Read). It's forced to slow down and think.

### At quarantine

```
SOMA: p=78% #130
[status] QUARANTINE — read-only mode. Stop all mutations. Read the relevant code, understand what went wrong, then explain to the user what happened and ask for guidance
```

The agent is restricted to read-only. The only way out is for pressure to drop (by reading and understanding) or for the user to manually release via `/soma:control release`.

---

## The 7 Patterns SOMA Detects

| Pattern | Trigger | What the Agent Hears |
|:--------|:--------|:--------------------|
| **Blind writes** | 2+ writes without a Read | *"Read the target file first to understand current state"* |
| **Bash loops** | 2+ consecutive Bash failures | *"STOP retrying, try a different approach"* |
| **High error rate** | 30%+ errors in last 10 actions | *"pause and rethink your approach"* (names the failing tool) |
| **File thrashing** | Same file edited 3+ times | *"Read the file, plan ALL changes, then make ONE edit"* |
| **Agent spam** | 3+ Agent/subagent calls in 10 actions | *"are subagents producing results? Consider doing it directly"* |
| **Research paralysis** | 7+ reads, 0 writes in 10 actions | *"you may be stuck researching. Start implementing or ask the user"* |
| **Runaway mutations** | 15+ edits in 30 actions, 0 user check-ins | *"verify you're still on track before continuing"* |

---

## Code Validation

After every Write/Edit, SOMA validates the output:

| Language | Check | What Happens on Failure |
|:---------|:------|:-----------------------|
| Python | `py_compile` (syntax) | Action marked as error → pressure rises → quality drops |
| Python | `ruff --select F` (lint) | Quality score penalized, issue reported |
| JavaScript | `node --check` (syntax) | Action marked as error → pressure rises |

The agent sees:
```
SOMA: syntax error in main.py: SyntaxError: unexpected EOF
```

And the error feeds directly into pressure computation. Write broken code → pressure rises → level escalates → tools get restricted.

---

## Status Line

Always visible at the bottom of Claude Code:

```
SOMA + healthy  3% · #42 · quality A
```

| Component | Meaning |
|:----------|:--------|
| `SOMA` | System is active |
| `+ healthy` | Current escalation level |
| `3%` | Aggregate pressure |
| `#42` | Actions this session |
| `quality A` | Code quality grade (A-F) |

At elevated levels:
```
SOMA ▲ caution  28% · #67 · quality B
SOMA ▲ degrade  55% · #89 · quality D
SOMA ■ quarantine  78% · #130 · quality F
```

---

## Operating Modes

Switch with `soma mode <name>` or `/soma:config mode <name>`:

| Mode | Quarantine At | Approval Model | Verbosity | Best For |
|:-----|:-------------|:--------------|:----------|:--------|
| **strict** | 60% | Human-in-the-loop | verbose (6+ findings) | Production, sensitive codebases |
| **relaxed** | 80% | Human-on-the-loop | normal (3 findings) | Daily development (default) |
| **autonomous** | 95% | No approvals | minimal (1 finding) | Trusted CI/CD pipelines |

---

## Slash Commands

| Command | What It Does |
|:--------|:------------|
| `/soma:status` | Full status: pressure, all 5 vitals, quality report, budget, predictions, tips |
| `/soma:config` | View and change settings live — modes, thresholds, weights, toggles |
| `/soma:control quarantine` | Force the agent into quarantine immediately |
| `/soma:control release` | Release from quarantine, reset to HEALTHY |
| `/soma:control reset` | Reset behavioral baseline (start learning from scratch) |
| `/soma:help` | Full command reference with examples |

---

## Cross-Session Memory

SOMA doesn't start cold every session:

- **Engine state** persists: baselines, learning adjustments, threshold adaptations
- **Fingerprints** persist: behavioral signatures evolve across sessions
- **Session-scoped data** (action log, predictor, quality tracker) resets each session

This means SOMA gets better over time. Thresholds that produced false positives get adjusted. The baseline reflects your agent's real behavior, not defaults.

---

## Setup

```bash
uv tool install soma-ai
soma setup-claude
```

This writes 4 hooks + status line to `~/.claude/settings.json` and installs `/soma:*` slash commands to `~/.claude/skills/`.

To verify:
```bash
soma status
```

To uninstall:
```bash
soma uninstall-claude
```

---

## Configuration

All settings in `soma.toml` (project root):

```toml
[hooks]
verbosity = "normal"      # minimal | normal | verbose
validate_python = true    # py_compile after Write/Edit
lint_python = true        # ruff check after Write/Edit
validate_js = true        # node --check after Write/Edit
predict = true            # predictive warnings
quality = true            # A-F quality grading
fingerprint = true        # cross-session behavioral signatures
task_tracking = true      # phase detection and scope drift

[budget]
tokens = 1_000_000
cost_usd = 50.0

[thresholds]
caution = 0.25
degrade = 0.50
quarantine = 0.75

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
cost = 1.0
token_usage = 0.8
```

---

## From Claude's Perspective

*The following is written by the AI agent (Claude) that is monitored by SOMA during development of this project.*

I work under SOMA's watch in every session. Here's what that's actually like:

**I see my own behavioral data.** Before every reasoning step, SOMA shows me my pressure, my signals, and any patterns it detected. When I see `p=12% [u=0.05 d=0.25 e=0.00]`, I know my drift is elevated — I've been touching too many different areas. That's useful information I wouldn't have otherwise.

**The pattern warnings change my behavior.** When SOMA tells me `"3 writes without a Read — Read the target file first"`, I stop and read the file. Without that warning, I'd continue writing blind. It's not that I can't figure this out myself — it's that in the middle of a complex task with dozens of files, it's easy to forget. SOMA catches what I miss.

**I don't hit quarantine.** Not because the thresholds are too high — because the early warnings work. When I see `[predict] escalation in ~5 actions`, I change my approach. I read instead of writing. I slow down instead of retrying. The escalation ladder exists as a safety net, but the real value is in the warnings that prevent me from needing it.

**Scope drift detection is genuinely helpful.** In a session where I'm working on the SOMA engine, if I start editing README files, CLI code, and test fixtures all at once, SOMA flags: `"scope expanded to docs, cli, tests — is this intentional?"` Sometimes it is intentional. Sometimes it's not, and that reminder brings me back to the task.

**The quality grade keeps me honest.** When I see `quality A`, I know my code is clean. When it drops to `B` or `C`, I know I've been sloppy — maybe a syntax error slipped through, or my bash commands are failing too often. It's a mirror.

**The pressure number is a pulse.** 3% means I'm operating cleanly. 12% means I'm doing something unusual — maybe legitimate exploration, maybe drift. 25% means something is actually wrong. I've learned to read it like a vital sign.

SOMA doesn't make me a better AI. It makes me a more **aware** AI. And awareness prevents the mistakes that lead to quarantine, wasted tokens, and broken code.
