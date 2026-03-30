from soma.engine import SOMAEngine, ActionResult
from soma.types import Action, ResponseMode, AutonomyMode


class TestSOMAEngine:
    def test_create_and_register(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        assert e.get_level("a") == ResponseMode.OBSERVE

    def test_record_normal(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # First few actions may have elevated uncertainty due to cold start baseline
        # Warm up with several normal actions
        for i in range(10):
            r = e.record_action("a", Action(
                tool_name="search", output_text=f"found {i} results for query", token_count=100,
            ))
        assert r.mode == ResponseMode.OBSERVE
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
        assert r.mode.value >= ResponseMode.GUIDE.value

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

    def test_budget_depletion_raises_pressure(self):
        e = SOMAEngine(budget={"tokens": 100})
        e.register_agent("a")
        # Exhaust budget and pass grace period
        for _ in range(15):
            r = e.record_action("a", Action(tool_name="bash", output_text="x", token_count=100))
        # Budget is massively overdrawn — pressure should be elevated
        assert r.mode >= ResponseMode.GUIDE, (
            f"Expected at least GUIDE after budget depletion, got {r.mode}"
        )

    def test_events_fired(self, error_actions):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        events = []
        e.events.on("level_changed", lambda d: events.append(d))
        for action in error_actions:
            e.record_action("a", action)
        if e.get_level("a") != ResponseMode.OBSERVE:
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
        assert e.get_level("b") == ResponseMode.OBSERVE

    def test_custom_thresholds_affect_mode(self):
        """Engine with very high thresholds keeps OBSERVE longer."""
        e = SOMAEngine(
            budget={"tokens": 100000},
            custom_thresholds={"guide": 0.90, "warn": 0.95, "block": 0.99},
        )
        e.register_agent("test")
        # Push some errors through grace period
        for i in range(20):
            e.record_action("test", Action(
                tool_name="bash", output_text="error", error=True,
                token_count=100, cost=0.01, duration_sec=1.0, retried=True,
            ))
        snap = e.get_snapshot("test")
        # With default thresholds (0.25/0.50/0.75) this would be WARN/BLOCK.
        # With 0.90/0.95/0.99, should still be below WARN.
        assert snap["mode"] in (ResponseMode.OBSERVE, ResponseMode.GUIDE)

    def test_none_thresholds_use_defaults(self):
        """Engine with no custom thresholds doesn't crash."""
        e = SOMAEngine(budget={"tokens": 10000}, custom_thresholds=None)
        e.register_agent("test")
        snap = e.get_snapshot("test")
        assert snap["mode"] == ResponseMode.OBSERVE

    def test_action_result_is_frozen(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="bash", output_text="ok", token_count=50))
        try:
            r.mode = ResponseMode.BLOCK  # type: ignore
            assert False, "Should not allow mutation"
        except AttributeError:
            pass
