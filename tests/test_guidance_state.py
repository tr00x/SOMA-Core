import pytest
from soma.guidance_state import GuidanceState, INVESTIGATION_TOOLS, _SIGNAL_TOOL_MAP


class TestGuidanceStateDefaults:
    def test_defaults(self):
        gs = GuidanceState()
        assert gs.dominant_signal == ""
        assert gs.last_guidance_action_num == 0
        assert gs.ignore_count == 0
        assert gs.escalation_level == 0
        assert gs.throttled_tool == ""
        assert gs.throttle_remaining == 0

    def test_frozen(self):
        gs = GuidanceState()
        with pytest.raises(AttributeError):
            gs.escalation_level = 5  # type: ignore[misc]


class TestInCooldown:
    def test_no_prior_guidance(self):
        gs = GuidanceState()
        assert gs.in_cooldown(10) is False

    def test_within_cooldown(self):
        gs = GuidanceState(last_guidance_action_num=10)
        assert gs.in_cooldown(12) is True
        assert gs.in_cooldown(14) is True

    def test_exactly_at_cooldown_boundary(self):
        gs = GuidanceState(last_guidance_action_num=10)
        assert gs.in_cooldown(15) is False

    def test_past_cooldown(self):
        gs = GuidanceState(last_guidance_action_num=10)
        assert gs.in_cooldown(20) is False

    def test_custom_cooldown_window(self):
        gs = GuidanceState(last_guidance_action_num=10)
        assert gs.in_cooldown(12, cooldown_actions=2) is False
        assert gs.in_cooldown(11, cooldown_actions=2) is True


class TestAfterGuidance:
    def test_records_action_and_signal(self):
        gs = GuidanceState()
        new = gs.after_guidance(action_num=42, dominant_signal="error_rate")
        assert new.last_guidance_action_num == 42
        assert new.dominant_signal == "error_rate"
        # Original unchanged
        assert gs.last_guidance_action_num == 0

    def test_preserves_other_fields(self):
        gs = GuidanceState(escalation_level=2, ignore_count=3)
        new = gs.after_guidance(action_num=10, dominant_signal="drift")
        assert new.escalation_level == 2
        assert new.ignore_count == 3


class TestEscalate:
    def test_increments_level(self):
        gs = GuidanceState()
        e1 = gs.escalate()
        assert e1.escalation_level == 1
        assert e1.ignore_count == 1

    def test_escalate_twice(self):
        gs = GuidanceState()
        e2 = gs.escalate().escalate()
        assert e2.escalation_level == 2
        assert e2.ignore_count == 2

    def test_escalate_to_throttle_with_known_signal(self):
        gs = GuidanceState(dominant_signal="error_rate", escalation_level=2, ignore_count=2)
        e3 = gs.escalate()
        assert e3.escalation_level == 3
        assert e3.throttled_tool == "Bash"
        assert e3.throttle_remaining == 3
        assert e3.ignore_count == 3

    def test_escalate_to_throttle_drift(self):
        gs = GuidanceState(dominant_signal="drift", escalation_level=2, ignore_count=2)
        e3 = gs.escalate()
        assert e3.throttled_tool == "Agent"
        assert e3.throttle_remaining == 3

    def test_escalate_caps_at_max(self):
        gs = GuidanceState(dominant_signal="error_rate", escalation_level=3, ignore_count=5)
        e = gs.escalate()
        assert e.escalation_level == 3
        assert e.ignore_count == 6

    def test_escalate_unknown_signal_caps_at_2(self):
        gs = GuidanceState(dominant_signal="unknown_signal", escalation_level=2, ignore_count=2)
        e3 = gs.escalate()
        assert e3.escalation_level == 2
        assert e3.throttled_tool == ""
        assert e3.throttle_remaining == 0

    def test_escalate_no_signal_caps_at_2(self):
        gs = GuidanceState(dominant_signal="", escalation_level=2, ignore_count=2)
        e3 = gs.escalate()
        assert e3.escalation_level == 2

    def test_custom_max_level(self):
        gs = GuidanceState(escalation_level=1)
        e = gs.escalate(max_level=2)
        assert e.escalation_level == 2


class TestResetEscalation:
    def test_resets_level_and_count(self):
        gs = GuidanceState(escalation_level=3, ignore_count=5)
        r = gs.reset_escalation()
        assert r.escalation_level == 0
        assert r.ignore_count == 0

    def test_preserves_other_fields(self):
        gs = GuidanceState(dominant_signal="drift", last_guidance_action_num=50,
                           escalation_level=2, ignore_count=3)
        r = gs.reset_escalation()
        assert r.dominant_signal == "drift"
        assert r.last_guidance_action_num == 50


class TestResetAfterThrottle:
    def test_drops_to_level_1(self):
        gs = GuidanceState(escalation_level=3, throttled_tool="Bash", throttle_remaining=1)
        r = gs.reset_after_throttle()
        assert r.escalation_level == 1
        assert r.throttled_tool == ""
        assert r.throttle_remaining == 0


class TestDecrementThrottle:
    def test_decrements(self):
        gs = GuidanceState(throttle_remaining=3)
        d = gs.decrement_throttle()
        assert d.throttle_remaining == 2

    def test_floor_at_zero(self):
        gs = GuidanceState(throttle_remaining=0)
        d = gs.decrement_throttle()
        assert d.throttle_remaining == 0


class TestSerialization:
    def test_roundtrip(self):
        gs = GuidanceState(
            dominant_signal="error_rate",
            last_guidance_action_num=42,
            ignore_count=3,
            escalation_level=2,
            throttled_tool="Bash",
            throttle_remaining=1,
        )
        d = gs.to_dict()
        restored = GuidanceState.from_dict(d)
        assert restored == gs

    def test_from_empty_dict(self):
        gs = GuidanceState.from_dict({})
        assert gs == GuidanceState()

    def test_from_partial_dict(self):
        gs = GuidanceState.from_dict({"dominant_signal": "drift", "escalation_level": 1})
        assert gs.dominant_signal == "drift"
        assert gs.escalation_level == 1
        assert gs.ignore_count == 0

    def test_to_dict_keys(self):
        gs = GuidanceState()
        d = gs.to_dict()
        expected_keys = {"dominant_signal", "last_guidance_action_num", "ignore_count",
                         "escalation_level", "throttled_tool", "throttle_remaining"}
        assert set(d.keys()) == expected_keys


class TestModuleConstants:
    def test_investigation_tools(self):
        assert "Read" in INVESTIGATION_TOOLS
        assert "Grep" in INVESTIGATION_TOOLS
        assert "Glob" in INVESTIGATION_TOOLS
        assert "Bash" not in INVESTIGATION_TOOLS

    def test_signal_tool_map(self):
        assert _SIGNAL_TOOL_MAP["error_rate"] == "Bash"
        assert _SIGNAL_TOOL_MAP["uncertainty"] == "Bash"
        assert _SIGNAL_TOOL_MAP["drift"] == "Agent"
