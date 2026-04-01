"""Integration tests for signal reflex hook wiring.

Tests commit gate in PreToolUse, signal injections in Notification,
_auto_checkpoint helper, and checkpoint counter in common.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ── Test _auto_checkpoint ──────────────────────────────────────────


class TestAutoCheckpoint:
    """Auto-checkpoint runs git stash push with proper safety checks."""

    @patch("subprocess.run")
    def test_auto_checkpoint_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from soma.hooks.common import _auto_checkpoint

        result = _auto_checkpoint(1)

        assert result is True
        # First call: git rev-parse --git-dir
        assert mock_run.call_args_list[0][0][0] == ["git", "rev-parse", "--git-dir"]
        # Second call: git stash push -m soma-checkpoint-1
        assert mock_run.call_args_list[1][0][0] == [
            "git", "stash", "push", "-m", "soma-checkpoint-1"
        ]

    @patch("subprocess.run")
    def test_auto_checkpoint_not_git_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128)
        from soma.hooks.common import _auto_checkpoint

        result = _auto_checkpoint(1)

        assert result is False
        # Only rev-parse called, stash never attempted
        assert mock_run.call_count == 1

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
    def test_auto_checkpoint_timeout(self, mock_run):
        from soma.hooks.common import _auto_checkpoint

        result = _auto_checkpoint(1)
        assert result is False


# ── Test checkpoint counter ────────────────────────────────────────


class TestCheckpointCounter:
    """Checkpoint counter persists to disk like block_count."""

    def test_checkpoint_count_starts_at_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.hooks.common.SOMA_DIR", tmp_path)
        from soma.hooks.common import get_checkpoint_count

        assert get_checkpoint_count() == 0

    def test_increment_checkpoint_count(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.hooks.common.SOMA_DIR", tmp_path)
        monkeypatch.setattr("soma.hooks.common.SESSIONS_DIR", tmp_path / "sessions")
        from soma.hooks.common import increment_checkpoint_count, get_checkpoint_count

        result = increment_checkpoint_count()
        assert result == 1
        assert get_checkpoint_count() == 1

        result = increment_checkpoint_count()
        assert result == 2
        assert get_checkpoint_count() == 2


# ── Test commit gate in PreToolUse ─────────────────────────────────


class TestCommitGatePreToolUse:
    """Commit gate blocks git commit on grade D/F via PreToolUse."""

    @patch("soma.hooks.pre_tool_use.read_stdin", return_value={
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'test'"},
    })
    @patch("soma.hooks.pre_tool_use.get_engine")
    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_reflex_config", return_value={})
    @patch("soma.hooks.common.read_bash_history", return_value=[])
    @patch("soma.hooks.common.read_action_log", return_value=[])
    @patch("soma.hooks.common.write_bash_history")
    @patch("soma.hooks.common.increment_block_count")
    @patch("soma.hooks.common.get_guidance_thresholds", return_value=None)
    def test_commit_gate_blocks_grade_d(
        self, mock_thresh, mock_inc, mock_write_hist,
        mock_log, mock_bash_hist, mock_reflex_cfg,
        mock_mode, mock_engine, mock_stdin,
    ):
        from soma.reflexes import ReflexResult

        engine = MagicMock()
        engine.get_snapshot.return_value = {"pressure": 0.3}
        mock_engine.return_value = (engine, "test-agent")

        # Pattern reflexes pass (allow=True)
        with patch("soma.reflexes.evaluate", return_value=ReflexResult(allow=True)):
            # Quality tracker returns grade D
            mock_qt = MagicMock()
            mock_qt.get_report.return_value = MagicMock(grade="D")
            with patch("soma.hooks.common.get_quality_tracker", return_value=mock_qt):
                with patch("soma.audit.AuditLogger.append"):
                    with pytest.raises(SystemExit) as exc_info:
                        from soma.hooks.pre_tool_use import main
                        main()
                    assert exc_info.value.code == 2

    @patch("soma.hooks.pre_tool_use.read_stdin", return_value={
        "tool_name": "Read",
        "tool_input": {"file_path": "x.py"},
    })
    @patch("soma.hooks.pre_tool_use.get_engine")
    @patch("soma.hooks.common.get_soma_mode", return_value="guide")
    @patch("soma.hooks.common.read_action_log", return_value=[])
    @patch("soma.hooks.common.get_guidance_thresholds", return_value=None)
    def test_commit_gate_skips_non_commit(
        self, mock_thresh, mock_log, mock_mode, mock_engine, mock_stdin,
    ):
        """Non-commit tools should not trigger commit gate."""
        engine = MagicMock()
        engine.get_snapshot.return_value = {"pressure": 0.1}
        mock_engine.return_value = (engine, "test-agent")

        mock_qt = MagicMock()
        mock_qt.get_report.return_value = MagicMock(grade="D")
        with patch("soma.hooks.common.get_quality_tracker", return_value=mock_qt):
            with patch("soma.guidance.evaluate") as mock_guidance:
                mock_guidance.return_value = MagicMock(allow=True, message="")
                from soma.hooks.pre_tool_use import main
                main()  # Should not raise SystemExit


# ── Test signal injections in Notification ─────────────────────────


class TestSignalInjectionNotification:
    """Signal reflex injections appear in notification output."""

    def _setup_notification_mocks(self, actions=5, pressure=0.3, soma_mode="reflex"):
        """Set up standard mocks for notification tests."""
        engine = MagicMock()
        engine.get_snapshot.return_value = {
            "level": MagicMock(name="GUIDE"),
            "pressure": pressure,
            "action_count": actions,
            "vitals": {"uncertainty": 0.1, "drift": 0.5, "error_rate": 0.4},
        }
        engine._graph._adj = {}
        return engine

    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Bash", "error": True, "file": "", "ts": 1},
        {"tool": "Bash", "error": True, "file": "", "ts": 2},
        {"tool": "Bash", "error": True, "file": "", "ts": 3},
    ])
    @patch("soma.hooks.common.get_engine")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    def test_signal_injections_appear_in_output(
        self, mock_config, mock_engine_fn, mock_log, mock_mode, capsys,
    ):
        engine = self._setup_notification_mocks()
        mock_engine_fn.return_value = (engine, "test-agent")

        from soma.reflexes import ReflexResult

        fake_results = [
            ReflexResult(
                allow=True,
                reflex_kind="rca_injection",
                inject_message="[SOMA DIAGNOSIS] Root cause: bash errors",
                detail="error_rate=0.40",
            ),
        ]

        with patch("soma.signal_reflexes.evaluate_all_signals", return_value=fake_results):
            with patch("soma.findings.collect", return_value=[]):
                with patch("soma.audit.AuditLogger.append"):
                    from soma.hooks.notification import main
                    main()

        captured = capsys.readouterr()
        assert "[SOMA DIAGNOSIS]" in captured.out

    @patch("soma.hooks.common.get_soma_mode", return_value="observe")
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Bash", "error": False, "file": "", "ts": 1},
        {"tool": "Bash", "error": False, "file": "", "ts": 2},
        {"tool": "Bash", "error": False, "file": "", "ts": 3},
    ])
    @patch("soma.hooks.common.get_engine")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    def test_observe_mode_skips_signal_reflexes(
        self, mock_config, mock_engine_fn, mock_log, mock_mode, capsys,
    ):
        engine = self._setup_notification_mocks(soma_mode="observe")
        mock_engine_fn.return_value = (engine, "test-agent")

        with patch("soma.signal_reflexes.evaluate_all_signals") as mock_eval:
            with patch("soma.findings.collect", return_value=[]):
                from soma.hooks.notification import main
                main()

        # Signal reflexes should NOT be called in observe mode
        mock_eval.assert_not_called()

    @patch("soma.hooks.common.get_soma_mode", return_value="guide")
    @patch("soma.hooks.common.read_action_log", return_value=[
        {"tool": "Bash", "error": False, "file": "", "ts": 1},
        {"tool": "Bash", "error": False, "file": "", "ts": 2},
        {"tool": "Bash", "error": False, "file": "", "ts": 3},
    ])
    @patch("soma.hooks.common.get_engine")
    @patch("soma.hooks.common.get_hook_config", return_value={"verbosity": "normal"})
    def test_max_two_injections_per_cycle(
        self, mock_config, mock_engine_fn, mock_log, mock_mode, capsys,
    ):
        """evaluate_all_signals already caps at 2 — verify wiring passes through."""
        engine = self._setup_notification_mocks(soma_mode="guide")
        mock_engine_fn.return_value = (engine, "test-agent")

        from soma.reflexes import ReflexResult

        # evaluate_all_signals returns max 2 (already capped)
        fake_results = [
            ReflexResult(
                allow=True,
                reflex_kind="rca_injection",
                inject_message="[SOMA] injection 1",
            ),
            ReflexResult(
                allow=True,
                reflex_kind="drift_guardian",
                inject_message="[SOMA] injection 2",
            ),
        ]

        with patch("soma.signal_reflexes.evaluate_all_signals", return_value=fake_results):
            with patch("soma.findings.collect", return_value=[]):
                with patch("soma.audit.AuditLogger.append"):
                    from soma.hooks.notification import main
                    main()

        captured = capsys.readouterr()
        assert "injection 1" in captured.out
        assert "injection 2" in captured.out
