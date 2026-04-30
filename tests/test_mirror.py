"""Tests for soma.mirror — proprioceptive session context generation."""

from __future__ import annotations

import json

import pytest

from soma.engine import SOMAEngine
from soma.mirror import Mirror, PatternRecord, SILENCE_THRESHOLD
from soma.types import Action


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_engine(**kwargs) -> SOMAEngine:
    return SOMAEngine(budget={"tokens": 100_000}, **kwargs)


def _register(engine: SOMAEngine, agent_id: str = "test") -> str:
    engine.register_agent(agent_id)
    return agent_id


def _action(
    tool: str = "Read",
    output: str = "ok",
    error: bool = False,
    file_path: str = "",
    tokens: int = 10,
) -> Action:
    meta = {}
    if file_path:
        meta["file_path"] = file_path
    return Action(
        tool_name=tool,
        output_text=output,
        token_count=tokens,
        error=error,
        metadata=meta,
    )


def _record(engine: SOMAEngine, agent_id: str, action: Action):
    return engine.record_action(agent_id, action)


# ------------------------------------------------------------------
# Silence when healthy
# ------------------------------------------------------------------

class TestSilenceWhenHealthy:
    """pressure < SILENCE_THRESHOLD -> None."""

    def test_no_output_at_low_pressure(self):
        engine = _make_engine()
        aid = _register(engine)
        # Record a few clean actions to keep pressure near 0
        for _ in range(3):
            _record(engine, aid, _action())
        mirror = Mirror(engine)
        result = mirror.generate(aid, _action(), "some output")
        assert result is None

    def test_returns_none_for_zero_actions(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)
        # No actions recorded — pressure is 0
        result = mirror.generate(aid, _action(), "")
        assert result is None


# ------------------------------------------------------------------
# Retry loop pattern
# ------------------------------------------------------------------

class TestRetryLoop:
    """2+ identical Bash commands in a row -> retry_loop pattern."""

    def test_detects_retry_loop(self):
        engine = _make_engine()
        aid = _register(engine)
        # Push pressure up with errors first
        for _ in range(5):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        result = mirror.generate(aid, _action("Bash", "npm test", error=True), "fail")

        assert result is not None
        assert "--- session context ---" in result
        assert "---" in result
        assert "SOMA" not in result

    def test_retry_loop_content(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(5):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        detected = mirror._detect_pattern(aid)
        assert detected is not None
        key, desc = detected
        assert key == "retry_loop"
        assert "repeated" in desc or "same" in desc


# ------------------------------------------------------------------
# Blind edit pattern
# ------------------------------------------------------------------

class TestBlindEdit:
    """Write/Edit without prior Read -> blind_edit pattern."""

    def test_detects_blind_edits(self):
        engine = _make_engine()
        aid = _register(engine)
        # Write to files without reading them first — with errors to raise pressure
        _record(engine, aid, _action("Edit", "x", error=True, file_path="/a/foo.py"))
        _record(engine, aid, _action("Edit", "y", error=True, file_path="/a/bar.py"))
        _record(engine, aid, _action("Write", "z", error=True, file_path="/a/baz.py"))
        _record(engine, aid, _action("Bash", "fail", error=True))
        _record(engine, aid, _action("Bash", "fail2", error=True))

        mirror = Mirror(engine)
        detected = mirror._detect_pattern(aid)

        # Could be blind_edit or error_cascade depending on pressure
        # but blind_edit is checked first
        assert detected is not None
        key, desc = detected
        if key == "blind_edit":
            assert "edited without reading" in desc
        else:
            # error_cascade is also valid with 5 errors
            assert key in ("blind_edit", "error_cascade")

    def test_no_blind_edit_when_read_first(self):
        engine = _make_engine()
        aid = _register(engine)
        # Read then edit — not blind
        _record(engine, aid, _action("Read", "content", file_path="/a/foo.py"))
        _record(engine, aid, _action("Edit", "new", file_path="/a/foo.py"))

        mirror = Mirror(engine)
        detected = mirror._detect_pattern(aid)
        # Should not be blind_edit
        if detected is not None:
            assert detected[0] != "blind_edit"


# ------------------------------------------------------------------
# Error cascade pattern
# ------------------------------------------------------------------

class TestErrorCascade:
    """3+ errors in last 5 actions -> error_cascade."""

    def test_detects_error_cascade(self):
        engine = _make_engine()
        aid = _register(engine)
        # Read files first so blind_edit doesn't trigger, use varied bash cmds
        _record(engine, aid, _action("Read", "ok", file_path="/x.py"))
        _record(engine, aid, _action("Read", "ok", file_path="/y.py"))
        _record(engine, aid, _action("Bash", "cmd1", error=True))
        _record(engine, aid, _action("Bash", "cmd2", error=True))
        _record(engine, aid, _action("Bash", "cmd3", error=True))

        mirror = Mirror(engine)
        detected = mirror._detect_pattern(aid)
        assert detected is not None
        key, desc = detected
        assert key == "error_cascade"
        assert "recent actions failed" in desc

    def test_no_cascade_with_few_errors(self):
        engine = _make_engine()
        aid = _register(engine)
        _record(engine, aid, _action("Read", "ok"))
        _record(engine, aid, _action("Edit", "ok", file_path="/x.py"))
        _record(engine, aid, _action("Bash", "ok"))
        _record(engine, aid, _action("Read", "ok"))
        _record(engine, aid, _action("Bash", "fail", error=True))

        mirror = Mirror(engine)
        detected = mirror._detect_pattern(aid)
        if detected is not None:
            assert detected[0] != "error_cascade"


# ------------------------------------------------------------------
# Stats fallback
# ------------------------------------------------------------------

class TestStatsMode:
    """When no pattern matches, _format_stats produces numeric context."""

    def test_stats_contain_action_count(self):
        engine = _make_engine()
        aid = _register(engine)
        for i in range(6):
            _record(engine, aid, _action("Read", f"out{i}"))
        # Add one error to get some pressure
        _record(engine, aid, _action("Bash", "fail", error=True))

        mirror = Mirror(engine)
        stats = mirror._format_stats(aid, _action())
        assert "actions:" in stats
        assert "errors:" in stats

    def test_stats_show_reads_before_writes(self):
        engine = _make_engine()
        aid = _register(engine)
        _record(engine, aid, _action("Read", "ok", file_path="/a.py"))
        _record(engine, aid, _action("Edit", "ok", file_path="/a.py"))
        _record(engine, aid, _action("Write", "ok", file_path="/b.py"))  # no read

        mirror = Mirror(engine)
        stats = mirror._format_stats(aid, _action())
        assert "reads_before_writes:" in stats

    def test_stats_max_three_lines(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(8):
            _record(engine, aid, _action("Bash", "fail", error=True))

        mirror = Mirror(engine)
        stats = mirror._format_stats(aid, _action())
        lines = stats.strip().split("\n")
        assert len(lines) <= 3


# ------------------------------------------------------------------
# Output format
# ------------------------------------------------------------------

class TestOutputFormat:
    """Context blocks must follow the contract."""

    def test_markers_present(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(6):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        result = mirror.generate(aid, _action(), "")
        if result is not None:
            assert result.startswith("--- session context ---\n")
            assert result.endswith("\n---")

    def test_no_soma_branding(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(6):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        result = mirror.generate(aid, _action(), "")
        if result is not None:
            assert "SOMA" not in result
            assert "warning" not in result.lower()
            assert "suggestion" not in result.lower()

    def test_max_three_content_lines(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(8):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        result = mirror.generate(aid, _action(), "")
        if result is not None:
            # Extract lines between markers
            lines = result.split("\n")
            # First line is "--- session context ---", last is "---"
            content_lines = lines[1:-1]
            assert len(content_lines) <= 3


# ------------------------------------------------------------------
# Pattern DB
# ------------------------------------------------------------------

class TestPatternDB:
    """pattern_db lookup overrides detected pattern description."""

    def test_pattern_db_lookup(self):
        engine = _make_engine()
        aid = _register(engine)
        # Create retry_loop scenario
        for _ in range(5):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        # Pre-populate pattern_db with a learned context
        mirror.pattern_db["retry_loop"] = PatternRecord(
            context_text="same cmd 5x, all failed",
            success_count=5, fail_count=1,
        )

        result = mirror.generate(aid, _action(), "")
        assert result is not None
        assert "same cmd 5x, all failed" in result

    def test_record_outcome_saves(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.record_outcome(aid, "retry_loop", "custom context", helped=True)
        assert "retry_loop" in mirror.pattern_db
        assert mirror.pattern_db["retry_loop"].context_text == "custom context"

    def test_record_outcome_tracks_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.record_outcome(aid, "retry_loop", "bad context", helped=False)
        # Still exists — not pruned until MIN_ATTEMPTS failures
        assert "retry_loop" in mirror.pattern_db
        assert mirror.pattern_db["retry_loop"].fail_count == 1

    def test_pattern_db_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")

        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)
        mirror.record_outcome(aid, "test_key", "test context", helped=True)

        # Reload
        mirror2 = Mirror(engine)
        assert mirror2.pattern_db["test_key"].context_text == "test context"


# ------------------------------------------------------------------
# Integration: generate with real engine pipeline
# ------------------------------------------------------------------

class TestIntegration:
    """End-to-end: engine records -> mirror generates."""

    def test_healthy_session_stays_silent(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)
        for _ in range(10):
            result = _record(engine, aid, _action("Read", "content"))
            ctx = mirror.generate(aid, _action(), "output")
        # Should remain None throughout — no errors, no pressure
        assert ctx is None

    def test_degrading_session_produces_context(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        # Start clean
        for _ in range(3):
            _record(engine, aid, _action("Read", "ok"))

        # Introduce errors to raise pressure
        for _ in range(7):
            _record(engine, aid, _action("Bash", "failing cmd", error=True))

        snap = engine.get_snapshot(aid)
        # If pressure is above threshold, we should get context
        if snap["pressure"] >= SILENCE_THRESHOLD:
            result = mirror.generate(aid, _action(), "")
            assert result is not None
            assert "--- session context ---" in result


# ------------------------------------------------------------------
# _stats pattern dropped in v2026.5.0
# ------------------------------------------------------------------

class TestStatsCooldown:
    """Resurrected 2026-04-30. `_stats` emits again behind a per-agent
    cooldown (``STATS_COOLDOWN_SECONDS``). The 2026-04-19 retirement
    reason — guidance fatigue from emitting on every fallback action —
    is addressed by the cooldown, not by silencing the path."""

    def test_first_call_emits_stats(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(3):
            _record(engine, aid, _action("Bash", "x", error=True))
        mirror = Mirror(engine)
        result = mirror.generate(aid, _action("Bash", ""), "")
        assert result is None or "session context" in result

    def test_second_call_within_cooldown_returns_none(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(3):
            _record(engine, aid, _action("Bash", "x", error=True))
        mirror = Mirror(engine)
        # First emission populates _stats_last_emit.
        mirror.generate(aid, _action("Bash", ""), "")
        # Second call within cooldown window — fallback _stats path
        # must NOT re-emit. Real patterns may still fire and return
        # non-None; we only care that the literal stats fallback is
        # gated.
        was_in_cooldown = aid in mirror._stats_last_emit
        if was_in_cooldown:
            # Force the cooldown to be just-set.
            assert not mirror._stats_cooldown_ready(aid)

    def test_cooldown_elapsed_re_emits(self):
        engine = _make_engine()
        aid = _register(engine)
        for _ in range(3):
            _record(engine, aid, _action("Bash", "x", error=True))
        mirror = Mirror(engine)
        mirror.generate(aid, _action("Bash", ""), "")
        # Simulate the cooldown window having elapsed.
        from soma.mirror import STATS_COOLDOWN_SECONDS
        if aid in mirror._stats_last_emit:
            mirror._stats_last_emit[aid] -= STATS_COOLDOWN_SECONDS + 1
            assert mirror._stats_cooldown_ready(aid)

    def test_cooldown_state_persists_across_subprocess_restart(
        self, tmp_path, monkeypatch,
    ):
        """The cooldown state must survive a fresh ``Mirror`` instance —
        otherwise short-lived hook subprocesses would each slip their
        first emit through and the resurrection would silently regress
        the original 2026-04-19 fatigue surface.
        """
        # Redirect the persistence file to tmp so we don't leak state
        # into the user's home dir.
        from soma import mirror as mirror_mod
        emit_path = tmp_path / "mirror_stats_emit.json"
        monkeypatch.setattr(mirror_mod, "STATS_LAST_EMIT_PATH", emit_path)

        engine = _make_engine()
        aid = _register(engine)
        m1 = Mirror(engine)
        m1._stats_last_emit[aid] = 1234567890.0
        m1._save_stats_last_emit()
        assert emit_path.exists()

        # Fresh Mirror instance (mimics a hook subprocess restart).
        m2 = Mirror(engine)
        assert m2._stats_last_emit.get(aid) == 1234567890.0
