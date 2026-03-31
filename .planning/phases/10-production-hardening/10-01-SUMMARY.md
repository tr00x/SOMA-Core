---
phase: 10-production-hardening
plan: 01
subsystem: core
tags: [context-tracking, audit-logging, json-lines, half-life, vitals]

requires:
  - phase: 09-async-streaming
    provides: wrap() and engine pipeline foundation
provides:
  - VitalsSnapshot.context_usage field tracking cumulative tokens as fraction of context window
  - AuditLogger writing JSON Lines to ~/.soma/audit.jsonl
  - Context degradation factor applied to half-life predicted_success_rate
affects: [hooks, dashboard, wrap, persistence]

tech-stack:
  added: []
  patterns: [json-lines-audit, context-window-degradation-model]

key-files:
  created:
    - src/soma/audit.py
    - tests/test_context_usage.py
    - tests/test_audit.py
  modified:
    - src/soma/types.py
    - src/soma/engine.py
    - src/soma/__init__.py

key-decisions:
  - "Context degradation uses linear factor: max(0.4, 1.0 - usage*0.6) applied to predicted_success_rate"
  - "Audit log rotation at 10MB with timestamped backup files"
  - "Audit is zero-config (on by default) and never crashes the engine on write failure"

patterns-established:
  - "JSON Lines for structured logs: one valid JSON object per line, jq-compatible"
  - "Context window tracking: cumulative tokens per agent, configurable window size"

requirements-completed: [CTX-01, LOG-01]

duration: 5min
completed: 2026-03-31
---

# Phase 10 Plan 01: Context Usage Tracking and Audit Logging Summary

**VitalsSnapshot.context_usage tracks cumulative tokens as fraction of context window; AuditLogger writes JSON Lines per action to ~/.soma/audit.jsonl with rotation**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T15:39:05Z
- **Completed:** 2026-03-31T15:44:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added context_usage field to VitalsSnapshot with cumulative token tracking per agent
- Context degradation factor reduces predicted_success_rate as context fills (0.7 usage -> 0.58x multiplier)
- Created AuditLogger writing append-only JSON Lines with 6 required fields (timestamp, agent_id, tool_name, error, pressure, mode)
- Audit log is zero-config, auto-rotates at 10MB, parseable by jq

## Task Commits

Each task was committed atomically:

1. **Task 1: Add context_usage to VitalsSnapshot and integrate with half-life** - `685a68f` (feat)
2. **Task 2: Add structured audit logging (JSON Lines)** - `dd1ce0e` (feat)

_Note: TDD tasks had RED/GREEN phases within each commit_

## Files Created/Modified
- `src/soma/types.py` - Added context_usage field to VitalsSnapshot
- `src/soma/engine.py` - Added context_window param, cumulative_tokens tracking, context degradation, AuditLogger integration
- `src/soma/audit.py` - New AuditLogger class with JSON Lines output and rotation
- `src/soma/__init__.py` - Exported AuditLogger in public API
- `tests/test_context_usage.py` - 9 tests for context window tracking
- `tests/test_audit.py` - 9 tests for audit logging

## Decisions Made
- Context degradation uses linear factor `max(0.4, 1.0 - usage*0.6)` -- at 70% usage success multiplied by 0.58, at 100% by 0.4
- Default context window is 200k tokens (Claude's typical window), configurable via constructor or soma.toml
- Audit log silently catches OSError to never crash the engine for logging failures
- Rotation uses timestamp suffix for backup files (audit.1711900000.jsonl)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Context usage and audit logging are wired into the engine pipeline
- Both features are zero-config and backward compatible
- 768 tests passing with no regression

---
*Phase: 10-production-hardening*
*Completed: 2026-03-31*
