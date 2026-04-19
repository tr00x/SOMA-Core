---
name: soma:control
description: Control SOMA monitoring — stop, start, reset baseline, uninstall hooks. Use when user wants to manually intervene in SOMA monitoring.
---

# SOMA Agent Control

Manual control over the SOMA monitoring engine.

## Instructions

Parse the user's arguments from `$ARGUMENTS`. The default agent is `claude-code`.

### `stop` — pause monitoring
Run `soma stop` via Bash.
Explain: "SOMA monitoring paused. Tool calls are no longer tracked. Use `/soma:control start` to resume."

### `start` — resume monitoring
Run `soma start` via Bash.
Explain: "SOMA monitoring resumed. All hooks active."

### `reset [agent-id]` — reset baseline
Run `soma reset <agent-id>` via Bash (default: `claude-code`).
Explain: "Baseline reset. SOMA will re-learn normal patterns from scratch. First 10 actions are grace period."

### `uninstall-claude` — remove Claude Code hooks
Run `soma uninstall-claude` via Bash.
Explain: "SOMA hooks removed from Claude Code settings. Run `soma init claude-code` to reinstall."

### No arguments or `help`
Show available control commands:
```
/soma:control stop              — pause SOMA monitoring
/soma:control start             — resume SOMA monitoring
/soma:control reset             — reset behavioral baseline (re-learn from scratch)
/soma:control uninstall-claude  — remove SOMA hooks from Claude Code
```

Reset defaults to agent `claude-code`. Specify agent ID for multi-agent setups.
