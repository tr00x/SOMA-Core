# Changelog

## [0.4.5] — 2026-03-30

### Fixed
- "Edit without Read" no longer fires when file/directory was recently read via Read/Grep/Glob
- Pattern detection checks last 30 actions for read context, not just sequential edits

## [0.4.4] — 2026-03-30

### Added
- Ruff lint in CI pipeline (GitHub Actions)
- Ruff config in pyproject.toml with per-file ignores

### Fixed
- All lint errors across core modules (unused imports, f-strings)

## [0.4.3] — 2026-03-30

### Added
- `soma doctor` — check installation health (hooks, binary, state, version)
- Auto-migrate soma.toml old keys on first hook run

### Fixed
- `soma mode` command uses new threshold key names

## [0.4.2] — 2026-03-30

### Fixed
- Scope drift uses cwd-relative paths — moving between `src/` and `tests/` in same project no longer triggers false drift
- Skip pattern analysis at very low pressure (<10%) — reduces noise in healthy sessions
- GSD active suppresses agent spawn suggestions — agent spawning is expected in workflows

## [0.4.1] — 2026-03-30

### Changed
- Threshold config keys renamed: `caution`/`degrade`/`quarantine` → `guide`/`warn`/`block`
- `restart` threshold removed — SOMA no longer has a restart concept
- `pressure_to_mode()` and `evaluate()` accept optional `thresholds` dict
- Engine uses `custom_thresholds` for mode transitions
- `stale_timeout` configurable via `[hooks]` section in soma.toml

### Added
- `migrate_config()` auto-migrates old config keys on load
- `get_guidance_thresholds()` loads thresholds from soma.toml for hooks

## [0.4.0] — 2026-03-30

Redesigned from a blocking system to a guidance system. SOMA no longer blocks normal tools at any pressure level — it guides the agent with increasingly urgent feedback, and only blocks truly destructive operations.

### Changed
- **Guidance over blocking**: replaced 6-level escalation ladder (HEALTHY → CAUTION → DEGRADE → QUARANTINE → RESTART → SAFE_MODE) with 4-mode guidance system (OBSERVE → GUIDE → WARN → BLOCK)
- **OBSERVE (0-24%)**: silent monitoring, metrics only (replaces HEALTHY)
- **GUIDE (25-49%)**: soft suggestions injected into context, never blocks (replaces CAUTION)
- **WARN (50-74%)**: insistent warnings, still never blocks normal tools (replaces DEGRADE)
- **BLOCK (75-100%)**: blocks ONLY destructive operations — `rm -rf`, `git push --force`, `.env` file writes (replaces QUARANTINE/RESTART)
- Write, Edit, Bash, and Agent tools are **never blocked** at any pressure level
- Central decision engine moved to new `guidance.py` module
- `ladder.py` and `Ladder` class deleted
- Threshold config keys renamed: `caution`/`degrade`/`quarantine` → `guide`/`warn`/`block`
- Dead command queue IPC (`commands.py`) deleted

### Added
- `soma stop` — stop SOMA monitoring
- `soma start` — start SOMA monitoring
- `soma uninstall-claude` — remove SOMA hooks from Claude Code

### Removed
- `soma quarantine` — manual quarantine no longer exists
- `soma release` — no quarantine means no release
- `soma approve` — approval queue removed
- `soma daemon` — daemon mode removed
- `soma export` — export command removed
- Slash command `/soma:control quarantine` removed
- Slash command `/soma:control release` removed

### Fixed
- `soma reset` now works directly (was broken due to IPC indirection)

### Upgrading from 0.3.x

1. **Config**: rename threshold keys in `soma.toml`:
   ```toml
   # Old
   [thresholds]
   caution = 0.25
   degrade = 0.50
   quarantine = 0.75

   # New
   [thresholds]
   guide = 0.25
   warn = 0.50
   block = 0.75
   ```

2. **Code**: if you imported `Ladder` or `Level`, switch to `Guidance` and `Mode` from `soma.guidance`

3. **CLI scripts**: remove any references to `soma quarantine`, `soma release`, `soma approve`, `soma daemon`, `soma export`

4. **Slash commands**: `/soma:control quarantine` and `/soma:control release` no longer exist. Use `/soma:control reset` to reset baselines.
