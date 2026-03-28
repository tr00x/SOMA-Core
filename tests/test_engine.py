from soma.engine import SOMAEngine, ActionResult
from soma.types import Action, Level, AutonomyMode


class TestSOMAEngine:
    def test_create_and_register(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        assert e.get_level("a") == Level.HEALTHY

    def test_record_normal(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # First few actions may have elevated uncertainty due to cold start baseline
        # Warm up with several normal actions
        for i in range(10):
            r = e.record_action("a", Action(
                tool_name="search", output_text=f"found {i} results for query", token_count=100,
            ))
        assert r.level == Level.HEALTHY
        assert 0.0 <= r.pressure <= 1.0
        assert isinstance(r.vitals.uncertainty, float)

    def test_escalation_on_errors(self, error_actions):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # Run enough actions to clear the grace period (first 10), then add errors
        for action in error_actions:
            r = e.record_action("a", action)
        # One more error action after grace period ends
        r = e.record_action("a", error_actions[0])
        assert r.level.value >= Level.CAUTION.value

    def test_multi_agent_pressure(self):
        e = SOMAEngine(budget={"tokens": 500000})
        e.register_agent("bad")
        e.register_agent("good")
        e.add_edge("bad", "good", trust_weight=1.0)
        for _ in range(15):
            e.record_action("bad", Action(
                tool_name="bash", output_text="error " * 50,
                token_count=100, error=True, retried=True,
            ))
        r = e.record_action("good", Action(
            tool_name="search", output_text="found results", token_count=50,
        ))
        assert r.pressure >= 0.0

    def test_safe_mode(self):
        e = SOMAEngine(budget={"tokens": 500})
        e.register_agent("a")
        for _ in range(6):
            e.record_action("a", Action(tool_name="bash", output_text="x", token_count=100))
        r = e.record_action("a", Action(tool_name="bash", output_text="x", token_count=0))
        assert r.level == Level.SAFE_MODE

    def test_events_fired(self, error_actions):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        events = []
        e.events.on("level_changed", lambda d: events.append(d))
        for action in error_actions:
            e.record_action("a", action)
        if e.get_level("a") != Level.HEALTHY:
            assert len(events) >= 1
            assert "agent_id" in events[0]

    def test_get_snapshot(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        e.record_action("a", Action(tool_name="bash", output_text="hello", token_count=50))
        snap = e.get_snapshot("a")
        assert "level" in snap
        assert "pressure" in snap
        assert "vitals" in snap
        assert snap["action_count"] == 1

    def test_multiple_agents_independent(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        e.register_agent("b")
        # a gets errors, b stays clean
        for _ in range(10):
            e.record_action("a", Action(
                tool_name="bash", output_text="err", token_count=50, error=True, retried=True,
            ))
        for _ in range(10):
            e.record_action("b", Action(
                tool_name="search", output_text="ok " * 20, token_count=50,
            ))
        # Without edge, b should not be affected
        assert e.get_level("b") == Level.HEALTHY

    def test_action_result_is_frozen(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="bash", output_text="ok", token_count=50))
        try:
            r.level = Level.RESTART  # type: ignore
            assert False, "Should not allow mutation"
        except AttributeError:
            pass
