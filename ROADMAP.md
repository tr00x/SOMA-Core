# SOMA Core Roadmap

Where we are. Where we're going. What you can help build.

---

## The Vision

SOMA becomes the standard way to monitor and control AI agents — the same way Prometheus became standard for infrastructure monitoring. Every agent framework, every LLM provider, every production deployment runs through SOMA.

Not because we want lock-in. Because agents without oversight are dangerous, expensive, and unpredictable. The research proves it. We're building the fix.

---

## Milestone 1: Foundation (DONE)

*Shipped: March 28, 2026*

The core engine works. You can monitor agents, compute pressure, propagate it across graphs, and control agent behavior directively. The math is verified, the tests are comprehensive, and the CLI is ready.

| Deliverable | Status |
|---|---|
| Core engine (vitals, baseline, pressure, graph, ladder, learning) | Done. 100% coverage. |
| `soma.wrap()` — universal API client wrapper | Done. Anthropic + OpenAI. |
| CLI: `soma`, `soma init`, `soma status`, `soma replay` | Done. |
| TUI Dashboard (4 tabs) | Done. |
| Session recording + replay | Done. |
| `soma.testing.Monitor` for pytest | Done. |
| State persistence | Done. |
| Cold start grace period | Done. |
| Self-learning feedback loop | Done. Connected. |
| Claude Code hooks (PreToolUse, PostToolUse, PostMessage, Stop) | Done. |
| Paperclip plugin | Done. Installed. |
| Documentation (guide + reference + API) | Done. 3,449 lines. |
| 399 tests | Done. |

---

## Milestone 2: Real-World Ready

*Target: April 2026*

Make SOMA work seamlessly in production. No rough edges. Install, configure, forget.

| Deliverable | Issue | Priority |
|---|---|---|
| **PyPI publish** — `pip install soma-core` works globally | [#1](https://github.com/tr00x/SOMA-Core/issues/1) | Critical |
| **Async client support** — `soma.wrap(AsyncAnthropic())` | [#2](https://github.com/tr00x/SOMA-Core/issues/2) | High |
| **Progress tracking** — detect stuck agents (not just confused) | [#6](https://github.com/tr00x/SOMA-Core/issues/6) | High |
| **GIF/demo recording** — for README and social media | | High |
| **Real API testing** — verified with live Anthropic + OpenAI calls | | High |
| **Dashboard UX polish** — responsive layout, keybindings, help text | | Medium |
| **soma.toml validation** — helpful errors on bad config | | Medium |
| **GitHub Actions CI** — green badge on every PR | | Medium |

---

## Milestone 3: Ecosystem

*Target: May 2026*

Framework integrations. Community layers. SOMA works with everything.

| Deliverable | Issue | Owner |
|---|---|---|
| **soma-langchain** — LangChain callback integration | [#4](https://github.com/tr00x/SOMA-Core/issues/4) | Community |
| **soma-crewai** — CrewAI middleware | [#5](https://github.com/tr00x/SOMA-Core/issues/5) | Community |
| **soma-autogen** — AutoGen observer | | Community |
| **soma-openai-agents** — OpenAI Agents SDK integration | | Community |
| **OpenTelemetry export** — metrics to Grafana/Datadog | [#7](https://github.com/tr00x/SOMA-Core/issues/7) | Community |
| **Layer SDK** — make it trivial to build new layers | | Core team |
| **Layer registry** — discover and install layers from CLI | | Core team |

---

## Milestone 4: Intelligence

*Target: June-July 2026*

SOMA stops being reactive and starts being predictive. Machine learning on agent behavior patterns.

| Deliverable | Description |
|---|---|
| **Anomaly prediction** | Predict escalation 5-10 actions before it happens based on historical patterns |
| **Automatic threshold tuning** | ML-optimized thresholds per agent, per task type — no manual config |
| **Root cause analysis** | When SOMA escalates, explain WHY in plain English: "Agent stuck in search→edit→search loop since action #42" |
| **Agent fingerprinting** | Learn each agent's "normal" profile and detect impersonation or corruption |
| **Cross-session learning** | Carry behavioral insights across sessions — "This agent always struggles with file operations" |

---

## Milestone 5: Platform

*Target: Q3-Q4 2026*

SOMA becomes a platform. Web dashboard. Teams. Alerting. The works.

| Deliverable | Description |
|---|---|
| **Web dashboard** | Browser-based alternative to TUI. Real-time WebSocket updates. Shareable URLs. |
| **Team monitoring** | Multiple users watching the same agents. Role-based access. |
| **Alert channels** | Slack, Discord, email, PagerDuty — notify when agents escalate |
| **Historical analytics** | Trends over time. Which agents struggle most? Which tasks cause drift? |
| **API server** | REST/GraphQL API for custom integrations |
| **SOMA Cloud** | Hosted version. No setup. Sign up, wrap your client, done. |

---

## Milestone 6: Research

*Target: 2027*

Contribute back to the research community. Publish findings from real-world SOMA deployments.

| Deliverable | Description |
|---|---|
| **Paper: Behavioral Pressure as Agent Health Metric** | Formalize pressure computation, validate on production data |
| **Paper: Trust Dynamics in Multi-Agent Monitoring** | Analyze trust decay/recovery patterns in real deployments |
| **Open dataset** | Anonymized agent behavior traces for research community |
| **Benchmark suite** | Standard benchmark for agent monitoring tools |

---

## How to Contribute

Every milestone has tasks marked `help wanted` and `good first issue` in [GitHub Issues](https://github.com/tr00x/SOMA-Core/issues).

**Easiest way to start:** Build a layer. Pick a framework you use (LangChain, CrewAI, AutoGen) and create a `soma-{framework}` package. See [CONTRIBUTING.md](CONTRIBUTING.md) for the guide.

**For researchers:** If you work on agent reliability, behavioral analysis, or multi-agent systems — we want to talk. Open an issue or reach out.

**For companies:** If you run AI agents in production and want early access to Milestone 4+ features — open an issue describing your use case.

---

## Principles

These don't change regardless of milestone:

1. **Controller, not logger.** SOMA intervenes. It doesn't just record.
2. **Behavioral signals first.** Uncertainty and drift matter more than tokens and cost.
3. **One-line integration.** `soma.wrap(client)` and you're done. Complexity is opt-in.
4. **Open core.** The engine is MIT. Always. Community layers welcome.
5. **Math you can verify.** Every formula is documented. Every constant has a source file.
