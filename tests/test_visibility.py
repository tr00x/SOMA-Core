"""User-facing visibility — statusline calibration phase + end-of-session summary."""

from __future__ import annotations

from pathlib import Path

import pytest

from soma import blocks as _blocks
from soma import calibration as _cal
from soma.blocks import BlockState, save_block_state
from soma.calibration import CalibrationProfile, WARMUP_EXIT_ACTIONS


@pytest.fixture(autouse=True)
def _isolated_soma(tmp_path, monkeypatch):
    monkeypatch.setattr(_blocks, "SOMA_DIR", tmp_path)
    monkeypatch.setattr(_cal, "SOMA_DIR", tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from soma import state as _state
    monkeypatch.setattr(_state, "SOMA_DIR", tmp_path)
    yield tmp_path


# ── Statusline: warmup shows learning progress ──────────────────────

def test_statusline_warmup_shows_learning_counter(tmp_path, monkeypatch, capsys):
    warmup_count = max(1, WARMUP_EXIT_ACTIONS - 5)
    _cal.save_profile(CalibrationProfile(family="cc", action_count=warmup_count))

    class _FakeSnap(dict):
        pass
    class _FakeEngine:
        def get_snapshot(self, _):
            return {
                "level": _Level("GUIDE"), "pressure": 0.2,
                "action_count": warmup_count, "vitals": {},
            }
    class _Level:
        def __init__(self, name): self.name = name

    from soma.hooks import common as _common, statusline as _sl
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))

    _sl.main()
    out = capsys.readouterr().out
    assert f"learning {warmup_count}/{WARMUP_EXIT_ACTIONS}" in out


def test_statusline_calibrated_phase_shows_normal_line(tmp_path, monkeypatch, capsys):
    _cal.save_profile(CalibrationProfile(family="cc", action_count=250))

    class _Level:
        def __init__(self, name): self.name = name
    class _FakeEngine:
        def get_snapshot(self, _):
            return {
                "level": _Level("GUIDE"), "pressure": 0.15,
                "action_count": 250, "vitals": {},
            }
    from soma.hooks import common as _common, statusline as _sl
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))

    _sl.main()
    out = capsys.readouterr().out
    assert "learning" not in out
    assert "SOMA" in out
    assert "15%" in out


def test_statusline_shows_red_block_indicator(tmp_path, monkeypatch, capsys):
    _cal.save_profile(CalibrationProfile(family="cc", action_count=250))
    bs = BlockState(family="cc")
    bs.add_block("retry_storm", "Bash", reason="streak")
    save_block_state(bs)

    class _Level:
        def __init__(self, name): self.name = name
    class _FakeEngine:
        def get_snapshot(self, _):
            return {
                "level": _Level("GUIDE"), "pressure": 0.3,
                "action_count": 250, "vitals": {},
            }
    from soma.hooks import common as _common, statusline as _sl
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))

    _sl.main()
    out = capsys.readouterr().out
    assert "🔴" in out
    assert "retry_storm" in out


# ── Stop hook: session summary emits to stdout ──────────────────────

def test_stop_hook_prints_summary_with_calibration_phase(
    tmp_path, monkeypatch, capsys,
):
    # Land inside the calibrated band, never past CALIBRATED_EXIT_ACTIONS.
    from soma.calibration import CALIBRATED_EXIT_ACTIONS as _CE
    calibrated_count = (WARMUP_EXIT_ACTIONS + _CE) // 2
    _cal.save_profile(CalibrationProfile(family="cc", action_count=calibrated_count))

    # Stub engine so stop() has something to work with.
    class _Level:
        def __init__(self, name): self.name = name
    class _FakeEngine:
        def get_snapshot(self, _):
            return {
                "action_count": calibrated_count, "pressure": 0.18,
                "level": _Level("GUIDE"), "vitals": {},
            }
        _agents = {"cc-99": None}

    from soma.hooks import stop as _stop, common as _common
    monkeypatch.setattr(_stop, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_stop, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_common, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [
        {"tool": "Bash", "error": False, "ts": 0.0},
        {"tool": "Read", "error": False, "ts": 1.0},
        {"tool": "Edit", "error": False, "ts": 2.0},
    ])
    monkeypatch.setattr(_common, "read_pressure_trajectory", lambda *_a, **_k: [0.1, 0.2])

    # Avoid touching analytics/fingerprint/subagent — they're side paths.
    _stop.main()
    out = capsys.readouterr().out
    # Summary header + at least one calibration line.
    assert "[SOMA session summary]" in out
    assert "calibration:" in out
    assert "calibrated" in out


def test_stop_hook_surfaces_unresolved_blocks(tmp_path, monkeypatch, capsys):
    _cal.save_profile(CalibrationProfile(family="cc", action_count=250))
    bs = BlockState(family="cc")
    bs.add_block("blind_edit", "Edit", reason="read first")
    save_block_state(bs)

    class _Level:
        def __init__(self, name): self.name = name
    class _FakeEngine:
        def get_snapshot(self, _):
            return {
                "action_count": 250, "pressure": 0.18,
                "level": _Level("GUIDE"), "vitals": {},
            }
        _agents = {"cc-99": None}

    from soma.hooks import stop as _stop, common as _common
    monkeypatch.setattr(_stop, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_stop, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_common, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(_common, "read_action_log", lambda *_a, **_k: [
        {"tool": "Edit", "error": False, "ts": 0.0},
        {"tool": "Bash", "error": False, "ts": 1.0},
        {"tool": "Read", "error": False, "ts": 2.0},
    ])
    monkeypatch.setattr(_common, "read_pressure_trajectory", lambda *_a, **_k: [0.1, 0.2])

    _stop.main()
    out = capsys.readouterr().out
    assert "unresolved blocks" in out
    assert "blind_edit" in out
