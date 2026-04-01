"""Integration tests for reflex hook behavior.

Tests PreToolUse mode gating, notification awareness prompt, and statusline
block count / mode display using mocked dependencies.
"""

from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch

import pytest


# ── Test Awareness Prompt ────────────────────────────────────────────


class TestAwarenessPrompt:
    """Notification hook injects awareness prompt on first action only."""

    @patch("soma.hooks.notification.get_engine")
    @patch("soma.hooks.notification.read_action_log", return_value=[])
    @patch("soma.hooks.notification.get_soma_mode", return_value="guide")
    def test_awareness_on_first_action(self, mock_mode, mock_log, mock_engine, capsys):
        engine = MagicMock()
        engine.get_snapshot.return_value = {
            "level": MagicMock(name="OBSERVE"),
            "pressure": 0.1,
            "action_count": 0,
            "vitals": {},
        }
        mock_engine.return_value = (engine, "test-agent")

        from soma.hooks.notification import main
        main()

        captured = capsys.readouterr()
        assert "[SOMA Active]" in captured.out

    @patch("soma.hooks.notification.get_engine")
    @patch("soma.hooks.notification.read_action_log", return_value=[
        {"tool": "Read", "error": False, "file": "x.py", "ts": 1}
    ])
    @patch("soma.hooks.notification.get_soma_mode", return_value="guide")
    def test_no_awareness_after_first(self, mock_mode, mock_log, mock_engine, capsys):
        engine = MagicMock()
        engine.get_snapshot.return_value = {
            "level": MagicMock(name="OBSERVE"),
            "pressure": 0.1,
            "action_count": 1,
            "vitals": {},
        }
        mock_engine.return_value = (engine, "test-agent")

        from soma.hooks.notification import main
        main()

        captured = capsys.readouterr()
        assert "[SOMA Active]" not in captured.out


# ── Test PreToolUse Reflex ───────────────────────────────────────────


class TestPreToolUseReflex:
    """PreToolUse has 3-mode gating: observe, guide, reflex."""

    @patch("soma.hooks.pre_tool_use.read_stdin", return_value={"tool_name": "Bash", "tool_input": {"command": "ls"}})
    @patch("soma.hooks.pre_tool_use.get_engine")
    @patch("soma.hooks.common.get_soma_mode", return_value="observe")
    def test_observe_mode_returns_early(self, mock_mode, mock_engine, mock_stdin):
        engine = MagicMock()
        engine.get_snapshot.return_value = {"pressure": 0.1}
        mock_engine.return_value = (engine, "test-agent")

        from soma.hooks.pre_tool_use import main
        # Should not raise SystemExit
        main()

    @patch("soma.hooks.pre_tool_use.read_stdin", return_value={"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    @patch("soma.hooks.pre_tool_use.get_engine")
    @patch("soma.hooks.common.get_soma_mode", return_value="reflex")
    @patch("soma.hooks.common.get_reflex_config", return_value={})
    @patch("soma.hooks.common.read_bash_history", return_value=[])
    @patch("soma.hooks.common.read_action_log", return_value=[])
    @patch("soma.hooks.common.write_bash_history")
    @patch("soma.hooks.common.increment_block_count")
    @patch("soma.hooks.common.get_guidance_thresholds", return_value=None)
    def test_reflex_mode_blocks(self, mock_thresh, mock_inc, mock_write_hist,
                                mock_log, mock_bash_hist, mock_reflex_cfg,
                                mock_mode, mock_engine, mock_stdin):
        from soma.reflexes import ReflexResult

        engine = MagicMock()
        engine.get_snapshot.return_value = {"pressure": 0.5}
        mock_engine.return_value = (engine, "test-agent")

        with patch("soma.reflexes.evaluate", return_value=ReflexResult(
            allow=False,
            reflex_kind="bash_failures",
            block_message="[SOMA BLOCKED] test block",
        )):
            with pytest.raises(SystemExit) as exc_info:
                from soma.hooks.pre_tool_use import main
                main()
            assert exc_info.value.code == 2

    @patch("soma.hooks.pre_tool_use.read_stdin", return_value={"tool_name": "Read", "tool_input": {"file_path": "x.py"}})
    @patch("soma.hooks.pre_tool_use.get_engine")
    @patch("soma.hooks.common.get_soma_mode", return_value="guide")
    @patch("soma.hooks.common.read_action_log", return_value=[])
    @patch("soma.hooks.common.get_guidance_thresholds", return_value=None)
    def test_guide_mode_no_reflexes(self, mock_thresh, mock_log, mock_mode,
                                    mock_engine, mock_stdin):
        engine = MagicMock()
        engine.get_snapshot.return_value = {"pressure": 0.1}
        mock_engine.return_value = (engine, "test-agent")

        with patch("soma.reflexes.evaluate") as mock_reflex_eval:
            with patch("soma.guidance.evaluate") as mock_guidance:
                mock_guidance.return_value = MagicMock(allow=True, message="")
                from soma.hooks.pre_tool_use import main
                main()
            # In guide mode, reflexes.evaluate should NOT be called
            mock_reflex_eval.assert_not_called()


# ── Test Statusline Blocks ───────────────────────────────────────────


class TestStatuslineBlocks:
    """Statusline shows block count and non-default mode."""

    @patch("soma.hooks.statusline.get_engine")
    def test_block_count_shown(self, mock_engine, capsys):
        engine = MagicMock()
        engine.get_snapshot.return_value = {
            "level": MagicMock(name="GUIDE"),
            "pressure": 0.2,
            "action_count": 10,
            "vitals": {},
        }
        mock_engine.return_value = (engine, "test-agent")

        with patch("soma.hooks.statusline.get_block_count", return_value=3):
            with patch("soma.hooks.statusline.get_soma_mode", return_value="guide"):
                from soma.hooks.statusline import main
                main()

        captured = capsys.readouterr()
        assert "3 blocked" in captured.out

    @patch("soma.hooks.statusline.get_engine")
    def test_mode_shown_when_reflex(self, mock_engine, capsys):
        engine = MagicMock()
        engine.get_snapshot.return_value = {
            "level": MagicMock(name="GUIDE"),
            "pressure": 0.2,
            "action_count": 10,
            "vitals": {},
        }
        mock_engine.return_value = (engine, "test-agent")

        with patch("soma.hooks.statusline.get_block_count", return_value=0):
            with patch("soma.hooks.statusline.get_soma_mode", return_value="reflex"):
                from soma.hooks.statusline import main
                main()

        captured = capsys.readouterr()
        assert "REFLEX" in captured.out
