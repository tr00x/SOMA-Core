"""Tests for `soma prune` CLI (P1.5)."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pytest

from soma.cli.main import (
    _cmd_prune,
    _dir_size_bytes,
    _find_stale_sessions,
)


# ── _find_stale_sessions ─────────────────────────────────────────────

def test_find_stale_missing_dir_is_empty(tmp_path):
    assert _find_stale_sessions(tmp_path / "nope", cutoff_ts=time.time()) == []


def test_find_stale_honors_cutoff(tmp_path):
    sessions = tmp_path / ".soma" / "sessions"
    sessions.mkdir(parents=True)

    fresh = sessions / "fresh"
    fresh.mkdir()
    old = sessions / "old"
    old.mkdir()

    # Backdate `old` to 60 days ago
    sixty_days = time.time() - 60 * 86_400
    os.utime(old, (sixty_days, sixty_days))

    # Cutoff = 30 days ago → only `old` is stale
    cutoff = time.time() - 30 * 86_400
    stale = _find_stale_sessions(sessions, cutoff_ts=cutoff)
    assert [p.name for p in stale] == ["old"]


def test_find_stale_skips_non_directory(tmp_path):
    sessions = tmp_path / ".soma" / "sessions"
    sessions.mkdir(parents=True)

    stray_file = sessions / "stray.json"
    stray_file.write_text("{}")
    sixty_days = time.time() - 60 * 86_400
    os.utime(stray_file, (sixty_days, sixty_days))

    cutoff = time.time() - 30 * 86_400
    # Non-dir entries are skipped even if older than cutoff.
    assert _find_stale_sessions(sessions, cutoff_ts=cutoff) == []


# ── _dir_size_bytes ──────────────────────────────────────────────────

def test_dir_size_bytes_counts_recursively(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 100)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b").write_bytes(b"y" * 50)
    assert _dir_size_bytes(tmp_path) == 150


def test_dir_size_bytes_missing_is_zero(tmp_path):
    assert _dir_size_bytes(tmp_path / "ghost") == 0


# ── _cmd_prune ───────────────────────────────────────────────────────

def _make_dry_run_args(days: int, yes: bool = False) -> argparse.Namespace:
    return argparse.Namespace(older_than=days, yes=yes)


def test_prune_dry_run_does_not_delete(tmp_path, monkeypatch, capsys):
    sessions = tmp_path / ".soma" / "sessions"
    sessions.mkdir(parents=True)
    old = sessions / "oldsession"
    old.mkdir()
    (old / "action_log.json").write_text("{}")

    sixty_days = time.time() - 60 * 86_400
    os.utime(old, (sixty_days, sixty_days))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    _cmd_prune(_make_dry_run_args(days=30, yes=False))

    out = capsys.readouterr().out
    assert "Would remove 1 session" in out
    assert "oldsession" in out
    assert old.exists(), "dry-run must not delete"


def test_prune_yes_deletes(tmp_path, monkeypatch, capsys):
    sessions = tmp_path / ".soma" / "sessions"
    sessions.mkdir(parents=True)
    old = sessions / "oldsession"
    old.mkdir()
    (old / "f.json").write_text("{}")
    fresh = sessions / "freshsession"
    fresh.mkdir()

    sixty_days = time.time() - 60 * 86_400
    os.utime(old, (sixty_days, sixty_days))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    _cmd_prune(_make_dry_run_args(days=30, yes=True))

    out = capsys.readouterr().out
    assert "Removed 1 session" in out
    assert not old.exists()
    assert fresh.exists(), "fresh session must survive"


def test_prune_empty_dir_is_noop(tmp_path, monkeypatch, capsys):
    (tmp_path / ".soma" / "sessions").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    _cmd_prune(_make_dry_run_args(days=30))

    assert "No sessions older than 30d" in capsys.readouterr().out


def test_prune_missing_sessions_dir_is_noop(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _cmd_prune(_make_dry_run_args(days=30))
    assert "No sessions older than 30d" in capsys.readouterr().out


def test_prune_clamps_days_to_minimum_one(tmp_path, monkeypatch, capsys):
    sessions = tmp_path / ".soma" / "sessions"
    sessions.mkdir(parents=True)
    old = sessions / "x"
    old.mkdir()
    # mtime = 2 days ago → would survive --older-than=3 but not --older-than=1
    two_days = time.time() - 2 * 86_400
    os.utime(old, (two_days, two_days))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # days=0 is clamped to 1 by _cmd_prune
    _cmd_prune(_make_dry_run_args(days=0))

    out = capsys.readouterr().out
    assert "older than 1d" in out
    assert "Would remove 1 session" in out
