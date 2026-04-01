# Phase 16: Advanced Reflexes - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Multi-agent circuit breakers, session memory injection, smart throttle, fingerprint anomaly detection, and context overflow management. The final wave of nervous system capabilities.

</domain>

<decisions>
## Implementation Decisions

### Graph Circuit Breaker
- **D-01:** When agent pressure > BLOCK for 5+ consecutive actions → circuit opens, trust → 0.1
- **D-02:** Recovery: 10 consecutive OBSERVE actions → circuit closes, trust rebuilds at normal rate
- **D-03:** Alert injected: "Agent {X} quarantined — sustained high pressure"
- **D-04:** Implemented in `src/soma/graph_reflexes.py`, called from engine after pressure update

### Session Memory
- **D-05:** Before task start, check `~/.soma/sessions/history.jsonl` for similar past sessions
- **D-06:** Match by tool usage pattern (cosine similarity of action vectors)
- **D-07:** Inject: "Last time on similar task, approach X worked after Y failed"
- **D-08:** Only inject if similarity > 0.7 and session had successful outcome

### Smart Throttle
- **D-09:** As pressure rises, inject progressively stronger focus hints
- **D-10:** GUIDE: "Keep responses focused". WARN: "Max 500 tokens". BLOCK: "One sentence only"
- **D-11:** Not a hard block — injection only, agent decides

### Fingerprint Anomaly Detection
- **D-12:** When JSD divergence > 2x baseline → alert
- **D-13:** Alert: "Behavioral anomaly — agent pattern changed significantly"
- **D-14:** Log to audit trail with type "anomaly"

### Context Overflow Management
- **D-15:** Context > 80% → inject "Context 85% full. Checkpoint your work."
- **D-16:** Context > 95% → inject "CRITICAL: Context nearly full. Commit and /clear NOW."
- **D-17:** Uses existing context tracking from engine

### Claude's Discretion
- Circuit breaker state storage (in-memory vs persistent)
- Session memory matching algorithm details
- Exact throttle thresholds per mode
- Anomaly detection sensitivity tuning

</decisions>

<canonical_refs>
## Canonical References

- `docs/superpowers/specs/2026-04-01-soma-nervous-system-design.md` §3.5, §4 — Advanced reflex specs
- `src/soma/graph.py` — PressureGraph, trust edges, propagation
- `src/soma/fingerprint.py` — FingerprintEngine, JSD divergence
- `src/soma/session_store.py` — SessionRecord, append/load history
- `src/soma/context.py` — SessionContext, context tracking
- `src/soma/reflexes.py` — Pattern reflex engine (Phase 14)
- `src/soma/signal_reflexes.py` — Signal reflex evaluators (Phase 15)

</canonical_refs>

<deferred>
## Deferred Ideas

None — this is the final nervous system phase.

</deferred>

---

*Phase: 16-advanced-reflexes*
*Context gathered: 2026-04-01*
