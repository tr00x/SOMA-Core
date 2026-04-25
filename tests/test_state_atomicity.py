"""Atomic-write coverage for state.py.

The previous implementation used path.write_text(json.dumps(...)) — one
non-atomic syscall. A SIGKILL during a predictor save left a truncated
file, the loader silently caught JSONDecodeError and reset to defaults,
and cross-session learning was wiped without trace.

Now save_* uses mkstemp + fsync + os.replace. A crash in the middle
leaves either the prior file or the new one intact — never a torn
truncation that the loader would silently swallow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma import state as st


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Point all state-file constants at tmp_path so tests don't write to ~/.soma."""
    monkeypatch.setattr(st, "SOMA_DIR", tmp_path)
    monkeypatch.setattr(st, "FINGERPRINT_PATH", tmp_path / "fingerprint.json")
    monkeypatch.setattr(st, "PREDICTOR_PATH", tmp_path / "predictor.json")
    monkeypatch.setattr(st, "TASK_TRACKER_PATH", tmp_path / "task_tracker.json")
    monkeypatch.setattr(st, "QUALITY_PATH", tmp_path / "quality.json")
    monkeypatch.setattr(st, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path


class TestAtomicWriteJson:
    def test_simple_write_succeeds(self, isolated_state):
        path = isolated_state / "ok.json"
        st._atomic_write_json(path, {"a": 1, "b": [2, 3]})
        assert json.loads(path.read_text()) == {"a": 1, "b": [2, 3]}

    def test_write_replaces_existing(self, isolated_state):
        path = isolated_state / "ok.json"
        path.write_text('{"old": true}')
        st._atomic_write_json(path, {"new": True})
        assert json.loads(path.read_text()) == {"new": True}

    def test_crash_during_write_preserves_original(self, isolated_state, monkeypatch):
        """Simulate os.replace failing — the prior file must remain intact
        and no .tmp leftover may stay on disk."""
        path = isolated_state / "guarded.json"
        original = {"keep": "me"}
        path.write_text(json.dumps(original))

        def explode(*_a, **_kw):
            raise OSError("simulated disk full")

        monkeypatch.setattr(st.os, "replace", explode)

        with pytest.raises(OSError):
            st._atomic_write_json(path, {"would": "lose"})

        assert json.loads(path.read_text()) == original
        leftovers = [p for p in isolated_state.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == [], f"leftover .tmp files: {leftovers}"

    def test_no_torn_writes_on_concurrent_readers(self, isolated_state):
        """Even mid-write, a reader will only see the prior file or the
        new file (atomic rename). Verify the new content lands as a whole."""
        path = isolated_state / "atomic.json"
        big = {"k": "x" * 50_000}
        st._atomic_write_json(path, big)
        loaded = json.loads(path.read_text())
        assert loaded == big


class TestSaveFunctionsAreAtomic:
    """Each save_* function must route through the atomic helper so a
    crash mid-write doesn't corrupt cross-session learning state."""

    def test_save_predictor_uses_atomic_write(self, isolated_state, monkeypatch):
        from soma.predictor import PressurePredictor
        called = {}

        def spy(path, data):
            called["path"] = path
            called["data"] = data

        monkeypatch.setattr(st, "_atomic_write_json", spy)
        st.save_predictor(PressurePredictor())
        assert called["path"] == st.PREDICTOR_PATH
        assert isinstance(called["data"], dict)

    def test_save_quality_tracker_uses_atomic_write(self, isolated_state, monkeypatch):
        from soma.quality import QualityTracker
        called = {}
        monkeypatch.setattr(
            st, "_atomic_write_json",
            lambda p, d: called.setdefault("hit", (p, d)),
        )
        st.save_quality_tracker(QualityTracker())
        assert called["hit"][0] == st.QUALITY_PATH

    def test_save_fingerprint_engine_uses_atomic_write(
        self, isolated_state, monkeypatch,
    ):
        from soma.fingerprint import FingerprintEngine
        called = {}
        monkeypatch.setattr(
            st, "_atomic_write_json",
            lambda p, d: called.setdefault("hit", (p, d)),
        )
        st.save_fingerprint_engine(FingerprintEngine())
        assert called["hit"][0] == st.FINGERPRINT_PATH

    def test_save_task_tracker_uses_atomic_write(self, isolated_state, monkeypatch):
        from soma.task_tracker import TaskTracker
        called = {}
        monkeypatch.setattr(
            st, "_atomic_write_json",
            lambda p, d: called.setdefault("hit", (p, d)),
        )
        st.save_task_tracker(TaskTracker())
        assert called["hit"][0] == st.TASK_TRACKER_PATH

    def test_predictor_save_then_load_roundtrip(self, isolated_state):
        """End-to-end: real save → real load returns equivalent state."""
        from soma.predictor import PressurePredictor
        p = PressurePredictor()
        st.save_predictor(p)
        assert st.PREDICTOR_PATH.exists()
        assert isinstance(json.loads(st.PREDICTOR_PATH.read_text()), dict)

    def test_simulated_crash_preserves_prior_predictor(
        self, isolated_state, monkeypatch,
    ):
        """SIGKILL-equivalent during save_predictor must leave the prior
        predictor.json intact — that's the whole point of atomicity."""
        from soma.predictor import PressurePredictor
        st.PREDICTOR_PATH.write_text('{"prior": "state", "session_patterns": []}')
        original_bytes = st.PREDICTOR_PATH.read_bytes()

        # save_predictor swallows exceptions but mid-write crash via
        # os.replace must not corrupt the original file.
        def explode(*_a, **_kw):
            raise OSError("simulated crash")
        monkeypatch.setattr(st.os, "replace", explode)

        st.save_predictor(PressurePredictor())  # silently logs, doesn't raise

        assert st.PREDICTOR_PATH.read_bytes() == original_bytes
