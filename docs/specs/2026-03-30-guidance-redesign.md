# SOMA Guidance Redesign Spec

**Date:** 2026-03-30
**Version:** 0.4.0 (breaking change)
**Status:** Approved

## Problem

SOMA acts as a dumb kill-switch. When pressure >= threshold, it blocks ALL tools except Read/Glob/Grep via escalation levels (CAUTION → DEGRADE → QUARANTINE → SAFE_MODE). This kills legitimate workflows:

- GSD spawning 4+ parallel agents — normal, not drift
- Many Writes without Reads — agents creating new files, Read not needed
- Editing same file 4 times — normal iterative work

SOMA doesn't understand context. It sees a pattern and blocks.

## Solution

Transform SOMA from a blocking system into a guidance (nervous) system. Replace 6 escalation levels with 4 response modes. Block ONLY destructive operations at extreme pressure.

## Design

### ResponseMode (replaces Level enum)

| Mode | Pressure | Behavior |
|------|----------|----------|
| OBSERVE | 0-25% | Silent. Metrics only. |
| GUIDE | 25-50% | Soft suggestions when patterns detected. Never blocks. |
| WARN | 50-75% | Insistent warnings + alternative suggestions. Never blocks. |
| BLOCK | 75-100% | Blocks ONLY destructive operations. Normal Write/Edit/Bash/Agent always allowed. |

### GuidanceResponse

```python
@dataclass
class GuidanceResponse:
    mode: ResponseMode
    allow: bool
    message: str | None
    suggestions: list[str]
```

### Guidance Engine (`guidance.py`)

Central decision point. Single function:

```python
def evaluate(pressure, tool_name, tool_input, action_log, context) -> GuidanceResponse
```

Logic:
1. Map pressure → mode
2. If BLOCK: check if operation is destructive → allow=False only for destructive
3. If WARN: generate contextual warnings based on action patterns
4. If GUIDE: generate soft suggestions only when patterns detected
5. If OBSERVE: message=None, silent

### Destructive Operations (blocked at BLOCK mode only)

Bash commands matching:
- `rm -rf`, `rm -r`, `rm --recursive`, `rm --force`
- `git reset --hard`
- `git push --force`, `git push -f`
- `git clean -f`
- `git checkout .`
- `chmod 777`
- `kill -9`

File writes to:
- `.env*`
- `credentials*`
- `*.pem`, `*.key`
- Files matching `secret` in name

Everything else: ALWAYS ALLOWED regardless of pressure.

### Context Awareness

**GSD detection:** If `.planning/` directory exists in working directory:
- Reduce drift weight to 0.5x (high activity is normal)
- Don't count Agent spawns as drift signal
- Don't flag writes to `.planning/` as suspicious

**Pattern-based suggestions (not blocks):**
- File thrashing: "you've edited X 4 times — consider collecting all changes first"
- Parallel agents: "3 agents working — check for file conflicts"
- Bash failures: "3 consecutive failures — check assumptions before retrying"
- Sensitive file: "this looks like credentials — are you sure?"

### Hook Response Format

**PreToolUse:**
- `exit(0)` + message on stderr → tool allowed, agent sees suggestion
- `exit(2)` → tool blocked (ONLY destructive ops at p>75%)

**Notification (UserPromptSubmit):**
- OBSERVE: `SOMA: p=12% #45 [u=0.02 d=0.15 e=0.00]`
- GUIDE: metrics + 1 soft suggestion
- WARN: metrics + insistent warning + suggestions
- BLOCK: metrics + "destructive operations blocked"

**Statusline:** Adapted for new mode names (observe/guide/warn/block).

## What Changes

| Component | Action |
|-----------|--------|
| `types.py` | Replace `Level` enum with `ResponseMode` enum |
| `guidance.py` | **NEW** — central decision engine |
| `ladder.py` | **DELETE** — replaced by pressure_to_mode() |
| `pre_tool_use.py` | Rewrite — single call to guidance.evaluate() |
| `notification.py` | Refactor — use ResponseMode for message tone |
| `statusline.py` | Adapt labels/emojis for new modes |
| `engine.py` | Remove ladder dependency, return pressure + mode |
| `persistence.py` | Update state schema (no more ladder state) |
| `common.py` | Remove SAFE_TOOLS/MUTATION_TOOLS/DEGRADE_BLOCKED |

## What Stays

| Component | Reason |
|-----------|--------|
| `pressure.py` | Pressure calculation works fine |
| `vitals.py` | Signal computation (u/d/e) works fine |
| `baseline.py` | EMA learning works fine |
| `ring_buffer.py` | No changes needed |
| `graph.py` | Trust propagation stays |
| `quality.py` | Code quality scoring stays |
| `predictor.py` | Adapt predictions for new modes |
| `rca.py` | Root cause analysis stays |

## What's Removed

- `Level` enum (HEALTHY/CAUTION/DEGRADE/QUARANTINE/RESTART/SAFE_MODE)
- `Ladder` class and hysteresis logic
- All tool blocking except destructive ops
- SAFE_TOOLS / MUTATION_TOOLS / DEGRADE_BLOCKED constants
- "Read before Write" enforcement
- SAFE_MODE budget latch

## Migration

Breaking change. Version bump to 0.4.0. No migration path — old config keys for thresholds (caution/degrade/quarantine/restart) become mode boundaries (guide/warn/block).
