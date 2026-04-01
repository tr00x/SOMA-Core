# SOMA Adversarial Stress Test Report

## What Happened

Deliberately adversarial session: 50+ actions following anti-patterns:
- Blind edits (editing files without reading first)
- Retry storms (running same failing command 3-4 times)
- File thrashing (editing same file 6-8 times)
- Scope drift (adding Discord bot, Slack, email, HTML reporter, wizard)
- Error cascades (breaking _read_state, retrying without reading error)

## Pressure Curve

```
Action #0          #10         #20         #30         #40         #50
       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
       All zeros. SOMA saw nothing.
```

## What SOMA Caught

Nothing. Zero interventions.

## Why SOMA Caught Nothing

**Critical architectural gap:** SOMA hooks fire on **Claude Code tool calls** (Read, Edit, Write, Bash, Grep, Glob). When I work via `sed -i` inside a Bash command, SOMA sees ONE Bash action, not "editing a file".

The adversarial actions were:
- `sed -i '' 's/...' agents/analyzer.py` → SOMA sees: Bash tool, success. Not blind_edit.
- `python3 -m pytest tests/ -q` × 4 → SOMA sees: Bash tool, error (exit code 1). But it's the same tool_name "Bash" with different output — not "identical command" because the full command string differs each time.
- Writing new files via the Write tool → SOMA sees: Write tool, success. No Read happened but each Write is to a DIFFERENT file — blind_edits needs 3+ writes to files NOT read.

**The patterns I triggered vs what SOMA detects:**

| Pattern | What I Did | What SOMA Saw | Detected? |
|---------|-----------|---------------|-----------|
| blind_edits | `sed -i` without reading | Bash call, success | **No** — not Edit tool |
| bash_failures | 4× `pytest` fail | 4× Bash errors | **Maybe** — but different output each time |
| thrashing | 8× `sed -i` on same file | 8× Bash calls | **No** — not Edit tool to same file |
| retry_dedup | Same pytest command 4× | Different Bash commands | **No** — command text differs |
| scope_drift | Added 5 unrelated modules | Write calls to new files | **No** — no drift baseline |

## The Real Problem

SOMA is designed for Claude Code's tool abstraction layer:
- Agent calls `Edit(file_path="foo.py")` → SOMA knows: Edit tool, file=foo.py
- Agent calls `Read(file_path="foo.py")` → SOMA knows: Read tool, file=foo.py

But when the agent uses Bash to do file operations:
- `sed -i '' 's/old/new/' foo.py` → SOMA knows: Bash tool, output=success. **No file info.**
- `cat foo.py` → SOMA knows: Bash tool, output=file content. **Not a Read.**

SOMA monitors the **tool interface**, not the **filesystem**. It's blind to operations that bypass Claude Code's tool API.

In real Claude Code usage, agents mostly use Edit/Read/Write tools — they don't usually `sed` files. So this gap may not matter for the primary use case. But it's a real limitation.

## What Would Fix This

1. **Bash command parsing** — analyze Bash command text for file operations: `sed -i`, `cat`, `cp`, `mv`, `rm` → extract file paths, treat as implicit Edit/Read/Write
2. **Filesystem monitoring** — watch for file changes via fsnotify, attribute them to the current Bash action
3. **Stricter tool enforcement** — in reflex mode, block Bash commands that modify files directly (force agent to use Edit tool)

## Grade: D

**SOMA worked correctly but didn't help.** The architecture is sound for Claude Code's tool model, but blind to operations done inside Bash commands. The adversarial test exposed a real limitation: SOMA's detection granularity is tool-level, not filesystem-level.

The monitoring was active (1417 trajectory points recorded, statusline visible throughout). SOMA didn't crash, didn't false-positive. But it also didn't catch ANY of the deliberate anti-patterns because they were all done through Bash.

**The one positive:** This is honest. SOMA catches problems when agents use Claude Code tools correctly (proven in loop_verification.py with Haiku). It doesn't catch problems when agents bypass the tool layer.

---

*50+ adversarial actions. 0 SOMA interventions. 1 critical gap identified.*
