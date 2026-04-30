"""
Regression for v2026.6.x fix #17 — `soma mode <invalid>` must not
crash with a traceback. Discovered during clean-venv smoke:

  $ soma mode  # showed "Current mode: guide"
  $ soma mode guide
  Traceback (most recent call last):
  ...
  ValueError: Unknown mode: 'guide'. Choose from: strict, relaxed, autonomous

Two distinct concepts shared the word "mode":
- soma.mode in config: observe / guide / reflex (engine response mode)
- preset name: strict / relaxed / autonomous (bundled config slice)

The CLI now distinguishes them in the no-arg display and catches
the ValueError with a friendly message.
"""
from __future__ import annotations

from pathlib import Path
import argparse

import pytest


def _run_mode_command(mode_name, monkeypatch, tmp_path):
    """Invoke _cmd_mode with a synthetic args namespace."""
    from soma.cli.main import _cmd_mode
    from soma import config as cfg

    # Isolate config writes to tmp_path
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(mode_name=mode_name)
    _cmd_mode(args)


def test_mode_invalid_does_not_traceback(monkeypatch, tmp_path, capsys):
    """Invalid mode → SystemExit(1) with friendly error, not traceback."""
    with pytest.raises(SystemExit) as exc:
        _run_mode_command("guide", monkeypatch, tmp_path)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Error" in out or "error" in out
    assert "guide" in out
    assert "Usage" in out


def test_mode_valid_preset_works(monkeypatch, tmp_path, capsys):
    """Sanity — a real preset name applies cleanly."""
    _run_mode_command("strict", monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert "Mode set to: strict" in out
    assert "Autonomy" in out


def test_mode_no_args_disambiguates_preset_vs_engine_mode(monkeypatch, tmp_path, capsys):
    """`soma mode` (no args) must label the current value as 'preset'
    or 'engine mode' depending on which set it belongs to. Otherwise
    a user sees 'Current mode: guide' and tries `soma mode guide`."""
    # Seed a soma.toml where soma.mode = "guide" (an engine mode, not a preset)
    (tmp_path / "soma.toml").write_text(
        "[soma]\nmode = \"guide\"\n[budget]\ntokens = 100\n"
    )
    _run_mode_command(None, monkeypatch, tmp_path)
    out = capsys.readouterr().out
    # The display must NOT just say "Current mode: guide" — that was
    # the trap. It must say "engine mode" so the user knows `soma mode
    # guide` won't roundtrip.
    assert "engine mode" in out, (
        f"display did not disambiguate engine mode vs preset:\n{out}"
    )
