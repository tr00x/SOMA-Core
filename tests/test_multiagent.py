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
