# Roadmap: SOMA

## Overview

SOMA v0.5.0 — fully operational behavioral monitoring system with 773 tests, 10 phases of research-backed agent intelligence, production API support (sync/async/streaming), and published on PyPI. Next: observability exports, ecosystem expansion, and advanced intelligence.

## Milestones

- ✅ **Milestone 1+2 — Core Engine + Agent Intelligence** — Phases 1-8 (shipped pre-v0.5.0)
- ✅ **Milestone 3 — Production Ready** — Phases 9-10 (shipped 2026-03-31, v0.5.0)
- ✅ **Milestone 4 — Observability** — Phase 11 (completed 2026-04-01)
- ✅ **Milestone 5 — Ecosystem** — Phase 12 (completed 2026-04-01)
- ✅ **Milestone 6 — Intelligence** — Phase 13
- 🚧 **Milestone 7 — Nervous System (v1.0)** — Phase 14
- 📋 **Milestone 8 — Platform** — Phase 15

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

<details>
<summary>✅ Milestone 4: Observability (Phase 11) — COMPLETED 2026-04-01</summary>

- [x] **Phase 11: Observability** — OpenTelemetry exporter + session reports + webhook alerting (completed 2026-04-01)

</details>

<details>
<summary>✅ Milestone 5: Ecosystem (Phase 12) — COMPLETED 2026-04-01</summary>

- [x] **Phase 12: Ecosystem** — Cursor/Windsurf hooks, NPM publish, demo, community policy packs (completed 2026-04-01)

</details>

### ✅ Milestone 6 — Intelligence

- [x] **Phase 13: Intelligence** — Benchmark-first proof, cross-session learning, threshold tuning, phase-aware drift (completed 2026-04-01)

### 🚧 Milestone 7 — Nervous System (v1.0)

- [x] **Phase 14: Core Reflexes** — Reflex engine, 3 modes, pattern blocks, agent awareness, benchmark proof (completed 2026-04-01)
- [x] **Phase 15: Signal Reflexes** — Auto-checkpoint, scope guardian, handoff, RCA injection, commit gate (completed 2026-04-01)
- [ ] **Phase 16: Advanced Reflexes** — Circuit breaker, session memory, smart throttle, anomaly detection

### 📋 Milestone 8 — Platform

- [ ] **Phase 17: Dashboard** — Web dashboard, fleet management, teams

### 📋 Milestone 9 — Research

- [ ] **Phase 18: Research** — Papers, open datasets, benchmarks

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
**Plans**: 3 plans

Plans:
- [x] 11-01-PLAN.md — Exporter interface, context exhaustion pressure, model-aware sizing
- [x] 11-02-PLAN.md — OpenTelemetry exporter and webhook alerting
- [x] 11-03-PLAN.md — Session reports, historical analytics, CLI commands

### Phase 12: Ecosystem
**Goal**: SOMA works with every AI coding tool, not just Claude Code
**Depends on**: Phase 11
**Requirements**: HOOK-01, NPM-01, DEMO-01, POL-03, LAYER-01
**Plans**: 3 plans

Plans:
- [x] 12-01-PLAN.md — Hook adapter protocol (LAYER-01) + Cursor/Windsurf adapters (HOOK-01)
- [x] 12-02-PLAN.md — NPM publish prep (NPM-01) + community policy packs (POL-03)
- [x] 12-03-PLAN.md — Demo tape for README (DEMO-01)

### Phase 13: Intelligence
**Goal**: Benchmark-first proof that SOMA improves agent behavior, then cross-session learning
**Depends on**: Phase 12
**Requirements**: PRED-01, TUNE-01, TASK-01, ANOM-01
**Plans**: 3 plans

Plans:
- [x] 13-01-PLAN.md — Benchmark harness, scenarios, and metrics collection (PRED-01)
- [x] 13-02-PLAN.md — Session store, cross-session predictor, threshold tuner, phase-aware drift (TUNE-01, TASK-01, ANOM-01)
- [x] 13-03-PLAN.md — CLI wiring, report generation, docs/BENCHMARK.md with real results

### Phase 14: Core Reflexes
**Goal**: SOMA blocks harmful patterns and forces correct behavior — mechanical, not advisory
**Depends on**: Phase 13
**Requirements**: RFX-01, RFX-02, RFX-03, RFX-04
**Plans**: 3 plans

Plans:
- [x] 14-01-PLAN.md — Reflex engine module (reflexes.py) + config loader (mode, reflexes sections)
- [x] 14-02-PLAN.md — Hook integration (PreToolUse, Notification, Statusline) + agent awareness prompt
- [x] 14-03-PLAN.md — Benchmark proof with reflex mode + docs/BENCHMARK.md update

### Phase 15: Signal Reflexes
**Goal**: Every existing pipeline signal triggers a real action, not just a number
**Depends on**: Phase 14
**Requirements**: RFX-05, RFX-06, RFX-07, RFX-08, RFX-09
**Plans**: 2 plans

Plans:
- [x] 15-01-PLAN.md — Signal reflex evaluator module (all 5 pure-function reflexes + tests)
- [x] 15-02-PLAN.md — Hook integration (commit gate, notification injections, git stash, report stats)

### Phase 16: Advanced Reflexes
**Goal**: Multi-agent circuit breakers, session memory, context management
**Depends on**: Phase 15
**Requirements**: RFX-10, RFX-11, RFX-12, RFX-13
**Plans**: 3 plans

Plans:
- [x] 16-01-PLAN.md — Circuit breaker, smart throttle, anomaly detection, context overflow evaluators
- [x] 16-02-PLAN.md — Session memory matching and injection module
- [ ] 16-03-PLAN.md — Hook integration for all advanced reflexes

### Phase 17: Dashboard
**Goal**: Self-hosted web dashboard for multi-agent monitoring
**Depends on**: Phase 16
**Requirements**: DSH-01, DSH-02, DSH-03, DSH-04, FLT-01, FLT-02, TEAM-01
**Plans**: TBD

### Phase 18: Research
**Goal**: Contribute back to the research community
**Depends on**: Phase 17
**Requirements**: BEN-01, BEN-02, SAF-01
**Plans**: TBD

## Backlog

### Phase 999.1: Degradation-Aware Checkpoint Recommendation (BACKLOG)

**Goal:** New guidance type that signals frameworks WHEN to shard/checkpoint based on half-life prediction + context_usage + success rate. Instead of just raising pressure, emit targeted "recommend state checkpoint and handoff" guidance with predicted success rate at N actions, context usage %, and optimal checkpoint moment. Framework (GSD, LangGraph, CrewAI) decides HOW to shard, SOMA tells WHEN. Differentiator: nobody else does this.
**Requirements:** TBD
**Plans:** 2/3 plans executed

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)
