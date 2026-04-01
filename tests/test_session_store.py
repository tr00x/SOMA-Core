"""Tests for SOMA session store — append-only JSON Lines history."""

from __future__ import annotations

import json

from soma.session_store import SessionRecord, append_session, load_sessions


def _make_record(**overrides) -> SessionRecord:
    defaults = dict(
        session_id="sess-001",
        agent_id="agent-1",
        started=1000.0,
        ended=2000.0,
        action_count=50,
        final_pressure=0.3,
        max_pressure=0.6,
        avg_pressure=0.25,
        error_count=2,
        retry_count=1,
        total_tokens=5000,
        mode_transitions=[{"from": "OBSERVE", "to": "GUIDE", "at_action": 10, "pressure": 0.3}],
        pressure_trajectory=[0.1, 0.2, 0.3, 0.25, 0.3],
        tool_distribution={"Read": 20, "Edit": 15, "Bash": 10},
        phase_sequence=["research", "implement", "test"],
        fingerprint_divergence=0.05,
    )
    defaults.update(overrides)
    return SessionRecord(**defaults)


def test_append_session_creates_jsonl(tmp_path):
    """append_session writes JSON line to sessions/history.jsonl."""
    record = _make_record()
    append_session(record, base_dir=tmp_path)

    jsonl = tmp_path / "sessions" / "history.jsonl"
    assert jsonl.exists()
    line = json.loads(jsonl.read_text().strip())
    assert line["session_id"] == "sess-001"
    assert line["agent_id"] == "agent-1"


def test_load_sessions_returns_records(tmp_path):
    """load_sessions returns list of SessionRecord from JSON Lines file."""
    for i in range(3):
        append_session(_make_record(session_id=f"sess-{i}"), base_dir=tmp_path)

    records = load_sessions(base_dir=tmp_path)
    assert len(records) == 3
    assert records[0].session_id == "sess-0"
    assert records[2].session_id == "sess-2"


def test_session_store_creates_parent_dirs(tmp_path):
    """Session store creates parent directories if missing."""
    nested = tmp_path / "deep" / "nested"
    append_session(_make_record(), base_dir=nested)
    jsonl = nested / "sessions" / "history.jsonl"
    assert jsonl.exists()


def test_session_store_rotates_at_max_bytes(tmp_path):
    """Session store rotates when file exceeds max_bytes."""
    record = _make_record()
    # Write enough to exceed a tiny max_bytes
    for i in range(10):
        append_session(record, base_dir=tmp_path, max_bytes=100)

    sessions_dir = tmp_path / "sessions"
    files = list(sessions_dir.iterdir())
    # Should have history.jsonl plus at least one rotated file
    assert len(files) >= 2
    assert any(f.name == "history.jsonl" for f in files)


def test_load_sessions_empty_file(tmp_path):
    """load_sessions returns [] for missing file."""
    records = load_sessions(base_dir=tmp_path)
    assert records == []


def test_load_sessions_skips_malformed(tmp_path):
    """load_sessions skips malformed JSON lines."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)
    jsonl = sessions_dir / "history.jsonl"

    record = _make_record()
    import dataclasses
    good_line = json.dumps(dataclasses.asdict(record))
    jsonl.write_text(f"{good_line}\nBAD JSON LINE\n{good_line}\n")

    records = load_sessions(base_dir=tmp_path)
    assert len(records) == 2


def test_append_session_never_raises(tmp_path):
    """append_session catches OSError silently."""
    # Create a file where directory is expected to force OSError
    blocker = tmp_path / "sessions"
    blocker.write_text("not a directory")

    # Should not raise
    append_session(_make_record(), base_dir=tmp_path)


def test_load_sessions_max_sessions(tmp_path):
    """load_sessions respects max_sessions parameter."""
    for i in range(10):
        append_session(_make_record(session_id=f"sess-{i}"), base_dir=tmp_path)

    records = load_sessions(base_dir=tmp_path, max_sessions=3)
    assert len(records) == 3
    # Should be the last 3
    assert records[0].session_id == "sess-7"
