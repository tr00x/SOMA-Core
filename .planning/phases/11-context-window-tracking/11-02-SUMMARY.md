---
phase: 11-context-window-tracking
plan: 02
subsystem: observability
tags: [opentelemetry, otel, webhooks, exporters, alerting, grpc]

requires:
  - phase: 11-context-window-tracking plan 01
    provides: Exporter protocol, engine.add_exporter(), EventBus events
provides:
  - OTelExporter class emitting spans and metrics to any OTel collector
  - WebhookExporter class firing HTTP POST alerts on WARN/BLOCK events
  - create_exporters_from_config() for config-driven exporter activation
  - OTLP gRPC exporter optional dependency
affects: [11-context-window-tracking, dashboard, fleet]

tech-stack:
  added: [opentelemetry-exporter-otlp-proto-grpc]
  patterns: [try/except import with HAS_OTEL flag, daemon thread dispatch, retry-once-then-drop]

key-files:
  created:
    - src/soma/exporters/otel.py
    - src/soma/exporters/webhook.py
    - tests/test_otel_exporter.py
    - tests/test_webhook.py
  modified:
    - src/soma/cli/config_loader.py
    - pyproject.toml

key-decisions:
  - "Local TracerProvider/MeterProvider — no global OTel state pollution"
  - "Daemon threads for webhook dispatch — fire-and-forget, never blocks engine"
  - "Retry once on webhook failure then silently drop — no queue buildup"

patterns-established:
  - "Try/except import guard with HAS_OTEL flag for graceful degradation"
  - "Daemon thread dispatch for non-blocking external I/O in exporters"
  - "Config-driven exporter instantiation via create_exporters_from_config()"

requirements-completed: [OTL-01, ALT-01]

duration: 5min
completed: 2026-03-31
---

# Phase 11 Plan 02: OTel + Webhook Exporters Summary

**OTel exporter emitting spans/metrics per action to any collector, webhook alerter firing HTTP POST on WARN/BLOCK via daemon threads, both config-driven from soma.toml**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-01T00:04:47Z
- **Completed:** 2026-04-01T00:10:13Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- OTelExporter creates spans per action (soma.action.{tool_name}) with agent_id, pressure, mode, error, token_count attributes
- OTelExporter records gauge metrics (pressure, uncertainty, drift, error_rate, context_usage) and counter metrics (actions.total, actions.errors)
- OTelExporter gracefully no-ops when opentelemetry packages not installed
- WebhookExporter fires HTTP POST on WARN/BLOCK mode changes to all configured URLs
- Webhook dispatch on daemon threads — non-blocking, retry once on failure then drop
- config_loader.py reads [otel] and [webhooks] from soma.toml, auto-instantiates exporters
- 836 tests pass (31 new), full suite green

## Task Commits

Each task was committed atomically:

1. **Task 1: OpenTelemetry exporter with spans and metrics** - `736be32` (test: RED), `f8a3b81` (feat: GREEN)
2. **Task 2: Webhook exporter, config_loader integration** - `b3c5108` (test: RED), `9b0a8db` (feat: GREEN)

## Files Created/Modified
- `src/soma/exporters/otel.py` - OTelExporter class: spans + metrics to OTel collector
- `src/soma/exporters/webhook.py` - WebhookExporter class: fire-and-forget HTTP POST alerting
- `src/soma/cli/config_loader.py` - Added create_exporters_from_config() and wired into create_engine_from_config()
- `pyproject.toml` - Added opentelemetry-exporter-otlp-proto-grpc to otel optional dep
- `tests/test_otel_exporter.py` - 12 tests for OTel exporter (spans, metrics, no-op, protocol)
- `tests/test_webhook.py` - 19 tests for webhook exporter and config_loader integration

## Decisions Made
- Local TracerProvider/MeterProvider (no global trace.set_tracer_provider) to avoid polluting user's OTel setup
- Daemon threads for webhook dispatch — process exit cleans up automatically
- Retry once on webhook failure then silently drop — prevents queue buildup
- Distinct gauge per metric name via create_gauge() for proper OTel semantics

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- MagicMock(name="WARN") sets the mock's internal __name__, not the .name attribute — fixed with helper factory function in tests

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all functionality is fully wired.

## Next Phase Readiness
- OTel and webhook exporters ready for use
- Config sections [otel] and [webhooks] in soma.toml activate exporters
- Exporter protocol from Plan 01 fully implemented by both exporters
- Ready for Plan 03 (reports & analytics)

---
*Phase: 11-context-window-tracking*
*Completed: 2026-03-31*
