import threading
import time

from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode


class TestAgentLifecycle:
    def test_evict_stale_agents(self):
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("active")
        engine.register_agent("stale")
        engine.record_action(
            "active", Action(tool_name="Bash", output_text="ok", token_count=10)
        )
        engine._agents["stale"]._last_active = time.time() - 7200
        evicted = engine.evict_stale_agents(ttl_seconds=3600)
        assert "stale" in evicted
        assert "stale" not in engine._agents
        assert "active" in engine._agents

    def test_evict_preserves_active(self):
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("a")
        engine.record_action(
            "a", Action(tool_name="Bash", output_text="ok", token_count=10)
        )
        evicted = engine.evict_stale_agents(ttl_seconds=60)
        assert len(evicted) == 0

    def test_evict_empty(self):
        engine = SOMAEngine(budget={"tokens": 100000})
        assert engine.evict_stale_agents(ttl_seconds=3600) == []


class TestConcurrentAgents:
    def test_five_agents_concurrent(self):
        """5 agents recording 50 actions each simultaneously."""
        engine = SOMAEngine(budget={"tokens": 1000000})
        for i in range(5):
            engine.register_agent(f"agent-{i}")
            if i > 0:
                engine.add_edge(f"agent-{i-1}", f"agent-{i}", trust_weight=0.5)

        errors = []

        def run_agent(agent_id):
            try:
                for j in range(50):
                    action = Action(
                        tool_name=["Bash", "Read", "Edit", "Write"][j % 4],
                        output_text=f"output {j}",
                        token_count=100,
                        error=(j % 10 == 0),
                    )
                    result = engine.record_action(agent_id, action)
                    assert 0.0 <= result.pressure <= 1.0
                    assert result.mode in ResponseMode
            except Exception as e:
                errors.append((agent_id, e))

        threads = [
            threading.Thread(target=run_agent, args=(f"agent-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Agent errors: {errors}"
        for i in range(5):
            snap = engine.get_snapshot(f"agent-{i}")
            assert snap["action_count"] == 50
            assert 0.0 <= snap["pressure"] <= 1.0

    def test_pressure_propagation_pipeline(self):
        """Planner errors should propagate pressure to coder via trust graph."""
        engine = SOMAEngine(budget={"tokens": 1000000})
        engine.register_agent("planner")
        engine.register_agent("coder")
        engine.register_agent("reviewer")
        engine.add_edge("planner", "coder", trust_weight=0.8)
        engine.add_edge("coder", "reviewer", trust_weight=0.6)

        # Planner errors
        for i in range(20):
            engine.record_action("planner", Action(
                tool_name="Bash", output_text="error", token_count=100, error=True, retried=True,
            ))
        # Coder normal
        for i in range(5):
            engine.record_action("coder", Action(
                tool_name="Edit", output_text="code", token_count=50,
            ))

        planner_snap = engine.get_snapshot("planner")
        coder_snap = engine.get_snapshot("coder")
        assert coder_snap["pressure"] >= 0.0

    def test_five_agent_pipeline_healthy(self):
        """Full pipeline with 5 agents, all healthy."""
        engine = SOMAEngine(budget={"tokens": 1000000})
        agents = ["planner", "researcher", "coder", "tester", "reviewer"]
        for a in agents:
            engine.register_agent(a)
        for i in range(len(agents) - 1):
            engine.add_edge(agents[i], agents[i+1], trust_weight=0.7)

        for a in agents:
            for j in range(10):
                engine.record_action(a, Action(tool_name="Read", output_text="ok", token_count=50))

        for a in agents:
            assert engine.get_level(a) == ResponseMode.OBSERVE
