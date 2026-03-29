---
name: soma:control
description: Control SOMA agent state — quarantine, release, reset baseline, approve escalation. Use when user wants to manually intervene in SOMA monitoring.
---

# SOMA Agent Control

Manual control over the SOMA monitoring engine.

## Instructions

Parse the user's arguments from `$ARGUMENTS`. The default agent is `claude-code`.

### `quarantine [agent-id]` — force quarantine
Run `soma quarantine <agent-id>` via Bash (default: `claude-code`).
Explain: "Agent forced to QUARANTINE level. Tool calls will be blocked until released. Use `/soma:control release` to lift."

### `release [agent-id]` — release from quarantine
Run `soma release <agent-id>` via Bash (default: `claude-code`).
Explain: "Agent released to HEALTHY. Normal monitoring resumed."

### `reset [agent-id]` — reset baseline
Run `soma reset <agent-id>` via Bash (default: `claude-code`).
Explain: "Baseline reset. SOMA will re-learn normal patterns from scratch. First 10 actions are grace period."

### `approve [agent-id]` — approve pending escalation
Run `soma approve <agent-id>` via Bash (default: `claude-code`).
Explain: "Escalation approved. Agent continues at current level."

### No arguments or `help`
Show available control commands:
```
/soma:control quarantine    — force agent to QUARANTINE (blocks tools)
/soma:control release       — release agent back to HEALTHY
/soma:control reset         — reset behavioral baseline (re-learn from scratch)
/soma:control approve       — approve a pending escalation decision
```

All commands default to agent `claude-code`. Specify agent ID for multi-agent setups.
