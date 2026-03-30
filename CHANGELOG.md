# Changelog

## [0.4.12] — 2026-03-30

Multi-agent core hardening: concurrent safety, agent lifecycle, learning validation.

### Added
- Atomic persistence with file locking (`fcntl` + temp file + `os.rename`) — safe for concurrent multi-agent writes
- Agent TTL eviction — `engine.evict_stale_agents(ttl_seconds=3600)` removes dead agents from state
- Shared engine support in `wrap()` — `soma.wrap(client, engine=shared_engine)` for multi-agent pipelines
- Multi-agent stress tests: 5 concurrent agents, trust propagation, pipeline scenarios
- Learning convergence validation: thresholds proven bounded, non-oscillating

### Fixed
- Persistence race condition: concurrent saves no longer corrupt state file
- Lock held across full write cycle (mkstemp → fsync → rename)
- Windows compatibility: `fcntl` import guarded, graceful fallback

## [0.4.11] — 2026-03-30

Core polish sprint: false positive reduction, actionable feedback, layer-agnostic architecture, and visibility fixes across 11 micro-releases.

### Architecture
- **Layer-agnostic intelligence** — pattern analysis, findings collection, workflow context extracted from Claude Code hooks into core modules (`soma/patterns.py`, `soma/findings.py`, `soma/context.py`)
- `notification.py` reduced from 420 to 154 lines — now a thin Claude Code formatter
- New layers (Cursor, Windsurf, etc) get full intelligence by importing core modules

### Added
- `soma doctor` — check installation health (hooks, binary, state, version)
- Auto-migrate soma.toml old keys on first hook run
- Ruff lint in CI pipeline (GitHub Actions), ruff config in pyproject.toml
- `detect_workflow_mode()` reads .planning/STATE.md for GSD context
- Workflow-aware severity: patterns suppressed when they'd be noise during plan/discuss/execute
- Positive feedback: `[✓] read-before-edit maintained` and `[✓] clean streak` when doing well
- `TaskTracker.get_efficiency()` — context_efficiency, success_rate, focus metrics
- Phase-aware header: `SOMA: #42 [implement] ctx=73% focused`
- Directive prompt injections: `[do] Read before editing` replaces `[pattern] 3 blind edits`
- WARN/BLOCK messages include specific recovery guidance
- Tests for `_collect_findings`, engine threshold propagation, config migration

### Changed
- Threshold config keys renamed: `caution`/`degrade`/`quarantine` -> `guide`/`warn`/`block`
- `restart` threshold removed — SOMA no longer has a restart concept
- `pressure_to_mode()` and `evaluate()` accept optional `thresholds` dict
- Engine uses `custom_thresholds` for mode transitions
- `stale_timeout` configurable via `[hooks]` section in soma.toml
- Grace period reduced to 3 actions (was: full silence below 10% pressure)
- Findings always collected and shown when present, regardless of pressure
- Periodic header every 15 actions when no findings
- Positive feedback thresholds lowered: 3 read-edit pairs (was 5), 10 clean actions (was 15)
- Agent spawn suggestions suppressed when GSD active
- Status line shows `ctx:high focus:focused` when healthy instead of raw vitals

### Fixed
- Scope drift uses cwd-relative paths — moving between `src/` and `tests/` no longer triggers false drift
- "Edit without Read" no longer fires when file was recently read via Read/Grep/Glob (checks last 30 actions)
- Pattern analysis skipped at very low pressure (<10%) — reduces noise in healthy sessions
- `_collect_findings` used stale level names (DEGRADE/QUARANTINE) — now uses WARN/BLOCK
- RCA priority checked "HEALTHY" instead of "OBSERVE"
- `soma mode` command uses new threshold key names
- Notification `ctx=0%` on cold start — now requires 10+ actions
- `detect_workflow_mode` fallback to `os.getcwd()` when env var missing
- All lint errors across core modules (unused imports, f-strings)
- SOMA visibility: silent mode at p<10% and suppression at p<25% meant agent never saw SOMA output

## [0.4.0] — 2026-03-30

Redesigned from a blocking system to a guidance system. SOMA no longer blocks normal tools at any pressure level — it guides the agent with increasingly urgent feedback, and only blocks truly destructive operations.

### Changed
- **Guidance over blocking**: replaced 6-level escalation ladder (HEALTHY -> CAUTION -> DEGRADE -> QUARANTINE -> RESTART -> SAFE_MODE) with 4-mode guidance system (OBSERVE -> GUIDE -> WARN -> BLOCK)
- **OBSERVE (0-24%)**: silent monitoring, metrics only (replaces HEALTHY)
- **GUIDE (25-49%)**: soft suggestions injected into context, never blocks (replaces CAUTION)
- **WARN (50-74%)**: insistent warnings, still never blocks normal tools (replaces DEGRADE)
- **BLOCK (75-100%)**: blocks ONLY destructive operations — `rm -rf`, `git push --force`, `.env` file writes (replaces QUARANTINE/RESTART)
- Write, Edit, Bash, and Agent tools are **never blocked** at any pressure level
- Central decision engine moved to new `guidance.py` module
- `ladder.py` and `Ladder` class deleted
- Threshold config keys renamed: `caution`/`degrade`/`quarantine` -> `guide`/`warn`/`block`
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
