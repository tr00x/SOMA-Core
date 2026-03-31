# Roadmap

Where we are. Where we're going. What you can help build.

---

## The Vision

SOMA becomes the standard way to monitor and control AI agents — the way Prometheus became standard for infrastructure monitoring. Every agent framework, every LLM provider, every production deployment runs through SOMA.

Not because we want lock-in. Because agents without oversight are dangerous, expensive, and unpredictable. The research proves it. We're building the fix.

---

## Current Version: 0.5.0

---

## Milestone 1: Foundation ✓

*Shipped March 28, 2026*

Core engine, CLI, hooks, persistence, self-learning, test suite.

| Deliverable | Status |
|:------------|:-------|
| Core engine (vitals, baseline, pressure, graph, learning) | Done |
| `soma.wrap()` — Anthropic + OpenAI client wrapper | Done |
| CLI + TUI Dashboard | Done |
| Session recording + replay | Done |
| State persistence (atomic writes, file locking) | Done |
| Self-learning feedback loop | Done |
| Claude Code hooks (4 lifecycle hooks + status line) | Done |
| 4-mode guidance (OBSERVE/GUIDE/WARN/BLOCK) | Done |
| False positive reduction, read-context awareness | Done |
| Layer-agnostic architecture (patterns, findings, context) | Done |
| Test suite — 476 tests | Done |

---

## Milestone 2: Agent Intelligence ✓

*Shipped March 31, 2026 — v0.5.0*

8 phases of behavioral analysis. SOMA gains uncertainty classification, vector pressure propagation, temporal modeling, reliability metrics, policy engine, framework adapters, and per-session isolation.

| Deliverable | Description | Status |
|:------------|:------------|:-------|
| Vitals Accuracy | Goal coherence, uncertainty classification, baseline integrity | Done |
| Uncertainty Classification | Epistemic/aleatoric via entropy, pressure modulation (1.3x/0.7x) | Done |
| Vector Pressure Propagation | PressureVector per-signal through trust graph | Done |
| Coordination Intelligence | SNR isolation, task complexity estimation | Done |
| Temporal Half-Life | Exponential decay modeling, handoff suggestions | Done |
| Reliability Metrics | Calibration scoring, verbal-behavioral divergence | Done |
| Universal Python SDK | LangChain, CrewAI, AutoGen adapters | Done |
| Policy Engine + TypeScript | Declarative YAML/TOML rules, @guardrail, TypeScript SDK scaffold | Done |
| Error-Rate Aggregate Floor | Prevents weighted-mean dilution of dominant error signals | Done |
| Per-Session Isolation | Each Claude Code instance gets own agent_id + state files | Done |
| Test suite — 735 tests | Done |

---

## Milestone 3: Production Ready

*Target: April 2026*

**Without this, nobody can use SOMA in real production.** These are adoption blockers.

| Deliverable | Priority | Why |
|:------------|:---------|:----|
| **Async client support** — `soma.wrap(AsyncAnthropic())` | Critical | 90% of production Python uses async |
| **Streaming support** — intercept `client.messages.stream()` | Critical | Every real app streams responses |
| **PyPI publish 0.5.0** — update the published package | Critical | Users still get 0.4.12 |
| **Real API testing** — verified with live Anthropic + OpenAI calls | Critical | Never tested against real API response formats |
| **Phase 11: Context window tracking** — context exhaustion as first-class pressure signal | High | Strongest predictor of agent degradation; half-life model needs this input |
| **Structured audit log** (OTL-02) — JSON Lines per action, zero config | High | Done (Phase 10) |
| **Phase 12: CONTRIBUTING.md** — how to contribute, dev setup, test instructions | High | Open source without it is dead |
| **Phase 13: soma.toml validation** — helpful errors on bad config | Medium | Current failure mode is silent |

---

## Milestone 4: Observability

*Target: April–May 2026*

SOMA speaks the language of existing monitoring infrastructure.

| Deliverable | Description |
|:------------|:------------|
| **OpenTelemetry export** (OTL-01) | Export pressure, vitals, mode changes as OTEL spans + metrics. Grafana/Datadog/New Relic out of the box. |
| **Session reports** (RPT-01) | Automatic post-session summary — actions, quality, cost, patterns, interventions. HTML or Markdown. |
| **Webhook alerting** | Slack, Discord, PagerDuty on WARN/BLOCK/policy violation |
| **Historical analytics** | Trends over time per agent. Which tasks cause drift? Which agents degrade fastest? |

---

## Milestone 5: Ecosystem

*Target: May 2026*

SOMA works with every agent platform, not just Claude Code.

| Deliverable | Description |
|:------------|:------------|
| **Cursor/Windsurf hooks** | Same 4-hook architecture adapted for other AI coding tools |
| **OpenAI Agents SDK adapter** | Native integration with OpenAI's agent framework |
| **NPM publish TypeScript SDK** | `packages/soma-ai/` published to npm |
| **Demo GIF/video** | README demo showing SOMA in action — the "aha moment" |
| **Community policy packs** (POL-03) | Shareable rule sets on GitHub — security, cost, quality presets |
| **Layer SDK** | Trivial creation of new platform integrations |

---

## Milestone 6: Intelligence

*Target: June–July 2026*

SOMA stops being reactive and starts being predictive.

| Deliverable | Description |
|:------------|:------------|
| **Context-aware degradation** | Combine context window usage + half-life + error trend into composite degradation score |
| **Automatic threshold tuning** | ML-optimized thresholds per agent type, per task type, per codebase |
| **Task-aware monitoring** | Understand WHAT the agent is doing (not just HOW) — semantic drift from goal |
| **Anomaly prediction** | Predict escalation 5–10 actions ahead from historical cross-session patterns |
| **Agent comparison** | Same task, different models — which performs better under SOMA? |

---

## Milestone 7: Platform

*Target: Q3–Q4 2026*

SOMA becomes a platform. Web dashboard. Teams. Fleet management.

| Deliverable | Description |
|:------------|:------------|
| **Web dashboard** | Browser-based real-time monitoring. WebSocket. Multi-agent view. |
| **Team monitoring** | Multiple users, same project. Role-based access. |
| **Fleet management** | Central config for multiple machines. Aggregate dashboards. |
| **API server** | REST/GraphQL for custom integrations |
| **SOMA Cloud** | Hosted version. Sign up, wrap your client, done. |

---

## Milestone 8: Research

*Target: 2027*

Contribute back to the research community.

| Deliverable | Description |
|:------------|:------------|
| **Paper: Behavioral Pressure as Agent Health Metric** | Formalize pressure computation, validate on production data |
| **Paper: Trust Dynamics in Multi-Agent Monitoring** | Analyze trust decay/recovery patterns in real deployments |
| **Open dataset** | Anonymized agent behavior traces from real sessions |
| **Benchmark suite** | Standard benchmark for agent monitoring tools |

---

## Contributing

Every milestone has tasks marked [`help wanted`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) and [`good first issue`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

**Easiest start:** Pick a framework you use and write an adapter. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Researchers:** Working on agent reliability, behavioral analysis, or multi-agent systems? Open an issue or reach out.

**Companies:** Running AI agents in production? Open an issue with your use case.

---

## Principles

These don't change regardless of milestone:

1. **Controller, not logger.** SOMA intervenes. It doesn't just record.
2. **Behavioral signals first.** Uncertainty classification, reliability metrics, and drift matter more than tokens and cost.
3. **One-line integration.** `soma.wrap(client)` and you're done. Complexity is opt-in.
4. **Open core.** The engine is MIT. Always. Community layers welcome.
5. **Math you can verify.** Every formula is documented. Every constant has a source file.
