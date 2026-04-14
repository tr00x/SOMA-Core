"""Tests for Mirror self-learning: track_injection → evaluate_pending → record_outcome."""

from __future__ import annotations

import pytest

from soma.engine import SOMAEngine
from soma.mirror import (
    Mirror, PatternRecord, PendingEval,
    SILENCE_THRESHOLD, EVAL_WINDOW, MIN_ATTEMPTS_FOR_PRUNE,
    EFFECTIVE_THRESHOLD, PRUNE_THRESHOLD,
)
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
    tokens: int = 10,
) -> Action:
    return Action(tool_name=tool, output_text=output, token_count=tokens, error=error)


def _record(engine: SOMAEngine, agent_id: str, action: Action):
    return engine.record_action(agent_id, action)


@pytest.fixture(autouse=True)
def isolate_pattern_db(tmp_path, monkeypatch):
    """Prevent tests from reading/writing the real pattern/pending DB."""
    monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")
    monkeypatch.setattr("soma.mirror.PENDING_DB_PATH", tmp_path / "pending.json")


# ------------------------------------------------------------------
# track_injection
# ------------------------------------------------------------------

class TestTrackInjection:
    """track_injection queues a PendingEval."""

    def test_creates_pending(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "retry_loop", "some context", 0.40)

        assert len(mirror._pending) == 1
        p = mirror._pending[0]
        assert p.agent_id == aid
        assert p.pattern_key == "retry_loop"
        assert p.pressure_at_injection == 0.40
        assert p.actions_since == 0

    def test_multiple_injections_queue(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "retry_loop", "ctx1", 0.40)
        mirror.track_injection(aid, "blind_edit", "ctx2", 0.50)

        assert len(mirror._pending) == 2


# ------------------------------------------------------------------
# evaluate_pending: timing
# ------------------------------------------------------------------

class TestEvaluateTiming:
    """evaluate_pending must wait EVAL_WINDOW actions before evaluating."""

    def test_no_eval_before_window(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "retry_loop", "ctx", 0.40)

        # Call evaluate for fewer than EVAL_WINDOW times
        for _ in range(EVAL_WINDOW - 1):
            mirror.evaluate_pending(aid, 0.20)

        # Should still be pending
        assert len(mirror._pending) == 1
        assert mirror._pending[0].actions_since == EVAL_WINDOW - 1

    def test_eval_fires_at_window(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "retry_loop", "ctx", 0.40)

        # Call evaluate exactly EVAL_WINDOW times
        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid, 0.20)

        # Should have been evaluated and removed from pending
        assert len(mirror._pending) == 0
        # And recorded in pattern_db
        assert "retry_loop" in mirror.pattern_db


# ------------------------------------------------------------------
# evaluate_pending: pressure drop → helped=True
# ------------------------------------------------------------------

class TestPressureDropHelped:
    """Pressure drop ≥ 10% of injection pressure → helped=True."""

    def test_pressure_drops_records_success(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        injection_pressure = 0.50
        # Drop to 0.40 = 20% drop relative to 0.50 → helped
        current_pressure = 0.40

        mirror.track_injection(aid, "retry_loop", "good context", injection_pressure)

        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid, current_pressure)

        record = mirror.pattern_db["retry_loop"]
        assert record.success_count == 1
        assert record.fail_count == 0
        assert record.context_text == "good context"

    def test_large_drop_records_success(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "error_cascade", "ctx", 0.80)

        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid, 0.30)  # 62.5% drop

        record = mirror.pattern_db["error_cascade"]
        assert record.success_count == 1


# ------------------------------------------------------------------
# evaluate_pending: pressure stays/rises → helped=False
# ------------------------------------------------------------------

class TestPressureStaysNotHelped:
    """Pressure doesn't drop enough → helped=False."""

    def test_pressure_rises_records_failure(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "retry_loop", "bad context", 0.50)

        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid, 0.60)  # pressure rose

        record = mirror.pattern_db["retry_loop"]
        assert record.success_count == 0
        assert record.fail_count == 1

    def test_pressure_flat_records_failure(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        mirror.track_injection(aid, "retry_loop", "meh context", 0.50)

        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid, 0.49)  # 2% drop, below 10% threshold

        record = mirror.pattern_db["retry_loop"]
        assert record.fail_count == 1

    def test_tiny_drop_not_enough(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        # 0.50 * 0.10 = 0.05 required drop. 0.50 - 0.46 = 0.04 → not enough
        mirror.track_injection(aid, "retry_loop", "ctx", 0.50)

        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid, 0.46)

        record = mirror.pattern_db["retry_loop"]
        assert record.fail_count == 1


# ------------------------------------------------------------------
# Pattern with high success_rate used from cache
# ------------------------------------------------------------------

class TestEffectivePatternCache:
    """Pattern with success_rate > EFFECTIVE_THRESHOLD is reused."""

    def test_effective_pattern_used_in_generate(self):
        engine = _make_engine()
        aid = _register(engine)

        # Build up pressure
        for _ in range(6):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        mirror.pattern_db["retry_loop"] = PatternRecord(
            context_text="cached: cmd repeated, try different approach",
            success_count=8,
            fail_count=2,  # 80% success rate
        )

        snap = engine.get_snapshot(aid)
        if snap["pressure"] >= SILENCE_THRESHOLD:
            result = mirror.generate(aid, _action(), "")
            assert result is not None
            assert "cached: cmd repeated" in result

    def test_ineffective_pattern_not_used_from_cache(self):
        engine = _make_engine()
        aid = _register(engine)

        for _ in range(6):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        mirror.pattern_db["retry_loop"] = PatternRecord(
            context_text="this never helps",
            success_count=1,
            fail_count=5,  # 17% success rate
        )

        snap = engine.get_snapshot(aid)
        if snap["pressure"] >= SILENCE_THRESHOLD:
            result = mirror.generate(aid, _action(), "")
            assert result is not None
            # Should use detected pattern desc, not the cached ineffective one
            assert "this never helps" not in result


# ------------------------------------------------------------------
# Pattern pruning
# ------------------------------------------------------------------

class TestPatternPruning:
    """Pattern with success_rate < PRUNE_THRESHOLD after MIN_ATTEMPTS is deleted."""

    def test_prune_after_enough_failures(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        # Record MIN_ATTEMPTS_FOR_PRUNE failures
        for _ in range(MIN_ATTEMPTS_FOR_PRUNE):
            mirror.record_outcome(aid, "bad_pattern", "useless", helped=False)

        # Should have been pruned
        assert "bad_pattern" not in mirror.pattern_db

    def test_no_prune_before_min_attempts(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        # Record fewer than MIN_ATTEMPTS failures
        for _ in range(MIN_ATTEMPTS_FOR_PRUNE - 1):
            mirror.record_outcome(aid, "maybe_bad", "ctx", helped=False)

        # Should still exist
        assert "maybe_bad" in mirror.pattern_db

    def test_no_prune_if_some_successes(self):
        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        # 3 successes + 4 failures = 43% success rate > PRUNE_THRESHOLD
        for _ in range(3):
            mirror.record_outcome(aid, "mixed", "ctx", helped=True)
        for _ in range(4):
            mirror.record_outcome(aid, "mixed", "ctx", helped=False)

        assert "mixed" in mirror.pattern_db
        assert mirror.pattern_db["mixed"].success_rate > PRUNE_THRESHOLD


# ------------------------------------------------------------------
# Pattern DB save/load cycle
# ------------------------------------------------------------------

class TestPatternDBPersistence:
    """pattern_db survives save → load cycle with full PatternRecord data."""

    def test_full_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")

        engine = _make_engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        # Build up some history
        mirror.record_outcome(aid, "retry_loop", "ctx1", helped=True)
        mirror.record_outcome(aid, "retry_loop", "ctx1", helped=True)
        mirror.record_outcome(aid, "retry_loop", "ctx1", helped=False)
        mirror.record_outcome(aid, "blind_edit", "ctx2", helped=True)

        # Reload from disk
        mirror2 = Mirror(engine)

        assert "retry_loop" in mirror2.pattern_db
        r = mirror2.pattern_db["retry_loop"]
        assert r.success_count == 2
        assert r.fail_count == 1
        assert r.context_text == "ctx1"

        assert "blind_edit" in mirror2.pattern_db
        assert mirror2.pattern_db["blind_edit"].success_count == 1

    def test_empty_db_loads_clean(self, tmp_path, monkeypatch):
        monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")

        engine = _make_engine()
        mirror = Mirror(engine)
        assert mirror.pattern_db == {}


# ------------------------------------------------------------------
# Isolation: different agent_ids don't interfere
# ------------------------------------------------------------------

class TestAgentIsolation:
    """Pending evals for different agents don't interfere."""

    def test_evaluate_only_affects_own_agent(self):
        engine = _make_engine()
        aid_a = _register(engine, "agent-a")
        aid_b = _register(engine, "agent-b")
        mirror = Mirror(engine)

        mirror.track_injection(aid_a, "retry_loop", "ctx_a", 0.50)
        mirror.track_injection(aid_b, "blind_edit", "ctx_b", 0.60)

        # Evaluate only agent-a for EVAL_WINDOW actions
        for _ in range(EVAL_WINDOW):
            mirror.evaluate_pending(aid_a, 0.20)

        # agent-a's pending should be resolved
        assert all(p.agent_id != aid_a for p in mirror._pending)
        # agent-b's pending should remain
        assert any(p.agent_id == aid_b for p in mirror._pending)


# ------------------------------------------------------------------
# Integration: generate triggers track_injection automatically
# ------------------------------------------------------------------

class TestGenerateTracking:
    """generate() should automatically call track_injection."""

    def test_generate_creates_pending(self):
        engine = _make_engine()
        aid = _register(engine)

        for _ in range(6):
            _record(engine, aid, _action("Bash", "npm test", error=True))

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SILENCE_THRESHOLD:
            result = mirror.generate(aid, _action(), "")
            assert result is not None
            # Should have created a pending evaluation
            assert len(mirror._pending) == 1
            assert mirror._pending[0].agent_id == aid

    def test_generate_none_no_pending(self):
        engine = _make_engine()
        aid = _register(engine)

        # Clean session — no pressure
        for _ in range(3):
            _record(engine, aid, _action("Read", "ok"))

        mirror = Mirror(engine)
        result = mirror.generate(aid, _action(), "")
        assert result is None
        assert len(mirror._pending) == 0
