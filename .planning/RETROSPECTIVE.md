# SOMA Retrospective

Living document. Updated at milestone boundaries.

---

## Milestone: v0.5.0 — Production Ready

**Shipped:** 2026-03-31
**Phases:** 2 (9-10) | **Plans:** 6

### What Was Built
- Async client wrapper: `soma.wrap(AsyncAnthropic())` with full pipeline
- Streaming interception for Anthropic (context manager) and OpenAI (iterator)
- Context window tracking with half-life degradation factor
- Structured JSON Lines audit logging with rotation
- Real API integration tests (5 tests, Anthropic + OpenAI)
- CONTRIBUTING.md, PyPI 0.5.0 published

### What Worked
- TDD approach on streaming wrappers caught API surface issues early
- Real API integration tests found a genuine streaming bug (MessageStreamManager vs MessageStream context entry) — the exact kind of bug mocks would miss
- Gap closure workflow handled the human-gated checkpoints cleanly
- Parallel plan execution saved time on independent Wave 2 plans

### What Was Inefficient
- Wave 2 agents hit rate limits and had to be completed inline — parallel Opus agents are expensive
- anthropic/openai SDKs weren't in dev dependencies — integration tests failed on import before any API call
- REQUIREMENTS.md traceability table was stale (DSH-01-04 mapped to Phase 10 incorrectly)

### Patterns Established
- Real API tests should always be in the test suite (skip without keys, run with keys)
- `soma.wrap()` context manager pattern: always capture `__enter__` return value
- Gap closure plans work well for human-gated items (API keys, publishing)

### Key Lessons
- Mock-only testing is insufficient for API wrappers — real API tests found a bug that 35 mock tests missed
- Rate limits are a real constraint for parallel Opus agents — consider sequential execution or Sonnet for executor agents
- Dev dependencies (anthropic, openai SDKs) should be in optional extras for integration testing

---

## Cross-Milestone Trends

| Metric | v0.5.0 |
|--------|--------|
| Phases | 2 |
| Plans | 6 |
| Tests | 773 |
| LOC | 10,169 |
| Timeline | 1 day |
