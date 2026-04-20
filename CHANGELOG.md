# Changelog

## 2026.5.1

Released April 20, 2026.

Post-release self-audit uncovered 12 real bugs in the 5.0 surface.
All fixed here. Upgrade strongly recommended — 5.0 shipped with
the entropy_drop ceiling logic inverted, meaning diverse users
saw *more* false positives, not fewer.

### Fixes
- **entropy_drop ceiling inversion** — 5.0 used personal P75 as the
  healthy-diversity ceiling, which made the pattern more aggressive
  for diverse users (opposite of intent). Now uses P25 clamped to
  [0.5, 1.0] so a focused user's own low baseline is the floor and
  diverse users see legacy behavior.
- **calibration action-count integrity** — `profile.advance()` could
  double-count or lose actions if `save_profile` raised after the
  advance. Save now runs first; distribution refresh is a
  self-healing retry when defaults remain after a phase transition.
- **stop summary missed strict blocks** — strict-mode blocks are
  recorded with `mode="strict"` but the end-of-session counter only
  checked `"BLOCK"`. Now counts both.
- **typical_retry_burst duplicated error_burst** — two distinct
  fields computed identical values. `compute_distributions` accepts
  an optional `bash_retry_history` to decouple them.
- **SQLite FD leak** — `maybe_refresh_silence` opened an
  `AnalyticsStore` every `SILENCE_REFRESH_INTERVAL` actions and
  never closed it. Now closes connections it owns.
- **bell marker ordering** — pre_tool_use wrote the bell character
  before creating the once-only marker, so a partial filesystem
  failure could cause the bell to re-fire on every block.
- **mirror semantic path still emitted _stats** — CHANGELOG said
  "`_stats` no longer emits", but the semantic branch still
  prepended a stats one-liner. Now honestly no stats output on any
  branch.
- **`soma unblock --all --pattern X`** — silently dropped the
  pattern before. Now exits with an error when both are passed.
- **corrupt profile wipes** — `load_profile` on corrupt JSON
  silently started fresh; user lost accumulated calibration with
  no way to inspect. Now renames to `.corrupt` first.
- **statusline hot-path cost** — warmup probe now does a cheap
  mtime check before parsing JSON so Claude Code's frequent polling
  doesn't pay the JSON parse on every render.
- **`__version__` hardcoded** — was stuck at "2026.4.0" in
  `soma/__init__.py`. Now derives from `importlib.metadata` so
  `pyproject.toml` is the single source of truth.
- **CLI --help epilog missing** — `soma prune`, `soma unblock`,
  `soma healing` were missing from the top-level help listing.

### Quality
- 8 new regression tests in `test_audit_regressions.py` pin each
  bug so it cannot silently come back.
- 1569 tests passing.

## 2026.5.0

Released April 20, 2026.

**Major release — Self-Calibration + Strict Mode + Signal Pruning.**

### Self-Calibration Pipeline

SOMA now learns each user's personal baseline instead of shipping
hardcoded thresholds that fit a statistical average.

- **Warmup phase (0-99 actions)** — guidance stays silent while SOMA
  collects personal distributions (error bursts, drift percentiles,
  tool entropy). Statusline shows `learning N/100` so the user knows
  SOMA is working, not dead.
- **Calibrated phase (100-499)** — pattern checks use personal
  thresholds: `error_cascade_streak = max(typical_burst + 1, 3)`,
  `entropy_ceiling = max(personal_P75, 1.0)`, etc. Legacy floors
  guarantee quiet users don't accidentally disable signals.
- **Adaptive phase (500+)** — every 100 actions SOMA queries
  analytics for each tracked pattern's precision on this user. If a
  pattern helps <20% of the time over ≥20 fires, SOMA auto-silences
  it. If it climbs back above 40%, SOMA re-enables.
- Profiles share state across session ids: `cc-92331`, `cc-47512`,
  ... collapse to the `cc` family via regex so short-lived ids don't
  force a permanent warmup.
- Profile persistence at `~/.soma/calibration_{family}.json` with
  atomic writes and corrupt-file tolerance.

### Strict Mode

`[soma] mode = "strict"` in `soma.toml` turns text guidance into a
hard PreToolUse gate.

- When `retry_storm`, `blind_edit`, `bash_retry`, `error_cascade`, or
  `cost_spiral` fires, SOMA registers a persistent block against the
  specific tool.
- On the next PreToolUse, if a matching block is active, SOMA writes
  `⛔ SOMA(strict): …` to stderr with unblock instructions and exits
  with code 2 — the agent physically cannot proceed.
- `check_followthrough` clears the block on real recovery
  (Read-before-Edit, tool switch, etc.) so nothing requires manual
  unblock in the happy path.
- Strict mode is skipped during warmup, so fresh installs never
  hard-block while SOMA is still learning.
- Block state persists at `~/.soma/blocks_{family}.json`.
- `soma unblock --agent <id>` clears all blocks; `--pattern X`
  silences one pattern for 30 min; `--all` wipes every family.

### Signal Pruning

- **`_stats` emission dropped** — was 242 firings with 31% helped,
  the single biggest guidance-fatigue source. Mirror returns None
  at the two fallback paths that used to emit it, and the key no
  longer accumulates in `pattern_db` or `REAL_PATTERN_KEYS`.
- **`context` pattern re-armed** — P1.4 transcript-size proxy
  (stat-based, O(1) per hook) closes the audit item.

### User Visibility

- **Statusline** shows calibration phase in warmup, a red 🔴 marker
  with pattern list when strict-mode blocks are active.
- **End-of-session summary** (Stop hook, stdout) surfaces a
  `[SOMA session summary]` block that Claude Code reads back to the
  user in its final reply — interventions count, guidance
  effectiveness, calibration phase, unresolved blocks.

### Quality

- 107 new tests across `test_calibration.py`,
  `test_calibration_gate.py`, `test_calibration_thresholds.py`,
  `test_calibration_silence.py`, `test_blocks.py`,
  `test_strict_mode.py`, `test_visibility.py`, plus added tests for
  `_stats` drop.
- 1555 tests passing.
- Ruff clean.

### Breaking changes

- None in the public API. `ContextualGuidance(profile=None)` keeps
  legacy behavior for the `soma.wrap` SDK path and tests that
  haven't opted into calibration.

## 2026.4.5

Released April 19, 2026.

### Fire-rate fix: context / cost_spiral patterns
- fix: `context_usage` now derived from Claude Code's `transcript_path`
  (JSONL file size → token estimate at 4 chars/token, clamped to the
  agent's `context_window`). Internal `engine.cumulative_tokens` only
  tallied tool outputs, so context_usage stayed near 0% on real sessions
  and both `context` (needs ≥80%) and `cost_spiral` (needs ≥50% context)
  patterns never armed. Proxy is O(1) — single `stat()` per hook —
  and falls back cleanly when `transcript_path` is absent.
- fix: analytics `context_usage` column now uses `max(engine, transcript_proxy)`
  so cross-session trend graphs reflect real context growth.

### Setup: slash-command skills ship with the wheel
- fix: `[tool.hatch.build.targets.wheel.force-include]` now maps
  `skills/` → `src/soma/_skills/` so `pip install soma-ai` populates
  the bundled-location path that `_install_skills` already checks.
  Previously the wheel contained no `_skills` tree, so pip-installed
  users got an installer that silently no-op'd — `/soma:status`,
  `/soma:config`, `/soma:control`, and `/soma:help` were effectively
  dev-only. `soma setup-claude` now works out-of-the-box.
- test: 3 new tests in `test_setup.py` lock the packaging config,
  assert the repo `skills/` tree contains the canonical four skills,
  and exercise `_install_skills` against a simulated pip layout.

### Dashboard: single source of truth for pattern whitelist
- refactor: `_REAL_PATTERN_KEYS` in `dashboard/data.py` now imports
  `REAL_PATTERN_KEYS` from `contextual_guidance` (derived from
  `_PATTERN_PRIORITY` + `"_stats"`). Adding a new pattern to the
  priority map automatically unblocks it on the ROI dashboard — no
  second place to update and no way for the whitelist to drift apart
  from the evaluator.

### CLI: soma prune
- add: `soma prune [--older-than DAYS] [--yes]` removes stale session
  directories from `~/.soma/sessions/`. Dry-run by default (prints a
  preview + total size); `--yes` performs deletion. Default cutoff is
  30 days; value clamped to a minimum of 1 day. Real installs accumulate
  thousands of `cc-*` dirs from long-running hooks — this gives a clean
  way to reclaim disk without a manual `rm -rf`.

### Quality
- test: 12 new tests in `test_transcript_context.py` — helper edge cases
  (missing/empty/oversized files, zero window) + integration assertion
  that `context` pattern fires at 85% proxy fullness.
- test: 10 new tests in `test_prune_cli.py` covering stale detection,
  dry-run vs `--yes`, missing dirs, and day-count clamping.
- test: 2 new tests asserting `REAL_PATTERN_KEYS` stays derived from
  `_PATTERN_PRIORITY` and that `dashboard.data` imports the same object.
- 1466 tests passing.

## 2026.4.4

Released April 19, 2026.

### Signal Pruning
- remove: `retry_storm` pattern dropped — zero firings on real production agents; scenario is covered earlier by `bash_retry` (1st Bash fail) and `error_cascade` (3+ errors any tool). All historical firings originated from the `claude-code` catch-all (missing `SOMA_AGENT_ID`) and were data pollution. Removed from `_PATTERN_PRIORITY`, evaluation, `check_followthrough`, and dashboard whitelist.
- remove: `drift` pattern dropped from actionable guidance — 0% precision on real agents (9 firings). Drift remains as a vital signal; only guidance emission is removed.

### Data Hygiene
- fix: hook layer refuses to write `claude-code`, `test`, `nonexistent-agent`, or `test-*` agent ids into analytics.db. Catch-all sessions (missing `SOMA_AGENT_ID`) and fixture runs no longer contaminate ROI metrics.
- chore: one-shot purge of polluted rows from historical `~/.soma/analytics.db`; clean aggregation requires manual `DELETE` on upgrade.

### Precision Fixes
- fix: `blind_edit` no longer fires on `Write` to a non-existing file — previously 0% precision on real agents (20/0) because the pattern fired during legitimate file creation where there is nothing to read. Edit/Write on existing files still fires as before.

### Quality
- test: removed 14 tests tied to dropped patterns (retry_storm evaluate/followthrough, drift evaluate/followthrough).
- test: added 2 tests for blind_edit create-vs-edit distinction.
- 1439 tests passing.

## 2026.4.3

Released April 19, 2026.

### Precision Fixes (carried from 2026.4.2)
- fix: drift pattern — fire targeting tightened to tool-shift cases, Read/Grep/Glob recognized as explicit followthrough, threshold raised 0.3→0.5 to reduce low-signal firings, vague "refocus" message replaced with concrete "Re-read the original task spec or grep for the main keyword". Prior analytics showed 0% precision (19 firings, 0 helped).

### Repository Hygiene
- chore: TypeScript SDK source published — `packages/soma-ai/` (v0.1.0 alpha): engine, track, wrap, types + vitest suite
- chore: ROADMAP corrected — OpenTelemetry exporter and TypeScript SDK moved from Future to Shipped (both already implemented, mislabeled)
- chore: `.gitignore` hardened — `*_PLAN.md`, `benchmarks/`, `packages/*/dist/`, `graphify-out/` always ignored
- chore: 2026.4.2 yanked + replaced — internal planning file accidentally shipped in 2026.4.2; this release is the clean equivalent

### Known Issues (deferred)
- retry_storm: audit revealed all 28 production firings came from a single broken hook dispatcher session (claude-code agent_id, 384 consecutive Bash errors). Lowering detection threshold would amplify the artifact, not fix it. Fix requires session-type filtering in analytics aggregation — tracked for v2026.5.0.

## 2026.4.1

Released April 17, 2026.

### Guidance → Analytics Pipeline
- fix: `_record_outcome_if_resolved` bridges pattern firings to analytics.db guidance_outcomes
- fix: `_resolve_via_pressure` helper for implicit pattern resolution (drift/cost_spiral/context/budget/error_cascade)
- fix: ROI dashboard whitelist filter — excludes test-fixture pollution (test_key/retry_loop/mixed/bad_pattern/maybe_bad)
- fix: fastapi/uvicorn moved from `[dashboard]` extra to core deps (dashboard works out of the box)
- docs: 1449 tests passing, honest ROI dashboard numbers (348K real vs. 1039K inflated)

## 2026.4.0

Released April 17, 2026.

### ROI Dashboard
- feat: ROI page — "Is SOMA worth it?" single-page answer
- feat: session health score (0-100 from vitals)
- feat: tokens saved estimate from broken error cascades
- feat: pattern hit rates with follow-through tracking
- feat: guidance precision metrics

### Contextual Guidance Patterns
- feat: panic detector + followthrough for new patterns
- feat: healing transition prescriptions — data-backed tool suggestions
- feat: bash retry intercept — fires after 1st Bash fail before blind retry
- feat: tool entropy pattern — detects monotool tunnel vision

### Intelligence Pipeline
- feat: trigram similarity for lesson matching
- feat: contextual guidance — pattern-based deep injection replaces abstract pressure messages
- feat: source tagging in analytics.db (hook/wrap/unknown)

### Hooks & Integration
- fix: hook path wires lesson_store + baseline into ContextualGuidance
- fix: wrap.py _track_action passes error output for lesson matching
- fix: add PostToolUseFailure handler
- fix: cooldown persistence wired into post_tool_use.py
- fix: wrap() display_name gap — parameter now forwarded to WrappedClient
- feat: SOMAEngine.get_budget_health() method added
- feat: guidance effectiveness tracking — record outcomes to analytics

### Code Quality
- fix: coverage gaps + 3 pre-existing bugs from deep review
- fix: 2 bugs + 4 hardening fixes from code review
- chore: switch to CalVer versioning
- 1438 tests passing

## 0.7.0

Released April 15, 2026.

### Dashboard Rebuild
- feat: modular FastAPI backend with 14 route modules
- feat: Preact SPA with no build step (import maps + CDN)
- feat: WebSocket live updates with HTTP polling fallback
- feat: agent cards, session history, pressure timeline, tool stats
- feat: black + pink design system
- fix: settings save persistence
- fix: static file 404 from SPA catch-all route order

## 0.6.1

Released April 12, 2026.

- fix: repo cleanup — removed unnecessary tracked files
- docs: updated README and CHANGELOG

## 0.6.0

Released April 1, 2026.

- feat: async client support
- feat: streaming interception (Anthropic + OpenAI)
- feat: context window tracking
- feat: bimodal pressure fix (linear ramp + error floor)
- feat: session state isolation fix
- fix: 13 bugs found via deep audit
- PyPI published as `soma-ai`
