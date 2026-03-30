# Roadmap

Where we are. Where we're going. What you can help build.

---

## The Vision

SOMA becomes the standard way to monitor and control AI agents — the way Prometheus became standard for infrastructure monitoring. Every agent framework, every LLM provider, every production deployment runs through SOMA.

Not because we want lock-in. Because agents without oversight are dangerous, expensive, and unpredictable. The research proves it. We're building the fix.

---

## Milestone 1: Foundation ✓

*Shipped March 28, 2026*

The core engine works. Monitor agents, compute pressure, propagate it across graphs, control behavior directively. The math is verified, the tests are comprehensive, the CLI is ready.

| Deliverable | Status |
|:------------|:-------|
| Core engine (vitals, baseline, pressure, graph, ladder, learning) | Done — 100% coverage |
| `soma.wrap()` — universal API client wrapper | Done — Anthropic + OpenAI |
| CLI: `soma`, `soma init`, `soma status`, `soma replay` | Done |
| TUI Dashboard (4 tabs) | Done |
| Session recording + replay | Done |
| `soma.testing.Monitor` for pytest | Done |
| State persistence | Done |
| Cold start grace period | Done |
| Self-learning feedback loop | Done — connected |
| Claude Code hooks (PreToolUse, PostToolUse, Stop) | Done |
| Paperclip plugin | Done — installed |
| Documentation (guide + reference + API) | Done — 3,449 lines |
| Test suite | Done — 399 tests |

---

## Milestone 1.5: Agent Intelligence ✓

*Shipped March 28, 2026*

SOMA stops being a passive monitor and starts actively improving agent quality.

| Deliverable | Status |
|:------------|:-------|
| **Action log** — track tool call patterns for analysis | Done |
| **Actionable feedback** — "3 writes without Read" instead of raw metrics | Done |
| **Post-write validation** — py_compile + ruff lint + node --check | Done |
| **Read-before-Write enforcement** — blocks blind mutations | Done |
| **Cross-session memory** — inherit baseline between sessions | Done |
| **Dead session cleanup** — auto-prune old agent states | Done |
| **Session stats** — error count + top tools on Stop | Done |
| **UserPromptSubmit hook** — inject tips into agent context | Done |
| **Specific block messages** — "Read bar.py first" not just "blocked" | Done |
| Test suite | Done — 476 tests |

---

## Milestone 1.7: Guidance System ✓

*Shipped March 2026 — v0.4.0*

SOMA shifts from progressive blocking (6 levels) to a guidance model (4 modes). Write/Edit/Bash/Agent are never blocked. Only destructive operations are gated at high pressure.

| Deliverable | Status |
|:------------|:-------|
| **4 modes** — OBSERVE / GUIDE / WARN / BLOCK replace 6-level ladder | Done |
| **Guidance over blocking** — tools stay available, advice injected | Done |
| **Destructive-op gating** — rm -rf, git push --force, .env blocked at 75%+ | Done |
| **Simplified CLI** — stop/start/reset/uninstall-claude | Done |
| **Removed commands** — quarantine/release/approve/daemon/export | Done |
| **Skill updates** — all Claude Code skills reflect new model | Done |

---

## Milestone 2: Real-World Ready

*Target: April 2026*

Make SOMA work seamlessly in production. No rough edges. Install, configure, forget.

| Deliverable | Priority | Status |
|:------------|:---------|:-------|
| **PyPI publish** — `pip install soma-ai` works globally | Critical | Done |
| **GitHub Actions CI** — tests on every push/PR | Critical | |
| **Async client support** — `soma.wrap(AsyncAnthropic())` | High | |
| **Progress tracking** — detect stuck agents, not just confused | High | |
| **GIF/demo recording** — for README and social | High | |
| **Real API testing** — verified with live Anthropic + OpenAI | High | |
| **Dashboard UX polish** — responsive layout, keybindings | Medium | |
| **soma.toml validation** — helpful errors on bad config | Medium | |

---

## Milestone 3: Ecosystem

*Target: May 2026*

Framework integrations. Community layers. SOMA works with everything.

| Deliverable | Owner |
|:------------|:------|
| **soma-langchain** — LangChain callback integration | Community |
| **soma-crewai** — CrewAI middleware | Community |
| **soma-autogen** — AutoGen observer | Community |
| **soma-openai-agents** — OpenAI Agents SDK | Community |
| **OpenTelemetry export** — Grafana/Datadog metrics | Community |
| **Layer SDK** — trivial layer creation | Core |
| **Layer registry** — discover and install from CLI | Core |
| **Cursor/Windsurf hooks** — not just Claude Code | Core |

---

## Milestone 4: Intelligence

*Target: June–July 2026*

SOMA stops being reactive and starts being predictive.

| Deliverable | Description |
|:------------|:------------|
| **Anomaly prediction** | Predict escalation 5–10 actions before it happens from historical patterns |
| **Automatic threshold tuning** | ML-optimized thresholds per agent, per task type |
| **Root cause analysis** | Explain WHY in plain English: "Agent stuck in search→edit→search loop since action #42" |
| **Agent fingerprinting** | Learn each agent's "normal" profile, detect corruption |
| **Task-aware monitoring** | Know WHAT the agent is doing, not just HOW — drift from goal, not just from stats |
| **Quality scoring** | Rate output quality, not just behavioral signals — did the code compile? tests pass? |

---

## Milestone 5: Platform

*Target: Q3–Q4 2026*

SOMA becomes a platform. Web dashboard. Teams. Alerting.

| Deliverable | Description |
|:------------|:------------|
| **Web dashboard** | Browser-based. Real-time WebSocket. Shareable URLs. |
| **Team monitoring** | Multiple users, same agents. Role-based access. |
| **Alert channels** | Slack, Discord, email, PagerDuty |
| **Historical analytics** | Trends over time. Which agents struggle? Which tasks cause drift? |
| **API server** | REST/GraphQL for custom integrations |
| **SOMA Cloud** | Hosted version. Sign up, wrap your client, done. |

---

## Milestone 6: Research

*Target: 2027*

Contribute back to the research community.

| Deliverable | Description |
|:------------|:------------|
| **Paper: Behavioral Pressure as Agent Health Metric** | Formalize pressure computation, validate on production data |
| **Paper: Trust Dynamics in Multi-Agent Monitoring** | Analyze trust decay/recovery patterns in real deployments |
| **Open dataset** | Anonymized agent behavior traces |
| **Benchmark suite** | Standard benchmark for agent monitoring tools |

---

## Contributing

Every milestone has tasks marked [`help wanted`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) and [`good first issue`](https://github.com/tr00x/SOMA-Core/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

**Easiest start:** Build a layer. Pick a framework you use and create `soma-{framework}`. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Researchers:** If you work on agent reliability, behavioral analysis, or multi-agent systems — open an issue or reach out.

**Companies:** Running AI agents in production? Want early access to Milestone 4+ features? Open an issue with your use case.

---

## Principles

These don't change regardless of milestone:

1. **Controller, not logger.** SOMA intervenes. It doesn't just record.
2. **Behavioral signals first.** Uncertainty and drift matter more than tokens and cost.
3. **One-line integration.** `soma.wrap(client)` and you're done. Complexity is opt-in.
4. **Open core.** The engine is MIT. Always. Community layers welcome.
5. **Math you can verify.** Every formula is documented. Every constant has a source file.
