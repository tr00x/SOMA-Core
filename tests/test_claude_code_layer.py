"""Tests for the Claude Code integration layer.

Covers: hooks (pre/post/stop), statusline, dispatcher, common utilities,
Claude Code config, persistence of custom weights/thresholds, and
the setup-claude command.
"""

import json
import os
import sys
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from soma.engine import SOMAEngine
from soma.types import Action, Level
from soma.persistence import save_engine_state, load_engine_state
from soma.hooks.common import (
    get_engine, save_state, read_stdin,
    CLAUDE_TOOLS, SOMA_DIR,
)
from soma.cli.config_loader import CLAUDE_CODE_CONFIG, DEFAULT_CONFIG


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def soma_dir(tmp_path, monkeypatch):
    """Redirect ~/.soma to a temp directory and fix agent ID for tests."""
    fake_soma = tmp_path / ".soma"
    fake_soma.mkdir()
    monkeypatch.setattr("soma.hooks.common.SOMA_DIR", fake_soma)
    monkeypatch.setattr("soma.hooks.common.ENGINE_STATE_PATH", fake_soma / "engine_state.json")
    monkeypatch.setattr("soma.hooks.common.STATE_PATH", fake_soma / "state.json")
    # Pin agent ID to "claude-code" in tests so all existing tests work
    monkeypatch.setattr("soma.hooks.common._get_session_agent_id", lambda: "claude-code")
    return fake_soma


@pytest.fixture
def engine_with_actions(tmp_path):
    """Engine with Claude Code config and 20 recorded actions."""
    engine = SOMAEngine(
        budget=CLAUDE_CODE_CONFIG["budget"],
        custom_weights=CLAUDE_CODE_CONFIG["weights"],
        custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
    )
    engine.register_agent("claude-code", tools=CLAUDE_TOOLS)
    for i in range(20):
        engine.record_action("claude-code", Action(
            tool_name=["Bash", "Read", "Edit", "Write", "Grep"][i % 5],
            output_text=f"output {i}" * 10,
            token_count=100 + i * 10,
            duration_sec=0.1 + i * 0.05,
        ))
    path = tmp_path / "engine_state.json"
    save_engine_state(engine, str(path))
    return engine, path


def _make_action(tool="Bash", error=False):
    return Action(
        tool_name=tool,
        output_text="output " * 20,
        token_count=200,
        duration_sec=0.5,
        error=error,
    )


# ──────────────────────────────────────────────────────────────────
# CLAUDE_CODE_CONFIG
# ──────────────────────────────────────────────────────────────────

class TestClaudeCodeConfig:
    """Verify the Claude Code config is properly defined and differs from default."""

    def test_config_has_all_sections(self):
        for key in ["soma", "budget", "agents", "thresholds", "weights", "graph"]:
            assert key in CLAUDE_CODE_CONFIG, f"Missing section: {key}"

    def test_budget_is_larger_than_default(self):
        assert CLAUDE_CODE_CONFIG["budget"]["tokens"] > DEFAULT_CONFIG["budget"]["tokens"]
        assert CLAUDE_CODE_CONFIG["budget"]["cost_usd"] > DEFAULT_CONFIG["budget"]["cost_usd"]

    def test_thresholds_are_higher_than_default(self):
        """Claude Code needs higher thresholds to avoid false alarms."""
        for key in ["caution", "degrade", "quarantine", "restart"]:
            assert CLAUDE_CODE_CONFIG["thresholds"][key] > DEFAULT_CONFIG["thresholds"][key], \
                f"Threshold {key} should be higher for Claude Code"

    def test_uncertainty_weight_is_lower(self):
        """Tool diversity is normal for Claude Code — lower uncertainty weight."""
        assert CLAUDE_CODE_CONFIG["weights"]["uncertainty"] < DEFAULT_CONFIG["weights"]["uncertainty"]

    def test_error_weight_is_higher(self):
        """Errors matter more in Claude Code — higher error_rate weight."""
        assert CLAUDE_CODE_CONFIG["weights"]["error_rate"] > DEFAULT_CONFIG["weights"]["error_rate"]

    def test_profile_is_claude_code(self):
        assert CLAUDE_CODE_CONFIG["soma"]["profile"] == "claude-code"

    def test_agent_has_all_claude_tools(self):
        tools = CLAUDE_CODE_CONFIG["agents"]["claude-code"]["tools"]
        for tool in CLAUDE_TOOLS:
            assert tool in tools

    def test_thresholds_are_ordered(self):
        t = CLAUDE_CODE_CONFIG["thresholds"]
        assert t["caution"] < t["degrade"] < t["quarantine"] < t["restart"]

    def test_all_weights_positive(self):
        for key, val in CLAUDE_CODE_CONFIG["weights"].items():
            assert val > 0, f"Weight {key} must be positive"


# ──────────────────────────────────────────────────────────────────
# Engine with Claude Code config
# ──────────────────────────────────────────────────────────────────

class TestEngineWithClaudeConfig:
    """Verify the engine applies Claude Code config correctly."""

    def test_engine_uses_custom_weights(self):
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
        )
        assert engine._custom_weights == CLAUDE_CODE_CONFIG["weights"]

    def test_engine_uses_custom_thresholds(self):
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )
        assert engine._custom_thresholds == CLAUDE_CODE_CONFIG["thresholds"]

    def test_higher_thresholds_mean_later_escalation(self):
        """With Claude Code thresholds, agent stays HEALTHY longer."""
        # Default engine (threshold caution=0.25)
        default_engine = SOMAEngine(budget={"tokens": 100000})
        default_engine.register_agent("test")

        # Claude Code engine (threshold caution=0.40)
        cc_engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )
        cc_engine.register_agent("test")

        # Pump both with the same actions
        for i in range(15):
            action = Action(
                tool_name="Bash",
                output_text="x" * (100 + i * 50),
                token_count=500,
                error=(i % 4 == 0),
                duration_sec=2.0,
            )
            default_engine.record_action("test", action)
            cc_engine.record_action("test", action)

        default_level = default_engine.get_level("test")
        cc_level = cc_engine.get_level("test")

        # Claude Code should be at same or lower level
        assert cc_level.value <= default_level.value

    def test_error_weight_amplifies_error_pressure(self):
        """Higher error_rate weight means errors push pressure higher."""
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
        )
        engine.register_agent("test")

        # Record mostly errors
        for i in range(15):
            result = engine.record_action("test", Action(
                tool_name="Bash",
                output_text="error output",
                token_count=100,
                error=True,
                duration_sec=0.5,
            ))

        snap = engine.get_snapshot("test")
        assert snap["pressure"] > 0.3, "High error rate should produce significant pressure"


# ──────────────────────────────────────────────────────────────────
# Persistence of custom config
# ──────────────────────────────────────────────────────────────────

class TestPersistenceWithConfig:
    """Custom weights/thresholds must survive save/load cycles."""

    def test_custom_weights_persist(self, tmp_path):
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
        )
        engine.register_agent("claude-code")

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))
        restored = load_engine_state(str(path))

        assert restored._custom_weights == CLAUDE_CODE_CONFIG["weights"]

    def test_custom_thresholds_persist(self, tmp_path):
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )
        engine.register_agent("claude-code")

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))
        restored = load_engine_state(str(path))

        assert restored._custom_thresholds == CLAUDE_CODE_CONFIG["thresholds"]

    def test_none_config_persists_as_none(self, tmp_path):
        """Default engine (no custom config) should load with None."""
        engine = SOMAEngine(budget={"tokens": 50000})
        engine.register_agent("test")

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))
        restored = load_engine_state(str(path))

        assert restored._custom_weights is None
        assert restored._custom_thresholds is None

    def test_config_survives_multiple_roundtrips(self, tmp_path):
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )
        engine.register_agent("claude-code")

        path = tmp_path / "state.json"
        for _ in range(5):
            save_engine_state(engine, str(path))
            engine = load_engine_state(str(path))
            engine.record_action("claude-code", _make_action())

        assert engine._custom_weights == CLAUDE_CODE_CONFIG["weights"]
        assert engine._custom_thresholds == CLAUDE_CODE_CONFIG["thresholds"]

    def test_restored_engine_uses_custom_weights_in_pressure(self, tmp_path):
        """After reload, engine must use custom weights not defaults."""
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights={"uncertainty": 0.1, "drift": 0.1, "error_rate": 10.0,
                            "cost": 0.1, "token_usage": 0.1},
        )
        engine.register_agent("test")

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))
        restored = load_engine_state(str(path))

        # Pump errors — extreme error_rate weight should show high pressure
        for _ in range(15):
            restored.record_action("test", Action(
                tool_name="Bash", output_text="fail", token_count=10,
                error=True, duration_sec=0.1,
            ))

        snap = restored.get_snapshot("test")
        assert snap["pressure"] > 0.3

    def test_state_json_contains_config_fields(self, tmp_path):
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )
        engine.register_agent("claude-code")

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))

        data = json.loads(path.read_text())
        assert "custom_weights" in data
        assert "custom_thresholds" in data
        assert data["custom_weights"]["error_rate"] == 2.5
        assert data["custom_thresholds"]["quarantine"] == 0.8

    def test_load_does_not_force_level(self, tmp_path):
        """Restored level must not use force_level — it should allow
        pressure-based re-evaluation after reload (no latch)."""
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("test")
        engine._agents["test"].ladder.force_level(Level.QUARANTINE)

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))
        restored = load_engine_state(str(path))

        agent_state = restored._agents["test"]
        # Level should be restored
        assert agent_state.ladder.current == Level.QUARANTINE
        # But _forced should be None — no latch
        assert agent_state.ladder._forced is None

    def test_restored_level_allows_re_evaluation(self, tmp_path):
        """After reload, pressure drop should be able to de-escalate the level."""
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("test")

        # Manually set to CAUTION (not force)
        engine._agents["test"].ladder._current = Level.CAUTION

        path = tmp_path / "state.json"
        save_engine_state(engine, str(path))
        restored = load_engine_state(str(path))

        # Evaluate with zero pressure — should de-escalate
        new_level = restored._agents["test"].ladder.evaluate(0.0, 1.0)
        assert new_level == Level.HEALTHY


# ──────────────────────────────────────────────────────────────────
# Common utilities
# ──────────────────────────────────────────────────────────────────

class TestCommon:
    def test_claude_tools_list(self):
        assert "Bash" in CLAUDE_TOOLS
        assert "Read" in CLAUDE_TOOLS
        assert "Edit" in CLAUDE_TOOLS
        assert "Write" in CLAUDE_TOOLS
        assert "Agent" in CLAUDE_TOOLS
        assert len(CLAUDE_TOOLS) >= 10

    def test_read_stdin_with_valid_json(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO('{"tool_name": "Bash"}'))
        result = read_stdin()
        assert result == {"tool_name": "Bash"}

    def test_read_stdin_with_empty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO(""))
        result = read_stdin()
        assert result == {}

    def test_read_stdin_with_invalid_json(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("not json"))
        result = read_stdin()
        assert result == {}

    def test_get_engine_creates_fresh_when_no_state(self, soma_dir):
        engine, agent_id = get_engine()
        assert engine is not None
        assert agent_id == "claude-code"  # pinned in test fixture
        assert engine.get_level("claude-code") == Level.HEALTHY

    def test_get_engine_has_claude_code_config(self, soma_dir):
        engine, _ = get_engine()
        assert engine._custom_weights == CLAUDE_CODE_CONFIG["weights"]
        assert engine._custom_thresholds == CLAUDE_CODE_CONFIG["thresholds"]

    def test_get_engine_loads_existing_state(self, soma_dir):
        # Create and save engine with some actions
        engine, _ = get_engine()
        for _ in range(5):
            engine.record_action("claude-code", _make_action())
        save_state(engine)

        # Load again — should have 5 actions
        engine2, _ = get_engine()
        snap = engine2.get_snapshot("claude-code")
        assert snap["action_count"] == 5

    def test_get_engine_registers_claude_code_if_missing(self, soma_dir):
        # Create engine without claude-code and save
        engine = SOMAEngine(budget={"tokens": 50000})
        engine.register_agent("other-agent")
        save_engine_state(engine, str(soma_dir / "engine_state.json"))

        # get_engine should add claude-code (pinned in test fixture)
        engine2, agent_id = get_engine()
        assert agent_id == "claude-code"
        assert "claude-code" in engine2._agents
        assert "other-agent" in engine2._agents

    def test_save_state_creates_both_files(self, soma_dir):
        engine, _ = get_engine()
        save_state(engine)
        assert (soma_dir / "engine_state.json").exists()
        assert (soma_dir / "state.json").exists()


# ──────────────────────────────────────────────────────────────────
# PreToolUse hook
# ──────────────────────────────────────────────────────────────────

class TestPreToolUse:
    def test_healthy_agent_passes(self, soma_dir):
        from soma.hooks.pre_tool_use import main
        # Should not raise or exit
        main()

    def test_quarantined_agent_blocks(self, soma_dir):
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.QUARANTINE)
        save_state(engine)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_critical_agent_does_not_block(self, soma_dir):
        """Only QUARANTINE and above block — DEGRADE should pass."""
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.DEGRADE)
        save_state(engine)

        # Should not raise
        main()

    def test_returns_none_when_no_engine(self, soma_dir, monkeypatch):
        from soma.hooks import pre_tool_use
        monkeypatch.setattr(pre_tool_use, "get_engine", lambda: (None, None))
        result = pre_tool_use.main()
        assert result is None

    def test_caution_allows_read(self, soma_dir):
        """CAUTION should not block Read tools."""
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.CAUTION)
        save_state(engine)

        # Should not raise
        main()

    def test_caution_blocks_mutation_without_read(self, soma_dir, monkeypatch):
        """CAUTION should block Edit when no recent Read in action log."""
        from soma.hooks.pre_tool_use import main
        from soma.hooks.common import ACTION_LOG_PATH

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.CAUTION)
        save_state(engine)

        # Empty action log — no recent Reads
        ACTION_LOG_PATH.write_text("[]")

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": "Edit"})))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_caution_allows_mutation_after_read(self, soma_dir, monkeypatch, capsys):
        """CAUTION should allow Edit when a recent Read exists in action log."""
        from soma.hooks.pre_tool_use import main
        from soma.hooks.common import ACTION_LOG_PATH
        import time

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.CAUTION)
        save_state(engine)

        # Action log with a recent Read
        log = [{"tool": "Read", "error": False, "file": "test.py", "ts": time.time()}]
        ACTION_LOG_PATH.write_text(json.dumps(log))

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": "Edit"})))
        main()
        captured = capsys.readouterr()
        assert "allowing Edit" in captured.err

    def test_degrade_blocks_bash(self, soma_dir, monkeypatch):
        """DEGRADE should block Bash entirely."""
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.DEGRADE)
        save_state(engine)

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": "Bash"})))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_degrade_allows_edit(self, soma_dir, monkeypatch):
        """DEGRADE should still allow Edit (not as risky as Bash)."""
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.DEGRADE)
        save_state(engine)

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": "Edit"})))
        main()  # Should not raise

    def test_degrade_blocks_agent(self, soma_dir, monkeypatch):
        """DEGRADE should block Agent tool (spawning subagents is high-risk)."""
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.DEGRADE)
        save_state(engine)

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": "Agent"})))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_healthy_is_silent(self, soma_dir, capsys):
        """HEALTHY level should produce no output at all."""
        from soma.hooks.pre_tool_use import main

        main()
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_safe_tools_allowed_during_quarantine(self, soma_dir, monkeypatch):
        """Read-only tools must NEVER be blocked, even in QUARANTINE."""
        from soma.hooks.pre_tool_use import main, SAFE_TOOLS

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.QUARANTINE)
        save_state(engine)

        for tool in ["Read", "Glob", "Grep"]:
            assert tool in SAFE_TOOLS
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": tool})))
            # Should NOT raise SystemExit
            main()

    def test_unsafe_tools_blocked_during_quarantine(self, soma_dir, monkeypatch):
        """Bash, Write, Edit should still be blocked in QUARANTINE."""
        from soma.hooks.pre_tool_use import main, SAFE_TOOLS

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.QUARANTINE)
        save_state(engine)

        for tool in ["Bash", "Write", "Edit", "Agent"]:
            assert tool not in SAFE_TOOLS
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": tool})))
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_safe_tools_not_blocked_during_restart(self, soma_dir, monkeypatch):
        """Safe tools pass even at RESTART level (highest blockable)."""
        from soma.hooks.pre_tool_use import main

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.RESTART)
        save_state(engine)

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"tool_name": "Read"})))
        main()  # Should not raise


# ──────────────────────────────────────────────────────────────────
# PostToolUse hook
# ──────────────────────────────────────────────────────────────────

class TestPostToolUse:
    def test_records_action(self, soma_dir, monkeypatch):
        from soma.hooks.post_tool_use import main

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
            "tool_name": "Edit",
            "output": "file edited successfully",
            "duration_ms": 150,
        })))

        main()

        engine, _ = get_engine()
        snap = engine.get_snapshot("claude-code")
        assert snap["action_count"] == 1

    def test_records_error_action(self, soma_dir, monkeypatch):
        from soma.hooks.post_tool_use import main

        monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
            "tool_name": "Bash",
            "output": "command failed",
            "is_error": True,
            "duration_ms": 500,
        })))

        main()

        engine, _ = get_engine()
        snap = engine.get_snapshot("claude-code")
        assert snap["action_count"] == 1

    def test_handles_empty_stdin(self, soma_dir, monkeypatch):
        from soma.hooks.post_tool_use import main
        monkeypatch.setattr("sys.stdin", StringIO(""))
        # Should not crash
        main()

    def test_handles_malformed_json(self, soma_dir, monkeypatch):
        from soma.hooks.post_tool_use import main
        monkeypatch.setattr("sys.stdin", StringIO("not json at all"))
        # Should not crash — records with defaults
        main()

    def test_multiple_actions_accumulate(self, soma_dir, monkeypatch):
        from soma.hooks.post_tool_use import main

        for i in range(10):
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
                "tool_name": ["Bash", "Read", "Edit", "Write", "Grep"][i % 5],
                "output": f"output {i}",
                "duration_ms": 100 + i * 20,
            })))
            main()

        engine, _ = get_engine()
        snap = engine.get_snapshot("claude-code")
        assert snap["action_count"] == 10

    def test_returns_none_when_no_engine(self, soma_dir, monkeypatch):
        from soma.hooks import post_tool_use
        monkeypatch.setattr(post_tool_use, "get_engine", lambda: (None, None))
        monkeypatch.setattr("sys.stdin", StringIO("{}"))
        result = post_tool_use.main()
        assert result is None

    def test_never_crashes_on_exception(self, soma_dir, monkeypatch):
        """Even if engine.record_action throws, hook must not crash."""
        from soma.hooks.post_tool_use import main

        def broken_get_engine():
            engine = SOMAEngine(budget={"tokens": 100})
            # Don't register agent — record_action will raise
            return engine, "nonexistent-agent"

        monkeypatch.setattr("soma.hooks.post_tool_use.get_engine", broken_get_engine)
        monkeypatch.setattr("sys.stdin", StringIO('{"tool_name":"Bash"}'))

        # Must not raise
        main()


# ──────────────────────────────────────────────────────────────────
# Stop hook
# ──────────────────────────────────────────────────────────────────

class TestStop:
    def test_saves_state(self, soma_dir):
        from soma.hooks.stop import main

        engine, _ = get_engine()
        engine.record_action("claude-code", _make_action())
        save_state(engine)

        main()

        assert (soma_dir / "engine_state.json").exists()

    def test_prints_summary(self, soma_dir, capsys):
        from soma.hooks.stop import main

        engine, _ = get_engine()
        for _ in range(5):
            engine.record_action("claude-code", _make_action())
        save_state(engine)

        main()

        captured = capsys.readouterr()
        assert "SOMA session end" in captured.err
        assert "HEALTHY" in captured.err

    def test_returns_none_when_no_engine(self, soma_dir, monkeypatch):
        from soma.hooks import stop
        monkeypatch.setattr(stop, "get_engine", lambda: (None, None))
        result = stop.main()
        assert result is None

    def test_never_crashes_on_exception(self, soma_dir, monkeypatch):
        """Even if get_snapshot throws, hook must not crash."""
        from soma.hooks.stop import main

        def broken_get_engine():
            engine = SOMAEngine(budget={"tokens": 100})
            return engine, "nonexistent-agent"

        monkeypatch.setattr("soma.hooks.stop.get_engine", broken_get_engine)
        # Must not raise
        main()


# ──────────────────────────────────────────────────────────────────
# Statusline
# ──────────────────────────────────────────────────────────────────

class TestStatusline:
    def test_shows_healthy(self, soma_dir, capsys):
        from soma.hooks.statusline import main

        engine, _ = get_engine()
        save_state(engine)

        main()
        out = capsys.readouterr().out.strip()
        assert "SOMA" in out
        assert "HEALTHY" in out

    def test_shows_action_count(self, soma_dir, capsys):
        from soma.hooks.statusline import main

        engine, _ = get_engine()
        for _ in range(7):
            engine.record_action("claude-code", _make_action())
        save_state(engine)

        main()
        out = capsys.readouterr().out.strip()
        # Action count should be present (format: #N)
        assert "#" in out
        assert "HEALTHY" in out or "CAUTION" in out

    def test_shows_waiting_when_no_state(self, soma_dir, capsys):
        from soma.hooks.statusline import main
        # No state file — should show waiting
        main()
        out = capsys.readouterr().out.strip()
        assert "waiting" in out or "SOMA" in out

    def test_never_crashes(self, soma_dir, capsys, monkeypatch):
        from soma.hooks.statusline import main

        # Write corrupt state to both files
        (soma_dir / "state.json").write_text("corrupt data {{{")
        (soma_dir / "engine_state.json").write_text("corrupt data {{{")
        main()

        out = capsys.readouterr().out.strip()
        assert "SOMA" in out  # Should output something, not crash

    def test_shows_correct_symbol_for_level(self, soma_dir, capsys):
        from soma.hooks.statusline import main, SYMBOLS

        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.QUARANTINE)
        save_state(engine)

        # Verify state.json was written with QUARANTINE
        import json
        state_data = json.loads((soma_dir / "state.json").read_text())
        assert state_data["agents"]["claude-code"]["level"] == "QUARANTINE"

        main()
        out = capsys.readouterr().out.strip()
        assert SYMBOLS["QUARANTINE"] in out
        assert "QUARANTINE" in out


# ──────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────

class TestDispatcher:
    def test_routes_pre_tool_use(self, soma_dir, monkeypatch):
        calls = []
        import soma.hooks.claude_code as dispatcher
        monkeypatch.setitem(dispatcher.DISPATCH, "PreToolUse", lambda: calls.append("pre"))
        monkeypatch.setattr("sys.argv", ["soma-hook", "PreToolUse"])
        monkeypatch.delenv("CLAUDE_HOOK", raising=False)

        dispatcher.main()
        assert calls == ["pre"]

    def test_routes_post_tool_use(self, soma_dir, monkeypatch):
        calls = []
        import soma.hooks.claude_code as dispatcher
        monkeypatch.setitem(dispatcher.DISPATCH, "PostToolUse", lambda: calls.append("post"))
        monkeypatch.setattr("sys.argv", ["soma-hook", "PostToolUse"])
        monkeypatch.delenv("CLAUDE_HOOK", raising=False)

        dispatcher.main()
        assert calls == ["post"]

    def test_routes_stop(self, soma_dir, monkeypatch):
        calls = []
        import soma.hooks.claude_code as dispatcher
        monkeypatch.setitem(dispatcher.DISPATCH, "Stop", lambda: calls.append("stop"))
        monkeypatch.setattr("sys.argv", ["soma-hook", "Stop"])
        monkeypatch.delenv("CLAUDE_HOOK", raising=False)

        dispatcher.main()
        assert calls == ["stop"]

    def test_env_var_takes_precedence(self, soma_dir, monkeypatch):
        calls = []
        import soma.hooks.claude_code as dispatcher
        monkeypatch.setitem(dispatcher.DISPATCH, "PreToolUse", lambda: calls.append("pre"))
        monkeypatch.setitem(dispatcher.DISPATCH, "PostToolUse", lambda: calls.append("post"))
        monkeypatch.setenv("CLAUDE_HOOK", "PreToolUse")
        monkeypatch.setattr("sys.argv", ["soma-hook", "PostToolUse"])

        dispatcher.main()
        assert calls == ["pre"]

    def test_unknown_hook_defaults_to_post(self, soma_dir, monkeypatch):
        calls = []
        monkeypatch.setattr("soma.hooks.claude_code.post_tool_use", lambda: calls.append("post"))
        monkeypatch.setattr("sys.argv", ["soma-hook", "UnknownHook"])
        monkeypatch.delenv("CLAUDE_HOOK", raising=False)

        from soma.hooks.claude_code import main
        main()
        assert calls == ["post"]


# ──────────────────────────────────────────────────────────────────
# Setup Claude
# ──────────────────────────────────────────────────────────────────

class TestSetupClaude:
    def test_install_hooks_creates_all_three(self, tmp_path):
        from soma.cli.setup_claude import _install_hooks

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")

        result = _install_hooks(settings_path, "soma-hook")
        assert result is True

        settings = json.loads(settings_path.read_text())
        assert "PreToolUse" in settings["hooks"]
        assert "PostToolUse" in settings["hooks"]
        assert "Stop" in settings["hooks"]

    def test_install_hooks_idempotent(self, tmp_path):
        from soma.cli.setup_claude import _install_hooks

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")

        _install_hooks(settings_path, "soma-hook")
        result = _install_hooks(settings_path, "soma-hook")
        assert result is False  # Already installed

    def test_install_hooks_preserves_existing(self, tmp_path):
        from soma.cli.setup_claude import _install_hooks

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({
            "hooks": {
                "PreToolUse": [{"hooks": [{"type": "command", "command": "other-tool"}]}]
            }
        }))

        _install_hooks(settings_path, "soma-hook")

        settings = json.loads(settings_path.read_text())
        # Should have both the existing hook and SOMA
        assert len(settings["hooks"]["PreToolUse"]) == 2

    def test_install_statusline(self, tmp_path):
        from soma.cli.setup_claude import _install_statusline

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")

        result = _install_statusline(settings_path, "soma-statusline")
        assert result is True

        settings = json.loads(settings_path.read_text())
        assert settings["statusLine"]["command"] == "soma-statusline"

    def test_install_statusline_idempotent(self, tmp_path):
        from soma.cli.setup_claude import _install_statusline

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")

        _install_statusline(settings_path, "soma-statusline")
        result = _install_statusline(settings_path, "soma-statusline")
        assert result is False

    def test_install_statusline_replaces_non_soma(self, tmp_path):
        from soma.cli.setup_claude import _install_statusline

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({
            "statusLine": {"type": "command", "command": "other-tool"}
        }))

        result = _install_statusline(settings_path, "soma-statusline")
        assert result is True

    def test_install_statusline_handles_non_dict(self, tmp_path):
        """If statusLine is somehow a string, should not crash."""
        from soma.cli.setup_claude import _install_statusline

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"statusLine": "something"}))

        # Should not crash
        result = _install_statusline(settings_path, "soma-statusline")
        assert result is True

    def test_hook_command_contains_soma(self, tmp_path):
        from soma.cli.setup_claude import _install_hooks

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")
        _install_hooks(settings_path, "soma-hook")

        settings = json.loads(settings_path.read_text())
        for hook_type in ["PreToolUse", "PostToolUse", "Stop"]:
            cmd = settings["hooks"][hook_type][0]["hooks"][0]["command"]
            assert "soma" in cmd

    def test_find_hook_command_returns_string(self):
        from soma.cli.setup_claude import _find_soma_hook_command
        cmd = _find_soma_hook_command()
        assert isinstance(cmd, str)
        assert "soma" in cmd

    def test_find_statusline_command_returns_string(self):
        from soma.cli.setup_claude import _find_statusline_command
        cmd = _find_statusline_command()
        assert isinstance(cmd, str)
        assert "soma" in cmd


# ──────────────────────────────────────────────────────────────────
# Integration: full session simulation
# ──────────────────────────────────────────────────────────────────

class TestFullSession:
    """Simulate a real Claude Code session through hooks."""

    def test_full_session_lifecycle(self, soma_dir, monkeypatch):
        """PreToolUse → PostToolUse (many) → Stop."""
        from soma.hooks.pre_tool_use import main as pre_main
        from soma.hooks.post_tool_use import main as post_main
        from soma.hooks.stop import main as stop_main

        # 1. PreToolUse — should pass
        pre_main()

        # 2. PostToolUse — record 50 actions (typical short session)
        tools = ["Read", "Bash", "Edit", "Write", "Grep", "Glob", "Read", "Bash"]
        for i in range(50):
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
                "tool_name": tools[i % len(tools)],
                "output": f"action output {i}" * 5,
                "duration_ms": 100 + (i % 10) * 50,
                "error": (i == 23),  # One error in the session
            })))
            post_main()

        # 3. Check state
        engine, _ = get_engine()
        snap = engine.get_snapshot("claude-code")
        assert snap["action_count"] == 50
        assert snap["level"] == Level.HEALTHY  # Should stay healthy with CC thresholds

        # 4. Stop — save final state
        stop_main()

    def test_error_heavy_session_escalates(self, soma_dir, monkeypatch):
        """Many errors should raise pressure with Claude Code config."""
        from soma.hooks.post_tool_use import main as post_main

        for i in range(30):
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
                "tool_name": "Bash",
                "output": "ERROR: command failed",
                "duration_ms": 200,
                "error": True,
            })))
            post_main()

        engine, _ = get_engine()
        snap = engine.get_snapshot("claude-code")
        assert snap["pressure"] > 0.2, "Constant errors should build pressure"

    def test_state_persists_across_sessions(self, soma_dir, monkeypatch):
        """Actions from session 1 should be visible in session 2."""
        from soma.hooks.post_tool_use import main as post_main
        from soma.hooks.stop import main as stop_main

        # Session 1: 10 actions
        for i in range(10):
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
                "tool_name": "Read",
                "output": f"file content {i}",
                "duration_ms": 50,
            })))
            post_main()
        stop_main()

        # Session 2: 5 more actions
        for i in range(5):
            monkeypatch.setattr("sys.stdin", StringIO(json.dumps({
                "tool_name": "Edit",
                "output": f"edited {i}",
                "duration_ms": 100,
            })))
            post_main()

        engine, _ = get_engine()
        snap = engine.get_snapshot("claude-code")
        assert snap["action_count"] == 15

    def test_quarantine_blocks_tools(self, soma_dir, monkeypatch):
        """If agent reaches QUARANTINE, PreToolUse should block."""
        from soma.hooks.pre_tool_use import main as pre_main

        # Force quarantine
        engine, _ = get_engine()
        engine._agents["claude-code"].ladder.force_level(Level.QUARANTINE)
        save_state(engine)

        with pytest.raises(SystemExit) as exc_info:
            pre_main()
        assert exc_info.value.code == 2


# ──────────────────────────────────────────────────────────────────
# Config loader integration
# ──────────────────────────────────────────────────────────────────

class TestConfigLoaderIntegration:
    def test_create_engine_from_claude_code_config(self):
        from soma.cli.config_loader import create_engine_from_config
        engine = create_engine_from_config(CLAUDE_CODE_CONFIG)

        assert engine._custom_weights == CLAUDE_CODE_CONFIG["weights"]
        assert engine._custom_thresholds == CLAUDE_CODE_CONFIG["thresholds"]
        assert engine.budget.limits["tokens"] == 1_000_000

    def test_create_engine_from_default_config(self):
        from soma.cli.config_loader import create_engine_from_config
        engine = create_engine_from_config(DEFAULT_CONFIG)

        assert engine._custom_weights == DEFAULT_CONFIG["weights"]
        assert engine._custom_thresholds == DEFAULT_CONFIG["thresholds"]
        assert engine.budget.limits["tokens"] == 100000

    def test_create_engine_from_empty_config(self):
        from soma.cli.config_loader import create_engine_from_config
        engine = create_engine_from_config({})

        assert engine._custom_weights is None
        assert engine._custom_thresholds is None


# ──────────────────────────────────────────────────────────────────
# Action Log
# ──────────────────────────────────────────────────────────────────

class TestActionLog:
    """Tests for the action log (pattern analysis data source)."""

    def test_append_and_read(self, soma_dir):
        from soma.hooks.common import append_action_log, read_action_log, ACTION_LOG_PATH
        # Patch ACTION_LOG_PATH to use soma_dir
        import soma.hooks.common as _common
        old = _common.ACTION_LOG_PATH
        _common.ACTION_LOG_PATH = soma_dir / "action_log.json"
        try:
            log = append_action_log("Read", error=False, file_path="test.py")
            assert len(log) == 1
            assert log[0]["tool"] == "Read"
            assert log[0]["file"] == "test.py"
            assert log[0]["error"] is False

            log2 = read_action_log()
            assert len(log2) == 1
        finally:
            _common.ACTION_LOG_PATH = old

    def test_log_max_cap(self, soma_dir):
        from soma.hooks.common import append_action_log, ACTION_LOG_MAX
        import soma.hooks.common as _common
        old = _common.ACTION_LOG_PATH
        _common.ACTION_LOG_PATH = soma_dir / "action_log.json"
        try:
            for i in range(ACTION_LOG_MAX + 10):
                append_action_log("Bash", error=False)

            from soma.hooks.common import read_action_log
            log = read_action_log()
            assert len(log) == ACTION_LOG_MAX
        finally:
            _common.ACTION_LOG_PATH = old

    def test_empty_log(self, soma_dir):
        from soma.hooks.common import read_action_log
        import soma.hooks.common as _common
        old = _common.ACTION_LOG_PATH
        _common.ACTION_LOG_PATH = soma_dir / "action_log.json"
        try:
            log = read_action_log()
            assert log == []
        finally:
            _common.ACTION_LOG_PATH = old


# ──────────────────────────────────────────────────────────────────
# Pattern Analysis
# ──────────────────────────────────────────────────────────────────

class TestPatternAnalysis:
    """Tests for notification.py pattern detection."""

    def test_no_tips_on_healthy_session(self):
        from soma.hooks.notification import _analyze_patterns
        log = [
            {"tool": "Read", "error": False, "file": "a.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "a.py", "ts": 2},
            {"tool": "Read", "error": False, "file": "b.py", "ts": 3},
            {"tool": "Write", "error": False, "file": "b.py", "ts": 4},
        ]
        assert _analyze_patterns(log) == []

    def test_writes_without_read(self):
        from soma.hooks.notification import _analyze_patterns
        log = [
            {"tool": "Write", "error": False, "file": "a.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "b.py", "ts": 2},
            {"tool": "Write", "error": False, "file": "c.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert len(tips) >= 1
        assert "writes without a Read" in tips[0]

    def test_consecutive_bash_failures(self):
        from soma.hooks.notification import _analyze_patterns
        log = [
            {"tool": "Bash", "error": True, "file": "", "ts": 1},
            {"tool": "Bash", "error": True, "file": "", "ts": 2},
            {"tool": "Bash", "error": True, "file": "", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert any("Bash failures" in t for t in tips)

    def test_high_error_rate(self):
        from soma.hooks.notification import _analyze_patterns
        log = [{"tool": "Read", "error": False, "file": "", "ts": i} for i in range(3)]
        log += [{"tool": "Bash", "error": True, "file": "", "ts": i + 3} for i in range(4)]
        tips = _analyze_patterns(log)
        assert any("recent actions failed" in t for t in tips)

    def test_file_thrashing(self):
        from soma.hooks.notification import _analyze_patterns
        log = [
            {"tool": "Edit", "error": False, "file": "/foo/bar.py", "ts": i}
            for i in range(4)
        ]
        tips = _analyze_patterns(log)
        assert any("bar.py" in t for t in tips)

    def test_empty_log(self):
        from soma.hooks.notification import _analyze_patterns
        assert _analyze_patterns([]) == []

    def test_max_two_tips(self):
        from soma.hooks.notification import _analyze_patterns
        # Trigger multiple patterns at once
        log = [
            {"tool": "Bash", "error": True, "file": "", "ts": 1},
            {"tool": "Bash", "error": True, "file": "", "ts": 2},
            {"tool": "Write", "error": False, "file": "/x/y.py", "ts": 3},
            {"tool": "Write", "error": False, "file": "/x/y.py", "ts": 4},
            {"tool": "Write", "error": False, "file": "/x/y.py", "ts": 5},
        ]
        tips = _analyze_patterns(log)
        assert len(tips) <= 2


# ──────────────────────────────────────────────────────────────────
# Post-write Validation
# ──────────────────────────────────────────────────────────────────

class TestPostWriteValidation:
    """Tests for syntax validation after Write/Edit."""

    def test_valid_python(self, tmp_path):
        from soma.hooks.post_tool_use import _validate_python_file
        f = tmp_path / "good.py"
        f.write_text("x = 1 + 2\ndef foo(): pass\n")
        assert _validate_python_file(str(f)) is None

    def test_invalid_python(self, tmp_path):
        from soma.hooks.post_tool_use import _validate_python_file
        f = tmp_path / "bad.py"
        f.write_text("def foo(\n  x = \n")
        result = _validate_python_file(str(f))
        assert result is not None
        assert "SyntaxError" in result

    def test_non_python_ignored(self):
        from soma.hooks.post_tool_use import _validate_python_file
        assert _validate_python_file("foo.js") is None
        assert _validate_python_file("") is None
        assert _validate_python_file("README.md") is None

    def test_lint_python_valid(self, tmp_path):
        from soma.hooks.post_tool_use import _lint_python_file
        f = tmp_path / "clean.py"
        f.write_text("x = 1\nprint(x)\n")
        # If ruff is installed, should return None for clean code
        # If ruff is not installed, should also return None (skip silently)
        assert _lint_python_file(str(f)) is None

    def test_lint_non_python_ignored(self):
        from soma.hooks.post_tool_use import _lint_python_file
        assert _lint_python_file("foo.js") is None
        assert _lint_python_file("") is None

    def test_js_validation_non_js_ignored(self):
        from soma.hooks.post_tool_use import _validate_js_file
        assert _validate_js_file("foo.py") is None
        assert _validate_js_file("") is None
        assert _validate_js_file("style.css") is None

    def test_js_validation_valid(self, tmp_path):
        from soma.hooks.post_tool_use import _validate_js_file
        f = tmp_path / "good.js"
        f.write_text("const x = 1;\nconsole.log(x);\n")
        # If node is installed, should return None for valid JS
        # If node is not installed, should also return None
        assert _validate_js_file(str(f)) is None

    def test_extract_file_path(self):
        from soma.hooks.post_tool_use import _extract_file_path
        assert _extract_file_path({"tool_input": {"file_path": "/a/b.py"}}) == "/a/b.py"
        assert _extract_file_path({"tool_input": {"path": "/c/d"}}) == "/c/d"
        assert _extract_file_path({}) == ""
        assert _extract_file_path({"tool_input": "string"}) == ""


# ──────────────────────────────────────────────────────────────────
# Stop Hook Cleanup
# ──────────────────────────────────────────────────────────────────

class TestStopCleanup:
    """Tests that Stop hook cleans up session artifacts."""

    def test_action_log_cleaned_on_stop(self, soma_dir, monkeypatch):
        from soma.hooks.stop import main
        import soma.hooks.common as _common
        import soma.hooks.stop as _stop

        # Point ACTION_LOG_PATH to temp dir
        log_path = soma_dir / "action_log.json"
        log_path.write_text('[{"tool": "Read", "ts": 1}]')
        monkeypatch.setattr(_common, "ACTION_LOG_PATH", log_path)
        monkeypatch.setattr(_stop, "ACTION_LOG_PATH", log_path)

        main()

        assert not log_path.exists()


# ──────────────────────────────────────────────────────────────────
# Cross-session Memory
# ──────────────────────────────────────────────────────────────────

class TestCrossSessionMemory:
    """Tests for baseline inheritance and dead agent cleanup."""

    def test_inherit_baseline_from_previous_session(self):
        """New session should inherit baseline from the most active prior session."""
        from soma.hooks.common import _inherit_baseline

        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("cc-old", tools=CLAUDE_TOOLS)

        # Simulate 20 actions on old agent to build up baseline
        old = engine._agents["cc-old"]
        for i in range(20):
            old.baseline.update("uncertainty", 0.3)
            old.baseline.update("drift", 0.2)
        old.action_count = 20
        old.known_tools = ["Bash", "Read", "Edit", "Grep", "Write"]
        old.baseline_vector = [1.0, 2.0, 3.0]

        # Register new session
        engine.register_agent("cc-new", tools=CLAUDE_TOOLS)

        # Inherit
        _inherit_baseline(engine, "cc-new")

        new = engine._agents["cc-new"]
        assert new.baseline.get_count("uncertainty") == 20
        assert new.baseline_vector == [1.0, 2.0, 3.0]
        assert "Bash" in new.known_tools

    def test_no_inherit_from_short_session(self):
        """Don't inherit from sessions with < 10 actions."""
        from soma.hooks.common import _inherit_baseline

        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("cc-short", tools=CLAUDE_TOOLS)
        engine._agents["cc-short"].action_count = 5

        engine.register_agent("cc-new", tools=CLAUDE_TOOLS)
        _inherit_baseline(engine, "cc-new")

        new = engine._agents["cc-new"]
        assert new.baseline.get_count("uncertainty") == 0

    def test_cleanup_old_agents(self):
        """Should keep only N most active agents + current."""
        from soma.hooks.common import _cleanup_old_agents

        engine = SOMAEngine(budget={"tokens": 100000})
        for i in range(5):
            aid = f"cc-{i}"
            engine.register_agent(aid, tools=CLAUDE_TOOLS)
            engine._agents[aid].action_count = i * 10

        engine.register_agent("cc-current", tools=CLAUDE_TOOLS)
        _cleanup_old_agents(engine, "cc-current", keep=2)

        remaining = set(engine._agents.keys())
        # Should keep cc-current + 2 most active (cc-4=40, cc-3=30)
        assert "cc-current" in remaining
        assert "cc-4" in remaining
        assert "cc-3" in remaining
        assert "cc-0" not in remaining
        assert "cc-1" not in remaining

    def test_cleanup_noop_when_few_agents(self):
        """Cleanup should not remove anything if <= keep agents exist."""
        from soma.hooks.common import _cleanup_old_agents

        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("cc-1", tools=CLAUDE_TOOLS)
        engine.register_agent("cc-current", tools=CLAUDE_TOOLS)

        _cleanup_old_agents(engine, "cc-current", keep=2)
        assert "cc-1" in engine._agents


# ──────────────────────────────────────────────────────────────────
# Predictor
# ──────────────────────────────────────────────────────────────────

class TestPredictor:
    """Tests for anomaly prediction."""

    def test_stable_pressure_no_escalation(self):
        from soma.predictor import PressurePredictor
        p = PressurePredictor(window=10, horizon=5)
        for _ in range(10):
            p.update(0.10)
        pred = p.predict(next_threshold=0.25)
        assert not pred.will_escalate
        assert pred.dominant_reason == "stable"

    def test_rising_pressure_predicts_escalation(self):
        from soma.predictor import PressurePredictor
        p = PressurePredictor(window=10, horizon=5)
        # Simulate steadily rising pressure
        for i in range(10):
            p.update(0.05 + i * 0.03)  # 0.05 → 0.32
        pred = p.predict(next_threshold=0.40)
        assert pred.predicted_pressure > 0.30
        assert pred.dominant_reason == "trend"

    def test_error_streak_boosts_prediction(self):
        from soma.predictor import PressurePredictor
        p = PressurePredictor(window=10, horizon=5)
        for i in range(5):
            p.update(0.15, {"tool": "Read", "error": False, "file": ""})
        # Now 3 errors in a row
        for i in range(3):
            p.update(0.18, {"tool": "Bash", "error": True, "file": ""})
        pred = p.predict(next_threshold=0.25)
        assert pred.predicted_pressure > 0.18  # Boosted by pattern

    def test_blind_writes_boost(self):
        from soma.predictor import PressurePredictor
        p = PressurePredictor(window=10, horizon=5)
        for i in range(5):
            p.update(0.15, {"tool": "Read", "error": False, "file": ""})
        p.update(0.16, {"tool": "Write", "error": False, "file": "a.py"})
        p.update(0.17, {"tool": "Write", "error": False, "file": "b.py"})
        pred = p.predict(next_threshold=0.25)
        assert pred.predicted_pressure > 0.17

    def test_serialization(self):
        from soma.predictor import PressurePredictor
        p = PressurePredictor(window=10, horizon=5)
        for i in range(5):
            p.update(0.1 * i, {"tool": "Read", "error": False, "file": ""})

        data = p.to_dict()
        p2 = PressurePredictor.from_dict(data)
        assert p2._pressures == p._pressures
        assert len(p2._action_log) == len(p._action_log)

    def test_empty_predictor(self):
        from soma.predictor import PressurePredictor
        p = PressurePredictor()
        pred = p.predict(next_threshold=0.25)
        assert not pred.will_escalate
        assert pred.predicted_pressure == 0.0

    def test_confidence_increases_with_samples(self):
        from soma.predictor import PressurePredictor
        p1 = PressurePredictor(window=10, horizon=5)
        p1.update(0.1)
        p1.update(0.2)
        pred1 = p1.predict(next_threshold=0.5)

        p2 = PressurePredictor(window=10, horizon=5)
        for i in range(10):
            p2.update(0.1 + i * 0.01)
        pred2 = p2.predict(next_threshold=0.5)

        assert pred2.confidence > pred1.confidence


# ──────────────────────────────────────────────────────────────────
# Root Cause Analysis
# ──────────────────────────────────────────────────────────────────

class TestRCA:
    """Tests for plain-English root cause analysis."""

    def test_healthy_returns_none(self):
        from soma.rca import diagnose
        result = diagnose([], {}, 0.05, "HEALTHY", 10)
        assert result is None

    def test_loop_detection(self):
        from soma.rca import diagnose
        log = []
        for _ in range(4):
            log.append({"tool": "Edit", "error": False, "file": "/x/config.py"})
            log.append({"tool": "Bash", "error": False, "file": ""})
        result = diagnose(log, {"drift": 0.3}, 0.30, "CAUTION", 20)
        assert result is not None
        assert "loop" in result
        assert "Edit→Bash" in result

    def test_error_cascade(self):
        from soma.rca import diagnose
        log = [
            {"tool": "Read", "error": False, "file": ""},
            {"tool": "Bash", "error": True, "file": ""},
            {"tool": "Bash", "error": True, "file": ""},
            {"tool": "Bash", "error": True, "file": ""},
        ]
        result = diagnose(log, {"error_rate": 0.40}, 0.35, "CAUTION", 15)
        assert result is not None
        assert "error cascade" in result
        assert "3 consecutive" in result

    def test_blind_mutation(self):
        from soma.rca import diagnose
        log = [
            {"tool": "Write", "error": False, "file": "/a/foo.py"},
            {"tool": "Edit", "error": False, "file": "/a/bar.py"},
            {"tool": "Write", "error": False, "file": "/a/baz.py"},
        ]
        result = diagnose(log, {"drift": 0.2}, 0.25, "CAUTION", 10)
        assert result is not None
        assert "blind mutation" in result

    def test_stall_detection(self):
        from soma.rca import diagnose
        # Mix of read-like tools (not a pure loop, but no writes)
        tools = ["Read", "Grep", "Glob", "Read", "Grep", "Read", "Glob", "Read"]
        log = [{"tool": t, "error": False, "file": f"{i}.py"} for i, t in enumerate(tools)]
        result = diagnose(log, {"drift": 0.15}, 0.20, "HEALTHY", 30)
        assert result is not None
        assert "stall" in result

    def test_drift_explanation(self):
        from soma.rca import diagnose
        log = [{"tool": "Read", "error": False, "file": ""}]
        result = diagnose(log, {"drift": 0.4, "uncertainty": 0.3, "error_rate": 0.0}, 0.30, "CAUTION", 20)
        assert result is not None
        assert "drift" in result

    def test_most_severe_wins(self):
        """When multiple findings exist, the most severe should be returned."""
        from soma.rca import diagnose
        # Both error cascade AND blind writes
        log = [
            {"tool": "Write", "error": True, "file": "/a/x.py"},
            {"tool": "Write", "error": True, "file": "/a/y.py"},
            {"tool": "Write", "error": True, "file": "/a/z.py"},
        ]
        result = diagnose(log, {"error_rate": 0.5, "drift": 0.3}, 0.40, "CAUTION", 20)
        assert result is not None
        # Error cascade should win (higher severity)
        assert "error" in result


# ──────────────────────────────────────────────────────────────────
# Agent Fingerprinting
# ──────────────────────────────────────────────────────────────────

class TestFingerprinting:
    """Tests for agent behavioral fingerprinting."""

    def test_build_fingerprint_from_session(self):
        from soma.fingerprint import FingerprintEngine
        fe = FingerprintEngine()
        log = [
            {"tool": "Read", "error": False, "file": "a.py"},
            {"tool": "Edit", "error": False, "file": "a.py"},
            {"tool": "Read", "error": False, "file": "b.py"},
            {"tool": "Bash", "error": False, "file": ""},
            {"tool": "Read", "error": False, "file": "c.py"},
        ]
        fp = fe.update_from_session("agent-1", log)
        assert fp.tool_distribution["Read"] == pytest.approx(0.6)
        assert fp.avg_error_rate == 0.0
        assert fp.sample_count == 1

    def test_fingerprint_ema_update(self):
        from soma.fingerprint import FingerprintEngine
        fe = FingerprintEngine(alpha=0.5)

        log1 = [{"tool": "Read", "error": False, "file": ""} for _ in range(10)]
        fe.update_from_session("a", log1)
        assert fe.get("a").tool_distribution["Read"] == 1.0

        log2 = [{"tool": "Bash", "error": False, "file": ""} for _ in range(10)]
        fe.update_from_session("a", log2)
        # After EMA: 0.5 * 1.0 + 0.5 * 0.0 = 0.5 for Read
        assert fe.get("a").tool_distribution["Read"] == pytest.approx(0.5)
        assert fe.get("a").tool_distribution["Bash"] == pytest.approx(0.5)

    def test_divergence_detection(self):
        from soma.fingerprint import FingerprintEngine
        fe = FingerprintEngine(alpha=0.1)

        # Build up a fingerprint over 10 sessions of mostly Read+Edit
        for _ in range(10):
            log = [
                {"tool": "Read", "error": False, "file": ""},
                {"tool": "Edit", "error": False, "file": ""},
                {"tool": "Read", "error": False, "file": ""},
                {"tool": "Bash", "error": False, "file": ""},
                {"tool": "Read", "error": False, "file": ""},
            ]
            fe.update_from_session("a", log)

        # Now a completely different session: all Bash with errors
        weird_log = [{"tool": "Bash", "error": True, "file": ""} for _ in range(10)]
        div, explanation = fe.check_divergence("a", weird_log)
        assert div > 0.2
        assert explanation  # Should explain what changed

    def test_no_divergence_for_new_agent(self):
        from soma.fingerprint import FingerprintEngine
        fe = FingerprintEngine()
        div, explanation = fe.check_divergence("unknown", [])
        assert div == 0.0

    def test_serialization(self):
        from soma.fingerprint import FingerprintEngine
        fe = FingerprintEngine()
        log = [{"tool": "Read", "error": False, "file": ""} for _ in range(5)]
        fe.update_from_session("a", log)

        data = fe.to_dict()
        fe2 = FingerprintEngine.from_dict(data)
        assert fe2.get("a").tool_distribution == fe.get("a").tool_distribution
        assert fe2.get("a").sample_count == fe.get("a").sample_count

    def test_fingerprint_divergence_score(self):
        from soma.fingerprint import Fingerprint
        fp1 = Fingerprint(
            tool_distribution={"Read": 0.5, "Edit": 0.3, "Bash": 0.2},
            avg_error_rate=0.05,
            read_write_ratio=2.0,
            sample_count=20,
        )
        # Same profile — no divergence
        fp_same = Fingerprint(
            tool_distribution={"Read": 0.5, "Edit": 0.3, "Bash": 0.2},
            avg_error_rate=0.05,
            read_write_ratio=2.0,
        )
        assert fp1.divergence(fp_same) < 0.1

        # Very different profile
        fp_diff = Fingerprint(
            tool_distribution={"Bash": 0.9, "Read": 0.1},
            avg_error_rate=0.5,
            read_write_ratio=10.0,
        )
        assert fp1.divergence(fp_diff) > 0.3
