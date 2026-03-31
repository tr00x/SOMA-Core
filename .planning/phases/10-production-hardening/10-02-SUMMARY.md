---
phase: 10-production-hardening
plan: 02
subsystem: testing
tags: [integration-tests, api-validation, anthropic, openai, real-api]

requires:
  - phase: 10-production-hardening
    plan: 01
    provides: context tracking and audit logging infrastructure
provides:
  - Real API validation for soma.wrap() with both Anthropic and OpenAI

key-files:
  created:
    - tests/test_integration_api.py
  modified: []
---

## What was built

Real API integration tests for soma.wrap() covering both Anthropic and OpenAI providers. 6 tests total: sync, async, and streaming variants for Anthropic; sync and streaming for OpenAI. All tests skip gracefully when API keys are not set (CI-safe via `@pytest.mark.skipif`).

## Tasks completed

| # | Task | Status |
|---|------|--------|
| 1 | Create real API integration tests | ✓ |
| 2 | Verify real API tests pass | ○ Checkpoint (requires API keys) |

## Deviations

None. Tests match the plan specification exactly.

## Self-Check: PASSED

- [x] tests/test_integration_api.py exists with 6 tests
- [x] Tests skip without API keys (768 passed, 5 skipped in full suite)
- [x] Covers sync, async, streaming for Anthropic
- [x] Covers sync, streaming for OpenAI
- [x] Each test verifies action_count, pressure, response content
