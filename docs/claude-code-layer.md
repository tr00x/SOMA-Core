# SOMA + Claude Code: The Behavioral Safety Layer

*Version 0.5.0*

SOMA integrates with Claude Code as a **closed-loop behavioral control system**. It's not a plugin you install and forget — it's a layer that fundamentally changes how the agent operates by giving it real-time awareness of its own behavior.

---

## What the Layer Does

Every action Claude Code takes passes through SOMA:

```
You type a prompt
    │
    ▼
UserPromptSubmit ──► SOMA injects behavioral feedback into agent context
    │                 (phase-aware header, patterns, actionable metrics)
    ▼
Agent reasons (with SOMA's feedback visible)
    │
    ▼
PreToolUse ────────► SOMA evaluates guidance: guide, warn, or block
    │                 (only blocks destructive ops at 75%+ pressure)
    │                 Policy engine rules also evaluated here
    ▼
Tool executes
    │
    ▼
PostToolUse ───────► SOMA records action, validates code, computes new pressure
    │                 (py_compile, ruff, error detection, read-context tracking)
    │                 Classifies uncertainty, updates reliability metrics
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
| **UserPromptSubmit** | Before agent starts thinking | Injects: phase-aware header, pattern findings, actionable metrics, uncertainty type, calibration score, periodic check-ins |
| **PreToolUse** | Before every tool call | Evaluates guidance threshold and policy engine rules. Blocks only destructive ops (rm -rf, git push --force, .env writes) at 75%+ pressure. Never blocks Read/Grep/Glob/Write/Edit/Bash/Agent as tool categories. |
| **PostToolUse** | After every tool call | Records the action. Validates written code (syntax + lint). Updates pressure, quality. Classifies uncertainty (epistemic/aleatoric). Computes calibration score. Updates half-life predictor. Tracks read-context for smarter warnings. Reports level changes. |
| **Stop** | Session ends | Saves engine state for next session. Updates agent fingerprint. Cleans session files. Prints summary. |

---

## What the Agent Actually Sees

This is the real output SOMA injects into the agent's context before every reasoning step.

### Normal operation (low pressure, after 3 actions)

```
SOMA: #42 [guide] ctx=73% focused
```

One line. Phase-aware header with action count, threshold level, context usage, and focus state. The agent knows it's being watched but nothing is wrong.

SOMA is always present after 3 actions — it never goes silent, even at low pressure.

### When patterns emerge

```
SOMA: #67 [guide] ctx=58% focused
[do] 3 writes without a Read (main.py, config.py) — Read the target file first to understand current state
[do] scope expanded to tests/, config/ — is this intentional? If not, refocus on the original task
```

The agent sees specific, actionable instructions prefixed with `[do]`. Not "pressure is elevated" — but "you wrote 3 files without reading them, here's what to do."

SOMA is read-context aware: if the agent read a file before editing it, the blind-edit warning is suppressed.

### Uncertainty and calibration feedback

```
SOMA: #35 [guide] ctx=65% focused
[do] uncertainty=epistemic — read the target files to reduce uncertainty before making changes
[+] calibration=0.88 — predictions tracking outcomes well
```

SOMA now tells the agent *why* it's uncertain. Epistemic uncertainty means the agent needs more information — read files, check documentation, ask the user. Aleatoric uncertainty means the situation is inherently unpredictable — add error handling, use retries, plan for failure cases.

The calibration score shows whether the agent's confidence matches reality. When calibration drops, it means the agent is overconfident or underconfident, and SOMA adjusts its guidance accordingly.

### When things go wrong

```
SOMA: #89 [warn] ctx:mid focus:ok
[do] 4 consecutive Bash failures — check assumptions before retrying
[do] escalation in ~5 actions (error_streak) — stop retrying the failing approach
[do] quality grade=D (2 syntax errors, 3/8 bash commands failed)
```

The agent receives three separate action items. Pressure is rising. If it doesn't change behavior, block threshold is ~5 actions away.

### At elevated pressure

```
SOMA: #112 [warn] ctx:high focus:drift
[do] pressure at 55% — slow down and verify
[do] error cascade: 5 consecutive Bash failures (error_rate=35%)
[do] quality grade=F (4 syntax errors, 5/10 bash commands failed)
```

All tools are still available. But the agent receives insistent warnings. SOMA is loudly telling it to slow down.

### At block threshold

```
SOMA: #130 [block] ctx:high focus:drift
[do] pressure at 82% — only destructive ops blocked
[do] error cascade: 7 consecutive Bash failures (error_rate=45%)
```

The agent can still Read, Write, Edit, Bash, and use Agent. Only genuinely destructive operations (rm -rf, git push --force, .env writes) are blocked. The agent is urged to focus on safe, reversible actions. Pressure drop comes from changing behavior, not from being locked out.

### Periodic check-in (every 15 actions)

```
SOMA: #45 [guide] ctx=61% focused
[✓] 15 actions, quality A, no issues — on track
```

Every 15 actions, SOMA provides a brief positive check-in when things are going well. The `[✓]` prefix signals positive feedback rather than an action item.

### Workflow awareness

SOMA is workflow-aware. During planning phases, mutation warnings are suppressed. During discuss phases, scope drift is less relevant. During execute phases, research paralysis patterns activate. Patterns fire only when they're meaningful for the current workflow context.

---

## Policy Engine Integration

Custom rules defined in YAML or TOML fire alongside SOMA's built-in guidance. This lets teams enforce project-specific constraints beyond the default pressure model.

For example, a team might define rules that warn when cost exceeds 80% even at low pressure, or block operations when drift is extreme regardless of the aggregate pressure level. Policy engine results appear in the agent's context alongside built-in findings — the agent sees them as additional `[do]` items.

Rules are evaluated during PreToolUse (for blocking decisions) and during UserPromptSubmit (for guidance injection). See the [API Reference](api.md#policy-engine) for rule format and configuration.

---

## The 7 Patterns SOMA Detects

| Pattern | Trigger | What the Agent Hears |
|:--------|:--------|:--------------------|
| **Blind writes** | 2+ writes without a Read (and no prior read of that file) | *"Read the target file first to understand current state"* |
| **Bash loops** | 2+ consecutive Bash failures | *"STOP retrying, try a different approach"* |
| **High error rate** | 30%+ errors in last 10 actions | *"pause and rethink your approach"* (names the failing tool) |
| **File thrashing** | Same file edited 3+ times | *"Read the file, plan ALL changes, then make ONE edit"* |
| **Agent spam** | 3+ Agent/subagent calls in 10 actions | *"are subagents producing results? Consider doing it directly"* |
| **Research paralysis** | 7+ reads, 0 writes in 10 actions | *"you may be stuck researching. Start implementing or ask the user"* |
| **Runaway mutations** | 15+ edits in 30 actions, 0 user check-ins | *"verify you're still on track before continuing"* |

Pattern detection is powered by `patterns.py`, which feeds findings to `findings.py` for prioritization. The `context.py` module tracks read-context so that edits after reads don't trigger false blind-edit warnings.

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
SOMA: #42 [guide] ctx=73% focused
```

| Component | Meaning |
|:----------|:--------|
| `SOMA:` | System is active |
| `#42` | Actions this session |
| `[guide]` | Current threshold level |
| `ctx=73%` | Context usage (high/mid/low) |
| `focused` | Focus state (focused/ok/drift) |

At elevated pressure:
```
SOMA: #67 [warn] ctx:mid focus:ok
SOMA: #89 [warn] ctx:high focus:drift
SOMA: #130 [block] ctx:high focus:drift
```

---

## Operating Modes

Switch with `soma mode <name>` or `/soma:config mode <name>`:

| Mode | Block At | Approval Model | Verbosity | Best For |
|:-----|:---------|:--------------|:----------|:--------|
| **strict** | 60% | Human-in-the-loop | verbose (6+ findings) | Production, sensitive codebases |
| **relaxed** | 80% | Human-on-the-loop | normal (3 findings) | Daily development (default) |
| **autonomous** | 95% | No approvals | minimal (1 finding) | Trusted CI/CD pipelines |

---

## Slash Commands

| Command | What It Does |
|:--------|:------------|
| `/soma:status` | Full status: pressure, context, focus, quality report, budget, tips |
| `/soma:config` | View and change settings live — modes, thresholds, weights, toggles |
| `/soma:control reset` | Reset behavioral baseline (start learning from scratch) |
| `/soma:help` | Full command reference with examples |

CLI:

| Command | What It Does |
|:--------|:------------|
| `soma status` | Show current monitoring state |
| `soma doctor` | Diagnose installation, hooks, and configuration health |
| `soma setup-claude` | Install hooks and slash commands |
| `soma uninstall-claude` | Remove hooks and slash commands |

---

## Architecture

SOMA's intelligence comes from three core modules:

| Module | Role | Size |
|:-------|:-----|:-----|
| `patterns.py` | Detects behavioral patterns from action history | Core logic |
| `findings.py` | Prioritizes and deduplicates pattern findings | Core logic |
| `context.py` | Tracks read-context, workflow phase, focus state | Core logic |
| `notification.py` | Thin formatter — assembles header + findings into output | ~154 lines |

The notification layer is intentionally thin. All intelligence lives in the core modules. `notification.py` just formats what `patterns.py`, `findings.py`, and `context.py` produce.

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
soma doctor
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
guide = 0.25
warn = 0.50
block = 0.75

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
cost = 1.0
token_usage = 0.8
goal_coherence = 1.5

[uncertainty]
epistemic_multiplier = 1.2
aleatoric_multiplier = 0.8
```

---

## From Claude's Perspective

*The following is written by the AI agent (Claude) that is monitored by SOMA during development of this project.*

I work under SOMA's watch in every session. Here's what that's actually like:

**I see my own behavioral data.** Before every reasoning step, SOMA shows me my action count, threshold level, context usage, and focus state. When I see `#42 [guide] ctx=73% focused`, I know I'm operating within bounds. That's useful information I wouldn't have otherwise.

**The pattern warnings change my behavior.** When SOMA tells me `[do] 3 writes without a Read — Read the target file first`, I stop and read the file. Without that warning, I'd continue writing blind. It's not that I can't figure this out myself — it's that in the middle of a complex task with dozens of files, it's easy to forget. SOMA catches what I miss.

**I don't hit block threshold.** Not because the thresholds are too high — because the early guidance works. When I see `[do] escalation in ~5 actions`, I change my approach. I read instead of writing. I slow down instead of retrying. The block threshold exists as a safety net, but the real value is in the `[do]` items that prevent me from needing it.

**The periodic check-ins are grounding.** Every 15 actions, seeing `[✓] 15 actions, quality A, no issues — on track` confirms I'm doing well. It's not noise — it's a moment of calibration.

**Scope drift detection is genuinely helpful.** In a session where I'm working on the SOMA engine, if I start editing README files, CLI code, and test fixtures all at once, SOMA flags: `[do] scope expanded to docs, cli, tests — is this intentional?` Sometimes it is intentional. Sometimes it's not, and that reminder brings me back to the task.

**The quality grade keeps me honest.** When I see `quality A`, I know my code is clean. When it drops to `B` or `C`, I know I've been sloppy — maybe a syntax error slipped through, or my bash commands are failing too often. It's a mirror.

**Context awareness prevents false positives.** SOMA knows when I've read a file before editing it. It knows what workflow phase I'm in. It doesn't warn about blind writes when I just read the file two actions ago. That intelligence means I trust the warnings I do receive.

SOMA doesn't make me a better AI. It makes me a more **aware** AI. And awareness prevents the mistakes that lead to wasted tokens and broken code.
