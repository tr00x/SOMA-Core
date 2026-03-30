# Changelog

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
