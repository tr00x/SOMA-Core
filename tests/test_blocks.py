"""Strict-mode block state + unblock CLI (v2026.5.0 Day 5a)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pytest

from soma import blocks as _blocks
from soma.blocks import (
    Block,
    BlockState,
    DEFAULT_SILENCE_SECONDS,
    clear_all_blocks,
    load_block_state,
    save_block_state,
)


@pytest.fixture(autouse=True)
def _isolated_soma_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_blocks, "SOMA_DIR", tmp_path)
    yield tmp_path


# ── Mutation primitives ─────────────────────────────────────────────

def test_add_block_records_single_entry():
    state = BlockState(family="cc")
    b = state.add_block("retry_storm", "Bash", reason="3 fails")
    assert state.blocks == [b]
    assert state.is_blocked("retry_storm", "Bash")


def test_add_block_replaces_existing_pair():
    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash", reason="old")
    state.add_block("retry_storm", "Bash", reason="new")
    assert len(state.blocks) == 1
    assert state.blocks[0].reason == "new"


def test_add_block_keeps_different_tool():
    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash")
    state.add_block("retry_storm", "Edit")
    assert len(state.blocks) == 2


def test_clear_block_no_args_clears_all():
    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash")
    state.add_block("blind_edit", "Edit")
    removed = state.clear_block()
    assert removed == 2
    assert state.blocks == []


def test_clear_block_by_pattern():
    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash")
    state.add_block("blind_edit", "Edit")
    removed = state.clear_block(pattern="retry_storm")
    assert removed == 1
    assert not state.is_blocked("retry_storm", "Bash")
    assert state.is_blocked("blind_edit", "Edit")


def test_any_block_for_tool_returns_newest():
    state = BlockState(family="cc")
    first = state.add_block("retry_storm", "Bash")
    # Manually force-order so the second has a strictly higher created_at.
    time.sleep(0.01)
    second = state.add_block("bash_retry", "Bash")
    newest = state.any_block_for_tool("Bash")
    assert newest == second
    assert newest != first


def test_any_block_for_tool_none_when_empty():
    assert BlockState(family="cc").any_block_for_tool("Bash") is None


# ── Silence windows ─────────────────────────────────────────────────

def test_silence_pattern_sets_deadline_in_future():
    state = BlockState(family="cc")
    deadline = state.silence_pattern("retry_storm", seconds=60)
    assert deadline > time.time()
    assert state.is_silenced("retry_storm")


def test_is_silenced_clears_expired_deadline():
    state = BlockState(family="cc")
    # Force an expired entry.
    state.silenced_until["retry_storm"] = time.time() - 1
    assert state.is_silenced("retry_storm") is False
    assert "retry_storm" not in state.silenced_until  # lazy cleanup


def test_silence_zero_seconds_clamped_to_one():
    state = BlockState(family="cc")
    d = state.silence_pattern("x", seconds=0)
    assert d > time.time()
    assert state.is_silenced("x")


# ── Serialization & persistence ─────────────────────────────────────

def test_save_load_roundtrip(tmp_path):
    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash", reason="streak")
    state.silence_pattern("blind_edit", seconds=120)
    save_block_state(state)

    reloaded = load_block_state("cc-42")
    assert reloaded.family == "cc"
    assert reloaded.is_blocked("retry_storm", "Bash")
    assert reloaded.is_silenced("blind_edit")


def test_load_missing_returns_fresh():
    s = load_block_state("cc-7")
    assert s.family == "cc"
    assert s.blocks == []
    assert s.silenced_until == {}


def test_load_corrupt_returns_fresh(tmp_path):
    (tmp_path / "blocks_cc.json").write_text("{not json")
    s = load_block_state("cc-7")
    assert s.blocks == []


def test_load_strips_expired_silences(tmp_path):
    path = tmp_path / "blocks_cc.json"
    path.write_text(json.dumps({
        "family": "cc",
        "blocks": [],
        "silenced_until": {
            "retry_storm": time.time() - 100,  # expired
            "blind_edit": time.time() + 600,   # live
        },
    }))
    s = load_block_state("cc-7")
    assert "retry_storm" not in s.silenced_until
    assert "blind_edit" in s.silenced_until


def test_load_skips_malformed_block_entries(tmp_path):
    path = tmp_path / "blocks_cc.json"
    path.write_text(json.dumps({
        "family": "cc",
        "blocks": [
            {"pattern": "retry_storm", "tool": "Bash", "created_at": time.time()},
            {"pattern": "", "tool": "Bash", "created_at": time.time()},  # bad
            "not a dict",  # bad
        ],
    }))
    s = load_block_state("cc-7")
    assert len(s.blocks) == 1
    assert s.blocks[0].pattern == "retry_storm"


def test_clear_all_blocks_deletes_file(tmp_path):
    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash")
    save_block_state(state)
    assert (tmp_path / "blocks_cc.json").exists()

    assert clear_all_blocks("cc-42") is True
    assert not (tmp_path / "blocks_cc.json").exists()


def test_clear_all_blocks_missing_returns_false():
    assert clear_all_blocks("cc-7") is False


# ── CLI ─────────────────────────────────────────────────────────────

def test_cli_unblock_clears_blocks(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # _cmd_unblock calls into soma.blocks which we've already redirected
    # via the _blocks.SOMA_DIR monkeypatch in the autouse fixture.
    from soma.cli.main import _cmd_unblock

    state = BlockState(family="cc")
    state.add_block("retry_storm", "Bash")
    state.add_block("blind_edit", "Edit")
    save_block_state(state)

    args = argparse.Namespace(agent_id="cc-99", pattern=None, all=False)
    _cmd_unblock(args)
    out = capsys.readouterr().out
    assert "Cleared 2 block(s)" in out

    # Persisted empty state.
    reloaded = load_block_state("cc-99")
    assert reloaded.blocks == []


def test_cli_unblock_silences_single_pattern(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from soma.cli.main import _cmd_unblock

    args = argparse.Namespace(agent_id="cc-99", pattern="retry_storm", all=False)
    _cmd_unblock(args)
    out = capsys.readouterr().out
    assert "Silenced 'retry_storm'" in out

    reloaded = load_block_state("cc-99")
    assert reloaded.is_silenced("retry_storm")


def test_cli_unblock_all_flag_deletes_every_family(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from soma.cli.main import _cmd_unblock

    # Two family files.
    save_block_state(BlockState(family="cc", blocks=[Block("x", "Bash", time.time())]))
    save_block_state(BlockState(family="swe", blocks=[Block("y", "Edit", time.time())]))
    assert (tmp_path / "blocks_cc.json").exists()
    assert (tmp_path / "blocks_swe.json").exists()

    args = argparse.Namespace(agent_id=None, pattern=None, all=True)
    _cmd_unblock(args)
    out = capsys.readouterr().out
    assert "Cleared 2 family block file(s)" in out
    assert not (tmp_path / "blocks_cc.json").exists()
    assert not (tmp_path / "blocks_swe.json").exists()
