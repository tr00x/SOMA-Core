# Requirements: SOMA

**Defined:** 2026-03-30
**Core Value:** Real-time behavioral guidance that makes AI agents safer and more effective without requiring human babysitting.

---

## Milestone 1 — Core Engine Upgrades (research-driven)

Research basis: SOMA-RESEARCH.pdf — 10 open problems from academic literature (2024–2026).

### Core Vitals Upgrades

- [ ] **VIT-01**: Goal Coherence Score — save initial task signature (first N actions behavior vector), periodically compute cosine distance to detect "agent solving wrong problem" separate from behavioral drift
- [ ] **VIT-02**: Aleatoric vs Epistemic Uncertainty split — classify uncertainty using task entropy heuristic (low entropy + high uncertainty = epistemic → escalate; high entropy + high uncertainty = aleatoric → guide only)
- [ ] **VIT-03**: Baseline Integrity Check — detect baseline corruption (adapting to bad behavior) by comparing baseline trajectory against historical fingerprint; distinguish adaptation from corruption

### Pressure & Graph Upgrades

- [ ] **PRS-01**: Epistemic Pressure Vector — propagate {uncertainty_p, drift_p, error_p, cost_p} vector through trust graph instead of scalar; downstream agents react more precisely to upstream failure causes
- [ ] **PRS-02**: Coordination SNR — ratio of real incoming pressure (confirmed by source agent errors) to coordination overhead (pressure without errors); isolate agent from graph when SNR is low
- [ ] **PRS-03**: Pre-execution Task Complexity Estimator — before task starts, estimate complexity score (length, ambiguity, dependencies); high complexity = lower initial thresholds, faster escalation

### Half-Life & Temporal

- [ ] **HLF-01**: Agent Half-Life Estimator — per-agent success rate decay model built from session history via fingerprinting; SOMA predicts when success rate will drop below threshold
- [ ] **HLF-02**: Temporal Task Sharding — when task approaches agent's half-life boundary, automatically suggest checkpoint + state handoff to fresh context

### Reliability Metrics (Princeton framework)

- [ ] **REL-01**: Calibration Score — measure how honestly agent signals uncertainty through hedging language vs actual errors; track verbal-behavioral alignment as new quality dimension
- [ ] **REL-02**: Deceptive Behavior Detection — Verbal-Behavioral Divergence signal: agent verbally reports low uncertainty but behavioral signals show high = miscalibration or deception flag

---

## Milestone 2 — Platform Expansion

### Universal SDK

- [ ] **SDK-01**: Universal Python SDK — `soma.track()` context manager for any agent framework (LangChain, CrewAI, AutoGen, custom)
- [ ] **SDK-02**: LangChain adapter — middleware that instruments LangChain agents transparently
- [ ] **SDK-03**: CrewAI adapter — observer for CrewAI crew execution
- [ ] **SDK-04**: AutoGen adapter — monitor for AutoGen conversation flows
- [ ] **SDK-05**: TypeScript SDK — first-class JS/TS support for Vercel AI SDK, LangChain.js

### Policy Engine

- [ ] **POL-01**: YAML policy engine — declarative rules (when/do) beyond pressure thresholds
- [ ] **POL-02**: Python guardrail decorator — `@soma.guardrail` for programmatic rules
- [ ] **POL-03**: Community policy packs — shareable rule sets hosted on GitHub

### Observability

- [ ] **OTL-01**: OpenTelemetry exporter — structured traces/metrics to any OTel collector (dep already exists)
- [ ] **OTL-02**: Structured audit log — JSON Lines out of the box, zero config
- [ ] **RPT-01**: Session reports — automatic post-session HTML/PDF summary (actions, quality, cost, patterns, interventions)

---

## Milestone 3 — Ecosystem & Visibility

### Web Dashboard

- [ ] **DSH-01**: Self-hosted web dashboard — real-time multi-agent monitoring (FastAPI + React/htmx, Docker)
- [ ] **DSH-02**: Pressure timeline graphs per agent
- [ ] **DSH-03**: Trust graph visualization
- [ ] **DSH-04**: Session history with drill-down

### Alerting & Fleet

- [ ] **ALT-01**: Webhook alerting — Slack, Discord, PagerDuty on WARN/BLOCK/policy violation
- [ ] **FLT-01**: Fleet management — central git-based config for multiple machines
- [ ] **FLT-02**: Aggregate fleet dashboards

### Research & Community

- [ ] **BEN-01**: Agent Safety Score — standardized cross-model safety metric using SOMA vitals
- [ ] **BEN-02**: Collective benchmarks — opt-in anonymized telemetry + community leaderboard
- [ ] **SAF-01**: Open research datasets — anonymized behavioral traces for AI safety research

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| SaaS / hosted service | MIT open-source only, self-hosted |
| Paid tiers / monetization | Community project, not a business |
| Model training / fine-tuning | SOMA observes and guides, doesn't modify models |
| Replacing the agent | Immune system, not a brain |
| Proprietary data formats | All formats open standard |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VIT-01 | Phase 1 | Pending |
| VIT-03 | Phase 1 | Pending |
| VIT-02 | Phase 2 | Pending |
| PRS-01 | Phase 3 | Pending |
| PRS-02 | Phase 4 | Pending |
| PRS-03 | Phase 4 | Pending |
| HLF-01 | Phase 5 | Pending |
| HLF-02 | Phase 5 | Pending |
| REL-01 | Phase 6 | Pending |
| REL-02 | Phase 6 | Pending |
| SDK-01 | Phase 7 | Pending |
| SDK-02 | Phase 7 | Pending |
| SDK-03 | Phase 7 | Pending |
| SDK-04 | Phase 7 | Pending |
| SDK-05 | Phase 8 | Pending |
| POL-01 | Phase 8 | Pending |
| POL-02 | Phase 8 | Pending |
| POL-03 | Phase 8 | Pending |
| OTL-01 | Phase 9 | Pending |
| OTL-02 | Phase 9 | Pending |
| RPT-01 | Phase 9 | Pending |
| DSH-01 | Phase 10 | Pending |
| DSH-02 | Phase 10 | Pending |
| DSH-03 | Phase 10 | Pending |
| DSH-04 | Phase 10 | Pending |
| ALT-01 | Phase 11 | Pending |
| FLT-01 | Phase 11 | Pending |
| FLT-02 | Phase 11 | Pending |
| BEN-01 | Phase 11 | Pending |
| BEN-02 | Phase 11 | Pending |
| SAF-01 | Phase 11 | Pending |

**Coverage:**
- Milestone 1 (core engine): 10 requirements across Phases 1-6
- Milestone 2 (platform): 11 requirements across Phases 7-9
- Milestone 3 (ecosystem): 10 requirements across Phases 10-11
- Total: 31 requirements across 11 phases

---
*Requirements defined: 2026-03-30*
*Research basis: SOMA-RESEARCH.pdf (10 open problems, arXiv 2024–2026)*
