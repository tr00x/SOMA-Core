# Changelog

## 2026.4.2

Released April 18, 2026.

### Precision Fixes
- fix: drift pattern — fire targeting tightened to tool-shift cases, Read/Grep/Glob recognized as explicit followthrough, threshold raised 0.3→0.5 to reduce low-signal firings, vague "refocus" message replaced with concrete "Re-read the original task spec or grep for the main keyword". Prior analytics showed 0% precision (19 firings, 0 helped) — all firings landed in low-pressure contexts where the pressure-drop fallback was mathematically unreachable.

### Known Issues (deferred to 2026.4.3)
- retry_storm: audit revealed all 28 firings in analytics came from a single broken hook dispatcher session (claude-code agent_id, 384 consecutive Bash errors). Lowering detection threshold would amplify the artifact, not fix it. Fix requires session-type filtering in analytics aggregation — tracked for next release.

### Docs
- docs: PRODUCTION_PLAN.md — honest per-pattern precision metrics + P0/P1/P2 roadmap

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
