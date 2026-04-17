# Changelog

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
