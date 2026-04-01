---
phase: 11-context-window-tracking
plan: 01
subsystem: engine
tags: [exporter, context-window, pressure, model-detection, eventbus]

# Dependency graph
requires: []
provides:
  - Exporter protocol in src/soma/exporters/__init__.py
  - Model context window lookup in src/soma/models.py
  - context_exhaustion pressure signal with weight 1.5
  - context_burn_rate field in VitalsSnapshot
  - add_exporter()/shutdown() on SOMAEngine
  - action_recorded event emission after every record_action()
  - Proactive context_warning (70%) and context_critical (90%) events
  - Model auto-detection in wrap.py via get_context_window()
affects: [11-02, 11-03, otel-exporter, webhooks, reports, analytics]

# Tech tracking
tech-stack:
  added: []
  patterns: [runtime_checkable Protocol for exporters, EventBus subscription wiring, sigmoid-based context exhaustion]

key-files:
  created:
    - src/soma/exporters/__init__.py
    - src/soma/models.py
    - tests/test_models.py
  modified:
    - src/soma/types.py
    - src/soma/pressure.py
    - src/soma/engine.py
    - src/soma/wrap.py
    - tests/test_context_usage.py

key-decisions:
  - "Exporter protocol uses runtime_checkable Protocol for duck-typing compatibility"
  - "Context exhaustion uses sigmoid_clamp((usage - 0.5) / 0.15) for smooth pressure curve"
  - "Model lookup uses longest-prefix match for versioned model names"
  - "Model auto-detection fires once per WrappedClient lifetime to avoid repeated lookups"

patterns-established:
  - "Exporter Protocol: implement on_action, on_mode_change, shutdown"
  - "EventBus wiring: add_exporter subscribes to action_recorded and level_changed"
  - "Proactive events: fire-once flags on _AgentState for threshold events"

requirements-completed: [OTL-01, ALT-01]

# Metrics
duration: 5min
completed: 2026-03-31
---

# Phase 11 Plan 01: Context Window Foundation Summary

**Exporter protocol, model context windows with prefix matching, context exhaustion pressure signal, burn rate tracking, proactive events, and wrap.py model auto-detection**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T23:58:05Z
- **Completed:** 2026-04-01T00:03:13Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Exporter protocol defined with on_action/on_mode_change/shutdown methods, importable from soma.exporters
- Model context window lookup supporting Anthropic and OpenAI models with exact, prefix, and default fallback
- Context exhaustion is now a first-class pressure signal (weight 1.5) computed via sigmoid curve
- Engine emits action_recorded event after every record_action(), enabling all downstream exporters
- wrap.py auto-detects model name from API responses and updates engine context window size

## Task Commits

Each task was committed atomically:

1. **Task 1: Create exporter protocol and model context windows** - `1b59c50` (feat)
2. **Task 2 RED: Failing tests** - `5ab392f` (test)
3. **Task 2 GREEN: Implementation** - `d87bec3` (feat)

## Files Created/Modified
- `src/soma/exporters/__init__.py` - Exporter Protocol (runtime_checkable) with on_action, on_mode_change, shutdown
- `src/soma/models.py` - MODEL_CONTEXT_WINDOWS dict + get_context_window() with prefix matching
- `tests/test_models.py` - 6 tests for model lookup (exact, prefix, unknown, specific models)
- `src/soma/types.py` - Added context_burn_rate field to VitalsSnapshot
- `src/soma/pressure.py` - Added context_exhaustion weight 1.5 to DEFAULT_WEIGHTS
- `src/soma/engine.py` - Added add_exporter, shutdown, context exhaustion/burn rate/proactive events, action_recorded emission
- `src/soma/wrap.py` - Added model auto-detection via get_context_window() on first API response
- `tests/test_context_usage.py` - Extended from 9 to 22 tests covering all new features

## Decisions Made
- Used runtime_checkable Protocol for exporters (duck-typing, no base class inheritance required)
- Context exhaustion formula: sigmoid_clamp((usage - 0.5) / 0.15) gives ~0.0 at 50%, high pressure at 85%+
- Model lookup uses longest-prefix match so versioned names (e.g. claude-3-opus-20240229-beta) resolve correctly
- Model detection fires once per WrappedClient to avoid repeated dictionary lookups on every API call

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data sources are wired and functional.

## Next Phase Readiness
- Exporter protocol ready for OTel exporter (11-02), webhook exporter (11-03)
- action_recorded event provides all data needed by exporters
- Model auto-detection ensures context window sizing works transparently with wrap.py

---
*Phase: 11-context-window-tracking*
*Completed: 2026-03-31*
