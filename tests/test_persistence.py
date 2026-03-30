"""Tests for SOMAEngine state persistence across process restarts."""

import json
import threading
import pytest
from pathlib import Path

from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode
from soma.persistence import save_engine_state, load_engine_state


def _make_action(i: int = 0) -> Action:
    return Action(
        tool_name="search",
        output_text=f"result {i} " + "output " * 5,
        token_count=100,
        cost=0.001,
    )


def _build_engine_with_agents(tmp_path: Path) -> tuple[SOMAEngine, Path]:
    """Create engine with 2 agents, each having 5 recorded actions."""
    engine = SOMAEngine(budget={"tokens": 50000, "cost_usd": 10.0})
    engine.register_agent("agent-alpha")
    engine.register_agent("agent-beta")

    for i in range(5):
        engine.record_action("agent-alpha", _make_action(i))
        engine.record_action("agent-beta", _make_action(i + 100))

    state_file = tmp_path / "engine_state.json"
    return engine, state_file


class TestSaveLoadRoundtrip:
    def test_roundtrip_agent_count(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        save_engine_state(engine, str(state_file))

        restored = load_engine_state(str(state_file))
        assert restored is not None
        assert set(restored._agents.keys()) == {"agent-alpha", "agent-beta"}

    def test_roundtrip_action_count(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        save_engine_state(engine, str(state_file))

        restored = load_engine_state(str(state_file))
        assert restored is not None
        assert restored._agents["agent-alpha"].action_count == 5
        assert restored._agents["agent-beta"].action_count == 5

    def test_roundtrip_baseline_values(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)

        # Capture baseline values before save
        orig_uncertainty = engine._agents["agent-alpha"].baseline.get("uncertainty")
        orig_drift = engine._agents["agent-alpha"].baseline.get("drift")

        save_engine_state(engine, str(state_file))
        restored = load_engine_state(str(state_file))

        assert restored is not None
        restored_uncertainty = restored._agents["agent-alpha"].baseline.get("uncertainty")
        restored_drift = restored._agents["agent-alpha"].baseline.get("drift")

        assert abs(restored_uncertainty - orig_uncertainty) < 1e-9
        assert abs(restored_drift - orig_drift) < 1e-9

    def test_roundtrip_budget(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        orig_spent_tokens = engine.budget.spent.get("tokens", 0)

        save_engine_state(engine, str(state_file))
        restored = load_engine_state(str(state_file))

        assert restored is not None
        assert abs(restored.budget.spent.get("tokens", 0) - orig_spent_tokens) < 1e-9
        assert restored.budget.limits == engine.budget.limits

    def test_roundtrip_level(self, tmp_path):
        engine = SOMAEngine(budget={"tokens": 50000})
        engine.register_agent("agent-x")

        # Force to a non-OBSERVE mode
        engine._agents["agent-x"].mode = ResponseMode.GUIDE

        state_file = tmp_path / "engine_state.json"
        save_engine_state(engine, str(state_file))
        restored = load_engine_state(str(state_file))

        assert restored is not None
        assert restored.get_level("agent-x") == ResponseMode.GUIDE

    def test_roundtrip_known_tools(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        orig_tools = list(engine._agents["agent-alpha"].known_tools)

        save_engine_state(engine, str(state_file))
        restored = load_engine_state(str(state_file))

        assert restored is not None
        assert restored._agents["agent-alpha"].known_tools == orig_tools

    def test_roundtrip_state_file_is_valid_json(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        save_engine_state(engine, str(state_file))

        data = json.loads(state_file.read_text())
        assert "agents" in data
        assert "budget" in data
        assert "graph" in data
        assert "learning" in data


class TestLoadNonexistent:
    def test_returns_none_when_no_file(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.json")
        result = load_engine_state(missing)
        assert result is None

    def test_returns_none_on_corrupt_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ this is not valid json }")
        result = load_engine_state(str(bad_file))
        assert result is None


class TestRestoredEngineIsUsable:
    def test_restored_engine_can_record_actions(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        save_engine_state(engine, str(state_file))

        restored = load_engine_state(str(state_file))
        assert restored is not None

        # Should be able to record more actions without error
        result = restored.record_action("agent-alpha", _make_action(999))
        assert result is not None
        assert isinstance(result.mode, ResponseMode)
        assert restored._agents["agent-alpha"].action_count == 6

    def test_restored_engine_correct_budget_limits(self, tmp_path):
        engine = SOMAEngine(budget={"tokens": 12345})
        engine.register_agent("a1")

        state_file = tmp_path / "engine_state.json"
        save_engine_state(engine, str(state_file))

        restored = load_engine_state(str(state_file))
        assert restored is not None
        assert restored.budget.limits["tokens"] == 12345

    def test_restored_engine_graph_has_agents(self, tmp_path):
        engine, state_file = _build_engine_with_agents(tmp_path)
        save_engine_state(engine, str(state_file))

        restored = load_engine_state(str(state_file))
        assert restored is not None
        # Graph should contain both agents
        assert "agent-alpha" in restored._graph.agents
        assert "agent-beta" in restored._graph.agents


class TestConcurrentSaves:
    def test_concurrent_saves_produce_valid_json(self, tmp_path):
        """Two threads saving simultaneously should not corrupt the state file."""
        state_file = tmp_path / "engine_state.json"
        errors: list[Exception] = []

        def save_worker(agent_name: str):
            try:
                engine = SOMAEngine(budget={"tokens": 50000})
                engine.register_agent(agent_name)
                for i in range(10):
                    engine.record_action(agent_name, _make_action(i))
                    save_engine_state(engine, str(state_file))
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=save_worker, args=("writer-1",))
        t2 = threading.Thread(target=save_worker, args=("writer-2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Threads raised exceptions: {errors}"

        # File must exist and be valid JSON
        data = json.loads(state_file.read_text())
        assert "agents" in data
        assert "budget" in data

        # State should be from one of the two writers (not a mix)
        agents = set(data["agents"].keys())
        assert agents == {"writer-1"} or agents == {"writer-2"}

    def test_concurrent_saves_never_produce_partial_file(self, tmp_path):
        """Rapid concurrent saves should always leave a parseable file."""
        state_file = tmp_path / "engine_state.json"
        read_errors: list[str] = []
        stop = threading.Event()

        def save_loop(agent_name: str):
            engine = SOMAEngine(budget={"tokens": 50000})
            engine.register_agent(agent_name)
            for i in range(20):
                if stop.is_set():
                    break
                engine.record_action(agent_name, _make_action(i))
                save_engine_state(engine, str(state_file))

        def read_loop():
            for _ in range(50):
                if stop.is_set():
                    break
                try:
                    text = state_file.read_text()
                    json.loads(text)
                except FileNotFoundError:
                    pass  # File not yet created
                except json.JSONDecodeError as exc:
                    read_errors.append(f"Corrupt JSON: {exc}")
                    stop.set()

        t1 = threading.Thread(target=save_loop, args=("w1",))
        t2 = threading.Thread(target=save_loop, args=("w2",))
        t3 = threading.Thread(target=read_loop)
        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        stop.set()
        t3.join()

        assert not read_errors, f"Found corrupt state: {read_errors}"
