"""Integration tests for the reflex system — NO MOCKS.

Tests the full pipeline: real engine → real reflexes → real decisions.
"""

from __future__ import annotations

import soma
from soma.reflexes import evaluate, ReflexResult
from soma.signal_reflexes import (
    evaluate_predictor_checkpoint,
    evaluate_drift_guardian,
    evaluate_handoff,
    evaluate_rca_injection,
    evaluate_commit_gate,
)
from soma.graph_reflexes import CircuitBreakerState, update_circuit_state, evaluate_circuit_breaker
from soma.advanced_signal_reflexes import (
    evaluate_smart_throttle,
    evaluate_fingerprint_anomaly,
    evaluate_context_overflow,
)
from soma.types import Action, ResponseMode


# ------------------------------------------------------------------
# Pattern reflexes — real action logs, real evaluate()
# ------------------------------------------------------------------


class TestBlindEditsReflex:
    def test_blocks_after_3_blind_edits(self):
        action_log = [
            {"tool": "Edit", "error": False, "file": "src/main.py", "ts": i}
            for i in range(3)
        ]
        result = evaluate(
            tool_name="Edit",
            tool_input={"file_path": "src/main.py"},
            action_log=action_log,
            pressure=0.3,
            config={},
        )
        assert not result.allow
        assert "blind_edits" in result.reflex_kind

    def test_allows_after_read(self):
        action_log = [
            {"tool": "Read", "error": False, "file": "src/main.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "src/main.py", "ts": 2},
        ]
        result = evaluate(
            tool_name="Edit",
            tool_input={"file_path": "src/main.py"},
            action_log=action_log,
            pressure=0.3,
            config={},
        )
        assert result.allow

    def test_does_not_block_read(self):
        action_log = [
            {"tool": "Edit", "error": False, "file": "src/main.py", "ts": i}
            for i in range(3)
        ]
        result = evaluate(
            tool_name="Read", tool_input={}, action_log=action_log,
            pressure=0.3, config={},
        )
        assert result.allow


class TestRetryDedupReflex:
    def test_blocks_duplicate_command(self):
        result = evaluate(
            tool_name="Bash",
            tool_input={"command": "npm test"},
            action_log=[{"tool": "Bash", "error": True, "file": "", "ts": 1}],
            pressure=0.1,
            config={},
            bash_history=["npm test", "npm test"],
        )
        assert not result.allow
        assert "retry_dedup" in result.reflex_kind

    def test_allows_different_command(self):
        result = evaluate(
            tool_name="Bash",
            tool_input={"command": "npm run build"},
            action_log=[{"tool": "Bash", "error": True, "file": "", "ts": 1}],
            pressure=0.1,
            config={},
            bash_history=["npm test"],
        )
        assert result.allow


class TestBashFailuresReflex:
    def test_blocks_after_3_consecutive(self):
        action_log = [
            {"tool": "Bash", "error": True, "file": "", "ts": i}
            for i in range(3)
        ]
        result = evaluate(
            tool_name="Bash",
            tool_input={"command": "make build"},
            action_log=action_log,
            pressure=0.3,
            config={},
        )
        assert not result.allow
        assert "bash_failures" in result.reflex_kind

    def test_allows_after_success(self):
        action_log = [
            {"tool": "Bash", "error": True, "file": "", "ts": 1},
            {"tool": "Bash", "error": False, "file": "", "ts": 2},
            {"tool": "Bash", "error": True, "file": "", "ts": 3},
        ]
        result = evaluate(
            tool_name="Bash",
            tool_input={"command": "make build"},
            action_log=action_log,
            pressure=0.3,
            config={},
        )
        assert result.allow


class TestThrashingReflex:
    def test_blocks_thrashed_file(self):
        # Reads mixed in so blind_edits doesn't fire — thrashing should
        action_log = [
            {"tool": "Read", "error": False, "file": "src/app.py", "ts": 0},
            {"tool": "Edit", "error": False, "file": "src/app.py", "ts": 1},
            {"tool": "Read", "error": False, "file": "src/app.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "src/app.py", "ts": 3},
            {"tool": "Read", "error": False, "file": "src/app.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "src/app.py", "ts": 5},
        ]
        result = evaluate(
            tool_name="Edit",
            tool_input={"file_path": "src/app.py"},
            action_log=action_log,
            pressure=0.2,
            config={},
        )
        assert not result.allow
        assert "thrashing" in result.reflex_kind or "blind_edits" in result.reflex_kind


# ------------------------------------------------------------------
# Signal reflexes — real functions, correct signatures
# ------------------------------------------------------------------


class TestDriftGuardian:
    def test_triggers_on_high_drift(self):
        result = evaluate_drift_guardian(drift=0.5, original_task="Implement auth module")
        assert result is not None
        assert result.inject_message is not None

    def test_no_trigger_on_low_drift(self):
        result = evaluate_drift_guardian(drift=0.1, original_task="anything")
        assert result is None or result.inject_message is None


class TestCommitGate:
    def test_blocks_on_grade_f(self):
        result = evaluate_commit_gate(
            grade="F",
            tool_name="Bash",
            tool_input={"command": "git commit -m 'test'"},
        )
        assert result is not None
        assert not result.allow

    def test_allows_grade_a(self):
        result = evaluate_commit_gate(
            grade="A",
            tool_name="Bash",
            tool_input={"command": "git commit -m 'test'"},
        )
        assert result is None or result.allow

    def test_ignores_non_commit(self):
        result = evaluate_commit_gate(
            grade="F",
            tool_name="Bash",
            tool_input={"command": "ls -la"},
        )
        assert result is None or result.allow


class TestHandoff:
    def test_triggers_on_low_success(self):
        result = evaluate_handoff(success_rate=0.3, handoff_text="summary here")
        assert result is not None
        assert result.inject_message is not None

    def test_no_trigger_on_healthy(self):
        result = evaluate_handoff(success_rate=0.8)
        assert result is None or result.inject_message is None


# ------------------------------------------------------------------
# Advanced reflexes
# ------------------------------------------------------------------


class TestCircuitBreaker:
    def test_opens_after_5_blocks(self):
        state = CircuitBreakerState(agent_id="test")
        for _ in range(5):
            state = update_circuit_state(state, mode=ResponseMode.BLOCK)
        assert state.is_open
        result = evaluate_circuit_breaker(state)
        assert result.inject_message is not None
        assert "quarantine" in result.inject_message.lower()

    def test_stays_closed_at_4(self):
        state = CircuitBreakerState(agent_id="test")
        for _ in range(4):
            state = update_circuit_state(state, mode=ResponseMode.BLOCK)
        assert not state.is_open

    def test_recovers_after_10_observes(self):
        state = CircuitBreakerState(agent_id="test")
        for _ in range(5):
            state = update_circuit_state(state, mode=ResponseMode.BLOCK)
        assert state.is_open
        for _ in range(10):
            state = update_circuit_state(state, mode=ResponseMode.OBSERVE)
        assert not state.is_open


class TestSmartThrottle:
    def test_no_throttle_at_observe(self):
        result = evaluate_smart_throttle(mode=ResponseMode.OBSERVE, pressure=0.1)
        assert result.inject_message is None

    def test_throttle_at_warn(self):
        result = evaluate_smart_throttle(mode=ResponseMode.WARN, pressure=0.55)
        assert result.inject_message is not None


class TestContextOverflow:
    def test_warns_at_85(self):
        result = evaluate_context_overflow(context_usage=0.85)
        assert result is not None
        assert result.inject_message is not None

    def test_critical_at_96(self):
        result = evaluate_context_overflow(context_usage=0.96)
        assert result is not None

    def test_no_warning_at_70(self):
        result = evaluate_context_overflow(context_usage=0.70)
        assert result is None or result.inject_message is None


# ------------------------------------------------------------------
# Full pipeline — real engine + real reflexes
# ------------------------------------------------------------------


class TestFullPipeline:
    def test_engine_feeds_reflex_blocks_bash_failures(self):
        """Real engine → real actions → reflex blocks on error pattern."""
        engine = soma.quickstart()
        engine.register_agent("test")

        action_log = []
        for i in range(5):
            engine.record_action("test", Action(
                tool_name="Bash",
                output_text="Error: command not found",
                token_count=100,
                error=True,
            ))
            action_log.append({"tool": "Bash", "error": True, "file": "", "ts": i})

        snap = engine.get_snapshot("test")
        result = evaluate(
            tool_name="Bash",
            tool_input={"command": "same-command"},
            action_log=action_log,
            pressure=snap.get("pressure", 0),
            config={},
        )
        assert not result.allow

    def test_healthy_session_zero_blocks(self):
        """Healthy session — no reflex should fire."""
        engine = soma.quickstart()
        engine.register_agent("test")

        action_log = []
        tools = ["Read", "Glob", "Read", "Edit", "Read", "Edit", "Bash", "Read"]
        for i, tool in enumerate(tools):
            engine.record_action("test", Action(
                tool_name=tool, output_text="ok", token_count=80, error=False,
            ))
            action_log.append({"tool": tool, "error": False, "file": f"src/f{i}.py", "ts": i})

        for tool in ["Edit", "Bash", "Read"]:
            result = evaluate(
                tool_name=tool, tool_input={},
                action_log=action_log, pressure=0.0, config={},
            )
            assert result.allow, f"{tool} blocked on healthy session"

    def test_benchmark_retry_storm_with_reflexes(self):
        """Real benchmark: retry_storm with reflex mode must reduce errors."""
        from soma.benchmark.harness import run_scenario
        from soma.benchmark.scenarios import retry_storm

        actions = retry_storm(seed=42)
        baseline = run_scenario(actions, soma_enabled=False)
        reflex = run_scenario(actions, soma_enabled=True, reflex_mode=True)

        assert reflex.error_rate < baseline.error_rate
        reflex_blocks = sum(1 for a in reflex.per_action if a.get("reflex_blocked"))
        assert reflex_blocks > 0

    def test_benchmark_healthy_zero_reflex_blocks(self):
        """Real benchmark: healthy_session must have 0 reflex blocks."""
        from soma.benchmark.harness import run_scenario
        from soma.benchmark.scenarios import healthy_session

        result = run_scenario(healthy_session(seed=42), soma_enabled=True, reflex_mode=True)
        reflex_blocks = sum(1 for a in result.per_action if a.get("reflex_blocked"))
        assert reflex_blocks == 0
