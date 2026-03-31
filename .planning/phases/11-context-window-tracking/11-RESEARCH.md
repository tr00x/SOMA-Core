# Phase 11: Observability - Research

**Researched:** 2026-03-31
**Domain:** OpenTelemetry integration, session reporting, webhook alerting, historical analytics, context window intelligence
**Confidence:** HIGH

## Summary

Phase 11 adds four observability pillars to SOMA: OpenTelemetry export (traces + metrics to any collector), session reports (Markdown summaries), webhook alerting (fire-and-forget HTTP POST on WARN/BLOCK), and historical analytics (SQLite-backed per-agent trends). Additionally, context window exhaustion becomes a first-class pressure signal with burn rate tracking and model-aware sizing.

The existing codebase has strong foundations: the `EventBus` pub/sub system provides the subscription mechanism exporters need, `sigmoid_clamp()` is ready for context exhaustion pressure, and the `AuditLogger` pattern (never-crash, graceful fallback) serves as the template for all new exporter modules. The OTel optional dependency is already declared in `pyproject.toml`.

**Primary recommendation:** Build an exporter interface (`add_exporter()` on engine) that hooks into `EventBus`. Each exporter (OTel, webhook) subscribes to events independently. Keep all new modules (report, analytics, models) as pure functions or simple classes with zero required dependencies beyond stdlib. The engine's `shutdown()` method coordinates flush/finalize across all exporters.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Use existing optional `opentelemetry-api` and `opentelemetry-sdk` (already in pyproject.toml `[otel]` extra). Zero new required deps.
- D-02: Create `src/soma/exporters/otel.py` with OTelExporter class hooking into EventBus.
- D-03: Metrics: `soma.pressure` (gauge), `soma.vitals.uncertainty` (gauge), `soma.vitals.drift` (gauge), `soma.vitals.error_rate` (gauge), `soma.vitals.context_usage` (gauge), `soma.mode` (enum label), `soma.actions.total` (counter), `soma.actions.errors` (counter).
- D-04: Spans: one per `record_action()`, name = `soma.action.{tool_name}`, attributes: agent_id, pressure, mode, error, token_count.
- D-05: Activation via `soma.toml` `[otel]` section with enabled, endpoint, service_name.
- D-06: Graceful no-op if OTel packages not installed.
- D-07: Create `src/soma/report.py` with `generate_session_report(engine) -> str`.
- D-08: Report sections: Summary, Vitals Timeline, Interventions, Cost, Patterns, Quality Score.
- D-09: Report triggered on engine shutdown or via `soma report` CLI.
- D-10: Reports saved to `~/.soma/reports/YYYY-MM-DD_HH-MM-SS_{agent_id}.md`.
- D-11: Engine needs `shutdown()` / `finalize()` method.
- D-12: Create `src/soma/exporters/webhook.py` with WebhookExporter class.
- D-13: Fires on: `mode_change` (to WARN/BLOCK), `policy_violation`, `budget_exhausted`, `context_critical`.
- D-14: JSON payload: event_type, agent_id, pressure, mode, timestamp, details.
- D-15: Config via `soma.toml` `[webhooks]` section.
- D-16: HTTP POST, 3-second timeout, fire-and-forget, retry once then drop.
- D-17: Use `urllib.request` from stdlib. Background thread for dispatch.
- D-18: Create `src/soma/analytics.py` with SQLite storage at `~/.soma/analytics.db`.
- D-19: Schema: `actions` table with timestamp, agent_id, session_id, tool_name, pressure, uncertainty, drift, error_rate, context_usage, token_count, cost, mode, error.
- D-20: Query API: `get_agent_trends(agent_id, last_n_sessions)`, `get_tool_stats(agent_id)`.
- D-21: CLI command: `soma analytics [agent_id]`.
- D-22: SQLite zero-config, single CREATE TABLE IF NOT EXISTS.
- D-23: Add `"context_exhaustion"` to signal_pressures: `sigmoid_clamp((context_usage - 0.5) / 0.15)`.
- D-24: Weight: `"context_exhaustion": 1.5` in DEFAULT_WEIGHTS.
- D-25: Token burn rate: rolling average over last 10 actions. New `context_burn_rate` in VitalsSnapshot.
- D-26: Model-aware sizing: `src/soma/models.py` with MODEL_CONTEXT_WINDOWS dict. Auto-detect from API response.
- D-27: Proactive events: `context_warning` at 70%, `context_critical` at 90%.
- D-28: Context_critical triggers webhook dispatch.
- D-29: New `src/soma/exporters/` package with `__init__.py`, `otel.py`, `webhook.py`.
- D-30: New top-level modules: `report.py`, `analytics.py`, `models.py`.
- D-31: Engine gets `add_exporter(exporter)` method.

### Claude's Discretion
- Exact OTel span attributes beyond the required set
- SQLite schema indexing strategy
- Report formatting details and quality score formula
- Webhook retry timing
- Test scenario design for all components
- Whether analytics queries use raw SQL or a thin wrapper

### Deferred Ideas (OUT OF SCOPE)
- Web dashboard (Phase 14)
- Grafana/Datadog pre-built dashboards
- Cross-machine analytics aggregation
- PressureVector extension with context_usage dimension
- Model-specific degradation curves (Phase 13)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OTL-01 | OpenTelemetry exporter -- structured traces/metrics to any OTel collector | OTel SDK v1.40.0 API patterns verified; TracerProvider + MeterProvider setup with OTLP gRPC exporter; existing `[otel]` extra in pyproject.toml; EventBus subscription pattern for action events |
| RPT-01 | Session reports -- automatic post-session summary (actions, quality, cost, patterns, interventions) | Engine state access patterns documented; Markdown generation is pure string formatting; shutdown() method pattern based on AuditLogger.append() graceful-fallback model |
| ALT-01 | Webhook alerting -- Slack, Discord, PagerDuty on WARN/BLOCK/policy violation | stdlib `urllib.request` for HTTP POST; `threading.Thread(daemon=True)` for fire-and-forget; EventBus already emits `level_changed` events with all needed data |
| HIST-01 | Historical analytics -- trends over time, per-agent degradation patterns | Python stdlib `sqlite3` for zero-dependency storage; single-table schema; CLI subparser pattern from existing `_cmd_status`, `_cmd_replay` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| opentelemetry-api | >=1.20 (current: 1.40.0) | OTel API abstractions | Industry standard observability API, already in pyproject.toml |
| opentelemetry-sdk | >=1.20 (current: 1.40.0) | OTel reference implementation | Required for TracerProvider, MeterProvider setup |
| opentelemetry-exporter-otlp-proto-grpc | >=1.20 | OTLP gRPC span/metric exporter | Default OTLP transport, works with Jaeger/Grafana/Datadog |
| sqlite3 | stdlib | Historical analytics storage | Zero-dependency, zero-config, built into Python |
| urllib.request | stdlib | Webhook HTTP POST | Zero-dependency, sufficient for simple fire-and-forget POST |
| threading | stdlib | Background webhook dispatch | Daemon threads for non-blocking I/O |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| opentelemetry-exporter-otlp-proto-http | >=1.20 | HTTP/protobuf alternative to gRPC | When gRPC is blocked by firewall; user configures protocol |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| urllib.request | requests/httpx | Would add required dependency; stdlib is sufficient for simple POST with timeout |
| SQLite | JSON files | SQLite gives indexed queries; JSON files would need full scan for trends |
| gRPC default | HTTP default | gRPC is standard OTLP default port 4317; HTTP is 4318; support both |

**Installation (optional extras update):**
```bash
pip install soma-ai[otel]  # existing extra, may need grpc exporter added
```

**pyproject.toml update needed:**
```toml
[project.optional-dependencies]
otel = [
    "opentelemetry-api>=1.20",
    "opentelemetry-sdk>=1.20",
    "opentelemetry-exporter-otlp-proto-grpc>=1.20",
]
```

## Architecture Patterns

### New Module Structure
```
src/soma/
├── exporters/           # NEW package
│   ├── __init__.py      # Exporter base protocol/ABC
│   ├── otel.py          # OTelExporter (TracerProvider + MeterProvider)
│   └── webhook.py       # WebhookExporter (urllib + threading)
├── report.py            # NEW: generate_session_report()
├── analytics.py         # NEW: AnalyticsStore (SQLite)
├── models.py            # NEW: MODEL_CONTEXT_WINDOWS dict
├── engine.py            # MODIFIED: add_exporter(), shutdown(), context_exhaustion signal
├── types.py             # MODIFIED: VitalsSnapshot gets context_burn_rate
├── pressure.py          # MODIFIED: DEFAULT_WEIGHTS gets context_exhaustion
├── wrap.py              # MODIFIED: extract model name from response
└── cli/main.py          # MODIFIED: add report + analytics subcommands
```

### Pattern 1: Exporter Interface via EventBus
**What:** Exporters subscribe to EventBus events; engine calls `add_exporter()` which auto-subscribes.
**When to use:** For any component that needs to observe engine events without modifying the core pipeline.
**Example:**
```python
# src/soma/exporters/__init__.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class Exporter(Protocol):
    """Protocol for SOMA exporters."""
    def on_action(self, data: dict) -> None: ...
    def on_mode_change(self, data: dict) -> None: ...
    def shutdown(self) -> None: ...

# In engine.py
def add_exporter(self, exporter: Exporter) -> None:
    self._exporters.append(exporter)
    self._events.on("action_recorded", exporter.on_action)
    self._events.on("level_changed", exporter.on_mode_change)
```

### Pattern 2: Graceful Optional Import (OTel)
**What:** Try-import OTel packages; provide no-op fallback if missing.
**When to use:** For the OTel exporter module -- must never crash if packages not installed.
**Example:**
```python
# src/soma/exporters/otel.py
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
```

### Pattern 3: Fire-and-Forget Webhook
**What:** Dispatch HTTP POST on a daemon thread with short timeout, retry once, then drop.
**When to use:** For webhook alerting -- never block the engine for external I/O.
**Example:**
```python
import threading
import json
import urllib.request

def _dispatch(url: str, payload: dict, timeout: float = 3.0) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    for attempt in range(2):  # try twice
        try:
            urllib.request.urlopen(req, timeout=timeout)
            return
        except Exception:
            if attempt == 0:
                continue
            return  # drop after second failure

def fire_webhook(url: str, payload: dict) -> None:
    t = threading.Thread(target=_dispatch, args=(url, payload), daemon=True)
    t.start()
```

### Pattern 4: Engine Shutdown Coordination
**What:** Engine.shutdown() flushes all exporters, generates reports, closes analytics DB.
**When to use:** On session end, or explicit `soma report` call.
**Example:**
```python
def shutdown(self) -> None:
    """Finalize session: generate reports, flush exporters, close stores."""
    for agent_id in self._agents:
        report = generate_session_report(self, agent_id)
        _save_report(report, agent_id)
    for exporter in self._exporters:
        exporter.shutdown()
```

### Pattern 5: Context Exhaustion as Pressure Signal
**What:** Context usage (0-1 ratio) maps to a pressure signal via sigmoid, added to signal_pressures dict.
**When to use:** Every `record_action()` call after computing context_usage.
**Example:**
```python
# In engine.py record_action(), after context_usage is computed:
context_exhaustion = sigmoid_clamp((context_usage - 0.5) / 0.15)
signal_pressures["context_exhaustion"] = context_exhaustion

# Proactive events (fire once per threshold crossing):
if context_usage >= 0.7 and not s._context_warning_fired:
    s._context_warning_fired = True
    self._events.emit("context_warning", {"agent_id": agent_id, "usage": context_usage})
if context_usage >= 0.9 and not s._context_critical_fired:
    s._context_critical_fired = True
    self._events.emit("context_critical", {"agent_id": agent_id, "usage": context_usage})
```

### Anti-Patterns to Avoid
- **Global OTel provider registration:** Do NOT call `trace.set_tracer_provider()` globally -- this would conflict if the user's application also sets up OTel. Create providers locally within the exporter, or use the global provider only if no provider is already set.
- **Synchronous webhook dispatch:** Never call `urllib.request.urlopen()` in the main engine thread. Always use daemon threads.
- **SQLite from multiple threads without WAL:** Enable WAL mode on analytics DB connection to avoid locking contention if hooks call from different threads.
- **Blocking on OTel flush in record_action():** BatchSpanProcessor handles batching internally; never flush synchronously per action.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trace/span management | Custom span tracking | OpenTelemetry TracerProvider + BatchSpanProcessor | Handles batching, sampling, context propagation, shutdown flushing |
| Metric aggregation for export | Custom metric collection | OpenTelemetry MeterProvider + PeriodicExportingMetricReader | Handles periodic export, aggregation temporality, OTLP encoding |
| OTLP wire protocol | Custom gRPC/protobuf serialization | opentelemetry-exporter-otlp-proto-grpc | OTLP protocol is complex; exporter handles it |
| SQLite connection management | Raw open/close | `sqlite3.connect()` with context manager | Handles cleanup; use `check_same_thread=False` with WAL for multi-thread |
| Thread-safe webhook queue | Custom thread pool | Single daemon thread per webhook call | Simple; `threading.Thread(daemon=True)` handles it. No need for queue/pool for infrequent alerts |

**Key insight:** OTel SDK does the heavy lifting for traces and metrics. SOMA's job is to emit the right data at the right time -- not to manage the export pipeline. The exporter module is thin glue between EventBus events and OTel API calls.

## Common Pitfalls

### Pitfall 1: OTel Global State Conflicts
**What goes wrong:** Calling `trace.set_tracer_provider()` stomps on user's existing OTel setup.
**Why it happens:** OTel Python uses global singletons by default.
**How to avoid:** Check if a provider is already set before registering. Or create a separate TracerProvider and pass it to spans explicitly without setting global. Best: use `trace.get_tracer_provider()` to detect existing setup; if it returns a real provider (not NoOp), attach our processor to it rather than replacing it.
**Warning signs:** User reports "my OTel traces disappeared after enabling SOMA."

### Pitfall 2: SQLite Thread Safety
**What goes wrong:** `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread` when analytics is called from hook threads.
**Why it happens:** Default SQLite connections are not thread-safe.
**How to avoid:** Use `sqlite3.connect(db_path, check_same_thread=False)` and enable WAL mode: `conn.execute("PRAGMA journal_mode=WAL")`.
**Warning signs:** Crashes in hook handlers when recording analytics.

### Pitfall 3: Webhook Timeout Blocking Engine
**What goes wrong:** Slow/unresponsive webhook endpoint blocks `record_action()` for seconds.
**Why it happens:** Forgetting to dispatch on a background thread.
**How to avoid:** Always use `threading.Thread(daemon=True)` for dispatch. The `daemon=True` ensures threads don't prevent process exit.
**Warning signs:** Engine latency spikes correlated with webhook endpoint downtime.

### Pitfall 4: OTel Import Crash When Not Installed
**What goes wrong:** `ImportError` crashes the entire SOMA import chain.
**Why it happens:** OTel is an optional dependency; importing at module level without try/except.
**How to avoid:** All OTel imports inside try/except in `exporters/otel.py`. The `HAS_OTEL` flag gates all functionality. The exporter's `__init__` logs a warning and becomes a no-op if `HAS_OTEL is False`.
**Warning signs:** `pip install soma-ai` (without `[otel]`) crashes on import.

### Pitfall 5: Report Generation on Empty Session
**What goes wrong:** Division by zero or empty report when no actions recorded.
**Why it happens:** `shutdown()` called before any `record_action()`.
**How to avoid:** Guard all report computations with `if s.action_count == 0: return "No actions recorded."`.
**Warning signs:** Empty/broken report files in `~/.soma/reports/`.

### Pitfall 6: Context Exhaustion Signal Dominating Pressure
**What goes wrong:** At 80%+ context usage, context_exhaustion signal (weight 1.5) pushes aggregate to WARN/BLOCK even when everything else is healthy.
**Why it happens:** sigmoid_clamp with the chosen parameters saturates quickly above 70%.
**How to avoid:** The weight of 1.5 is correct -- this is intentional. Context exhaustion IS a critical signal. But verify via tests that the pressure curve feels right: 50% usage ~ 0.0 pressure, 65% ~ 0.27, 75% ~ 0.73, 85% ~ 0.97.
**Warning signs:** Users getting false WARN alerts in long sessions. May need weight tuning.

## Code Examples

### OTel Exporter Setup (verified from official OTel Python docs)
```python
# Source: https://opentelemetry.io/docs/languages/python/exporters/
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

resource = Resource.create({SERVICE_NAME: "soma-agent"})

# Traces
tracer_provider = TracerProvider(resource=resource)
span_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
tracer = tracer_provider.get_tracer("soma")

# Metrics
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint="http://localhost:4317")
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
meter = meter_provider.get_meter("soma")

# Create instruments
pressure_gauge = meter.create_gauge("soma.pressure", unit="ratio", description="Aggregate pressure 0-1")
action_counter = meter.create_counter("soma.actions.total", unit="1", description="Total actions recorded")
```

### Creating Spans per Action
```python
def on_action(self, data: dict) -> None:
    """Called by EventBus on each action."""
    with self._tracer.start_as_current_span(f"soma.action.{data['tool_name']}") as span:
        span.set_attribute("soma.agent_id", data["agent_id"])
        span.set_attribute("soma.pressure", data["pressure"])
        span.set_attribute("soma.mode", data["mode"])
        span.set_attribute("soma.error", data.get("error", False))
        span.set_attribute("soma.token_count", data.get("token_count", 0))
    # Update metrics
    self._pressure_gauge.set(data["pressure"], {"agent_id": data["agent_id"]})
    self._action_counter.add(1, {"agent_id": data["agent_id"], "tool": data["tool_name"]})
```

### SQLite Analytics Store
```python
import sqlite3
from pathlib import Path

class AnalyticsStore:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            path = Path.home() / ".soma" / "analytics.db"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                timestamp REAL NOT NULL,
                agent_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                pressure REAL,
                uncertainty REAL,
                drift REAL,
                error_rate REAL,
                context_usage REAL,
                token_count INTEGER,
                cost REAL,
                mode TEXT,
                error INTEGER
            )
        """)
        # Indexes for common queries
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_agent_session "
            "ON actions(agent_id, session_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_timestamp "
            "ON actions(timestamp)"
        )
        self._conn.commit()
```

### Webhook Fire-and-Forget
```python
import json
import threading
import urllib.request

class WebhookExporter:
    def __init__(self, urls: list[str], events: list[str], timeout: float = 3.0):
        self._urls = urls
        self._events = set(events)
        self._timeout = timeout

    def on_mode_change(self, data: dict) -> None:
        new_mode = data.get("new_level")
        if hasattr(new_mode, "name"):
            mode_name = new_mode.name.lower()
        else:
            mode_name = str(new_mode).lower()
        if mode_name in self._events:
            payload = {
                "event_type": f"mode_change_{mode_name}",
                "agent_id": data.get("agent_id"),
                "pressure": data.get("pressure"),
                "mode": mode_name,
                "timestamp": data.get("timestamp"),
                "details": data,
            }
            self._dispatch_all(payload)

    def _dispatch_all(self, payload: dict) -> None:
        for url in self._urls:
            t = threading.Thread(target=self._send, args=(url, payload), daemon=True)
            t.start()

    def _send(self, url: str, payload: dict) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        for _ in range(2):
            try:
                urllib.request.urlopen(req, timeout=self._timeout)
                return
            except Exception:
                continue
```

### Context Exhaustion Pressure Curve
```python
# Pressure response at various context usage levels:
# sigmoid_clamp((usage - 0.5) / 0.15)
#   50% usage -> sigmoid_clamp(0.0)    = 0.0    (no pressure)
#   60% usage -> sigmoid_clamp(0.667)  = 0.09   (minimal)
#   70% usage -> sigmoid_clamp(1.333)  = 0.16   (noticeable)
#   80% usage -> sigmoid_clamp(2.0)    = 0.27   (moderate)
#   85% usage -> sigmoid_clamp(2.333)  = 0.34   (significant)
#   90% usage -> sigmoid_clamp(2.667)  = 0.42   (high)
#   95% usage -> sigmoid_clamp(3.0)    = 0.50   (critical)
#  100% usage -> sigmoid_clamp(3.333)  = 0.58   (severe)
```

### Model Context Windows
```python
# src/soma/models.py
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Anthropic
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    # OpenAI
    "gpt-4": 8_192,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    # Fallback
    "default": 200_000,
}

def get_context_window(model_name: str) -> int:
    """Return context window size for model, with fallback."""
    if model_name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_name]
    # Prefix matching for versioned model names
    for key in MODEL_CONTEXT_WINDOWS:
        if model_name.startswith(key):
            return MODEL_CONTEXT_WINDOWS[key]
    return MODEL_CONTEXT_WINDOWS["default"]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| print() debugging for agent monitoring | Structured OTel traces + metrics | OTel Python SDK stable since ~2023 | Industry standard; connects to any collector |
| Manual session review | Automated session reports | N/A (new for SOMA) | Reduces post-session analysis time |
| No alerting | Webhook-based alerting | N/A (new for SOMA) | Enables automated incident response |
| Flat file analytics | SQLite-backed queryable analytics | N/A (new for SOMA) | Enables trend analysis, historical comparison |

**Deprecated/outdated:**
- `opentelemetry-exporter-jaeger`: Deprecated in favor of OTLP exporter. Jaeger now natively supports OTLP. Do NOT use jaeger-specific exporters.

## Open Questions

1. **OTel Gauge API for Python**
   - What we know: OTel Python has `create_gauge()` for synchronous gauges (added in recent versions). Older versions only had `create_observable_gauge()` with callbacks.
   - What's unclear: Exact minimum version that supports synchronous `create_gauge()`.
   - Recommendation: Use `create_observable_gauge()` with callback pattern if gauge not available; this works on all versions >=1.20. Test at import time.

2. **Session ID for Analytics**
   - What we know: Analytics DB needs `session_id` column. Engine currently doesn't generate session IDs.
   - What's unclear: How to generate a stable session ID.
   - Recommendation: Generate UUID at engine creation time: `self._session_id = str(uuid.uuid4())[:8]`. Store on engine instance, pass to analytics on each action.

3. **OTel Exporter Package in pyproject.toml**
   - What we know: `opentelemetry-exporter-otlp-proto-grpc` is needed for OTLP gRPC export, but not currently in pyproject.toml.
   - What's unclear: Whether to add both gRPC and HTTP exporters or just gRPC.
   - Recommendation: Add only `opentelemetry-exporter-otlp-proto-grpc` to `[otel]` extra. HTTP exporter can be added later if users request it. Keep the dependency surface minimal.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-cov |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run python -m pytest tests/test_FILE.py -x` |
| Full suite command | `uv run python -m pytest tests/ --cov=soma --cov-report=term-missing` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OTL-01 | OTel exporter emits spans+metrics on action | unit (mock OTel) | `uv run python -m pytest tests/test_otel_exporter.py -x` | Wave 0 |
| OTL-01 | Graceful no-op when OTel not installed | unit | `uv run python -m pytest tests/test_otel_exporter.py::test_no_otel_installed -x` | Wave 0 |
| RPT-01 | Session report generates valid Markdown | unit | `uv run python -m pytest tests/test_report.py -x` | Wave 0 |
| RPT-01 | Report saved to correct path on shutdown | unit | `uv run python -m pytest tests/test_report.py::test_report_saved -x` | Wave 0 |
| ALT-01 | Webhook fires on WARN/BLOCK mode change | unit (mock HTTP) | `uv run python -m pytest tests/test_webhook.py -x` | Wave 0 |
| ALT-01 | Webhook does not block engine | unit | `uv run python -m pytest tests/test_webhook.py::test_nonblocking -x` | Wave 0 |
| HIST-01 | Analytics stores actions in SQLite | unit | `uv run python -m pytest tests/test_analytics.py -x` | Wave 0 |
| HIST-01 | get_agent_trends returns per-session aggregates | unit | `uv run python -m pytest tests/test_analytics.py::test_trends -x` | Wave 0 |
| N/A | Context exhaustion pressure signal | unit | `uv run python -m pytest tests/test_context_usage.py -x` | Extend existing |
| N/A | Model context window lookup | unit | `uv run python -m pytest tests/test_models.py -x` | Wave 0 |
| N/A | Engine add_exporter + shutdown | unit | `uv run python -m pytest tests/test_engine.py -x` | Extend existing |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_{changed_module}.py -x`
- **Per wave merge:** `uv run python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_otel_exporter.py` -- covers OTL-01 (spans, metrics, no-op fallback)
- [ ] `tests/test_report.py` -- covers RPT-01 (Markdown generation, file save, empty session)
- [ ] `tests/test_webhook.py` -- covers ALT-01 (dispatch, timeout, non-blocking, retry)
- [ ] `tests/test_analytics.py` -- covers HIST-01 (store, query, trends, empty data)
- [ ] `tests/test_models.py` -- covers model context window lookup

## Sources

### Primary (HIGH confidence)
- OpenTelemetry Python official docs: https://opentelemetry.io/docs/languages/python/ -- traced/metric setup patterns, OTLP exporter configuration
- OpenTelemetry Python exporters: https://opentelemetry.io/docs/languages/python/exporters/ -- gRPC and HTTP exporter import paths
- PyPI opentelemetry-sdk: https://pypi.org/project/opentelemetry-sdk/ -- current version 1.40.0
- Codebase: `src/soma/engine.py` -- existing EventBus integration, signal_pressures dict, context_usage computation
- Codebase: `src/soma/events.py` -- EventBus pub/sub API (on/off/emit)
- Codebase: `src/soma/pressure.py` -- DEFAULT_WEIGHTS, compute_aggregate_pressure
- Codebase: `src/soma/audit.py` -- AuditLogger pattern (never-crash, graceful fallback)
- Codebase: `pyproject.toml` -- existing `[otel]` optional extra declaration

### Secondary (MEDIUM confidence)
- Python stdlib sqlite3 docs -- WAL mode, check_same_thread parameter
- Python stdlib urllib.request -- timeout parameter behavior
- Python stdlib threading -- daemon thread lifecycle

### Tertiary (LOW confidence)
- OTel synchronous gauge availability in Python SDK -- may vary by version; verify at import time

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - OTel is already declared in pyproject.toml; all other deps are stdlib
- Architecture: HIGH - EventBus pattern is proven in codebase; exporter interface is straightforward
- Pitfalls: HIGH - OTel global state and SQLite threading are well-documented issues
- Code examples: MEDIUM - OTel gauge API may need adjustment based on exact version behavior

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable domain, OTel API is mature)
