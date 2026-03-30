"""Tests for soma/context.py — core session context."""

import os
from soma.context import detect_workflow_mode, get_session_context, SessionContext


class TestDetectWorkflowMode:
    def test_no_planning_dir(self, tmp_path):
        """Returns empty string when no .planning/ directory."""
        assert detect_workflow_mode(str(tmp_path)) == ""

    def test_no_state_file(self, tmp_path):
        """Returns empty string when .planning/ exists but no STATE.md."""
        (tmp_path / ".planning").mkdir()
        assert detect_workflow_mode(str(tmp_path)) == ""

    def test_executing_mode(self, tmp_path):
        """Detects 'execute' from STATE.md content."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text("Phase 3: Executing plan 1")
        assert detect_workflow_mode(str(tmp_path)) == "execute"

    def test_planning_mode(self, tmp_path):
        """Detects 'plan' from STATE.md content."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text("Phase 2: Planning phase 2")
        assert detect_workflow_mode(str(tmp_path)) == "plan"

    def test_discussing_mode(self, tmp_path):
        """Detects 'plan' from discussing content."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text("Discussing phase 1 approach")
        assert detect_workflow_mode(str(tmp_path)) == "plan"

    def test_unknown_content(self, tmp_path):
        """Returns empty for unrecognized STATE.md content."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text("Some random content")
        assert detect_workflow_mode(str(tmp_path)) == ""

    def test_fallback_to_getcwd(self, monkeypatch):
        """Falls back to os.getcwd() when cwd not provided."""
        monkeypatch.delenv("CLAUDE_WORKING_DIRECTORY", raising=False)
        # Should not crash
        result = detect_workflow_mode("")
        assert isinstance(result, str)


class TestGetSessionContext:
    def test_returns_session_context(self, tmp_path):
        ctx = get_session_context(cwd=str(tmp_path), action_count=42, pressure=0.15)
        assert isinstance(ctx, SessionContext)
        assert ctx.cwd == str(tmp_path)
        assert ctx.action_count == 42
        assert ctx.pressure == 0.15
        assert ctx.gsd_active is False
        assert ctx.workflow_mode == ""

    def test_gsd_active_detected(self, tmp_path):
        (tmp_path / ".planning").mkdir()
        ctx = get_session_context(cwd=str(tmp_path))
        assert ctx.gsd_active is True

    def test_frozen_dataclass(self, tmp_path):
        ctx = get_session_context(cwd=str(tmp_path))
        try:
            ctx.cwd = "/other"  # type: ignore
            assert False, "Should not allow mutation"
        except AttributeError:
            pass
