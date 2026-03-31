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

## Milestone 2 — Platform Expansion (DONE — v0.5.0)

### Universal SDK (DONE)

- [x] **SDK-01**: Universal Python SDK — `soma.track()` context manager
- [x] **SDK-02**: LangChain adapter — `SomaLangChainCallback`
- [x] **SDK-03**: CrewAI adapter — `SomaCrewObserver`
- [x] **SDK-04**: AutoGen adapter — `SomaAutoGenMonitor`
- [x] **SDK-05**: TypeScript SDK scaffold — `packages/soma-ai/`

### Policy Engine (DONE)

- [x] **POL-01**: YAML/TOML policy engine — declarative when/do rules
- [x] **POL-02**: Python guardrail decorator — `@soma.guardrail` sync/async
- [ ] **POL-03**: Community policy packs — shareable rule sets (Milestone 5)

---

## Milestone 3 — Production Ready

### Adoption Blockers

- [x] **ASYNC-01**: Async client support — `soma.wrap(AsyncAnthropic())`
- [x] **ASYNC-02**: Streaming support — intercept `client.messages.stream()`
- [ ] **PUB-01**: PyPI publish 0.5.0 — update published package
- [x] **TEST-01**: Real API testing — verified with live Anthropic + OpenAI calls
- [x] **CTX-01**: Context window tracking — monitor context consumption as degradation predictor
- [x] **LOG-01**: Structured audit log (OTL-02) — JSON Lines per action, zero config
- [x] **DOC-01**: CONTRIBUTING.md — dev setup, test instructions, contribution guide

---

## Milestone 4 — Observability

- [ ] **OTL-01**: OpenTelemetry exporter — structured traces/metrics to any OTel collector
- [ ] **RPT-01**: Session reports — automatic post-session summary (HTML/Markdown)
- [ ] **ALT-01**: Webhook alerting — Slack, Discord, PagerDuty on WARN/BLOCK/policy violation
- [ ] **HIST-01**: Historical analytics — trends over time, per-agent degradation patterns

---

## Milestone 5 — Ecosystem

- [ ] **HOOK-01**: Cursor/Windsurf hooks — same 4-hook architecture for other AI coding tools
- [ ] **OAAI-01**: OpenAI Agents SDK adapter
- [ ] **NPM-01**: NPM publish TypeScript SDK
- [ ] **DEMO-01**: Demo GIF/video for README
- [ ] **POL-03**: Community policy packs — shareable rule sets
- [ ] **LAYER-01**: Layer SDK — trivial creation of new platform integrations

---

## Milestone 6 — Intelligence

- [ ] **PRED-01**: Context-aware degradation score (context window + half-life + error trend)
- [ ] **TUNE-01**: ML-optimized thresholds per agent type, per task type
- [ ] **TASK-01**: Semantic task-aware monitoring (drift from goal, not just from stats)
- [ ] **ANOM-01**: Cross-session anomaly prediction (5-10 actions ahead)

---

## Milestone 7 — Platform

### Web Dashboard

- [ ] **DSH-01**: Self-hosted web dashboard (FastAPI + htmx/React, Docker)
- [ ] **DSH-02**: Pressure timeline graphs per agent
- [ ] **DSH-03**: Trust graph visualization
- [ ] **DSH-04**: Session history with drill-down

### Fleet & Teams

- [ ] **FLT-01**: Fleet management — central config for multiple machines
- [ ] **FLT-02**: Aggregate fleet dashboards
- [ ] **TEAM-01**: Multi-user, role-based access

### Research & Community

- [ ] **BEN-01**: Agent Safety Score — cross-model safety metric
- [ ] **BEN-02**: Collective benchmarks — opt-in anonymized telemetry
- [ ] **SAF-01**: Open research datasets — anonymized behavioral traces

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
