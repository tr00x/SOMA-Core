# Phase 13: Intelligence — Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

SOMA predicts problems before they happen using cross-session learning. But first — prove that SOMA's core guidance loop actually changes agent behavior. Without proof, everything built on top is wasted effort.

**Revised scope:** Benchmark-first intelligence. Build the proof infrastructure, run real A/B comparisons, then use that data to power cross-session learning and smarter predictions.

</domain>

<decisions>
## Implementation Decisions

### Benchmark architecture (priority #1)
- **D-01:** Build a benchmark harness that runs identical tasks with SOMA enabled vs disabled
- **D-02:** Tasks are Python scripts that simulate realistic agent sessions (not toy examples) — file editing, debugging, multi-step implementations
- **D-03:** Metrics collected per run: total errors, retries, tool calls, tokens used, time, drift, final code quality (pass/fail tests)
- **D-04:** Results stored as JSON, rendered as rich terminal tables AND markdown for README
- **D-05:** Minimum 3 scenarios: healthy session, degrading session, multi-agent coordination
- **D-06:** Each scenario runs 5x with and 5x without SOMA for statistical significance
- **D-07:** Benchmark is a CLI command: `soma benchmark` — anyone can reproduce

### What we're measuring
- **D-08:** Primary metric: error reduction rate (errors with SOMA / errors without)
- **D-09:** Secondary metrics: retry reduction, token savings, time to completion
- **D-10:** Tertiary: mode transition accuracy (did GUIDE fire at the right time?), false positive rate
- **D-11:** Deep engine metrics per action: pressure, all 5 vitals, mode, guidance issued, was guidance followed

### Cross-session learning (ANOM-01, TUNE-01)
- **D-12:** Session history in append-only JSON Lines at `~/.soma/sessions/` — one file per session, lightweight
- **D-13:** Threshold tuning uses benchmark data — statistical optimization (percentile-based), not ML models. Keep it simple, explainable, no sklearn dependency
- **D-14:** Anomaly prediction extends existing PressurePredictor with cross-session pattern matching — "last 3 sessions showed this pattern before escalation"

### Semantic task monitoring (TASK-01)
- **D-15:** No LLM calls for monitoring — too expensive, too slow, creates dependency
- **D-16:** Use existing behavior vectors weighted by detected task phase (exploring/implementing/testing/debugging) — phase detection from tool usage patterns already in context.py

### Output and presentation
- **D-17:** Benchmark results go in `docs/BENCHMARK.md` — auto-generated, always reproducible
- **D-18:** Summary table for README showing before/after with real numbers
- **D-19:** Rich terminal output during benchmark run — live progress, per-scenario results

### Claude's Discretion
- Exact scenario scripts and action sequences
- JSON schema for session history
- Statistical methods for threshold optimization
- Terminal output formatting details

</decisions>

<specifics>
## Specific Ideas

- User wants "пруфы на лицо" — proof that's undeniable, detailed, from every layer of the engine
- Benchmark should be beautiful and compelling — not just numbers in a table, but a story: "agent was failing, SOMA guided it back"
- The benchmark IS the marketing — if the numbers are good, they go straight to README
- If the numbers are bad — we know what to fix in guidance before building anything else on top

</specifics>

<canonical_refs>
## Canonical References

### Existing intelligence modules
- `src/soma/predictor.py` — PressurePredictor with linear trend + pattern boost
- `src/soma/learning.py` — LearningEngine adaptive thresholds via intervention outcomes
- `src/soma/halflife.py` — Temporal reliability decay modeling
- `src/soma/context.py` — SessionContext, workflow mode detection
- `src/soma/baseline.py` — EMA baselines with cold-start blending

### Existing test infrastructure
- `tests/test_stress.py` — 16 stress scenarios (reusable as benchmark seeds)
- `tests/test_integration.py` — Integration test scenarios
- `docs/INTEGRATION-TEST-REPORT.md` — 4 scenarios with 231 actions

### Requirements
- `.planning/milestones/v0.5.0-REQUIREMENTS.md` lines 99-102 — PRED-01, TUNE-01, TASK-01, ANOM-01

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SOMAEngine` + `record_action()` — full pipeline already works, benchmark wraps it
- `demo_session.py` — pattern for scripted scenarios with real engine
- `SessionRecorder` — can record/replay sessions, useful for reproducible benchmarks
- `stress.py` scenarios — 16 pre-built degradation patterns

### Established Patterns
- Rich terminal output (used in demo_session.py, CLI)
- JSON Lines for structured data (audit.py)
- Atomic file writes (persistence.py)

### Integration Points
- Benchmark extends CLI (`soma benchmark`)
- Session history extends persistence layer
- Cross-session predictor extends existing PressurePredictor

</code_context>

<deferred>
## Deferred Ideas

- Web dashboard visualization of benchmark results — Phase 14
- Community benchmarks / collective learning (BEN-02) — Phase 15
- Open research datasets from benchmark data (SAF-02) — Phase 15

</deferred>

---

*Phase: 13-config-validation*
*Context gathered: 2026-04-01*
