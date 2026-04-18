# Roadmap

## Current: v2026.4.2

9 guidance patterns | 1451 tests | Python 3.11+ | MIT

Two integration paths: hooks (zero-code for Claude Code) and `soma.wrap()` (any LLM SDK).

---

## Shipped

### Intelligence Pipeline (April 2026)
- 9 contextual guidance patterns with priority ranking
- Healing transitions: Bash→Read ↓7%, Edit→Read ↓5%, Write→Grep ↓5%
- Panic detector (entropy × velocity escalation)
- Cross-session lessons with trigram similarity matching
- Analytics source tagging and data cleanup
- Persistent cooldowns and followthrough tracking

### ROI Dashboard (April 2026)
- "Is SOMA worth it?" single-page answer
- Session health score, tokens saved, cascades broken
- Pattern hit rates with follow-through visualization
- FastAPI backend, Preact frontend, 5s auto-polling

### Web Dashboard (April 2026)
- Modular FastAPI backend (14 route modules)
- Preact SPA — no build step, import maps + CDN
- WebSocket live updates with HTTP polling fallback
- Agent cards, session history, pressure charts, tool stats

### Core Engine (March 2026)
- Vitals pipeline: uncertainty, drift, error rate, token usage, cost
- EMA baseline with cold-start blending
- Pressure graph with trust-weighted propagation
- 4-mode guidance: OBSERVE → GUIDE → WARN → BLOCK
- `soma.wrap()` SDK wrapper
- Claude Code hooks
- Session recording + replay
- Atomic state persistence with file locking

### TypeScript SDK (alpha)
- `packages/soma-ai` npm package (v0.1.0)
- Core exports: `SOMAEngine`, `quickstart`, `track`, `wrap`
- Parity surface with Python `soma.wrap()` for JS/TS agents
- Vitest test suite

### OpenTelemetry Exporter
- `src/soma/exporters/otel.py` — OTLP trace + metric export
- Optional `otel` extra in pyproject
- Integration tests in `tests/test_otel_exporter.py`

### Framework Adapters
- LangChain, CrewAI, AutoGen examples in `examples/`

---

## Next: v2026.5.0 — Self-Calibration + Strict Mode (April–May 2026)

Full plan in `SELF_CALIBRATION_PLAN.md`. Release blocks external marketing.

- **Self-calibration:** per-user warmup (0-100 actions) → calibrated thresholds from percentiles → adaptive auto-silence of noisy patterns
- **Strict mode:** PreToolUse hard blocks replace passive advice; `soma unblock` CLI
- **Signal pruning:** drop `_stats` (31% noise), audit `context` trigger, keep `entropy_drop` subject to auto-silence
- **User visibility:** colored statusline, terminal bell, end-of-session summary

## Future

- Predictive budgeting from session clustering
- Autonomous model switching (Opus→Sonnet on cost spiral via wrap)
- Pressure reset detector (context compaction detection)
- Guidance reinforcement learning (boost effective patterns, dampen ignored)
- TypeScript SDK → v1.0 + npm publish
