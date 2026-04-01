"""Tests for webhook exporter and config_loader exporter integration."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call

import pytest

from soma.exporters import Exporter


def _mock_mode(name: str) -> MagicMock:
    """Create a mock enum-like object with a .name attribute."""
    m = MagicMock()
    m.name = name
    return m


class TestWebhookExporterProtocol:
    def test_implements_exporter_protocol(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=[])
        assert isinstance(exporter, Exporter)


class TestWebhookOnModeChange:
    def _make_exporter(self, urls=None, events=None):
        from soma.exporters.webhook import WebhookExporter

        return WebhookExporter(urls=urls or ["http://hook.test/notify"], events=events)

    def test_fires_on_warn(self):
        exporter = self._make_exporter()
        with patch.object(exporter, "_dispatch_all") as mock_dispatch:
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "OBSERVE",
                "new_level": _mock_mode("WARN"),
                "pressure": 0.55,
            })
            # new_level.name.lower() should be "warn" which is in default events
            assert mock_dispatch.called

    def test_fires_on_block(self):
        exporter = self._make_exporter()
        with patch.object(exporter, "_dispatch_all") as mock_dispatch:
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "OBSERVE",
                "new_level": _mock_mode("BLOCK"),
                "pressure": 0.80,
            })
            assert mock_dispatch.called

    def test_ignores_observe(self):
        exporter = self._make_exporter()
        with patch.object(exporter, "_dispatch_all") as mock_dispatch:
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "GUIDE",
                "new_level": _mock_mode("OBSERVE"),
                "pressure": 0.1,
            })
            assert not mock_dispatch.called

    def test_ignores_guide(self):
        exporter = self._make_exporter()
        with patch.object(exporter, "_dispatch_all") as mock_dispatch:
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "OBSERVE",
                "new_level": _mock_mode("GUIDE"),
                "pressure": 0.3,
            })
            assert not mock_dispatch.called

    def test_payload_shape(self):
        exporter = self._make_exporter()
        captured = []

        def capture(payload):
            captured.append(payload)

        with patch.object(exporter, "_dispatch_all", side_effect=capture):
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "OBSERVE",
                "new_level": _mock_mode("WARN"),
                "pressure": 0.55,
            })

        assert len(captured) == 1
        payload = captured[0]
        assert "event_type" in payload
        assert "agent_id" in payload
        assert "pressure" in payload
        assert "mode" in payload
        assert "timestamp" in payload
        assert "details" in payload
        assert payload["agent_id"] == "a1"
        assert payload["pressure"] == 0.55
        assert payload["mode"] == "warn"

    def test_string_mode_handled(self):
        """When new_level is a plain string (not enum), still works."""
        exporter = self._make_exporter()
        with patch.object(exporter, "_dispatch_all") as mock_dispatch:
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "OBSERVE",
                "new_level": "warn",
                "pressure": 0.55,
            })
            assert mock_dispatch.called


class TestWebhookDispatch:
    def test_daemon_thread(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://hook.test/a"])
        with patch("soma.exporters.webhook.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            exporter._dispatch_all({"test": True})
            mock_thread_cls.assert_called_once()
            _, kwargs = mock_thread_cls.call_args
            assert kwargs.get("daemon") is True
            mock_thread.start.assert_called_once()

    def test_multiple_urls(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://a.test", "http://b.test"])
        with patch("soma.exporters.webhook.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            exporter._dispatch_all({"test": True})
            assert mock_thread_cls.call_count == 2

    def test_retry_on_failure(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://hook.test/a"], timeout=0.1)
        with patch("soma.exporters.webhook.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [Exception("fail"), MagicMock()]
            exporter._send("http://hook.test/a", {"test": True})
            assert mock_urlopen.call_count == 2

    def test_drop_after_two_failures(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://hook.test/a"], timeout=0.1)
        with patch("soma.exporters.webhook.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("always fail")
            exporter._send("http://hook.test/a", {"test": True})
            assert mock_urlopen.call_count == 2

    def test_nonblocking(self):
        """on_mode_change returns immediately even with slow mock."""
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://hook.test/a"])
        start = time.monotonic()
        with patch("soma.exporters.webhook.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = lambda *a, **kw: time.sleep(1)
            exporter.on_mode_change({
                "agent_id": "a1",
                "old_level": "OBSERVE",
                "new_level": _mock_mode("WARN"),
                "pressure": 0.55,
            })
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"on_mode_change took {elapsed:.2f}s — should be non-blocking"


class TestWebhookNoOps:
    def test_on_action_noop(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://hook.test/a"])
        with patch("soma.exporters.webhook.urllib.request.urlopen") as mock_urlopen:
            exporter.on_action({"tool_name": "Bash", "agent_id": "a"})
            mock_urlopen.assert_not_called()

    def test_shutdown_noop(self):
        from soma.exporters.webhook import WebhookExporter

        exporter = WebhookExporter(urls=["http://hook.test/a"])
        # Should not raise
        exporter.shutdown()


class TestCreateExportersFromConfig:
    def test_empty_config_returns_empty_list(self):
        from soma.cli.config_loader import create_exporters_from_config

        result = create_exporters_from_config({})
        assert result == []

    def test_otel_enabled(self):
        from soma.cli.config_loader import create_exporters_from_config

        config = {"otel": {"enabled": True, "endpoint": "http://x:4317"}}
        with patch("soma.exporters.otel.HAS_OTEL", True), \
             patch("soma.exporters.otel.TracerProvider"), \
             patch("soma.exporters.otel.MeterProvider"), \
             patch("soma.exporters.otel.BatchSpanProcessor"), \
             patch("soma.exporters.otel.PeriodicExportingMetricReader"), \
             patch("soma.exporters.otel.OTLPSpanExporter"), \
             patch("soma.exporters.otel.OTLPMetricExporter"), \
             patch("soma.exporters.otel.Resource"):
            result = create_exporters_from_config(config)

        assert len(result) == 1
        from soma.exporters.otel import OTelExporter
        assert isinstance(result[0], OTelExporter)

    def test_webhooks_enabled(self):
        from soma.cli.config_loader import create_exporters_from_config

        config = {"webhooks": {"enabled": True, "urls": ["http://hook.test/a"]}}
        result = create_exporters_from_config(config)
        assert len(result) == 1
        from soma.exporters.webhook import WebhookExporter
        assert isinstance(result[0], WebhookExporter)

    def test_webhooks_disabled(self):
        from soma.cli.config_loader import create_exporters_from_config

        config = {"webhooks": {"enabled": False, "urls": ["http://hook.test/a"]}}
        result = create_exporters_from_config(config)
        assert result == []

    def test_both_enabled(self):
        from soma.cli.config_loader import create_exporters_from_config

        config = {
            "otel": {"enabled": True},
            "webhooks": {"enabled": True, "urls": ["http://hook.test/a"]},
        }
        with patch("soma.exporters.otel.HAS_OTEL", True), \
             patch("soma.exporters.otel.TracerProvider"), \
             patch("soma.exporters.otel.MeterProvider"), \
             patch("soma.exporters.otel.BatchSpanProcessor"), \
             patch("soma.exporters.otel.PeriodicExportingMetricReader"), \
             patch("soma.exporters.otel.OTLPSpanExporter"), \
             patch("soma.exporters.otel.OTLPMetricExporter"), \
             patch("soma.exporters.otel.Resource"):
            result = create_exporters_from_config(config)
        assert len(result) == 2
