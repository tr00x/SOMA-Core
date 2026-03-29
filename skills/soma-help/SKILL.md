---
name: soma:help
description: Show SOMA help — all available commands, what they do, quick start guide. Use when user asks for SOMA help or doesn't know available commands.
---

# SOMA Help

Show the user everything they can do with SOMA in Claude Code.

## Instructions

Present this reference:

---

**SOMA** — Behavioral monitoring for AI agents. The nervous system for Claude Code.

### Slash Commands

| Command | What it does |
|---------|-------------|
| `/soma:status` | Live monitoring status — pressure, quality, vitals, budget |
| `/soma:config` | Settings — modes, thresholds, budget, validation toggles |
| `/soma:config mode strict` | Strict mode — low thresholds, all validation, verbose |
| `/soma:config mode relaxed` | Relaxed mode (default) — balanced monitoring |
| `/soma:config mode autonomous` | Autonomous — minimal monitoring for trusted runs |
| `/soma:control quarantine` | Force agent to quarantine (blocks tool calls) |
| `/soma:control release` | Release agent from quarantine |
| `/soma:control reset` | Reset behavioral baseline |
| `/soma:help` | This help page |

### Terminal Commands

| Command | What it does |
|---------|-------------|
| `soma` | Launch the TUI dashboard |
| `soma status` | Text status summary |
| `soma mode <name>` | Switch operating mode |
| `soma agents` | List monitored agents |
| `soma config show` | Print current soma.toml |
| `soma export` | Export session state to JSON |

### How SOMA Works

SOMA monitors every tool call Claude makes. It tracks 5 signals:

- **Uncertainty** — how diverse are tool choices (high = agent is guessing)
- **Drift** — deviation from established patterns (high = off-track)
- **Error rate** — syntax errors, failed commands
- **Cost** — token/dollar spend rate
- **Token usage** — cumulative consumption

These combine into a **pressure** score (0-100%). As pressure rises, SOMA escalates through levels:

**HEALTHY** (0-24%) -> **CAUTION** (25%) -> **DEGRADE** (50%) -> **QUARANTINE** (75%) -> **RESTART** (90%)

The status line at the bottom of Claude Code shows pressure in real time.

### Quick Start

Already running? You're set. SOMA hooks are active. Use `/soma:status` to check.

Want to adjust? Use `/soma:config mode <strict|relaxed|autonomous>`.
