---
name: soma:config
description: Configure SOMA settings — modes, thresholds, budget, validation toggles. Use when user wants to change SOMA behavior, switch modes, adjust sensitivity, or toggle features.
---

# SOMA Configuration

Manage SOMA settings from within Claude Code.

## Instructions

Parse the user's arguments from `$ARGUMENTS`. Route to the correct action:

### No arguments — show current config
Run `soma config show` via Bash and present a clean summary:
- Current mode (strict/relaxed/autonomous)
- Key thresholds (caution, quarantine)
- Budget limits
- Active features (validation, quality, predictions)
- Verbosity level

### `mode <name>` — switch operating mode
Run `soma mode <name>` via Bash. Valid modes:

| Mode | Description |
|------|-------------|
| **strict** | Low thresholds, human-in-the-loop, all validation on, verbose output. For critical work. |
| **relaxed** | Default. Balanced thresholds, human-on-the-loop. Good for normal coding. |
| **autonomous** | High thresholds, minimal monitoring, no quality tracking. For trusted autonomous runs. |

After switching, confirm the new settings.

### `threshold <name> <value>` — set a specific threshold
Run `soma config set thresholds.<name> <value>` via Bash.
Valid thresholds: caution, degrade, quarantine, restart.
Value must be between 0.0 and 1.0.

### `budget <dimension> <value>` — set budget limit
Run `soma config set budget.<dimension> <value>` via Bash.
Valid dimensions: tokens, cost_usd.

### `validate <type> <on|off>` — toggle validation
Run `soma config set hooks.validate_<type> <true|false>` via Bash.
Valid types: python, js.

### `verbosity <level>` — set output verbosity
Run `soma config set hooks.verbosity <level>` via Bash.
Valid levels: minimal, normal, verbose.

### `weight <signal> <value>` — adjust signal weight
Run `soma config set weights.<signal> <value>` via Bash.
Valid signals: uncertainty, drift, error_rate, cost, token_usage.

### Help / unknown
If the arguments don't match any pattern, show available options with examples:
```
/soma:config                    — show current settings
/soma:config mode strict        — switch to strict mode
/soma:config mode relaxed       — switch to relaxed (default)
/soma:config mode autonomous    — minimal monitoring
/soma:config threshold caution 0.30
/soma:config budget tokens 500000
/soma:config validate python off
/soma:config verbosity minimal
/soma:config weight drift 2.0
```
