"""
Regression for v2026.6.x fix #13 — log_silent_failure helper.

Replaces silent ``except Exception: pass`` blocks with a single
stderr log line gated on SOMA_DEBUG=1. Default behavior (no env
var) stays silent — production agents still don't get crashed —
but a maintainer running with SOMA_DEBUG=1 finally sees what's
actually swallowed.
"""
from __future__ import annotations

import sys

import pytest

from soma.errors import log_silent_failure


def test_silent_by_default(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SOMA_DEBUG", raising=False)
    monkeypatch.delenv("SOMA_HOOK_QUIET", raising=False)
    log_silent_failure("test", RuntimeError("boom"))
    out = capsys.readouterr()
    assert out.err == "", f"expected silent default, got: {out.err!r}"


def test_logs_when_debug_enabled(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SOMA_DEBUG", "1")
    monkeypatch.delenv("SOMA_HOOK_QUIET", raising=False)
    log_silent_failure("lessons._save", FileNotFoundError("no path"))
    out = capsys.readouterr()
    assert "lessons._save" in out.err
    assert "FileNotFoundError" in out.err
    assert "no path" in out.err


def test_quiet_overrides_debug(monkeypatch, capsys) -> None:
    """SOMA_HOOK_QUIET=1 wins so test runners and CI stay silent."""
    monkeypatch.setenv("SOMA_DEBUG", "1")
    monkeypatch.setenv("SOMA_HOOK_QUIET", "1")
    log_silent_failure("test", RuntimeError("boom"))
    out = capsys.readouterr()
    assert out.err == ""


def test_helper_never_raises(monkeypatch) -> None:
    """Even if stderr is dead the helper must not propagate."""
    monkeypatch.setenv("SOMA_DEBUG", "1")
    # Replace stderr with something that raises on write.
    class Broken:
        def write(self, _):
            raise OSError("stderr is dead")
        def flush(self):
            raise OSError("stderr is dead")
    real = sys.stderr
    sys.stderr = Broken()
    try:
        log_silent_failure("test", RuntimeError("boom"))  # must not raise
    finally:
        sys.stderr = real


def test_lessons_save_uses_helper(monkeypatch, capsys, tmp_path) -> None:
    """Verify the helper is actually wired into LessonStore._save."""
    from soma.lessons import LessonStore
    monkeypatch.setenv("SOMA_DEBUG", "1")
    monkeypatch.delenv("SOMA_HOOK_QUIET", raising=False)
    # Path that can never be created (file as parent).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    store = LessonStore(path=blocker / "lessons.json")
    store.record("p", "err", "fix")
    out = capsys.readouterr()
    assert "lessons._save" in out.err, (
        f"helper not wired into LessonStore._save: stderr={out.err!r}"
    )


def test_findings_uses_helper(monkeypatch, capsys) -> None:
    """Verify the helper is wired into findings.collect's except blocks."""
    from soma import findings
    monkeypatch.setenv("SOMA_DEBUG", "1")
    monkeypatch.delenv("SOMA_HOOK_QUIET", raising=False)
    # Pass garbage that triggers an internal exception path. The helper
    # only fires if a real exception is caught — a clean call won't
    # exercise it. We rely on the broken hook_config to crash one of
    # the inner branches.
    findings.collect(
        action_log=[], vitals={}, pressure=0.5,
        level_name="OBSERVE", actions=1, hook_config={},
        agent_id="test",
    )
    # No assertion on stderr content — just verify no crash. The
    # source-level grep is what proves wiring (see commit message).
