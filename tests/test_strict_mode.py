"""Day 5b: strict-mode PreToolUse enforcement + block lifecycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from soma import blocks as _blocks
from soma import calibration as _cal
from soma.blocks import BlockState, load_block_state, save_block_state


@pytest.fixture(autouse=True)
def _isolated_soma(tmp_path, monkeypatch):
    """Redirect ~/.soma/ reads & writes into tmp_path for this test."""
    monkeypatch.setattr(_blocks, "SOMA_DIR", tmp_path)
    monkeypatch.setattr(_cal, "SOMA_DIR", tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Also need state.SOMA_DIR because engine.persistence uses it.
    from soma import state as _state
    monkeypatch.setattr(_state, "SOMA_DIR", tmp_path)
    yield tmp_path


def _set_strict_mode(monkeypatch, mode: str = "strict"):
    from soma.hooks import common as _common
    monkeypatch.setattr(_common, "get_soma_mode", lambda _agent_id=None: mode)


def _calibrated_profile(tmp_path, family: str = "cc") -> None:
    """Write a non-warmup profile so strict mode actually enforces."""
    prof = _cal.CalibrationProfile(family=family, action_count=200)
    _cal.save_profile(prof)


# ── PreToolUse enforcement ──────────────────────────────────────────

def test_pre_hook_blocks_when_block_active(tmp_path, monkeypatch, capsys):
    _set_strict_mode(monkeypatch)
    _calibrated_profile(tmp_path)
    bs = BlockState(family="cc")
    bs.add_block("retry_storm", "Bash", reason="3 fails")
    save_block_state(bs)

    # Stub engine so pre_tool_use main() has something to read.
    class _FakeSnap(dict):
        pass
    class _FakeEngine:
        def get_snapshot(self, _): return {"pressure": 0.5}
    from soma.hooks import common as _common, pre_tool_use as _ptu
    monkeypatch.setattr(_ptu, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_ptu, "read_stdin", lambda: {
        "tool_name": "Bash", "tool_input": {"command": "pytest"},
    })
    monkeypatch.setattr(_common, "increment_block_count", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [])

    from soma.hooks import pre_tool_use
    with pytest.raises(SystemExit) as exc:
        pre_tool_use.main()
    assert exc.value.code == 2

    err = capsys.readouterr().err
    assert "SOMA(strict)" in err
    assert "retry_storm blocks Bash" in err


def test_pre_hook_passes_when_no_matching_block(tmp_path, monkeypatch, capsys):
    _set_strict_mode(monkeypatch)
    _calibrated_profile(tmp_path)
    # Empty block state.
    save_block_state(BlockState(family="cc"))

    class _FakeEngine:
        def get_snapshot(self, _): return {"pressure": 0.1}
    from soma.hooks import common as _common
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_common, "increment_block_count", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [])
    monkeypatch.setattr(_common, "read_stdin", lambda: {
        "tool_name": "Bash", "tool_input": {"command": "pytest"},
    })

    from soma.hooks import pre_tool_use
    # Should not exit 2 — strict block path is skipped.
    # (Downstream paths may still exit for other reasons but our
    # isolated state makes those no-ops.)
    try:
        pre_tool_use.main()
    except SystemExit as e:
        # If another reflex blocks, that's out of scope for this test.
        # Only assert we didn't BLOCK on strict-mode gate — "SOMA(strict)"
        # text in stderr would be the fingerprint.
        err = capsys.readouterr().err
        assert "SOMA(strict)" not in err


def test_pre_hook_skips_strict_in_warmup(tmp_path, monkeypatch, capsys):
    _set_strict_mode(monkeypatch)
    # Warmup profile — action_count < 100.
    prof = _cal.CalibrationProfile(family="cc", action_count=10)
    _cal.save_profile(prof)

    bs = BlockState(family="cc")
    bs.add_block("retry_storm", "Bash")
    save_block_state(bs)

    class _FakeEngine:
        def get_snapshot(self, _): return {"pressure": 0.5}
    from soma.hooks import common as _common
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_common, "increment_block_count", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [])
    monkeypatch.setattr(_common, "read_stdin", lambda: {
        "tool_name": "Bash", "tool_input": {"command": "pytest"},
    })

    from soma.hooks import pre_tool_use
    try:
        pre_tool_use.main()
    except SystemExit:
        # If something else exited, fine — but not OUR strict-block path.
        pass
    err = capsys.readouterr().err
    assert "SOMA(strict)" not in err


def test_pre_hook_silenced_pattern_does_not_block(tmp_path, monkeypatch, capsys):
    _set_strict_mode(monkeypatch)
    _calibrated_profile(tmp_path)
    bs = BlockState(family="cc")
    bs.add_block("retry_storm", "Bash", reason="3 fails")
    bs.silence_pattern("retry_storm", seconds=60)
    save_block_state(bs)

    class _FakeEngine:
        def get_snapshot(self, _): return {"pressure": 0.5}
    from soma.hooks import common as _common
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_common, "increment_block_count", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [])
    monkeypatch.setattr(_common, "read_stdin", lambda: {
        "tool_name": "Bash", "tool_input": {"command": "pytest"},
    })

    from soma.hooks import pre_tool_use
    try:
        pre_tool_use.main()
    except SystemExit:
        pass
    err = capsys.readouterr().err
    # Silence window active → strict gate must not fire.
    assert "SOMA(strict)" not in err


def test_pre_hook_observe_mode_skips_strict(tmp_path, monkeypatch, capsys):
    _set_strict_mode(monkeypatch, mode="observe")
    _calibrated_profile(tmp_path)
    bs = BlockState(family="cc")
    bs.add_block("retry_storm", "Bash")
    save_block_state(bs)

    class _FakeEngine:
        def get_snapshot(self, _): return {"pressure": 0.5}
    from soma.hooks import common as _common
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [])
    monkeypatch.setattr(_common, "read_stdin", lambda: {
        "tool_name": "Bash", "tool_input": {"command": "pytest"},
    })

    from soma.hooks import pre_tool_use
    # Observe short-circuits before strict logic.
    pre_tool_use.main()
    err = capsys.readouterr().err
    assert "SOMA(strict)" not in err


# ── Block clear on followthrough (post_tool_use integration) ────────

def test_clear_block_pattern_removes_matching_tool_entries(tmp_path):
    bs = BlockState(family="cc")
    bs.add_block("retry_storm", "Bash")
    bs.add_block("retry_storm", "Edit")
    bs.add_block("blind_edit", "Edit")
    removed = bs.clear_block(pattern="retry_storm")
    assert removed == 2
    assert not bs.is_blocked("retry_storm", "Bash")
    assert bs.is_blocked("blind_edit", "Edit")
