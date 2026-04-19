# Changelog

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
