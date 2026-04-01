"""Integration tests for advanced reflex hook wiring (Phase 16).

Tests circuit breaker persistence, all 5 advanced reflexes in notification,
audit logging, and try/except isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from soma.graph_reflexes import CircuitBreakerState


# ── Circuit breaker state persistence ──────────────────────────────


class TestCircuitBreakerStatePersistence:
    """Circuit breaker state round-trips through save/load."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """State persists across save/load cycle."""
        from soma.hooks.common import get_circuit_breaker_state, save_circuit_breaker_state

        state = CircuitBreakerState(
            agent_id="test-agent",
            consecutive_block=3,
            consecutive_observe=0,
            is_open=True,
        )

        with patch("soma.hooks.common.SOMA_DIR", tmp_path):
            save_circuit_breaker_state(state, "test-agent")

            # Verify file exists
            path = tmp_path / "circuit_test-agent.json"
            assert path.exists()

            loaded = get_circuit_breaker_state("test-agent")
            assert loaded.agent_id == "test-agent"
            assert loaded.consecutive_block == 3
            assert loaded.is_open is True

    def test_load_missing_returns_default(self, tmp_path):
        """Missing file returns fresh state."""
        from soma.hooks.common import get_circuit_breaker_state

        with patch("soma.hooks.common.SOMA_DIR", tmp_path):
            state = get_circuit_breaker_state("nonexistent")
            assert state.consecutive_block == 0
            assert state.is_open is False


# ── Notification hook wiring ───────────────────────────────────────


def _make_mock_engine(agent_id="cc-test", pressure=0.3, mode_name="WARN",
                      action_count=5, vitals=None):
    """Build a mock engine + snapshot for notification tests."""
    from soma.types import ResponseMode

    mode = getattr(ResponseMode, mode_name)
    default_vitals = {
        "uncertainty": 0.1, "drift": 0.1, "error_rate": 0.1,
        "context_usage": 0.0,
    }
    if vitals:
        default_vitals.update(vitals)

    snap = {
        "level": mode,
        "mode": mode,
        "pressure": pressure,
        "action_count": action_count,
        "vitals": default_vitals,
    }

    engine = MagicMock()
    engine.get_snapshot.return_value = snap
    engine._graph = MagicMock()
    engine._graph._adj = {}

    return engine, agent_id, snap


class TestCircuitBreakerInNotification:
    """Circuit breaker quarantine message appears in output."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Bash", "error": False}, {"tool": "Bash", "error": False},
        {"tool": "Bash", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_quarantine_message_in_output(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode, tmp_path, capsys):
        """When circuit breaker is open, quarantine message appears."""
        engine, agent_id, _ = _make_mock_engine(
            pressure=0.8, mode_name="BLOCK", action_count=10,
        )
        mock_get_engine.return_value = (engine, agent_id)

        # Pre-seed an open circuit breaker state
        state = CircuitBreakerState(
            agent_id=agent_id, consecutive_block=6, is_open=True,
        )
        with patch("soma.hooks.common.SOMA_DIR", tmp_path):
            from soma.hooks.common import save_circuit_breaker_state
            save_circuit_breaker_state(state, agent_id)

        # Patch SOMA_DIR for both load and save during main()
        with patch("soma.hooks.common.SOMA_DIR", tmp_path):
            with patch("soma.audit.AuditLogger", MagicMock()):
                with patch("soma.findings.collect", return_value=[]):
                    from soma.hooks.notification import main
                    main()

        captured = capsys.readouterr()
        assert "quarantined" in captured.out


class TestSmartThrottleInNotification:
    """Smart throttle injection appears based on response mode."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Read", "error": False}, {"tool": "Read", "error": False},
        {"tool": "Read", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_throttle_at_warn(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode, capsys):
        """Smart throttle injects at WARN pressure."""
        engine, agent_id, _ = _make_mock_engine(
            pressure=0.6, mode_name="WARN", action_count=5,
        )
        mock_get_engine.return_value = (engine, agent_id)

        with patch("soma.audit.AuditLogger", MagicMock()):
            with patch("soma.findings.collect", return_value=[]):
                # Disable circuit breaker to isolate smart throttle
                with patch("soma.hooks.common.get_circuit_breaker_state",
                           return_value=CircuitBreakerState(agent_id=agent_id)):
                    from soma.hooks.notification import main
                    main()

        captured = capsys.readouterr()
        assert "500 tokens" in captured.out or "Pressure elevated" in captured.out


class TestContextOverflowInNotification:
    """Context overflow injection at 85% context."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Read", "error": False}, {"tool": "Read", "error": False},
        {"tool": "Read", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_overflow_at_85_pct(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode, capsys):
        """Context overflow fires at 85% usage."""
        engine, agent_id, _ = _make_mock_engine(
            pressure=0.2, mode_name="OBSERVE", action_count=5,
            vitals={"context_usage": 0.85},
        )
        mock_get_engine.return_value = (engine, agent_id)

        with patch("soma.audit.AuditLogger", MagicMock()):
            with patch("soma.findings.collect", return_value=[]):
                with patch("soma.hooks.common.get_circuit_breaker_state",
                           return_value=CircuitBreakerState(agent_id=agent_id)):
                    from soma.hooks.notification import main
                    main()

        captured = capsys.readouterr()
        assert "85%" in captured.out or "Context" in captured.out


class TestSessionMemoryInNotification:
    """Session memory injection appears on action 5 with matching history."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Read", "error": False}, {"tool": "Edit", "error": False},
        {"tool": "Read", "error": False}, {"tool": "Edit", "error": False},
        {"tool": "Read", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_memory_injection_action_5(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode, capsys):
        """Session memory injects on action 5 with similar past session."""
        from soma.session_store import SessionRecord

        engine, agent_id, _ = _make_mock_engine(
            pressure=0.1, mode_name="OBSERVE", action_count=5,
        )
        mock_get_engine.return_value = (engine, agent_id)

        past_session = SessionRecord(
            session_id="past-1", agent_id="cc-old", started=0, ended=100,
            action_count=20, final_pressure=0.1, max_pressure=0.3,
            avg_pressure=0.15, error_count=0, retry_count=0, total_tokens=1000,
            mode_transitions=[], pressure_trajectory=[],
            tool_distribution={"Read": 10, "Edit": 8, "Bash": 2},
            phase_sequence=[], fingerprint_divergence=0.05,
        )

        with patch("soma.audit.AuditLogger", MagicMock()):
            with patch("soma.findings.collect", return_value=[]):
                with patch("soma.hooks.common.get_circuit_breaker_state",
                           return_value=CircuitBreakerState(agent_id=agent_id)):
                    with patch("soma.session_store.load_sessions", return_value=[past_session]):
                        from soma.hooks.notification import main
                        main()

        captured = capsys.readouterr()
        assert "Similar past session" in captured.out


class TestAdvancedReflexIsolation:
    """All advanced reflexes silently swallowed on import error."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Read", "error": False}, {"tool": "Read", "error": False},
        {"tool": "Read", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_no_crash_on_import_error(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode, capsys):
        """Notification still works if advanced reflex modules fail to import."""
        engine, agent_id, _ = _make_mock_engine(
            pressure=0.3, mode_name="GUIDE", action_count=5,
        )
        mock_get_engine.return_value = (engine, agent_id)

        # Break all advanced reflex imports
        import builtins
        original_import = builtins.__import__

        def broken_import(name, *args, **kwargs):
            if name in ("soma.graph_reflexes", "soma.advanced_signal_reflexes",
                        "soma.session_memory"):
                raise ImportError(f"Broken: {name}")
            return original_import(name, *args, **kwargs)

        with patch("soma.findings.collect", return_value=[]):
            with patch("builtins.__import__", side_effect=broken_import):
                from soma.hooks.notification import main
                # Should not raise
                main()

        # No crash = pass


class TestAnomalyAuditEntry:
    """Anomaly audit entry has type='anomaly'."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Bash", "error": False}, {"tool": "Bash", "error": False},
        {"tool": "Bash", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_anomaly_logged_as_type_anomaly(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode):
        """Fingerprint anomaly uses type='anomaly' in audit."""
        engine, agent_id, _ = _make_mock_engine(
            pressure=0.4, mode_name="GUIDE", action_count=5,
        )
        mock_get_engine.return_value = (engine, agent_id)

        mock_audit = MagicMock()
        mock_audit_instance = MagicMock()
        mock_audit.return_value = mock_audit_instance

        # Mock fingerprint engine to return high divergence
        mock_fp = MagicMock()
        mock_fp.check_divergence.return_value = (0.8, "tool distribution shifted")

        with patch("soma.findings.collect", return_value=[]):
            with patch("soma.hooks.common.get_circuit_breaker_state",
                       return_value=CircuitBreakerState(agent_id=agent_id)):
                with patch("soma.hooks.common.get_fingerprint_engine", return_value=mock_fp):
                    with patch("soma.audit.AuditLogger", mock_audit):
                        from soma.hooks.notification import main
                        main()

        # Find the anomaly audit call
        found_anomaly = False
        for call in mock_audit_instance.append.call_args_list:
            kwargs = call.kwargs if call.kwargs else {}
            if kwargs.get("type") == "anomaly":
                found_anomaly = True
                assert kwargs.get("reflex_kind") == "fingerprint_anomaly"
                break

        assert found_anomaly, "Expected audit entry with type='anomaly'"


class TestFingerprintEngineUnavailable:
    """No crash when fingerprint engine is unavailable."""

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Read", "error": False}, {"tool": "Read", "error": False},
        {"tool": "Read", "error": False},
    ])
    @patch("soma.hooks.common.get_engine")
    def test_no_crash_fingerprint_unavailable(self, mock_get_engine, mock_read, mock_hook_cfg, mock_mode, capsys):
        """Notification works if fingerprint engine raises."""
        engine, agent_id, _ = _make_mock_engine(
            pressure=0.2, mode_name="OBSERVE", action_count=5,
        )
        mock_get_engine.return_value = (engine, agent_id)

        with patch("soma.findings.collect", return_value=[]):
            with patch("soma.hooks.common.get_circuit_breaker_state",
                       return_value=CircuitBreakerState(agent_id=agent_id)):
                with patch("soma.hooks.common.get_fingerprint_engine",
                           side_effect=Exception("fp engine broken")):
                    from soma.hooks.notification import main
                    main()

        # No crash = pass
