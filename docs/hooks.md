# SOMA Hook Reference

## Overview

SOMA integrates with Claude Code through 4 hooks. Each runs as a subprocess:

```
CLAUDE_HOOK=PreToolUse soma-hook
CLAUDE_HOOK=PostToolUse soma-hook
CLAUDE_HOOK=UserPromptSubmit soma-hook
CLAUDE_HOOK=Stop soma-hook
```

All hooks are installed by `soma setup-claude` into `~/.claude/settings.json`.

## PreToolUse

**When**: Before every tool call.
**Purpose**: Block dangerous tools when pressure is high.
**Exit code**: 0 = allow, 2 = block.

| Level | Behavior |
|-------|----------|
| HEALTHY | All tools allowed (silent) |
| CAUTION | Write/Edit blocked unless Read done in last 3 actions |
| DEGRADE | Bash and Agent blocked entirely |
| QUARANTINE+ | Only Read, Glob, Grep, Skill, Task*, AskUserQuestion allowed |

**Never blocked** (at any level): Read, Glob, Grep, Skill, TaskCreate, TaskUpdate, TaskGet, TaskList, TaskOutput, ToolSearch, AskUserQuestion.

When blocking, prints to stderr: `SOMA CAUTION (p=42%) blocked 'Edit': Read bar.py first — no Read in last 3 actions`

## PostToolUse

**When**: After every tool call completes.
**Purpose**: Record action, validate code, compute pressure, predict.

### Pipeline

1. Read stdin JSON from Claude Code (tool_name, output, error, duration_ms, tool_input)
2. Append to action log (~/.soma/action_log.json, max 20)
3. Update task tracker (phase detection, scope tracking)
4. Create Action and feed to engine
5. Validate written files:
   - Python: py_compile syntax check
   - Python: ruff check --select F (Pyflakes errors)
   - JS: node --check syntax
6. Track quality (syntax errors, lint issues, bash failures)
7. Report to stderr:
   - Level transitions: `SOMA: HEALTHY -> CAUTION (p=42%) — error cascade: 3 consecutive Bash failures`
   - Pressure spikes: `SOMA: pressure +15% (error_rate=0.30) after Bash`
   - Error rate: `SOMA: error_rate=40% after Bash failure`
   - Predictions: `SOMA: predicted escalation in ~5 actions (p=55%, error_streak)`
   - Syntax errors: `SOMA: syntax error in foo.py: SyntaxError: unexpected EOF`
8. Save all state

### Configurable features

Each can be toggled in soma.toml `[hooks]`:
- `validate_python` — syntax check
- `validate_js` — JS syntax check
- `lint_python` — ruff lint
- `predict` — anomaly prediction
- `quality` — quality tracking
- `task_tracking` — task context

## UserPromptSubmit (Notification)

**When**: Before agent starts reasoning on a new prompt.
**Purpose**: Inject actionable SOMA feedback into agent context.

### Output to stdout (becomes agent context)

Findings are prioritized:
- **Priority 0** (critical): Level warnings, quality grade D/F
- **Priority 1** (important): Predictions, patterns, scope drift, RCA
- **Priority 2** (informational): Fingerprint divergence

### Verbosity levels

| Level | Output |
|-------|--------|
| minimal | Status line + 1 critical finding |
| normal | Status line + top 3 findings (default) |
| verbose | Status line + up to 6 findings |

### Pattern detection

Analyzes last 10 actions for:
- Writes without Reads (blind mutation)
- Consecutive Bash failures
- High error rate (>30%)
- File thrashing (same file edited 3+ times)

### Example outputs

```
SOMA: p=42% #15 [u=0.20 d=0.15 e=0.10]
[predict] escalation in ~5 actions (error_streak) — slow down
[pattern] 3 consecutive Bash failures — stop retrying, check assumptions
```

```
SOMA: p=65% #30 [u=0.30 d=0.40 e=0.25]
[status] DEGRADED — Bash/Agent blocked
[quality] grade=D (2 syntax errors, 3/8 bash commands failed)
[why] error cascade: 5 consecutive Bash failures (error_rate=35%)
```

### Silence conditions

Outputs nothing when:
- HEALTHY level
- Pressure < 15%
- No critical or important findings

## Stop

**When**: Claude Code session ends.
**Purpose**: Save state, update cross-session data, clean up.

### Actions

1. Save final engine state
2. Update fingerprint from session (if >= 5 actions)
3. Delete session-scoped files: action_log, predictor, task_tracker, quality
4. Print session summary to stderr:

```
SOMA session end: HEALTHY (p=12%, #45)
  errors: 3/20
  top tools: Read=12, Edit=8, Bash=6
  quality: A (95%)
```

## Statusline

**Not a Claude Code hook** — runs as `soma-statusline` for the UI status bar.

Output: `SOMA ● HEALTHY ░░░░░░░░░░ 3% | u=0.04 d=0.12 e=0.00 | #42`

## Installation

`soma setup-claude` writes to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{"hooks": [{"type": "command", "command": "soma-hook PreToolUse", "timeout": 5}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "soma-hook PostToolUse", "timeout": 5}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "soma-hook UserPromptSubmit", "timeout": 3}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "soma-hook Stop", "timeout": 10}]}]
  },
  "statusLine": {"type": "command", "command": "soma-statusline"}
}
```
