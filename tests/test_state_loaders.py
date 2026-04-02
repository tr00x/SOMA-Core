"""Tests for soma.state — lazy state loaders for all subsystems."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def fake_soma(tmp_path, monkeypatch):
    """Redirect all state paths to temp directory."""
    fake = tmp_path / ".soma"
    fake.mkdir()
    sessions = fake / "sessions"
    sessions.mkdir()
    monkeypatch.setattr("soma.state.SOMA_DIR", fake)
    monkeypatch.setattr("soma.state.SESSIONS_DIR", sessions)
    monkeypatch.setattr("soma.state.FINGERPRINT_PATH", fake / "fingerprint.json")
    monkeypatch.setattr("soma.state.PREDICTOR_PATH", fake / "predictor.json")
    monkeypatch.setattr("soma.state.QUALITY_PATH", fake / "quality.json")
    monkeypatch.setattr("soma.state.TASK_TRACKER_PATH", fake / "task_tracker.json")
    return fake


# ------------------------------------------------------------------
# QualityTracker
# ------------------------------------------------------------------

class TestQualityTrackerLoader:
    def test_creates_new_when_no_file(self, fake_soma):
        from soma.state import get_quality_tracker
        from soma.quality import QualityTracker
        qt = get_quality_tracker()
        assert isinstance(qt, QualityTracker)

    def test_loads_from_file(self, fake_soma):
        from soma.state import get_quality_tracker, save_quality_tracker
        from soma.quality import QualityTracker
        qt = QualityTracker()
        qt.record_write(had_syntax_error=True, had_lint_issue=False)
        save_quality_tracker(qt)
        loaded = get_quality_tracker()
        assert isinstance(loaded, QualityTracker)
        report = loaded.get_report()
        assert report.total_writes == 1

    def test_session_scoped(self, fake_soma):
        from soma.state import get_quality_tracker, save_quality_tracker
        qt = get_quality_tracker(agent_id="cc-123")
        qt.record_write(had_syntax_error=False, had_lint_issue=True)
        save_quality_tracker(qt, agent_id="cc-123")
        loaded = get_quality_tracker(agent_id="cc-123")
        assert loaded.get_report().total_writes == 1

    def test_handles_corrupt_file(self, fake_soma):
        from soma.state import get_quality_tracker, QUALITY_PATH
        QUALITY_PATH.write_text("{bad json")
        qt = get_quality_tracker()
        assert qt is not None  # Returns fresh instance


# ------------------------------------------------------------------
# Predictor
# ------------------------------------------------------------------

class TestPredictorLoader:
    def test_creates_new_when_no_file(self, fake_soma):
        from soma.state import get_predictor
        p = get_predictor()
        assert p is not None
        assert hasattr(p, "update")
        assert hasattr(p, "predict")

    def test_roundtrip(self, fake_soma):
        from soma.state import get_predictor, save_predictor
        p = get_predictor()
        p.update(0.3, {"tool": "Bash", "error": True})
        save_predictor(p)
        loaded = get_predictor()
        assert len(loaded._pressures) >= 1

    def test_session_scoped(self, fake_soma):
        from soma.state import get_predictor, save_predictor
        p = get_predictor(agent_id="cc-456")
        p.update(0.5, {"tool": "Edit"})
        save_predictor(p, agent_id="cc-456")
        loaded = get_predictor(agent_id="cc-456")
        assert len(loaded._pressures) >= 1


# ------------------------------------------------------------------
# FingerprintEngine
# ------------------------------------------------------------------

class TestFingerprintLoader:
    def test_creates_new_when_no_file(self, fake_soma):
        from soma.state import get_fingerprint_engine
        from soma.fingerprint import FingerprintEngine
        fp = get_fingerprint_engine()
        assert isinstance(fp, FingerprintEngine)

    def test_roundtrip(self, fake_soma):
        from soma.state import get_fingerprint_engine, save_fingerprint_engine
        fp = get_fingerprint_engine()
        action_log = [
            {"tool": "Read", "error": False, "ts": 1.0},
            {"tool": "Bash", "error": True, "ts": 2.0},
            {"tool": "Edit", "error": False, "ts": 3.0},
            {"tool": "Read", "error": False, "ts": 4.0},
            {"tool": "Bash", "error": False, "ts": 5.0},
        ]
        fp.update_from_session("test-agent", action_log)
        save_fingerprint_engine(fp)
        loaded = get_fingerprint_engine()
        assert loaded.get("test-agent") is not None

    def test_handles_corrupt_file(self, fake_soma):
        from soma.state import get_fingerprint_engine, FINGERPRINT_PATH
        FINGERPRINT_PATH.write_text("not json!")
        fp = get_fingerprint_engine()
        assert fp is not None


# ------------------------------------------------------------------
# TaskTracker
# ------------------------------------------------------------------

class TestTaskTrackerLoader:
    def test_creates_new_when_no_file(self, fake_soma):
        from soma.state import get_task_tracker
        from soma.task_tracker import TaskTracker
        tt = get_task_tracker()
        assert isinstance(tt, TaskTracker)

    def test_roundtrip(self, fake_soma):
        from soma.state import get_task_tracker, save_task_tracker
        tt = get_task_tracker(cwd="/project")
        tt.record("Read", "/project/src/foo.py", False)
        save_task_tracker(tt)
        loaded = get_task_tracker()
        assert loaded is not None

    def test_cwd_applied(self, fake_soma):
        from soma.state import get_task_tracker
        tt = get_task_tracker(cwd="/my/project")
        assert tt.cwd == "/my/project"


# ------------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------------

class TestCleanup:
    def test_cleanup_removes_session_files(self, fake_soma):
        from soma.state import cleanup_session, save_quality_tracker, get_quality_tracker, SESSIONS_DIR
        qt = get_quality_tracker(agent_id="cleanup-test")
        save_quality_tracker(qt, agent_id="cleanup-test")
        session_dir = SESSIONS_DIR / "cleanup-test"
        assert session_dir.exists()

        cleanup_session("cleanup-test")
        assert not session_dir.exists()

    def test_cleanup_noop_for_missing(self, fake_soma):
        from soma.state import cleanup_session
        cleanup_session("nonexistent")  # Should not raise
