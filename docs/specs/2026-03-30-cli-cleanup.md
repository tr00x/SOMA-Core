# SOMA CLI Cleanup Spec

**Date:** 2026-03-30
**Version:** 0.4.1
**Status:** Approved

## Problem

SOMA CLI commands are broken or dead:
- `quarantine`/`release` write to IPC files nobody reads
- `daemon` doesn't exist
- No `stop`/`start`/`uninstall-claude` commands
- `status` shows hardcoded old version and Level names
- `approve` references non-existent approval workflow
- `commands.py` IPC queue is dead code

## Solution

Clean CLI: keep what works, fix what's broken, add missing commands, remove dead code.

## Final Command Set

| Command | Action |
|---------|--------|
| `soma status` | Quick text summary (version from pkg, ResponseMode names) |
| `soma setup-claude` | Install hooks into Claude Code settings.json |
| `soma uninstall-claude` | **NEW** Remove hooks from settings.json, optionally clean ~/.soma/ |
| `soma stop` | **NEW** Disable SOMA hooks (remove from settings.json) |
| `soma start` | **NEW** Re-enable SOMA hooks (re-add to settings.json) |
| `soma reset [agent-id]` | Reset agent baseline (direct state access, default: claude-code) |
| `soma config show` | Print soma.toml |
| `soma config set <key> <val>` | Update config value |
| `soma mode [name]` | Switch operating mode preset |
| `soma version` | Print version |
| `soma replay <file>` | Replay recorded session |
| `soma` (no args) | TUI dashboard |

## Removed Commands

| Command | Reason |
|---------|--------|
| `soma quarantine <id>` | No quarantine in guidance model |
| `soma release <id>` | No quarantine to release from |
| `soma approve <id>` | No approval workflow |
| `soma daemon` | Dead code, hooks handle everything |
| `soma export` | Unused |

## Removed Code

| File/Function | Reason |
|--------------|--------|
| `src/soma/commands.py` | Dead IPC queue, never processed |
| `_write_command()` in main.py | Part of dead IPC |

## Implementation Details

### `soma stop` / `soma start`

**stop:** Remove SOMA hook entries from `~/.claude/settings.json` and SOMA statusLine. Save a backup marker at `~/.soma/hooks_installed` so `start` knows what to restore.

**start:** Re-add hooks using same logic as `setup-claude`. Read marker from `~/.soma/hooks_installed`.

Both reuse `_install_hooks()` / `_install_statusline()` from setup_claude.py.

### `soma uninstall-claude`

1. Remove hooks from settings.json (same as stop)
2. Remove statusLine from settings.json
3. Optionally delete `~/.soma/` directory (prompt or --force flag)
4. Remove SOMA section from CLAUDE.md if present

### `soma reset`

Direct state modification:
```python
engine = load_engine_state(path)
agent = engine._agents[agent_id]
agent.baseline = Baseline()
agent.baseline_vector = None
agent.mode = ResponseMode.OBSERVE
save_engine_state(engine, path)
```

Default agent-id: `claude-code`

### `soma status`

- Version from `importlib.metadata.version("soma-ai")`
- Mode names: OBSERVE/GUIDE/WARN/BLOCK
- Colors updated for new modes

### `soma mode`

Update terminology: remove "quarantine threshold" references, use "pressure boundaries" instead.

## What Stays Unchanged

- `soma config show/set`
- `soma replay`
- `soma` TUI (dashboard tabs already updated in 0.4.0)
- `soma init` / wizard
