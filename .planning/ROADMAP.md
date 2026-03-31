# Roadmap: SOMA

## Overview

SOMA v0.5.0 — fully operational behavioral monitoring system with 773 tests, 10 phases of research-backed agent intelligence, production API support (sync/async/streaming), and published on PyPI. Next: observability exports, ecosystem expansion, and advanced intelligence.

## Milestones

- ✅ **Milestone 1+2 — Core Engine + Agent Intelligence** — Phases 1-8 (shipped pre-v0.5.0)
- ✅ **Milestone 3 — Production Ready** — Phases 9-10 (shipped 2026-03-31, v0.5.0)
- 🚧 **Milestone 4 — Observability** — Phase 11 (next)
- 📋 **Milestone 5 — Ecosystem** — Phase 12
- 📋 **Milestone 6 — Intelligence** — Phase 13
- 📋 **Milestone 7 — Platform** — Phase 14
- 📋 **Milestone 8 — Research** — Phase 15

## Phases

<details>
<summary>✅ Milestone 1+2: Core Engine + Agent Intelligence (Phases 1-8) — COMPLETE</summary>

- [x] Phase 1: Vitals Accuracy — Goal coherence scoring + baseline integrity checks
- [x] Phase 2: Uncertainty Classification — Epistemic vs aleatoric uncertainty split
- [x] Phase 3: Vector Pressure — PressureVector through trust graph
- [x] Phase 4: Coordination Intelligence — SNR isolation + task complexity estimation
- [x] Phase 5: Temporal Modeling — Agent half-life estimation + handoff suggestions
- [x] Phase 6: Reliability Metrics — Calibration scoring + verbal-behavioral divergence
- [x] Phase 7: Universal Python SDK — soma.track() + LangChain/CrewAI/AutoGen adapters
- [x] Phase 8: TypeScript SDK + Policy Engine — YAML/TOML rules, @guardrail, TS scaffold

</details>

<details>
<summary>✅ Milestone 3: Production Ready (Phases 9-10) — SHIPPED 2026-03-31</summary>

- [x] Phase 9: Async + Streaming — soma.wrap() for async clients and streaming responses (2 plans)
- [x] Phase 10: Production Hardening — Real API tests, context tracking, audit logging, PyPI 0.5.0 (4 plans)

</details>

### 🚧 Milestone 4 — Observability

- [ ] **Phase 11: Observability** — OpenTelemetry exporter + session reports + webhook alerting

### 📋 Milestone 5 — Ecosystem

- [ ] **Phase 12: Ecosystem** — Cursor/Windsurf hooks, NPM publish, demo, community policy packs

### 📋 Milestone 6 — Intelligence

- [ ] **Phase 13: Intelligence** — Context-aware degradation, ML threshold tuning, semantic monitoring

### 📋 Milestone 7 — Platform

- [ ] **Phase 14: Platform** — Web dashboard, fleet management, teams

### 📋 Milestone 8 — Research

- [ ] **Phase 15: Research** — Papers, open datasets, benchmarks

## Phase Details

### Phase 11: Observability
**Goal**: SOMA emits structured observability data to any OTel collector and produces session reports
**Depends on**: Phase 10
**Requirements**: OTL-01, RPT-01, ALT-01, HIST-01
**Success Criteria** (what must be TRUE):
  1. SOMA exports traces and metrics to any OpenTelemetry-compatible collector (Jaeger, Grafana, Datadog)
  2. At session end, SOMA generates a Markdown report covering actions, quality, cost, patterns, interventions
  3. Webhook alerting fires on WARN/BLOCK/policy violation to configurable endpoints
  4. Historical analytics API returns per-agent trends over time
**Plans**: TBD

### Phase 12: Ecosystem
**Goal**: SOMA works with every AI coding tool, not just Claude Code
**Depends on**: Phase 11
**Requirements**: HOOK-01, NPM-01, DEMO-01, POL-03, LAYER-01
**Plans**: TBD

### Phase 13: Intelligence
**Goal**: SOMA predicts problems before they happen using cross-session learning
**Depends on**: Phase 12
**Requirements**: PRED-01, TUNE-01, TASK-01, ANOM-01
**Plans**: TBD

### Phase 14: Platform
**Goal**: Self-hosted web dashboard for multi-agent monitoring
**Depends on**: Phase 13
**Requirements**: DSH-01, DSH-02, DSH-03, DSH-04, FLT-01, FLT-02, TEAM-01
**Plans**: TBD

### Phase 15: Research
**Goal**: Contribute back to the research community
**Depends on**: Phase 14
**Requirements**: BEN-01, BEN-02, SAF-01
**Plans**: TBD

## Backlog

### Phase 999.1: Degradation-Aware Checkpoint Recommendation (BACKLOG)

**Goal:** New guidance type that signals frameworks WHEN to shard/checkpoint based on half-life prediction + context_usage + success rate. Instead of just raising pressure, emit targeted "recommend state checkpoint and handoff" guidance with predicted success rate at N actions, context usage %, and optimal checkpoint moment. Framework (GSD, LangGraph, CrewAI) decides HOW to shard, SOMA tells WHEN. Differentiator: nobody else does this.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)
