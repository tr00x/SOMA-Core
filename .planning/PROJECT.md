# SOMA — Behavioral Monitoring for AI Agents

## What This Is

SOMA is an open-source (MIT) behavioral monitoring and guidance system for AI agents. It observes agent actions in real-time, computes behavioral pressure from 5 vital signals, and injects corrective guidance into agent context before problems escalate. Think of it as a nervous system for AI agents — htop/Prometheus for the agent era.

Published on PyPI as `soma-ai` (v0.5.0). Works as a Claude Code hook system and universal Python SDK via `soma.wrap()`. Supports Anthropic and OpenAI clients (sync, async, streaming). The goal is to become the industry standard for AI agent observability and safety — platform-agnostic, framework-agnostic, used by everyone from solo developers to enterprises.

## Core Value

**Real-time behavioral guidance that makes AI agents safer and more effective without requiring human babysitting.**

If everything else fails, the closed-loop feedback system must work: actions → vitals → pressure → guidance → agent behavior change.

## Requirements

### Validated

- ✓ 5 behavioral vitals (uncertainty, drift, error_rate, cost, token_usage) — v0.4.x
- ✓ Pressure computation with z-score sigmoid + weighted aggregation — v0.4.x
- ✓ 4-mode guidance (OBSERVE → GUIDE → WARN → BLOCK) — v0.4.x
- ✓ Self-learning thresholds via intervention outcome tracking — v0.4.x
- ✓ Multi-agent trust graph with pressure propagation — v0.4.x
- ✓ Agent fingerprinting with JS divergence drift detection — v0.4.x
- ✓ Pattern detection (blind writes, bash failures, thrashing, scope drift, agent spam, research stall) — v0.4.x
- ✓ Code validation (py_compile, ruff, node --check) before pressure computation — v0.4.x
- ✓ Budget tracking (tokens + cost) with automatic SAFE_MODE — v0.4.x
- ✓ Predictive guidance (~5 actions ahead via linear regression + pattern boosts) — v0.4.x
- ✓ Real-time statusline + context injection for Claude Code — v0.4.x
- ✓ TUI dashboard with live agent cards — v0.4.x
- ✓ Configurable via soma.toml with operating mode presets — v0.4.x
- ✓ Atomic persistence with fcntl file locking — v0.4.x
- ✓ Session recording and replay — v0.4.x
- ✓ CI pipeline (GitHub Actions, 3 Python versions, ruff lint) — v0.4.x
- ✓ Goal coherence scoring + baseline integrity checks — v0.5.0
- ✓ Epistemic vs aleatoric uncertainty classification — v0.5.0
- ✓ Vector pressure propagation through trust graph — v0.5.0
- ✓ SNR isolation + task complexity estimation — v0.5.0
- ✓ Agent half-life estimation + handoff suggestions — v0.5.0
- ✓ Calibration scoring + verbal-behavioral divergence — v0.5.0
- ✓ Universal Python SDK: soma.track() + LangChain/CrewAI/AutoGen adapters — v0.5.0
- ✓ TypeScript SDK scaffold + YAML/TOML policy engine + @guardrail — v0.5.0
- ✓ Async client wrapper: soma.wrap(AsyncAnthropic()) — v0.5.0
- ✓ Streaming interception: client.messages.stream() — v0.5.0
- ✓ Context window tracking with half-life degradation — v0.5.0
- ✓ Structured JSON Lines audit logging — v0.5.0
- ✓ Real API integration tests (Anthropic + OpenAI) — v0.5.0
- ✓ CONTRIBUTING.md + PyPI 0.5.0 published — v0.5.0
- ✓ 773 tests, 90%+ core coverage — v0.5.0
- ✓ Cross-platform hook adapters (Cursor, Windsurf, ClaudeCode) with base protocol — Phase 12
- ✓ TypeScript SDK prepared for NPM publishing — Phase 12
- ✓ Community policy packs with YAML rules and CLI (`soma policy`) — Phase 12
- ✓ Terminal demo (VHS tape + demo.gif, real engine data) — Phase 12
- ✓ 890 tests passing — Phase 12
- ✓ A/B benchmark harness proving SOMA reduces errors 13.7%, retries 55.6% in retry storms — Phase 13
- ✓ Cross-session learning: session store, anomaly predictor, threshold tuner — Phase 13
- ✓ Phase-aware drift: reduces drift 50% for known task phases — Phase 13
- ✓ `soma benchmark` CLI command with rich output and docs/BENCHMARK.md — Phase 13
- ✓ 944 tests passing — Phase 13

### Active

- [ ] **SDK-01**: Universal Python SDK — `soma.track()` context manager for any agent framework
- [ ] **SDK-02**: Adapter for LangChain agents
- [ ] **SDK-03**: Adapter for CrewAI crews
- [ ] **SDK-04**: Adapter for AutoGen conversations
- [ ] **POL-01**: Policy engine — YAML-based rules (when/do) beyond pressure thresholds
- [ ] **POL-02**: Community policy packs (shareable rule sets)
- [ ] **POL-03**: Custom guardrails via Python decorators (`@soma.guardrail`)
- [ ] **RPT-01**: Session reports — automatic post-session summary (actions, quality, cost, patterns, interventions)
- [ ] **RPT-02**: HTML/PDF export for session reports
- [ ] **OTL-01**: OpenTelemetry exporter — structured traces/metrics to any OTel collector
- [ ] **OTL-02**: Structured audit log (JSON Lines) out of the box
- [ ] **DSH-01**: Web dashboard — real-time multi-agent monitoring (self-hosted)
- [ ] **DSH-02**: Pressure timeline graphs
- [ ] **DSH-03**: Trust graph visualization
- [ ] **DSH-04**: Session history with drill-down
- [ ] **ALT-01**: Alerting via webhooks (Slack, Discord, PagerDuty)
- [ ] **FLT-01**: Fleet management — central git-based config for multiple developer machines
- [ ] **FLT-02**: Aggregate dashboards across fleet
- [ ] **HEL-01**: Self-healing actions (auto-insert Read before blind Write, auto-rollback on error streak)
- [ ] **BEN-01**: Agent benchmarking — compare models/configs on same tasks using fingerprint data
- [ ] **BEN-02**: Collective learning — opt-in anonymized telemetry for community benchmarks
- [ ] **TSK-01**: TypeScript SDK for JS agent ecosystem
- [ ] **INT-01**: Cursor plugin
- [ ] **INT-02**: Windsurf plugin
- [ ] **SAF-01**: Agent Safety Score — standardized safety metric for AI models
- [ ] **SAF-02**: Open research datasets (anonymized behavioral data)

### Out of Scope

- SaaS / hosted service — SOMA is MIT open-source, self-hosted only
- Paid tiers / monetization — this is a community project, not a business
- Proprietary protocols — all formats and APIs are open standards
- Model training / fine-tuning — SOMA observes and guides, doesn't modify models
- Replacing the agent — SOMA is an immune system, not a brain

## Context

**Current state (v0.5.0):**
- Published on PyPI as `soma-ai` v0.5.0
- Works with Claude Code (hook system) + any Python agent framework (soma.wrap(), soma.track())
- Core engine is platform-agnostic with thin integration layers
- `wrap()` API fully supports Anthropic/OpenAI (sync, async, streaming)
- 8 research-backed intelligence features: goal coherence, uncertainty classification, vector pressure, SNR isolation, half-life, calibration, policy engine, framework adapters
- Structured JSON Lines audit logging, context window tracking
- OpenTelemetry optional dependency exists but no exporter implemented yet
- Cross-platform hook adapters: Cursor, Windsurf, ClaudeCode via unified HookAdapter protocol
- TypeScript SDK prepped for NPM publishing, community policy packs with CLI
- Terminal demo with real engine data (demo.gif)
- ~10,500 LOC Python, 890 tests

**Ecosystem opportunity:**
- No established standard for AI agent behavioral monitoring exists
- Prometheus/Datadog don't understand agent-specific signals (drift, uncertainty, scope)
- AI safety is a growing concern — Anthropic, OpenAI, Google all investing heavily
- Agent frameworks (LangChain, CrewAI, AutoGen) have no built-in monitoring
- Enterprise adoption of AI agents is accelerating but governance tooling lags

**Technical foundation:**
- Python 3.11+, hatchling build, ruff lint, pytest
- Clean 2-layer architecture: core (no deps) + thin integration layer
- EMA baselines, z-score sigmoid pressure, weighted aggregation
- Atomic file persistence with fcntl locking
- Self-learning via intervention outcome tracking

## Constraints

- **Language**: Python-first (core + CLI), TypeScript SDK later
- **License**: MIT — everything stays open
- **Compatibility**: Python 3.11+ (matching current CI matrix)
- **Dependencies**: Minimal core deps (rich, textual, tomli-w); everything else optional
- **Architecture**: Core must remain platform-agnostic — no Claude Code imports in core
- **Quality**: 90%+ test coverage for core, all CI green before release

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| MIT license, no monetization | Goal is industry standard adoption, not revenue | ✓ Good |
| Python-first, TS later | Python dominates agent ecosystem (LangChain, CrewAI, AutoGen) | ✓ Good — TS scaffold ready |
| Policy-as-Code in YAML/TOML | Open, shareable, community-driven (like ESLint configs) | ✓ Good — engine shipped |
| Self-hosted dashboard | No SaaS dependency, enterprise-friendly | — Pending (Milestone 7) |
| OTel for observability | Industry standard, integrates with existing tooling | — Pending (Milestone 4) |
| soma.wrap() as primary API | Transparent proxy, zero code change for users | ✓ Good — sync/async/streaming |
| JSON Lines audit | Zero-config, parseable by jq, rotatable | ✓ Good — shipped v0.5.0 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-01 after Phase 13 (Intelligence: benchmark proof + cross-session learning)*
