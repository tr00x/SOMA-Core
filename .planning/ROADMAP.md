# Roadmap: SOMA

## Overview

SOMA v0.5.0 is a fully operational behavioral monitoring system with 735 tests, 8 phases of agent intelligence, and production Claude Code integration. This roadmap covers the completed foundation plus upcoming milestones: Milestone 3 makes the wrapper production-ready (async, streaming, structured logging); Milestone 4 adds observability exports; Milestone 5 expands the ecosystem; Milestones 6-8 cover intelligence, platform, and research.

## Milestones

- ✓ **Milestone 1 — Core Engine + Foundation** - Phases 1-8 (complete)
- ✓ **Milestone 2 — Agent Intelligence** - Phases 1-8 (complete, v0.5.0)
- 🚧 **Milestone 3 — Production Ready** - Phases 9-10 (in progress)
- 📋 **Milestone 4 — Observability** - Phase 11 (planned)
- 📋 **Milestone 5 — Ecosystem** - Phase 12 (planned)
- 📋 **Milestone 6 — Intelligence** - Phase 13 (planned)
- 📋 **Milestone 7 — Platform** - Phase 14 (planned)
- 📋 **Milestone 8 — Research** - Phase 15 (planned)

## Phases

### ✓ Milestone 1+2 — Core Engine + Agent Intelligence (Complete)

**Milestone Goal:** Build the full behavioral monitoring engine with research-backed capabilities — 6-signal vitals, vector pressure propagation, temporal reliability modeling, uncertainty classification, policy engine, framework adapters, and per-session isolation.

- [x] **Phase 1: Vitals Accuracy** - Goal coherence scoring + baseline integrity checks (VIT-01, VIT-03)
- [x] **Phase 2: Uncertainty Classification** - Epistemic vs aleatoric uncertainty split (VIT-02)
- [x] **Phase 3: Vector Pressure** - PressureVector through trust graph (PRS-01)
- [x] **Phase 4: Coordination Intelligence** - SNR isolation + task complexity estimation (PRS-02, PRS-03)
- [x] **Phase 5: Temporal Modeling** - Agent half-life estimation + handoff suggestions (HLF-01, HLF-02)
- [x] **Phase 6: Reliability Metrics** - Calibration scoring + verbal-behavioral divergence (REL-01, REL-02)
- [x] **Phase 7: Universal Python SDK** - soma.track() + LangChain/CrewAI/AutoGen adapters (SDK-01-04)
- [x] **Phase 8: TypeScript SDK + Policy Engine** - YAML/TOML rules, @guardrail, TS scaffold (SDK-05, POL-01, POL-02)

### 🚧 Milestone 3 — Production Ready

**Milestone Goal:** Remove every blocker preventing real production usage. Async/streaming support, real API validation, structured logging, and PyPI publish.

- [ ] **Phase 9: Async + Streaming** - Async client wrapper + streaming interception
- [ ] **Phase 10: Production Hardening** - Real API testing, context window tracking, structured audit log, PyPI 0.5.0

### 📋 Milestone 4 — Observability

- [ ] **Phase 11: Observability** - OpenTelemetry exporter + session reports + webhook alerting

### 📋 Milestone 5 — Ecosystem

- [ ] **Phase 12: Ecosystem** - Cursor/Windsurf hooks, NPM publish, demo, community policy packs

### 📋 Milestone 6 — Intelligence

- [ ] **Phase 13: Intelligence** - Context-aware degradation, ML threshold tuning, semantic monitoring

### 📋 Milestone 7 — Platform

- [ ] **Phase 14: Platform** - Web dashboard, fleet management, teams

### 📋 Milestone 8 — Research

- [ ] **Phase 15: Research** - Papers, open datasets, benchmarks

## Phase Details

### Phase 1: Vitals Accuracy ✓
**Goal**: SOMA correctly detects when an agent is solving the wrong problem and when baselines have been corrupted by bad behavior
**Depends on**: Nothing
**Requirements**: VIT-01, VIT-03
**Status**: Complete
**Plans:** 3 plans (01-01, 01-02, 01-03)

### Phase 2: Uncertainty Classification ✓
**Goal**: SOMA classifies uncertainty as epistemic or aleatoric, triggering different guidance responses
**Depends on**: Nothing
**Requirements**: VIT-02
**Status**: Complete
**Plans:** 2 plans (02-01, 02-02)

### Phase 3: Vector Pressure ✓
**Goal**: Downstream agents receive a pressure vector instead of scalar
**Depends on**: Phase 2
**Requirements**: PRS-01
**Status**: Complete

### Phase 4: Coordination Intelligence ✓
**Goal**: SNR isolation + pre-execution complexity estimation
**Depends on**: Phase 3
**Requirements**: PRS-02, PRS-03
**Status**: Complete

### Phase 5: Temporal Modeling ✓
**Goal**: Half-life estimation + handoff suggestions
**Depends on**: Nothing
**Requirements**: HLF-01, HLF-02
**Status**: Complete

### Phase 6: Reliability Metrics ✓
**Goal**: Calibration scoring + verbal-behavioral divergence detection
**Depends on**: Nothing
**Requirements**: REL-01, REL-02
**Status**: Complete

### Phase 7: Universal Python SDK ✓
**Goal**: Any Python agent framework can integrate SOMA
**Depends on**: Phase 6
**Requirements**: SDK-01, SDK-02, SDK-03, SDK-04
**Status**: Complete

### Phase 8: TypeScript SDK + Policy Engine ✓
**Goal**: YAML/TOML policy rules + @guardrail + TypeScript SDK scaffold
**Depends on**: Phase 7
**Requirements**: SDK-05, POL-01, POL-02
**Status**: Complete

### Phase 9: Async + Streaming
**Goal**: soma.wrap() works with async clients and streaming responses — the two patterns every production app uses
**Depends on**: Phase 8 (complete engine)
**Requirements**: ASYNC-01, ASYNC-02
**Success Criteria** (what must be TRUE):
  1. `soma.wrap(AsyncAnthropic())` returns a wrapped async client that intercepts `await client.messages.create()`
  2. `soma.wrap(Anthropic())` intercepts `client.messages.stream()` and records the full streamed response as one Action
  3. Async wrapper passes the same 22-step engine pipeline as sync — pressure, vitals, mode all computed identically
  4. Both sync and async wrappers handle errors (API timeouts, rate limits) gracefully — recording error=True without crashing
  5. Existing sync wrapper tests pass without regression; new async/streaming tests cover happy path + error cases
**Plans:** 2 plans
Plans:
- [x] 09-01-PLAN.md — Async client wrapper (ASYNC-01)
- [x] 09-02-PLAN.md — Streaming interception (ASYNC-02)

### Phase 10: Production Hardening
**Goal**: Validate SOMA against real APIs, add context window tracking, structured audit logging, and publish 0.5.0 to PyPI
**Depends on**: Phase 9 (async must work before real API testing)
**Requirements**: TEST-01, CTX-01, LOG-01, PUB-01, DOC-01
**Success Criteria** (what must be TRUE):
  1. Integration test makes real Anthropic API call through `soma.wrap()` — records token count, cost, output, and pressure updates correctly
  2. Integration test makes real OpenAI API call through `soma.wrap()` — same verification
  3. `VitalsSnapshot` includes `context_usage` field tracking cumulative tokens as fraction of model context window
  4. Context usage feeds into the half-life degradation model as a weighting factor
  5. Every `record_action()` call appends a JSON line to `~/.soma/audit.jsonl` with timestamp, agent_id, tool_name, error, pressure, mode
  6. Audit log is zero-config (on by default), rotatable, and parseable by standard tools (jq, etc.)
  7. `pip install soma-ai` installs version 0.5.0+ with all Phase 1-10 features
  8. CONTRIBUTING.md exists with dev setup, test instructions, and contribution guidelines
**Plans:** 3 plans
Plans:
- [ ] 10-01-PLAN.md — Context window tracking + structured audit log (CTX-01, LOG-01)
- [ ] 10-02-PLAN.md — Real API integration tests (TEST-01)
- [ ] 10-03-PLAN.md — CONTRIBUTING.md + PyPI publish readiness (DOC-01, PUB-01)

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
**Success Criteria** (what must be TRUE):
  1. Cursor and Windsurf have SOMA hook integrations using the same 4-hook architecture
  2. TypeScript SDK published to npm as `soma-ai`
  3. README includes animated GIF demonstrating SOMA in action
  4. Community policy packs loadable from GitHub URLs
  5. Layer SDK enables trivial creation of new platform integrations
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
