---
phase: 09-async-streaming
plan: 01
subsystem: api
tags: [async, asyncio, wrap, anthropic, openai, pytest-asyncio]

requires:
  - phase: 08-typescript-policy
    provides: complete engine + sync wrapper

provides:
  - async-aware soma.wrap() that detects and wraps async client methods
  - _make_async_wrapper method mirroring sync wrapper with await
  - async test suite with 8 test cases

affects: [09-02-streaming, 10-production-hardening]

tech-stack:
  added: [pytest-asyncio]
  patterns: [inspect.iscoroutinefunction for async detection, async wrapper mirroring sync wrapper]

key-files:
  created: [tests/test_wrap_async.py]
  modified: [src/soma/wrap.py, pyproject.toml]

key-decisions:
  - "Async detection via inspect.iscoroutinefunction at wrap time, not call time"
  - "engine.record_action() called synchronously from async wrapper (CPU-bound, no await needed)"
  - "Async wrapper duplicates sync wrapper logic rather than abstracting (keeps both simple and independent)"

patterns-established:
  - "Async wrapper pattern: mirror sync wrapper with async def + await on original_fn"
  - "Async test pattern: MockAsync* classes with async def create methods"

requirements-completed: [ASYNC-01]

duration: 2min
completed: 2026-03-31
---

# Phase 9 Plan 1: Async Client Wrapper Summary

**Async-aware soma.wrap() using inspect.iscoroutinefunction to detect and wrap async Anthropic/OpenAI clients with full SOMA pipeline**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T15:10:20Z
- **Completed:** 2026-03-31T15:12:40Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- soma.wrap(async_client) detects async methods and wraps with async closures
- await wrapped.messages.create() runs full SOMA pipeline (pre-check, budget, API call, record_action)
- Async wrapper handles SomaBlocked, SomaBudgetExhausted, and API errors identically to sync
- Both Anthropic and OpenAI async clients supported
- All 743 tests pass (20 sync wrap + 8 async wrap + 715 other)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing async tests** - `1a3a9ce` (test)
2. **Task 1 GREEN: Implement async wrapper** - `5e05642` (feat)

_TDD task: test commit followed by implementation commit_

## Files Created/Modified
- `src/soma/wrap.py` - Added _make_async_wrapper method, async detection in _wrap_client
- `tests/test_wrap_async.py` - 8 async test cases covering happy path, errors, blocking, budget
- `pyproject.toml` - Added pytest-asyncio to dev dependencies

## Decisions Made
- Used inspect.iscoroutinefunction for async detection at wrap time (not runtime type checking)
- engine.record_action() called synchronously from async wrapper since it is CPU-bound computation
- Duplicated context action logic in async wrapper rather than extracting shared helper (keeps wrappers self-contained and easy to read)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Async wrapper complete, ready for 09-02 streaming interception
- pytest-asyncio available for streaming tests

---
*Phase: 09-async-streaming*
*Completed: 2026-03-31*
