# Roadmap: SOMA

## Overview

SOMA v0.4.12 is a working behavioral monitoring system for Claude Code. This roadmap covers three milestones: Milestone 1 upgrades the core engine with research-backed vitals and pressure enhancements; Milestone 2 expands the platform to any agent framework via SDKs, policy engine, and observability; Milestone 3 builds ecosystem visibility through a web dashboard, alerting, fleet management, and community research infrastructure.

## Milestones

- 🚧 **Milestone 1 — Core Engine Upgrades** - Phases 1-6 (in progress)
- 📋 **Milestone 2 — Platform Expansion** - Phases 7-9 (planned)
- 📋 **Milestone 3 — Ecosystem & Visibility** - Phases 10-11 (planned)

## Phases

### 🚧 Milestone 1 — Core Engine Upgrades (Research-Driven)

**Milestone Goal:** Upgrade SOMA's core engine with research-backed capabilities — smarter vitals, vector pressure propagation, temporal reliability modeling, and deception detection. All from academic literature (2024-2026).

- [ ] **Phase 1: Vitals Accuracy** - Goal coherence scoring + baseline integrity checks
- [ ] **Phase 2: Uncertainty Classification** - Epistemic vs aleatoric uncertainty split
- [ ] **Phase 3: Vector Pressure** - Epistemic pressure vector through trust graph
- [ ] **Phase 4: Coordination Intelligence** - Graph SNR isolation + pre-execution complexity estimation
- [ ] **Phase 5: Temporal Modeling** - Agent half-life estimation + temporal task sharding
- [ ] **Phase 6: Reliability Metrics** - Calibration scoring + deceptive behavior detection

### 📋 Milestone 2 — Platform Expansion

**Milestone Goal:** Make SOMA framework-agnostic — any Python agent framework can use SOMA via a universal SDK and framework adapters. Add policy-as-code and structured observability.

- [ ] **Phase 7: Universal Python SDK** - `soma.track()` context manager + LangChain/CrewAI/AutoGen adapters
- [ ] **Phase 8: TypeScript SDK + Policy Engine** - JS ecosystem support + YAML rules + Python guardrails
- [ ] **Phase 9: Observability** - OpenTelemetry exporter + structured audit log + session reports

### 📋 Milestone 3 — Ecosystem & Visibility

**Milestone Goal:** Give SOMA a public face — self-hosted web dashboard for multi-agent visibility, fleet management for enterprise deployment, and community research infrastructure.

- [ ] **Phase 10: Web Dashboard** - Self-hosted real-time monitoring, pressure timelines, trust graph, session history
- [ ] **Phase 11: Fleet, Alerting & Research** - Webhook alerting, fleet management, safety scoring, community benchmarks

## Phase Details

### Phase 1: Vitals Accuracy
**Goal**: SOMA correctly detects when an agent is solving the wrong problem and when baselines have been corrupted by bad behavior
**Depends on**: Nothing (first phase, brownfield upgrade)
**Requirements**: VIT-01, VIT-03
**Success Criteria** (what must be TRUE):
  1. `VitalsSnapshot` includes a `goal_coherence` score computed as cosine distance from initial task signature to current behavior vector
  2. An agent that drifts to an unrelated task registers goal coherence below the threshold while behavioral drift stays normal
  3. `VitalsSnapshot` includes a `baseline_integrity` flag that activates when baseline trajectory diverges from historical fingerprint
  4. An agent running 20+ high-error actions that has adapted its baseline triggers baseline integrity failure, distinguishable from legitimate behavioral change
**Plans:** 3 plans

Plans:
- [ ] 01-01-PLAN.md — Wave 0: Extend types, config, state slots, pressure weights + failing test stubs
- [ ] 01-02-PLAN.md — Wave 1: Goal coherence scoring (VIT-01) — compute_goal_coherence + engine wiring
- [ ] 01-03-PLAN.md — Wave 2: Baseline integrity check (VIT-03) — compute_baseline_integrity + engine wiring

### Phase 2: Uncertainty Classification
**Goal**: SOMA classifies uncertainty as epistemic (agent doesn't know) or aleatoric (task is inherently ambiguous), triggering different guidance responses for each
**Depends on**: Nothing (M1 brownfield upgrade, independent of Phase 1)
**Requirements**: VIT-02
**Success Criteria** (what must be TRUE):
  1. `VitalsSnapshot` includes `uncertainty_type` field with values `epistemic` or `aleatoric`
  2. Low task entropy + high uncertainty classifies as epistemic and escalates to WARN faster than an equivalent aleatoric case
  3. High task entropy + high uncertainty classifies as aleatoric and produces GUIDE-level guidance without pressure escalation
  4. Classification logic has test coverage with synthetic task entropy scenarios
**Plans:** 2 plans

Plans:
- [ ] 02-01-PLAN.md — Wave 1: Add uncertainty_type to VitalsSnapshot + classify_uncertainty function + unit tests
- [ ] 02-02-PLAN.md — Wave 2: Wire classification into engine + pressure modulation (epistemic 1.3x, aleatoric 0.7x) + integration tests

### Phase 3: Vector Pressure
**Goal**: Downstream agents in the trust graph receive a pressure vector (uncertainty, drift, error, cost components) instead of a scalar, enabling them to react precisely to upstream failure causes
**Depends on**: Phase 2 (requires epistemic/aleatoric split to populate uncertainty_p correctly)
**Requirements**: PRS-01
**Success Criteria** (what must be TRUE):
  1. `PressureGraph.propagate()` produces a `{uncertainty_p, drift_p, error_p, cost_p}` vector per agent, not a scalar
  2. A downstream agent receiving high `error_p` from upstream adjusts its error-rate threshold, not its drift threshold
  3. Scalar aggregate pressure (for ResponseMode mapping) is preserved as the max/weighted reduction of the vector
  4. Existing multi-agent tests pass without regression; new vector-specific tests cover propagation fidelity
**Plans**: TBD

### Phase 4: Coordination Intelligence
**Goal**: SOMA isolates agents from noisy graph pressure when incoming signals are uncorroborated, and adjusts escalation thresholds before high-complexity tasks begin
**Depends on**: Phase 3
**Requirements**: PRS-02, PRS-03
**Success Criteria** (what must be TRUE):
  1. Coordination SNR is computed as the ratio of confirmed-error pressure to total incoming pressure per agent
  2. An agent with SNR below threshold is isolated from graph propagation (internal pressure only) until corroboration arrives
  3. Pre-execution complexity score is computed from task length, ambiguity markers, and dependency count before the first action records
  4. High-complexity tasks lower initial pressure thresholds so escalation to WARN occurs at fewer actions than baseline
**Plans**: TBD

### Phase 5: Temporal Modeling
**Goal**: SOMA predicts when an agent's success rate will degrade based on session history, and recommends task handoff before that boundary is crossed
**Depends on**: Nothing (M1 brownfield upgrade, independent of Phases 3-4)
**Requirements**: HLF-01, HLF-02
**Success Criteria** (what must be TRUE):
  1. Per-agent half-life model is computed from historical fingerprint data and produces a predicted success rate decay curve
  2. SOMA emits a GUIDE-level warning when projected success rate will cross threshold within the next N actions
  3. When a task approaches the agent's half-life boundary, SOMA generates a checkpoint + state handoff suggestion with context summary
  4. Half-life estimates persist across sessions via fingerprint storage and update incrementally as new session data arrives
**Plans**: TBD

### Phase 6: Reliability Metrics
**Goal**: SOMA measures how honestly an agent signals its own uncertainty, detecting miscalibration or deceptive behavior when verbal confidence diverges from behavioral signals
**Depends on**: Nothing (M1 brownfield upgrade, independent of Phases 4-5)
**Requirements**: REL-01, REL-02
**Success Criteria** (what must be TRUE):
  1. `VitalsSnapshot` includes `calibration_score` tracking alignment between hedging language in outputs and actual error rates
  2. An agent that consistently hedges ("I'm not sure...") but rarely errors has high calibration; one that hedges and errors frequently has low calibration
  3. `VitalsSnapshot` includes `verbal_behavioral_divergence` flag that activates when agent reports low uncertainty verbally but behavioral signals show high pressure
  4. Verbal-behavioral divergence triggers a distinct WARN-level guidance message distinguishable from standard pressure WARN
**Plans**: TBD

### Phase 7: Universal Python SDK
**Goal**: Any Python agent framework can integrate SOMA via a `soma.track()` context manager, with zero-friction adapters for LangChain, CrewAI, and AutoGen
**Depends on**: Phase 6 (full M1 engine in place before external-facing SDK)
**Requirements**: SDK-01, SDK-02, SDK-03, SDK-04
**Success Criteria** (what must be TRUE):
  1. `soma.track(agent_id, tool, output)` context manager works without framework-specific imports; drop-in for any Python agent
  2. LangChain agents instrumented via `SomaLangChainCallback` emit vitals and pressure without modifying agent code
  3. CrewAI crews instrumented via `SomaCrewObserver` capture per-agent actions across crew execution
  4. AutoGen conversations instrumented via `SomaAutoGenMonitor` track conversation-level behavioral signals
**Plans**: TBD

### Phase 8: TypeScript SDK + Policy Engine
**Goal**: JavaScript/TypeScript agent ecosystems can use SOMA, and any deployment can define behavioral rules declaratively in YAML or programmatically via Python decorators
**Depends on**: Phase 7
**Requirements**: SDK-05, POL-01, POL-02, POL-03
**Success Criteria** (what must be TRUE):
  1. `soma-ai` npm package provides `track()` and `wrap()` for Vercel AI SDK and LangChain.js agents
  2. A `soma.yaml` policy file with `when`/`do` rules fires correctly when matching conditions occur during agent execution
  3. `@soma.guardrail` decorator on a Python function blocks the decorated operation when SOMA pressure exceeds policy threshold
  4. Community policy pack (a `.yaml` rule set) can be loaded from a URL or local path without code changes
**Plans**: TBD

### Phase 9: Observability
**Goal**: SOMA emits structured, machine-readable observability data to any OTel collector and produces human-readable session reports automatically
**Depends on**: Phase 8
**Requirements**: OTL-01, OTL-02, RPT-01
**Success Criteria** (what must be TRUE):
  1. SOMA exports traces and metrics to any OpenTelemetry-compatible collector (Jaeger, Grafana, Datadog) using the existing optional `otel` dep
  2. Every session writes a `~/.soma/audit.jsonl` file with one JSON line per action, zero config required
  3. At session end, SOMA generates an HTML report covering actions taken, quality score, cost, detected patterns, and interventions
  4. OTel export and audit log work independently — enabling one does not require the other
**Plans**: TBD

### Phase 10: Web Dashboard
**Goal**: Developers can monitor multiple agents in real time from a self-hosted web interface, with pressure timelines, trust graph visualization, and session history drill-down
**Depends on**: Phase 9
**Requirements**: DSH-01, DSH-02, DSH-03, DSH-04
**Success Criteria** (what must be TRUE):
  1. `soma dashboard` command starts a local FastAPI server serving a real-time multi-agent monitoring UI
  2. Each active agent has a live pressure timeline graph updating as actions are recorded
  3. Trust graph between agents is visualized with edge weights and current pressure levels visible
  4. Session history is browsable with per-session drill-down showing action log, vitals, interventions, and final report
**Plans**: TBD

### Phase 11: Fleet, Alerting & Research
**Goal**: Enterprises can deploy SOMA across multiple machines from a central git config, receive real-time alerts on critical events, and contribute to community AI safety research
**Depends on**: Phase 10
**Requirements**: ALT-01, FLT-01, FLT-02, BEN-01, BEN-02, SAF-01
**Success Criteria** (what must be TRUE):
  1. WARN/BLOCK events and policy violations trigger webhook notifications to Slack, Discord, or PagerDuty with agent context
  2. A single `soma.toml` in a git repo applies configuration to all registered machines on next sync
  3. Fleet aggregate dashboard shows cross-machine pressure trends, session counts, and intervention rates
  4. Agent Safety Score computes a standardized cross-model safety metric from SOMA vitals, comparable across agents and models
  5. Opt-in anonymized session telemetry publishes behavioral metrics to a community benchmark endpoint with agent-type leaderboard
  6. Anonymized behavioral traces export in a documented format consumable as open research datasets for AI safety research
**Plans**: TBD

## Progress

**Execution Order:** Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Vitals Accuracy | M1 | 0/3 | Planning complete | - |
| 2. Uncertainty Classification | M1 | 0/2 | Planning complete | - |
| 3. Vector Pressure | M1 | 0/TBD | Not started | - |
| 4. Coordination Intelligence | M1 | 0/TBD | Not started | - |
| 5. Temporal Modeling | M1 | 0/TBD | Not started | - |
| 6. Reliability Metrics | M1 | 0/TBD | Not started | - |
| 7. Universal Python SDK | M2 | 0/TBD | Not started | - |
| 8. TypeScript SDK + Policy Engine | M2 | 0/TBD | Not started | - |
| 9. Observability | M2 | 0/TBD | Not started | - |
| 10. Web Dashboard | M3 | 0/TBD | Not started | - |
| 11. Fleet, Alerting & Research | M3 | 0/TBD | Not started | - |
