"""Tests for soma.subagent_monitor — subagent log reading and aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.subagent_monitor import (
    watch,
    aggregate,
    get_cascade_risk,
    get_subagent_summary,
    SUBAGENTS_DIR,
)


@pytest.fixture
def sub_dir(tmp_path, monkeypatch):
    """Redirect SUBAGENTS_DIR to tmp_path for isolation."""
    monkeypatch.setattr("soma.subagent_monitor.SUBAGENTS_DIR", tmp_path)
    return tmp_path


def _write_log(sub_dir: Path, parent_id: str, sub_id: str, entries: list[dict]) -> Path:
    """Write a JSONL log file for a subagent."""
    log_dir = sub_dir / parent_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{sub_id}.jsonl"
    lines = [json.dumps(e) for e in entries]
    log_file.write_text("\n".join(lines))
    return log_file


class TestWatch:
    def test_no_logs_returns_empty(self, sub_dir):
        assert watch("nonexistent") == {}

    def test_reads_single_subagent(self, sub_dir):
        entries = [
            {"action": 1, "tool": "Read", "error": False, "tokens": 100},
            {"action": 2, "tool": "Write", "error": False, "tokens": 200},
        ]
        _write_log(sub_dir, "parent-1", "sub-abc", entries)
        result = watch("parent-1")
        assert "sub-abc" in result
        assert len(result["sub-abc"]) == 2
        assert result["sub-abc"][0]["tool"] == "Read"

    def test_reads_multiple_subagents(self, sub_dir):
        _write_log(sub_dir, "p1", "s1", [{"action": 1, "tool": "Read", "error": False}])
        _write_log(sub_dir, "p1", "s2", [{"action": 1, "tool": "Bash", "error": True}])
        result = watch("p1")
        assert len(result) == 2
        assert "s1" in result
        assert "s2" in result

    def test_ignores_malformed_lines(self, sub_dir):
        log_dir = sub_dir / "p1"
        log_dir.mkdir(parents=True)
        (log_dir / "bad.jsonl").write_text('{"action": 1}\nnot json\n{"action": 2}\n')
        # Malformed file is skipped entirely (JSONDecodeError)
        result = watch("p1")
        # The whole file is skipped on error
        assert "bad" not in result or len(result.get("bad", [])) == 0


class TestAggregate:
    def test_empty_returns_empty(self, sub_dir):
        assert aggregate("nope") == {}

    def test_computes_vitals(self, sub_dir):
        entries = [
            {"action": 1, "tool": "Read", "error": False, "tokens": 100},
            {"action": 2, "tool": "Write", "error": False, "tokens": 200},
            {"action": 3, "tool": "Bash", "error": True, "tokens": 50},
            {"action": 4, "tool": "Read", "error": False, "tokens": 80},
        ]
        _write_log(sub_dir, "p1", "sub1", entries)
        result = aggregate("p1")
        v = result["sub1"]
        assert v["action_count"] == 4
        assert v["error_count"] == 1
        assert v["error_rate"] == pytest.approx(0.25)
        assert v["total_tokens"] == 430
        assert v["tools_used"]["Read"] == 2
        assert v["tools_used"]["Bash"] == 1

    def test_multiple_subagents(self, sub_dir):
        _write_log(sub_dir, "p1", "good", [
            {"action": 1, "tool": "Read", "error": False, "tokens": 100},
        ])
        _write_log(sub_dir, "p1", "bad", [
            {"action": 1, "tool": "Bash", "error": True, "tokens": 50},
            {"action": 2, "tool": "Bash", "error": True, "tokens": 50},
        ])
        result = aggregate("p1")
        assert result["good"]["error_rate"] == 0.0
        assert result["bad"]["error_rate"] == 1.0


class TestCascadeRisk:
    def test_no_subagents_returns_zero(self, sub_dir):
        assert get_cascade_risk("empty") == 0.0

    def test_healthy_subagents_returns_zero(self, sub_dir):
        _write_log(sub_dir, "p1", "s1", [
            {"action": 1, "tool": "Read", "error": False},
            {"action": 2, "tool": "Write", "error": False},
        ])
        assert get_cascade_risk("p1") == 0.0

    def test_failing_subagent_returns_risk(self, sub_dir):
        # 3 out of 4 actions are errors → error_rate=0.75, above 0.3
        _write_log(sub_dir, "p1", "s1", [
            {"action": 1, "tool": "Bash", "error": True},
            {"action": 2, "tool": "Bash", "error": True},
            {"action": 3, "tool": "Bash", "error": True},
            {"action": 4, "tool": "Read", "error": False},
        ])
        risk = get_cascade_risk("p1")
        assert risk > 0
        # (0.75 - 0.3) / (1.0 - 0.3) ≈ 0.643
        assert risk == pytest.approx(0.6428, abs=0.01)

    def test_custom_threshold(self, sub_dir):
        _write_log(sub_dir, "p1", "s1", [
            {"action": 1, "tool": "Bash", "error": True},
            {"action": 2, "tool": "Read", "error": False},
        ])
        # error_rate=0.5, default threshold=0.3 → risk > 0
        assert get_cascade_risk("p1", threshold=0.3) > 0
        # error_rate=0.5, threshold=0.6 → no risk
        assert get_cascade_risk("p1", threshold=0.6) == 0.0

    def test_worst_subagent_determines_risk(self, sub_dir):
        _write_log(sub_dir, "p1", "good", [
            {"action": 1, "tool": "Read", "error": False},
        ])
        _write_log(sub_dir, "p1", "bad", [
            {"action": 1, "tool": "Bash", "error": True},
        ])
        # bad has error_rate=1.0 → risk = (1.0 - 0.3) / 0.7 = 1.0
        assert get_cascade_risk("p1") == 1.0


class TestSubagentSummary:
    def test_empty(self, sub_dir):
        assert get_subagent_summary("nope") == {}

    def test_summary_format(self, sub_dir):
        _write_log(sub_dir, "p1", "s1", [
            {"action": 1, "tool": "Read", "error": False, "tokens": 100},
            {"action": 2, "tool": "Read", "error": False, "tokens": 200},
            {"action": 3, "tool": "Bash", "error": True, "tokens": 50},
        ])
        s = get_subagent_summary("p1")["s1"]
        assert s["actions"] == 3
        assert s["errors"] == 1
        assert s["error_rate"] == 0.33
        assert s["top_tool"] == "Read"


class TestInjection:
    """Test the injection function from pre_tool_use."""

    def test_inject_prepends_awareness(self):
        from soma.hooks.pre_tool_use import _inject_subagent_awareness

        tool_input = {"prompt": "Do the thing."}
        _inject_subagent_awareness(tool_input, "parent-123", {})

        assert tool_input["prompt"].startswith("\n[SOMA Subagent Monitor Active]")
        assert "Do the thing." in tool_input["prompt"]
        assert "parent-123" in tool_input["prompt"]
        assert ".jsonl" in tool_input["prompt"]

    def test_inject_empty_prompt_noop(self):
        from soma.hooks.pre_tool_use import _inject_subagent_awareness

        tool_input = {"prompt": ""}
        _inject_subagent_awareness(tool_input, "parent", {})
        assert tool_input["prompt"] == ""

    def test_inject_preserves_original_task(self):
        from soma.hooks.pre_tool_use import _inject_subagent_awareness

        original = "Refactor the database models and run all tests."
        tool_input = {"prompt": original}
        _inject_subagent_awareness(tool_input, "p1", {})

        # Original task must appear AFTER the awareness block
        assert tool_input["prompt"].endswith(original)
        # Awareness block must NOT contain task-changing instructions
        awareness_part = tool_input["prompt"].replace(original, "")
        assert "refactor" not in awareness_part.lower()
        assert "database" not in awareness_part.lower()
