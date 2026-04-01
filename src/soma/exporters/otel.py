"""OpenTelemetry exporter — spans + metrics to any OTel collector."""

from __future__ import annotations

from typing import Any

try:
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

    # Stubs so the class body can reference names without NameError.
    TracerProvider = None  # type: ignore[assignment,misc]
    MeterProvider = None  # type: ignore[assignment,misc]
    BatchSpanProcessor = None  # type: ignore[assignment,misc]
    PeriodicExportingMetricReader = None  # type: ignore[assignment,misc]
    Resource = None  # type: ignore[assignment,misc]
    SERVICE_NAME = "service.name"  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment,misc]
    OTLPMetricExporter = None  # type: ignore[assignment,misc]


__all__ = ["OTelExporter"]


class OTelExporter:
    """Export SOMA telemetry as OpenTelemetry spans and metrics.

    When the ``opentelemetry-sdk`` packages are not installed the exporter
    becomes a complete no-op — no imports fail, no methods crash.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        service_name: str = "soma-agent",
    ) -> None:
        if not HAS_OTEL:
            self._enabled = False
            return

        resource = Resource.create({SERVICE_NAME: service_name})

        # Tracer setup — local provider, NOT global.
        self._tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=endpoint)
        self._tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        self._tracer = self._tracer_provider.get_tracer("soma")

        # Meter setup
        metric_exporter = OTLPMetricExporter(endpoint=endpoint)
        reader = PeriodicExportingMetricReader(metric_exporter)
        self._meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        self._meter = self._meter_provider.get_meter("soma")

        # Instruments
        self._pressure_gauge = self._meter.create_gauge(
            "soma.pressure", unit="ratio", description="Aggregate pressure 0-1"
        )
        self._uncertainty_gauge = self._meter.create_gauge(
            "soma.vitals.uncertainty", unit="ratio", description="Uncertainty signal"
        )
        self._drift_gauge = self._meter.create_gauge(
            "soma.vitals.drift", unit="ratio", description="Drift signal"
        )
        self._error_rate_gauge = self._meter.create_gauge(
            "soma.vitals.error_rate", unit="ratio", description="Error rate signal"
        )
        self._context_usage_gauge = self._meter.create_gauge(
            "soma.vitals.context_usage", unit="ratio", description="Context window usage"
        )
        self._action_counter = self._meter.create_counter(
            "soma.actions.total", unit="1", description="Total actions recorded"
        )
        self._error_counter = self._meter.create_counter(
            "soma.actions.errors", unit="1", description="Total errored actions"
        )

        self._enabled = True

    # ------------------------------------------------------------------
    # Exporter protocol
    # ------------------------------------------------------------------

    def on_action(self, data: dict[str, Any]) -> None:
        """Create a span and update metrics for each recorded action."""
        if not self._enabled:
            return

        tool_name = data.get("tool_name", "unknown")
        with self._tracer.start_as_current_span(f"soma.action.{tool_name}") as span:
            span.set_attribute("soma.agent_id", data.get("agent_id", ""))
            span.set_attribute("soma.pressure", data.get("pressure", 0.0))
            span.set_attribute("soma.mode", data.get("mode", "OBSERVE"))
            span.set_attribute("soma.error", data.get("error", False))
            span.set_attribute("soma.token_count", data.get("token_count", 0))

        # Metrics
        self._pressure_gauge.set(data.get("pressure", 0.0))
        vitals = data.get("vitals", {})
        self._uncertainty_gauge.set(vitals.get("uncertainty", 0.0))
        self._drift_gauge.set(vitals.get("drift", 0.0))
        self._error_rate_gauge.set(vitals.get("error_rate", 0.0))
        self._context_usage_gauge.set(vitals.get("context_usage", 0.0))

        self._action_counter.add(1)
        if data.get("error"):
            self._error_counter.add(1)

    def on_mode_change(self, data: dict[str, Any]) -> None:
        """Create a span for response mode transitions."""
        if not self._enabled:
            return

        with self._tracer.start_as_current_span("soma.mode_change") as span:
            span.set_attribute("soma.agent_id", data.get("agent_id", ""))
            span.set_attribute("soma.old_level", str(data.get("old_level", "")))
            span.set_attribute("soma.new_level", str(data.get("new_level", "")))
            span.set_attribute("soma.pressure", data.get("pressure", 0.0))

    def shutdown(self) -> None:
        """Flush and shut down OTel providers."""
        if not self._enabled:
            return
        self._tracer_provider.shutdown()
        self._meter_provider.shutdown()
