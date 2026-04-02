# Roadmap

Where we are. Where we're going. What you can help build.

---

## The Vision

SOMA becomes the standard way to monitor AI agents — the way Prometheus became standard for infrastructure monitoring. Every agent framework, every LLM provider, every production deployment runs through SOMA.

Not because we want lock-in. Because agents without oversight are dangerous, expensive, and unpredictable. The research proves it. We're building the fix.

---

## Current Version: 0.6.0

86 modules | 1,213 tests | 25k lines | Python 3.11+ | MIT license

---

## Milestone 1: Foundation ✓

*Shipped March 28, 2026*

Core engine, CLI, hooks, persistence, self-learning, test suite.

- Core engine (vitals, baseline, pressure, graph, learning)
- `soma.wrap()` — Anthropic + OpenAI client wrapper
- CLI + TUI Dashboard
- Session recording + replay
- State persistence (atomic writes, file locking)
- Self-learning feedback loop
- Claude Code hooks (lifecycle hooks + status line)
- 4-mode guidance (OBSERVE/GUIDE/WARN/BLOCK)

---

## Milestone 2: Agent Intelligence ✓

*Shipped March 31, 2026 — v0.5.0*

Uncertainty classification, vector pressure propagation, temporal modeling, reliability metrics, policy engine, framework adapters.

- Epistemic/aleatoric uncertainty decomposition
- PressureVector per-signal propagation through trust graph
- Coordination SNR isolation
- Half-life temporal modeling + handoff suggestions
- Calibration scoring + verbal-behavioral divergence
- LangChain, CrewAI, AutoGen SDK adapters
- Policy engine (YAML/TOML rules, @guardrail decorator)
- Per-session isolation

---

## Milestone 3: Production Hardening ✓

*Shipped April 1, 2026 — v0.6.0*

Async support, streaming, real API testing, context tracking, reflexes, Mirror.

- Async client support (`soma.wrap(AsyncAnthropic())`)
- Streaming interception (Anthropic + OpenAI)
- Context window tracking — context_exhaustion as first-class signal
- Mirror — proprioceptive feedback via environment augmentation (PATTERN/STATS/SEMANTIC)
- Mirror self-learning with pattern database
- Reflex system — hard blocks for destructive ops, retry dedup, blind edits, commit gate
- SOMAProxy — universal tool wrapper for any framework
- Subagent monitoring with cascade risk propagation
- Bimodal pressure fix (linear ramp grace period + linear error floor)
- Session state isolation fix
- 13 bugs found and fixed via deep audit
- PyPI published as `soma-ai`
- OpenTelemetry export (optional `otel` extra)
- Webhook alerting on WARN/BLOCK events
- Session reports (Markdown)
- Cursor + Windsurf hook adapters
- Community policy packs
- CONTRIBUTING.md

---

## Milestone 4: Web Dashboard

*Target: April 2026*

SOMA gets a browser-based real-time dashboard. Everything visible at a glance.

| Deliverable | Description |
|:------------|:------------|
| **Web API server** | FastAPI backend serving SOMA state via REST endpoints |
| **Real-time dashboard** | Live pressure, vitals, patterns, findings — black + pink theme |
| **Pressure timeline** | Interactive chart of pressure trajectory over session |
| **Agent cards** | Per-agent status with vitals, mode, action count, quality grade |
| **Session history** | Browse past sessions, compare trajectories, view reports |
| **Audit log viewer** | Searchable/filterable view of audit.jsonl |
| **Multi-agent graph** | Visual PressureGraph with trust edges and cascade flow |

---

## Milestone 5: Ecosystem

*Target: May 2026*

SOMA works everywhere, not just Claude Code.

| Deliverable | Description |
|:------------|:------------|
| **OpenAI Agents SDK adapter** | Native integration with OpenAI's agent framework |
| **NPM publish TypeScript SDK** | `packages/soma-ai/` published to npm |
| **Vercel AI SDK adapter** | Integration for Next.js AI applications |
| **Demo GIF/video** | README demo showing SOMA in action |
| **Layer SDK** | Trivial creation of new platform integrations |

---

## Milestone 6: Intelligence

*Target: June–July 2026*

SOMA stops being reactive and starts being predictive.

| Deliverable | Description |
|:------------|:------------|
| **Composite degradation score** | Context usage + half-life + error trend → single agent health metric |
| **Automatic threshold tuning** | ML-optimized thresholds per agent type, per task type |
| **Semantic task understanding** | Understand WHAT the agent is doing, not just HOW — semantic drift from goal |
| **Deep anomaly prediction** | Predict escalation 10+ actions ahead from cross-session patterns |
| **Agent comparison** | Same task, different models — behavioral comparison under SOMA |
| **Benchmark suite** | Standard benchmark for agent monitoring tools |

---

## Milestone 7: Platform

*Target: Q3–Q4 2026*

SOMA becomes a platform. Teams. Fleet management. Central control.

| Deliverable | Description |
|:------------|:------------|
| **Team monitoring** | Multiple users, same project. Role-based access. |
| **Fleet management** | Central config for multiple machines. Aggregate dashboards. |
| **GraphQL API** | Flexible queries for custom integrations |
| **SOMA Cloud** | Hosted version. Sign up, wrap your client, done. |

---

## Milestone 8: Research

*Target: 2027*

Contribute back to the research community.

| Deliverable | Description |
|:------------|:------------|
| **Paper: Proprioceptive Monitoring** | Formalize environment augmentation, validate on production data |
| **Paper: Trust Dynamics** | Analyze trust decay/recovery in real multi-agent deployments |
| **Open dataset** | Anonymized agent behavior traces from real sessions |

---

## Contributing

Every milestone has tasks marked [`help wanted`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) and [`good first issue`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

**Easiest start:** Pick a framework you use and write an adapter. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Researchers:** Working on agent reliability or behavioral analysis? Open an issue or reach out.

---

## Principles

These don't change:

1. **Controller, not logger.** SOMA intervenes. It doesn't just record.
2. **Behavioral signals first.** Uncertainty, drift, and goal coherence matter more than token counts.
3. **One-line integration.** `soma.wrap(client)` and you're done.
4. **MIT forever.** The engine is open. Always.
5. **Math you can verify.** Every formula documented. Every constant has a source file.
