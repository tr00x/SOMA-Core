"""Tests for structured audit logging (LOG-01)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from soma.audit import AuditLogger
from soma.types import Action
from soma.engine import SOMAEngine


# ── Test 1: AuditLogger.append() writes a JSON line ──

def test_audit_logger_writes_json_line():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "audit.jsonl"
        logger = AuditLogger(path=path)
        logger.append(
            agent_id="a1",
            tool_name="Bash",
            error=False,
            pressure=0.3,
            mode="GUIDE",
        )
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["agent_id"] == "a1"


# ── Test 2: JSON line contains required keys ──

def test_audit_entry_has_required_keys():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "audit.jsonl"
        logger = AuditLogger(path=path)
        logger.append(
            agent_id="a1",
            tool_name="Read",
            error=True,
            pressure=0.5,
            mode="WARN",
        )
        entry = json.loads(path.read_text().strip())
        for key in ("timestamp", "agent_id", "tool_name", "error", "pressure", "mode"):
            assert key in entry, f"Missing key: {key}"
        assert entry["error"] is True
        assert entry["pressure"] == 0.5
        assert entry["mode"] == "WARN"


# ── Test 3: Default path is ~/.soma/audit.jsonl ──

def test_audit_logger_default_path():
    logger = AuditLogger()
    assert logger.path == Path.home() / ".soma" / "audit.jsonl"


# ── Test 4: SOMAEngine creates AuditLogger automatically ──

def test_engine_creates_audit_logger():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "audit.jsonl")
        engine = SOMAEngine(audit_path=path)
        assert engine._audit.enabled is True
        assert engine._audit.path == Path(path)


# ── Test 5: Audit entries are valid JSON ──

def test_audit_entries_are_valid_json():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "audit.jsonl"
        logger = AuditLogger(path=path)
        for i in range(5):
            logger.append(
                agent_id=f"a{i}",
                tool_name="Bash",
                error=False,
                pressure=i * 0.1,
                mode="OBSERVE",
            )
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 5
        for line in lines:
            entry = json.loads(line)  # must not raise
            assert "timestamp" in entry


# ── Test 6: File rotation when exceeding max_bytes ──

def test_audit_rotation():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "audit.jsonl"
        # Small max to trigger rotation easily
        logger = AuditLogger(path=path, max_bytes=100)
        for i in range(20):
            logger.append(
                agent_id="a1",
                tool_name="Bash",
                error=False,
                pressure=0.1,
                mode="OBSERVE",
            )
        # After rotation, there should be at least one rotated file
        rotated = [f for f in Path(td).iterdir() if f.name != "audit.jsonl"]
        assert len(rotated) >= 1


# ── Test 7: record_action() appends audit entry ──

def test_record_action_appends_audit():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "audit.jsonl")
        engine = SOMAEngine(
            budget={"tokens": 100_000},
            audit_path=path,
        )
        engine.register_agent("a1")
        action = Action(tool_name="Bash", output_text="hello", token_count=100)
        engine.record_action("a1", action)

        lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["agent_id"] == "a1"
        assert entry["tool_name"] == "Bash"
        assert entry["error"] is False
        assert "pressure" in entry
        assert "mode" in entry


# ── Test 8: AuditLogger can be disabled ──

def test_audit_disabled():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "audit.jsonl"
        logger = AuditLogger(path=path, enabled=False)
        logger.append(
            agent_id="a1",
            tool_name="Bash",
            error=False,
            pressure=0.0,
            mode="OBSERVE",
        )
        assert not path.exists()


def test_engine_audit_disabled():
    engine = SOMAEngine(audit_enabled=False)
    assert engine._audit.enabled is False
