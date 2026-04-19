---
name: soma:status
description: Show SOMA monitoring status — pressure, quality, vitals, budget, and actionable tips. Use when user asks about SOMA status, monitoring state, or agent health.
---

# SOMA Status

Show the current SOMA monitoring status with actionable insights.

## Instructions

1. Read the SOMA state file and quality file:
   - State: `~/.soma/state.json`
   - Quality: `~/.soma/quality.json`
   - Config: `soma.toml` (in project root, optional)

2. Run `soma status` via Bash to get the formatted summary.

3. Present the status in this format:

**SOMA Status:**
- **Mode:** {mode} | **Pressure:** {pressure}%
- **Actions:** {action_count} this session
- **Quality:** grade {grade} {issues if any}
- **Budget:** {health}% remaining

**Vitals:**
| Signal | Value | Weight | Contribution |
|--------|-------|--------|-------------|
| Uncertainty | {u} | {w_u} | {contribution} |
| Drift | {d} | {w_d} | {contribution} |
| Error rate | {e} | {w_e} | {contribution} |

4. Add **actionable tips** based on current state:
   - If pressure > 30%: explain what's driving it (highest vital) and suggest action
   - If quality grade < C: list the issues and what to fix
   - If budget < 50%: warn about remaining budget
   - If mode is GUIDE+: explain what SOMA will do at next threshold
   - If everything is clean: say "All systems nominal" and move on

5. If the user hasn't used SOMA before (no state file), explain briefly:
   "SOMA monitors your Claude Code session — tracking code quality, behavioral drift, and resource usage. It runs automatically via hooks. Use `/soma:config` to adjust settings or `/soma:help` for all commands."
