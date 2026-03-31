# Phase 11: Observability - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

SOMA emits structured observability data to any OpenTelemetry-compatible collector and produces session reports. This is the nervous system's ability to REPORT what it senses — pressure, vitals, mode changes, interventions — in formats that existing monitoring infrastructure understands. Additionally, context window monitoring graduates from a passive ratio to an active pressure signal with burn rate tracking and model-aware window sizing.

**What this phase delivers:**
1. **OpenTelemetry export** (OTL-01) — Export pressure, vitals, mode changes as OTEL spans + metrics
2. **Session reports** (RPT-01) — Automatic post-session Markdown report with actions, quality, cost, patterns
3. **Webhook alerting** (ALT-01) — Configurable webhook dispatch on WARN/BLOCK/policy violation
4. **Historical analytics** (HIST-01) — Per-agent trends over time queryable from stored data
5. **Context window intelligence** — Context exhaustion as first-class pressure signal, burn rate, model-aware sizing

**Out of scope:** Web dashboard (Phase 14), fleet management, cross-machine aggregation.

</domain>

<decisions>
## Implementation Decisions

### OpenTelemetry integration (OTL-01)
- **D-01:** Use the existing optional `opentelemetry-api` and `opentelemetry-sdk` dependencies (already in pyproject.toml `[otel]` extra). Zero new required deps.
- **D-02:** Create `src/soma/exporters/otel.py` — an OTelExporter class that hooks into the engine's EventBus. On each action result, emit a span (action name, duration, result) and gauge metrics (pressure, vitals).
- **D-03:** Metrics exported: `soma.pressure` (gauge, 0-1), `soma.vitals.uncertainty` (gauge), `soma.vitals.drift` (gauge), `soma.vitals.error_rate` (gauge), `soma.vitals.context_usage` (gauge), `soma.mode` (enum label), `soma.actions.total` (counter), `soma.actions.errors` (counter).
- **D-04:** Spans: one span per `record_action()` call. Span name = `soma.action.{tool_name}`. Attributes: agent_id, pressure, mode, error, token_count.
- **D-05:** Activation via `soma.toml`:
  ```toml
  [otel]
  enabled = true
  endpoint = "http://localhost:4317"  # OTLP gRPC default
  service_name = "soma-agent"
  ```
- **D-06:** If otel packages not installed, graceful no-op — log warning once, never crash.

### Session reports (RPT-01)
- **D-07:** Create `src/soma/report.py` — `generate_session_report(engine) -> str` returns Markdown.
- **D-08:** Report sections: Summary (duration, action count, final pressure, mode), Vitals Timeline (key metrics at start/mid/end), Interventions (list of WARN/BLOCK events with timestamps), Cost (total tokens, total cost), Patterns (top tool usage, error clusters), Quality Score (0-100 composite).
- **D-09:** Report triggered automatically on engine shutdown/cleanup, or manually via `soma report` CLI command.
- **D-10:** Reports saved to `~/.soma/reports/YYYY-MM-DD_HH-MM-SS_{agent_id}.md`. Directory auto-created.
- **D-11:** Engine needs a `shutdown()` or `finalize()` method that generates the report and flushes OTel spans.

### Webhook alerting (ALT-01)
- **D-12:** Create `src/soma/exporters/webhook.py` — WebhookExporter class subscribing to EventBus.
- **D-13:** Fires on events: `mode_change` (to WARN or BLOCK), `policy_violation`, `budget_exhausted`, `context_critical`.
- **D-14:** Payload format: JSON with `event_type`, `agent_id`, `pressure`, `mode`, `timestamp`, `details` dict.
- **D-15:** Configuration via `soma.toml`:
  ```toml
  [webhooks]
  enabled = true
  urls = ["https://hooks.slack.com/...", "https://discord.com/api/webhooks/..."]
  events = ["warn", "block", "policy_violation"]
  ```
- **D-16:** HTTP POST with 3-second timeout, fire-and-forget (async, never blocks engine). Retry once on failure, then drop.
- **D-17:** Use `urllib.request` from stdlib — no `requests` dependency. Background thread for dispatch.

### Historical analytics (HIST-01)
- **D-18:** Create `src/soma/analytics.py` — stores per-action snapshots to a local SQLite database at `~/.soma/analytics.db`.
- **D-19:** Schema: `actions` table with columns: `timestamp`, `agent_id`, `session_id`, `tool_name`, `pressure`, `uncertainty`, `drift`, `error_rate`, `context_usage`, `token_count`, `cost`, `mode`, `error`.
- **D-20:** Query API: `get_agent_trends(agent_id, last_n_sessions)` returns per-session aggregates. `get_tool_stats(agent_id)` returns tool usage distribution.
- **D-21:** CLI command: `soma analytics [agent_id]` — prints trend table with last 10 sessions.
- **D-22:** SQLite chosen for zero-config, zero-dependency (stdlib). No migration framework — single CREATE TABLE IF NOT EXISTS.

### Context window intelligence
- **D-23:** Add `"context_exhaustion"` to `signal_pressures` dict in engine.py. Computed as `sigmoid_clamp((context_usage - 0.5) / 0.15)` — starts rising at 50%, saturates near 85%.
- **D-24:** Weight in `DEFAULT_WEIGHTS`: `"context_exhaustion": 1.5`. Separate from existing `token_usage` (budget-based).
- **D-25:** Token burn rate: rolling average of tokens per action over last 10 actions. New field `context_burn_rate: float` in `VitalsSnapshot`.
- **D-26:** Model-aware sizing: extract model name from API response in `wrap.py`. New `src/soma/models.py` with `MODEL_CONTEXT_WINDOWS` dict mapping model names → window sizes. Auto-detect on first response.
- **D-27:** Proactive events: emit `"context_warning"` at 70% usage, `"context_critical"` at 90%. Fire once per threshold crossing.
- **D-28:** These events feed into webhook alerting (D-13) — context_critical triggers webhook dispatch.

### Module structure
- **D-29:** New `src/soma/exporters/` package with `__init__.py`, `otel.py`, `webhook.py`.
- **D-30:** New top-level modules: `src/soma/report.py`, `src/soma/analytics.py`, `src/soma/models.py`.
- **D-31:** Engine gets `add_exporter(exporter)` method — exporters subscribe to EventBus. Clean separation.

### Claude's Discretion
- Exact OTel span attributes beyond the required set
- SQLite schema indexing strategy
- Report formatting details and quality score formula
- Webhook retry timing
- Test scenario design for all components
- Whether analytics queries use raw SQL or a thin wrapper

</decisions>

<specifics>
## Specific Ideas

- "Нервная система киборга" — SOMA should FEEL everything and REPORT everything. OTel is the nervous system's output to external monitors. Session reports are the self-diagnostic readout.
- Context exhaustion should have "real teeth" in the pressure system — not just a modifier on success rate
- Zero new required dependencies — OTel is optional extra, webhooks use stdlib, SQLite is stdlib
- Fire-and-forget for webhooks — never slow down the engine for external reporting

</specifics>

<canonical_refs>
## Canonical References

### Roadmap
- `ROADMAP.md` §Milestone 4 — OpenTelemetry export, session reports, webhook alerting, historical analytics
- `.planning/ROADMAP.md` §Phase 11 — Goal, requirements (OTL-01, RPT-01, ALT-01, HIST-01), success criteria

### Existing code to extend
- `src/soma/engine.py` — SOMAEngine (add exporter registration, shutdown method, context pressure signal)
- `src/soma/engine.py` lines 392-399 — Signal pressures dict (add context_exhaustion)
- `src/soma/engine.py` lines 519-526 — Context usage computation
- `src/soma/events.py` — EventBus (exporters subscribe here)
- `src/soma/pressure.py` lines 8-15 — DEFAULT_WEIGHTS (add context_exhaustion)
- `src/soma/types.py` — VitalsSnapshot (add context_burn_rate), Action (metadata for model name)
- `src/soma/wrap.py` lines 484-515 — _extract_response_data (add model extraction)
- `src/soma/predictor.py` — Pattern boosts (add context patterns)
- `src/soma/cli/main.py` — CLI router (add `report` and `analytics` subcommands)

### Dependencies
- `pyproject.toml` — opentelemetry-api and opentelemetry-sdk already in `[otel]` optional extra

### Tests
- `tests/test_context_usage.py` — Extend for context exhaustion pressure
- `tests/test_predictor.py` — Extend for context patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `EventBus` in `events.py` — exporters subscribe to action events, mode changes, warnings
- `sigmoid_clamp()` in `pressure.py` — reuse for context exhaustion signal
- `SessionRecorder` in `recorder.py` — similar pattern to session report (captures action sequence)
- `persistence.py` — atomic write pattern for report/analytics file writes
- `MultiBudget.projected_overshoot()` — similar projection pattern for burn rate

### Established Patterns
- Optional extras: OTel already declared in pyproject.toml, import with try/except
- Signal pressures: add to dict → aggregate picks it up automatically
- Config sections: `config.get("section", {}).get("key", default)` pattern
- CLI subcommands: argparse subparsers in `cli/main.py`

### Integration Points
- `engine.record_action()` → emit event for exporters after computing ActionResult
- `engine.shutdown()` (new) → flush OTel, generate report, close analytics DB
- `wrap.py._extract_response_data()` → extract model name from response
- `_AgentState` → add token_burn_history list, context warning flags
- `soma.toml` → add `[otel]`, `[webhooks]` sections to config_loader

</code_context>

<deferred>
## Deferred Ideas

- Web dashboard (Phase 14) — will consume OTel data and analytics DB
- Grafana/Datadog pre-built dashboards — templates can ship later
- Cross-machine analytics aggregation — Phase 14 (Platform)
- PressureVector extension with context_usage dimension — can add without breaking changes
- Model-specific degradation curves — Phase 13 (Intelligence)

</deferred>

---

*Phase: 11-context-window-tracking*
*Context gathered: 2026-03-31*
