# SOMA Claude Code Plugin — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package SOMA as a Claude Code plugin so users get slash commands (`/soma:status`, `/soma:config`, `/soma:control`, `/soma:help`) and auto-registered hooks after install.

**Architecture:** Plugin lives in `.claude-plugin/` at repo root. Skills are markdown files that instruct Claude to call the `soma` CLI or read state files directly. Hooks are registered via `hooks.json` pointing to `soma-hook`. The existing `soma setup-claude` is updated to also work as a plugin installer. Three preset modes (strict/relaxed/autonomous) are stored in `config_loader.py`.

**Tech Stack:** Claude Code plugin system (`.claude-plugin/plugin.json`, `skills/`, `hooks/`), existing `soma` CLI, Python, TOML config.

---

## File Structure

```
.claude-plugin/
  plugin.json                          # Plugin manifest
  marketplace.json                     # For plugin marketplace discovery
skills/
  soma-status/SKILL.md                 # /soma:status — live status + tips
  soma-config/SKILL.md                 # /soma:config — modes, thresholds, budget, toggles
  soma-control/SKILL.md                # /soma:control — quarantine/release/reset/approve
  soma-help/SKILL.md                   # /soma:help — command reference
hooks/
  hooks.json                           # Hook registration for Claude Code plugin system
  run-hook.sh                          # Thin wrapper that calls soma-hook
src/soma/cli/config_loader.py          # Modified: add MODE_PRESETS dict
src/soma/cli/main.py                   # Modified: add `soma mode` subcommand
tests/test_modes.py                    # Tests for mode presets
tests/test_plugin_structure.py         # Tests plugin files exist and are valid
```

---

## Chunk 1: Plugin scaffold + hooks registration

### Task 1: Create plugin manifest

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Create `.claude-plugin/plugin.json`**

```json
{
  "name": "soma-core",
  "description": "Behavioral monitoring and directive control for AI agents. Gives your Claude Code a nervous system — tracks pressure, quality, drift, and budget in real time.",
  "version": "0.3.0",
  "author": {
    "name": "Tim Hunt",
    "url": "https://github.com/tr00x"
  },
  "repository": "https://github.com/tr00x/soma-core",
  "license": "MIT",
  "keywords": [
    "monitoring",
    "behavioral",
    "ai-agents",
    "observability",
    "safety",
    "pressure",
    "quality"
  ]
}
```

- [ ] **Step 2: Create `.claude-plugin/marketplace.json`**

```json
{
  "name": "soma-core",
  "description": "Behavioral monitoring for AI agents — the nervous system for Claude Code",
  "owner": {
    "name": "Tim Hunt",
    "url": "https://github.com/tr00x"
  },
  "plugins": [
    {
      "name": "soma-core",
      "description": "Behavioral monitoring and directive control for AI agents",
      "version": "0.3.0",
      "source": "./",
      "author": {
        "name": "Tim Hunt"
      }
    }
  ]
}
```

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/
git commit -m "feat: add Claude Code plugin manifest"
```

---

### Task 2: Create plugin hook registration

**Files:**
- Create: `hooks/hooks.json`
- Create: `hooks/run-hook.sh`

- [ ] **Step 1: Create `hooks/hooks.json`**

This registers all 4 SOMA hooks through the Claude Code plugin system. The `${CLAUDE_PLUGIN_ROOT}` variable is expanded by Claude Code at runtime to the plugin's install path.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh' PreToolUse",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh' PostToolUse",
            "timeout": 5000
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh' UserPromptSubmit",
            "timeout": 3000
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh' Stop",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Create `hooks/run-hook.sh`**

Thin wrapper that finds `soma-hook` (installed via pip) and delegates. Falls back to `python3 -m soma.hooks.claude_code` if `soma-hook` is not on PATH.

```bash
#!/usr/bin/env bash
set -euo pipefail

HOOK_TYPE="${1:-PostToolUse}"

# Try soma-hook first (installed via pip), fall back to module invocation
if command -v soma-hook &>/dev/null; then
    exec soma-hook "$HOOK_TYPE"
else
    exec python3 -m soma.hooks.claude_code "$HOOK_TYPE"
fi
```

- [ ] **Step 3: Make executable and commit**

```bash
chmod +x hooks/run-hook.sh
git add hooks/
git commit -m "feat: add plugin hook registration (PreToolUse, PostToolUse, UserPromptSubmit, Stop)"
```

---

### Task 3: Test plugin structure

**Files:**
- Create: `tests/test_plugin_structure.py`

- [ ] **Step 1: Write tests**

```python
"""Verify plugin structure is valid for Claude Code."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_plugin_json_exists_and_valid():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["name"] == "soma-core"
    assert "version" in data
    assert "description" in data


def test_marketplace_json_exists():
    p = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert "plugins" in data
    assert len(data["plugins"]) >= 1


def test_hooks_json_valid():
    p = REPO_ROOT / "hooks" / "hooks.json"
    assert p.exists()
    data = json.loads(p.read_text())
    hooks = data["hooks"]
    for required in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"):
        assert required in hooks, f"Missing hook: {required}"


def test_run_hook_sh_executable():
    p = REPO_ROOT / "hooks" / "run-hook.sh"
    assert p.exists()
    import os
    assert os.access(p, os.X_OK), "run-hook.sh must be executable"


def test_skill_dirs_exist():
    skills = REPO_ROOT / "skills"
    for name in ("soma-status", "soma-config", "soma-control", "soma-help"):
        skill_file = skills / name / "SKILL.md"
        assert skill_file.exists(), f"Missing skill: {skill_file}"
```

- [ ] **Step 2: Run tests (expect partial failure — skills not yet created)**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/test_plugin_structure.py -v`
Expected: First 4 tests PASS, last test (skills) FAIL

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_plugin_structure.py
git commit -m "test: add plugin structure validation tests"
```

---

## Chunk 2: Mode presets + CLI

### Task 4: Add mode presets to config_loader

**Files:**
- Modify: `src/soma/cli/config_loader.py`
- Create: `tests/test_modes.py`

- [ ] **Step 1: Write failing test**

```python
"""Test SOMA mode presets."""
from soma.cli.config_loader import MODE_PRESETS, apply_mode


def test_mode_presets_exist():
    assert "strict" in MODE_PRESETS
    assert "relaxed" in MODE_PRESETS
    assert "autonomous" in MODE_PRESETS


def test_strict_mode_values():
    m = MODE_PRESETS["strict"]
    assert m["agents"]["claude-code"]["autonomy"] == "human_in_the_loop"
    assert m["thresholds"]["caution"] == 0.20
    assert m["thresholds"]["quarantine"] == 0.60
    assert m["hooks"]["verbosity"] == "verbose"


def test_relaxed_mode_values():
    m = MODE_PRESETS["relaxed"]
    assert m["agents"]["claude-code"]["autonomy"] == "human_on_the_loop"
    assert m["thresholds"]["caution"] == 0.40
    assert m["thresholds"]["quarantine"] == 0.80
    assert m["hooks"]["verbosity"] == "normal"


def test_autonomous_mode_values():
    m = MODE_PRESETS["autonomous"]
    assert m["agents"]["claude-code"]["autonomy"] == "fully_autonomous"
    assert m["thresholds"]["caution"] == 0.60
    assert m["thresholds"]["quarantine"] == 0.95
    assert m["hooks"]["quality"] is False
    assert m["hooks"]["verbosity"] == "minimal"


def test_apply_mode_merges():
    from soma.cli.config_loader import CLAUDE_CODE_CONFIG
    import copy
    base = copy.deepcopy(CLAUDE_CODE_CONFIG)
    result = apply_mode(base, "strict")
    assert result["thresholds"]["caution"] == 0.20
    # Original keys that aren't in the preset stay untouched
    assert "weights" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/test_modes.py -v`
Expected: ImportError — `MODE_PRESETS` not found

- [ ] **Step 3: Implement mode presets**

Add to `src/soma/cli/config_loader.py` after `CLAUDE_CODE_CONFIG`:

```python
MODE_PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "agents": {
            "claude-code": {
                "autonomy": "human_in_the_loop",
            },
        },
        "thresholds": {
            "caution": 0.20,
            "degrade": 0.40,
            "quarantine": 0.60,
            "restart": 0.80,
        },
        "hooks": {
            "verbosity": "verbose",
            "validate_python": True,
            "validate_js": True,
            "lint_python": True,
            "predict": True,
            "fingerprint": True,
            "quality": True,
            "task_tracking": True,
        },
    },
    "relaxed": {
        "agents": {
            "claude-code": {
                "autonomy": "human_on_the_loop",
            },
        },
        "thresholds": {
            "caution": 0.40,
            "degrade": 0.60,
            "quarantine": 0.80,
            "restart": 0.95,
        },
        "hooks": {
            "verbosity": "normal",
            "validate_python": True,
            "validate_js": True,
            "lint_python": True,
            "predict": True,
            "fingerprint": True,
            "quality": True,
            "task_tracking": True,
        },
    },
    "autonomous": {
        "agents": {
            "claude-code": {
                "autonomy": "fully_autonomous",
            },
        },
        "thresholds": {
            "caution": 0.60,
            "degrade": 0.80,
            "quarantine": 0.95,
            "restart": 0.99,
        },
        "hooks": {
            "verbosity": "minimal",
            "validate_python": True,
            "validate_js": False,
            "lint_python": False,
            "predict": False,
            "fingerprint": False,
            "quality": False,
            "task_tracking": False,
        },
    },
}


def apply_mode(config: dict[str, Any], mode: str) -> dict[str, Any]:
    """Deep-merge a mode preset into config. Returns the merged config."""
    import copy
    preset = MODE_PRESETS.get(mode)
    if preset is None:
        raise ValueError(f"Unknown mode: {mode!r}. Choose from: {', '.join(MODE_PRESETS)}")
    result = copy.deepcopy(config)
    _deep_merge(result, preset)
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base, mutating base."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/test_modes.py -v`
Expected: ALL PASS

- [ ] **Step 5: Add `soma mode` CLI subcommand**

Add to `src/soma/cli/main.py` — new handler and parser entry:

Handler function (add after `_cmd_config`):
```python
def _cmd_mode(args: argparse.Namespace) -> None:
    from soma.cli.config_loader import (
        load_config, save_config, MODE_PRESETS, apply_mode,
    )

    if args.mode_name is None:
        # Show current mode and available modes
        config = load_config()
        current = config.get("soma", {}).get("mode", "relaxed")
        print(f"  Current mode: {current}")
        print()
        for name, preset in MODE_PRESETS.items():
            autonomy = preset["agents"]["claude-code"]["autonomy"]
            quarantine = preset["thresholds"]["quarantine"]
            verbosity = preset["hooks"]["verbosity"]
            marker = " <--" if name == current else ""
            print(f"  {name:<12} autonomy={autonomy}, quarantine={quarantine:.0%}, verbosity={verbosity}{marker}")
        print()
        print("  Usage: soma mode <strict|relaxed|autonomous>")
        return

    mode_name = args.mode_name
    config = load_config()
    config = apply_mode(config, mode_name)
    config.setdefault("soma", {})["mode"] = mode_name
    save_config(config)
    print(f"  Mode set to: {mode_name}")

    preset = MODE_PRESETS[mode_name]
    autonomy = preset["agents"]["claude-code"]["autonomy"]
    quarantine = preset["thresholds"]["quarantine"]
    print(f"  Autonomy: {autonomy}")
    print(f"  Quarantine threshold: {quarantine:.0%}")
    print(f"  Verbosity: {preset['hooks']['verbosity']}")
```

Parser entry (add after the `config` subparser block):
```python
mode_parser = subparsers.add_parser("mode", help="Switch SOMA operating mode")
mode_parser.add_argument("mode_name", nargs="?", default=None,
                         help="Mode: strict, relaxed, or autonomous")
```

Add `"mode": _cmd_mode` to the dispatch dict.

Add `"mode"` to the epilog help text under Configuration.

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/soma/cli/config_loader.py src/soma/cli/main.py tests/test_modes.py
git commit -m "feat: add mode presets (strict/relaxed/autonomous) with soma mode CLI"
```

---

## Chunk 3: Slash command skills

### Task 5: Create `/soma:status` skill

**Files:**
- Create: `skills/soma-status/SKILL.md`

- [ ] **Step 1: Create skill file**

```markdown
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
- **Level:** {level} | **Pressure:** {pressure}%
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
   - If level is CAUTION+: explain what SOMA will do at next threshold
   - If everything is clean: say "All systems nominal" and move on

5. If the user hasn't used SOMA before (no state file), explain briefly:
   "SOMA monitors your Claude Code session — tracking code quality, behavioral drift, and resource usage. It runs automatically via hooks. Use `/soma:config` to adjust settings or `/soma:help` for all commands."
```

- [ ] **Step 2: Commit**

```bash
mkdir -p skills/soma-status
git add skills/soma-status/SKILL.md
git commit -m "feat: add /soma:status slash command skill"
```

---

### Task 6: Create `/soma:config` skill

**Files:**
- Create: `skills/soma-config/SKILL.md`

- [ ] **Step 1: Create skill file**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
mkdir -p skills/soma-config
git add skills/soma-config/SKILL.md
git commit -m "feat: add /soma:config slash command skill"
```

---

### Task 7: Create `/soma:control` skill

**Files:**
- Create: `skills/soma-control/SKILL.md`

- [ ] **Step 1: Create skill file**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
mkdir -p skills/soma-control
git add skills/soma-control/SKILL.md
git commit -m "feat: add /soma:control slash command skill"
```

---

### Task 8: Create `/soma:help` skill

**Files:**
- Create: `skills/soma-help/SKILL.md`

- [ ] **Step 1: Create skill file**

```markdown
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

**HEALTHY** (0-24%) → **CAUTION** (25%) → **DEGRADE** (50%) → **QUARANTINE** (75%) → **RESTART** (90%)

The status line at the bottom of Claude Code shows pressure in real time.

### Quick Start

Already running? You're set. SOMA hooks are active. Use `/soma:status` to check.

Want to adjust? Use `/soma:config mode <strict|relaxed|autonomous>`.
```

- [ ] **Step 2: Commit**

```bash
mkdir -p skills/soma-help
git add skills/soma-help/SKILL.md
git commit -m "feat: add /soma:help slash command skill"
```

---

### Task 9: Run all tests, verify plugin structure

- [ ] **Step 1: Run plugin structure tests**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/test_plugin_structure.py -v`
Expected: ALL PASS (including skill dirs)

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 3: Verify skills are discoverable**

```bash
# Check each skill has valid frontmatter
for skill in skills/soma-*/SKILL.md; do
  echo "=== $skill ==="
  head -4 "$skill"
  echo
done
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: SOMA Claude Code plugin — slash commands and plugin structure

Adds /soma:status, /soma:config, /soma:control, /soma:help slash commands.
Adds mode presets (strict/relaxed/autonomous).
Packages SOMA as a Claude Code plugin with auto-registered hooks."
```

---

## Chunk 4: Update setup-claude for dual-path install

### Task 10: Update setup-claude to mention plugin path

**Files:**
- Modify: `src/soma/cli/setup_claude.py`

- [ ] **Step 1: Add plugin info to setup output**

At the end of `run_setup_claude()`, after the existing output, add:

```python
    print("  Plugin install (alternative):")
    print("    /install tr00x/soma-core")
    print()
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/timur/projectos/soma && .venv/bin/python -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/soma/cli/setup_claude.py
git commit -m "feat: mention plugin install path in setup-claude output"
```
