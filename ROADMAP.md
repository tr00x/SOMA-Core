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

---

## Next: Data Validation (May 2026)

Requires 2+ weeks of clean data from production usage.

- Validate healing transition numbers from real data
- Calibrate entropy threshold (1.0 vs 0.8 vs 1.2)
- Task complexity proxy from initial tool entropy
- Predictive budgeting from session clustering
- Guidance reinforcement learning (boost effective patterns, dampen ignored)

## Future

- Autonomous model switching (Opus→Sonnet on cost spiral via wrap)
- Pressure reset detector (context compaction detection)
- Multi-framework adapters (LangChain, CrewAI, AutoGen)
- OpenTelemetry export
