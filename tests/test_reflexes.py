"""Tests for SOMA reflex engine — pattern-based blocking and injection."""

from __future__ import annotations

from soma.reflexes import (
    BLOCKING_REFLEXES,
    INJECTION_REFLEXES,
    ReflexResult,
    evaluate,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_log(entries: list[tuple[str, bool, str]]) -> list[dict]:
    """Build action_log from (tool, error, file) tuples."""
    return [
        {"tool": tool, "error": error, "file": file, "ts": float(i)}
        for i, (tool, error, file) in enumerate(entries)
    ]


# ── TestReflexResult ─────────────────────────────────────────────────


class TestReflexResult:
    def test_frozen_dataclass(self):
        r = ReflexResult(allow=True)
        try:
            r.allow = False  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_default_values(self):
        r = ReflexResult(allow=True)
        assert r.reflex_kind == ""
        assert r.block_message is None
        assert r.inject_message is None
        assert r.detail == ""


# ── TestBlindEditsReflex ─────────────────────────────────────────────


class TestBlindEditsReflex:
    def test_blocks_edit_without_read(self):
        log = _make_log([
            ("Edit", False, "a.py"),
            ("Edit", False, "b.py"),
            ("Edit", False, "c.py"),
        ])
        result = evaluate("Edit", {"file_path": "d.py"}, log)
        assert result.allow is False
        assert result.reflex_kind == "blind_edits"
        assert "SOMA BLOCKED" in (result.block_message or "")

    def test_allows_after_read(self):
        log = _make_log([
            ("Read", False, "a.py"),
            ("Edit", False, "a.py"),
        ])
        result = evaluate("Edit", {"file_path": "a.py"}, log)
        assert result.allow is True

    def test_toggle_off_skips(self):
        log = _make_log([
            ("Edit", False, "a.py"),
            ("Edit", False, "b.py"),
            ("Edit", False, "c.py"),
        ])
        result = evaluate("Edit", {"file_path": "d.py"}, log, config={"blind_edits": False})
        assert result.allow is True

    def test_allows_non_edit_tool(self):
        log = _make_log([
            ("Edit", False, "a.py"),
            ("Edit", False, "b.py"),
            ("Edit", False, "c.py"),
        ])
        result = evaluate("Bash", {"command": "ls"}, log)
        assert result.allow is True


# ── TestRetryDedup ───────────────────────────────────────────────────


class TestRetryDedup:
    def test_blocks_identical_bash(self):
        result = evaluate(
            "Bash", {"command": "ls -la"},
            action_log=[],
            bash_history=["ls -la"],
        )
        assert result.allow is False
        assert result.reflex_kind == "retry_dedup"

    def test_allows_different_command(self):
        result = evaluate(
            "Bash", {"command": "cat foo.txt"},
            action_log=[],
            bash_history=["ls -la"],
        )
        assert result.allow is True

    def test_whitespace_normalization(self):
        result = evaluate(
            "Bash", {"command": "  ls   -la  "},
            action_log=[],
            bash_history=["ls -la"],
        )
        assert result.allow is False
        assert result.reflex_kind == "retry_dedup"

    def test_allows_non_bash(self):
        result = evaluate(
            "Edit", {"file_path": "a.py"},
            action_log=[],
            bash_history=["ls -la"],
        )
        assert result.allow is True


# ── TestBashFailuresReflex ───────────────────────────────────────────


class TestBashFailuresReflex:
    def test_blocks_after_3_consecutive_errors(self):
        log = _make_log([
            ("Bash", True, ""),
            ("Bash", True, ""),
            ("Bash", True, ""),
        ])
        result = evaluate("Bash", {"command": "make"}, log)
        assert result.allow is False
        assert result.reflex_kind == "bash_failures"

    def test_allows_non_bash_tool(self):
        log = _make_log([
            ("Bash", True, ""),
            ("Bash", True, ""),
            ("Bash", True, ""),
        ])
        result = evaluate("Read", {"file_path": "a.py"}, log)
        assert result.allow is True

    def test_allows_after_success(self):
        log = _make_log([
            ("Bash", True, ""),
            ("Bash", False, ""),
            ("Bash", True, ""),
        ])
        result = evaluate("Bash", {"command": "make"}, log)
        assert result.allow is True


# ── TestThrashingReflex ──────────────────────────────────────────────


class TestThrashingReflex:
    def test_blocks_repeated_edits_same_file(self):
        log = _make_log([
            ("Read", False, "x.py"),
            ("Edit", False, "x.py"),
            ("Edit", False, "x.py"),
            ("Edit", False, "x.py"),
        ])
        result = evaluate("Edit", {"file_path": "x.py"}, log)
        assert result.allow is False
        assert result.reflex_kind == "thrashing"

    def test_allows_different_file(self):
        log = _make_log([
            ("Read", False, "x.py"),
            ("Edit", False, "x.py"),
            ("Edit", False, "x.py"),
            ("Edit", False, "x.py"),
        ])
        result = evaluate("Edit", {"file_path": "y.py"}, log)
        assert result.allow is True


# ── TestErrorRateReflex ──────────────────────────────────────────────


class TestErrorRateReflex:
    def test_inject_only(self):
        # Error rate >= 30% but no consecutive bash failures
        log = _make_log([
            ("Bash", True, ""),
            ("Bash", False, ""),  # break bash_failures streak
            ("Edit", True, "a.py"),
            ("Read", True, "b.py"),
            ("Bash", True, ""),
        ])
        result = evaluate("Read", {"file_path": "c.py"}, log)
        assert result.allow is True
        assert result.inject_message is not None
        assert result.reflex_kind == "error_rate"


# ── TestInjectionOnlyReflexes ────────────────────────────────────────


class TestInjectionOnlyReflexes:
    def test_research_stall(self):
        log = _make_log([
            ("Read", False, "a.py"),
            ("Read", False, "b.py"),
            ("Grep", False, "c.py"),
            ("Read", False, "d.py"),
            ("Read", False, "e.py"),
            ("Read", False, "f.py"),
            ("Glob", False, ""),
            ("Read", False, "g.py"),
        ])
        result = evaluate("Read", {"file_path": "h.py"}, log)
        assert result.allow is True
        assert result.inject_message is not None
        assert result.reflex_kind == "research_stall"

    def test_agent_spam(self):
        log = _make_log([
            ("Agent", False, ""),
            ("Agent", False, ""),
            ("Agent", False, ""),
            ("Bash", False, ""),
        ])
        result = evaluate("Agent", {}, log)
        assert result.allow is True
        assert result.inject_message is not None
        assert result.reflex_kind == "agent_spam"


# ── TestBlockFormat ──────────────────────────────────────────────────


class TestBlockFormat:
    def test_format_matches_d16(self):
        log = _make_log([
            ("Edit", False, "a.py"),
            ("Edit", False, "b.py"),
            ("Edit", False, "c.py"),
        ])
        result = evaluate("Edit", {"file_path": "d.py"}, log, pressure=0.65)
        assert result.allow is False
        msg = result.block_message or ""
        assert "[SOMA BLOCKED]" in msg
        assert "Edit" in msg
        assert "65%" in msg


# ── TestReflexConfig ─────────────────────────────────────────────────


class TestReflexConfig:
    def test_per_reflex_toggle(self):
        log = _make_log([
            ("Edit", False, "a.py"),
            ("Edit", False, "b.py"),
            ("Edit", False, "c.py"),
        ])
        result = evaluate("Edit", {"file_path": "d.py"}, log, config={"blind_edits": False})
        assert result.allow is True

    def test_override_allowed(self):
        log = _make_log([
            ("Bash", True, ""),
            ("Bash", True, ""),
            ("Bash", True, ""),
        ])
        result = evaluate(
            "Bash",
            {"command": "make SOMA override"},
            log,
            config={"override_allowed": True},
        )
        assert result.allow is True

    def test_override_not_allowed_by_default(self):
        log = _make_log([
            ("Bash", True, ""),
            ("Bash", True, ""),
            ("Bash", True, ""),
        ])
        result = evaluate(
            "Bash",
            {"command": "make SOMA override"},
            log,
        )
        assert result.allow is False


# ── TestNoPatterns ───────────────────────────────────────────────────


class TestNoPatterns:
    def test_clean_action_log(self):
        log = _make_log([
            ("Read", False, "a.py"),
            ("Edit", False, "a.py"),
        ])
        result = evaluate("Edit", {"file_path": "a.py"}, log)
        assert result.allow is True
        assert result.reflex_kind == ""
        assert result.block_message is None
        assert result.inject_message is None

    def test_empty_action_log(self):
        result = evaluate("Edit", {"file_path": "a.py"}, [])
        assert result.allow is True
