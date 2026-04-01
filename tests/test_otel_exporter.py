"""Tests for OpenTelemetry exporter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soma.exporters import Exporter


class TestOTelExporterProtocol:
    """OTelExporter satisfies the Exporter protocol."""

    def test_implements_exporter_protocol(self):
        """OTelExporter is an instance of Exporter protocol."""
        from soma.exporters.otel import OTelExporter

        # Mock OTel so it thinks packages are installed
        with patch("soma.exporters.otel.HAS_OTEL", False):
            exporter = OTelExporter()
        assert isinstance(exporter, Exporter)


class TestOTelExporterEnabled:
    """Tests with OTel mocked as available."""

    def _make_exporter(self):
        """Create an OTelExporter with all OTel internals mocked."""
        from soma.exporters.otel import OTelExporter

        mock_tracer_provider = MagicMock()
        mock_meter_provider = MagicMock()
        mock_tracer = MagicMock()
        mock_meter = MagicMock()

        mock_tracer_provider.get_tracer.return_value = mock_tracer
        mock_meter_provider.get_meter.return_value = mock_meter

        # Mock gauge/counter creation — each call returns a distinct mock
        gauges = {}

        def _create_gauge(name, **kwargs):
            g = MagicMock(name=f"gauge_{name}")
            gauges[name] = g
            return g

        counters = {}

        def _create_counter(name, **kwargs):
            c = MagicMock(name=f"counter_{name}")
            counters[name] = c
            return c

        mock_meter.create_gauge.side_effect = _create_gauge
        mock_meter.create_counter.side_effect = _create_counter

        with (
            patch("soma.exporters.otel.HAS_OTEL", True),
            patch("soma.exporters.otel.TracerProvider", return_value=mock_tracer_provider),
            patch("soma.exporters.otel.MeterProvider", return_value=mock_meter_provider),
            patch("soma.exporters.otel.BatchSpanProcessor"),
            patch("soma.exporters.otel.PeriodicExportingMetricReader"),
            patch("soma.exporters.otel.OTLPSpanExporter"),
            patch("soma.exporters.otel.OTLPMetricExporter"),
            patch("soma.exporters.otel.Resource"),
        ):
            exporter = OTelExporter(
                endpoint="http://localhost:4317",
                service_name="soma-test",
            )

        return exporter, mock_tracer, mock_meter, gauges, counters

    def test_creates_tracer_and_meter_providers(self):
        exporter, tracer, meter, _, _ = self._make_exporter()
        assert exporter._enabled is True
        assert exporter._tracer is tracer
        assert exporter._meter is meter

    def test_on_action_creates_span(self):
        exporter, tracer, _, _, _ = self._make_exporter()
        mock_span = MagicMock()
        tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        data = {
            "agent_id": "test-agent",
            "tool_name": "Bash",
            "pressure": 0.42,
            "mode": "WARN",
            "error": False,
            "token_count": 150,
            "vitals": {
                "uncertainty": 0.3,
                "drift": 0.1,
                "error_rate": 0.05,
                "context_usage": 0.2,
            },
        }
        exporter.on_action(data)

        tracer.start_as_current_span.assert_called_once_with("soma.action.Bash")
        mock_span.set_attribute.assert_any_call("soma.agent_id", "test-agent")
        mock_span.set_attribute.assert_any_call("soma.pressure", 0.42)
        mock_span.set_attribute.assert_any_call("soma.mode", "WARN")
        mock_span.set_attribute.assert_any_call("soma.error", False)
        mock_span.set_attribute.assert_any_call("soma.token_count", 150)

    def test_on_action_updates_gauge_metrics(self):
        exporter, tracer, _, _, _ = self._make_exporter()
        mock_span = MagicMock()
        tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        data = {
            "agent_id": "test-agent",
            "tool_name": "Read",
            "pressure": 0.55,
            "mode": "GUIDE",
            "error": False,
            "token_count": 100,
            "vitals": {
                "uncertainty": 0.3,
                "drift": 0.1,
                "error_rate": 0.05,
                "context_usage": 0.2,
            },
        }
        exporter.on_action(data)

        # Check that pressure gauge was set
        exporter._pressure_gauge.set.assert_called_with(0.55)
        exporter._uncertainty_gauge.set.assert_called_with(0.3)
        exporter._drift_gauge.set.assert_called_with(0.1)
        exporter._error_rate_gauge.set.assert_called_with(0.05)
        exporter._context_usage_gauge.set.assert_called_with(0.2)

    def test_on_action_increments_action_counter(self):
        exporter, tracer, _, _, _ = self._make_exporter()
        mock_span = MagicMock()
        tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        data = {
            "agent_id": "a",
            "tool_name": "X",
            "pressure": 0.1,
            "mode": "OBSERVE",
            "error": False,
            "token_count": 0,
            "vitals": {"uncertainty": 0, "drift": 0, "error_rate": 0, "context_usage": 0},
        }
        exporter.on_action(data)
        exporter._action_counter.add.assert_called_with(1)

    def test_on_action_error_increments_error_counter(self):
        exporter, tracer, _, _, _ = self._make_exporter()
        mock_span = MagicMock()
        tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        data = {
            "agent_id": "a",
            "tool_name": "X",
            "pressure": 0.1,
            "mode": "OBSERVE",
            "error": True,
            "token_count": 0,
            "vitals": {"uncertainty": 0, "drift": 0, "error_rate": 0, "context_usage": 0},
        }
        exporter.on_action(data)
        exporter._error_counter.add.assert_called_with(1)

    def test_on_mode_change_creates_span(self):
        exporter, tracer, _, _, _ = self._make_exporter()
        mock_span = MagicMock()
        tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        data = {
            "agent_id": "test-agent",
            "old_level": "OBSERVE",
            "new_level": "WARN",
            "pressure": 0.55,
        }
        exporter.on_mode_change(data)

        tracer.start_as_current_span.assert_called_once_with("soma.mode_change")
        mock_span.set_attribute.assert_any_call("soma.agent_id", "test-agent")
        mock_span.set_attribute.assert_any_call("soma.old_level", "OBSERVE")
        mock_span.set_attribute.assert_any_call("soma.new_level", "WARN")
        mock_span.set_attribute.assert_any_call("soma.pressure", 0.55)

    def test_shutdown_calls_providers(self):
        exporter, _, _, _, _ = self._make_exporter()
        exporter.shutdown()
        exporter._tracer_provider.shutdown.assert_called_once()
        exporter._meter_provider.shutdown.assert_called_once()


class TestOTelExporterDisabled:
    """Tests when OTel packages are NOT installed."""

    def test_init_does_not_crash(self):
        from soma.exporters.otel import OTelExporter

        with patch("soma.exporters.otel.HAS_OTEL", False):
            exporter = OTelExporter()
        assert exporter._enabled is False

    def test_on_action_is_noop(self):
        from soma.exporters.otel import OTelExporter

        with patch("soma.exporters.otel.HAS_OTEL", False):
            exporter = OTelExporter()
        # Should not raise
        exporter.on_action({"tool_name": "X", "agent_id": "a", "pressure": 0, "mode": "OBSERVE"})

    def test_on_mode_change_is_noop(self):
        from soma.exporters.otel import OTelExporter

        with patch("soma.exporters.otel.HAS_OTEL", False):
            exporter = OTelExporter()
        exporter.on_mode_change({"agent_id": "a", "old_level": "OBSERVE", "new_level": "WARN", "pressure": 0.5})

    def test_shutdown_is_noop(self):
        from soma.exporters.otel import OTelExporter

        with patch("soma.exporters.otel.HAS_OTEL", False):
            exporter = OTelExporter()
        exporter.shutdown()
