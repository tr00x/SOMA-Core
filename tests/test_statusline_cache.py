"""Statusline mtime-keyed cache.

Statusline runs every ~5s in Claude Code; the full render path opens
engine_state.json + soma.toml + calibration profile + block files +
circuit_<aid>.json — that's 5-6 JSON parses per tick. The cache cuts
the warm path to one stat() + one tiny JSON read.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from soma.hooks import statusline as sl


@pytest.fixture
def isolated_soma(tmp_path, monkeypatch):
    """Point cache + state at tmp_path."""
    monkeypatch.setattr(sl, "_STATUSLINE_CACHE_PATH", tmp_path / "statusline_cache.json")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    home_soma = tmp_path / "home" / ".soma"
    home_soma.mkdir(parents=True)
    return home_soma


class TestCache:
    def test_no_engine_state_returns_false(self, isolated_soma):
        # cache miss when there's nothing to key on
        assert sl._try_print_cached() is False

    def test_cache_hit_prints_and_returns_true(self, isolated_soma, capsys):
        engine_path = isolated_soma / "engine_state.json"
        engine_path.write_text("{}")
        cache_path = sl._statusline_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "mtime_engine": engine_path.stat().st_mtime,
            "rendered": "🧠 SOMA · cached output",
            "cached_at": time.time(),
        }))

        assert sl._try_print_cached() is True
        out = capsys.readouterr().out.strip()
        assert out == "🧠 SOMA · cached output"

    def test_cache_miss_when_engine_state_changed(self, isolated_soma):
        engine_path = isolated_soma / "engine_state.json"
        engine_path.write_text("{}")
        cache_path = sl._statusline_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "mtime_engine": 0.0,  # stale
            "rendered": "stale",
            "cached_at": time.time(),
        }))
        assert sl._try_print_cached() is False

    def test_cache_miss_when_ttl_expired(self, isolated_soma):
        engine_path = isolated_soma / "engine_state.json"
        engine_path.write_text("{}")
        cache_path = sl._statusline_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "mtime_engine": engine_path.stat().st_mtime,
            "rendered": "old",
            "cached_at": time.time() - sl._STATUSLINE_CACHE_TTL_SEC - 5,
        }))
        assert sl._try_print_cached() is False

    def test_save_cache_round_trip(self, isolated_soma):
        engine_path = isolated_soma / "engine_state.json"
        engine_path.write_text("{}")
        sl._save_cache("🧠 SOMA · test render")
        cache = json.loads(sl._statusline_cache_path().read_text())
        assert cache["rendered"] == "🧠 SOMA · test render"
        assert cache["mtime_engine"] == engine_path.stat().st_mtime

    def test_save_cache_silently_skips_when_no_engine_state(self, isolated_soma):
        # No engine_state.json exists → don't write garbage cache.
        sl._save_cache("would-not-be-cached")
        assert not sl._statusline_cache_path().exists()
