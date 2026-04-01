# SOMA Production Setup Report

## Installation

```bash
pip install soma-ai
soma install --mode reflex
```

## Commands

### `soma install [--mode observe|guide|reflex] [--profile claude-code|strict|relaxed|autonomous]`

One-command setup for Claude Code. Installs hooks, statusline, engine state, soma.toml, and slash commands. Then applies the chosen mode and profile to soma.toml. `soma update` is an alias.

Default: `--mode reflex --profile claude-code`

### `soma stats [--week] [--all]`

Session statistics from session_store history. Shows:
- Session count, total actions
- Average and peak pressure
- Error count and rate
- Patterns caught (tool distribution heuristic)
- Best session (lowest errors), worst session (highest pressure)
- Week-over-week comparison (with `--week` and enough data)

Default time range: today. Use `--week` for 7 days, `--all` for everything.

### `soma replay --last | --worst | --session N`

Replay sessions from session_store without needing a file path:
- `--last`: most recent session
- `--worst`: session with highest peak pressure
- `--session N`: Nth session (0 = most recent)

Shows action-by-action pressure trajectory with tool names, error/pattern markers.

File-based replay (`soma replay <file>`) still works as before.

### Enhanced stop hook summary

The stop hook now prints a richer summary for notable sessions (>=10 actions OR peak pressure >30%):

```
── SOMA Session ──────────────────
Duration: 12min  Actions: 45  Grade: B (82%)
Peak: 38% at action #23
Errors: 2/45 (4%)
Pattern: Read heavy (28/45 actions)
────────────────────────────────────
```

Short/quiet sessions get a minimal one-liner: `SOMA: 5 actions, p=3%`

## Known Limitations

- `soma stats` and `soma replay --last/--worst` require session_store data, which is only written when Claude Code sessions end (stop hook). No data appears until at least one session completes.
- `soma replay --session N` action-by-action tool assignment is approximate -- tool distribution is known but exact action order is not preserved in session_store.
- Error markers in replay are approximate (errors are counted but not tied to specific action indices in session_store).
- `soma install` always runs full setup (hooks, statusline, etc.) even if only mode/profile change is needed. Existing installations skip already-configured items.
- Week-over-week comparison in `soma stats --week` requires sessions from the previous week to be present in history.jsonl.
