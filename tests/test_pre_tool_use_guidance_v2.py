"""Integration tests for Smart Guidance v2 in pre_tool_use."""
import pytest
from soma.guidance_state import GuidanceState, INVESTIGATION_TOOLS


class TestCooldownSuppression:
    def test_in_cooldown_when_recent(self):
        gs = GuidanceState(last_guidance_action_num=10)
        assert gs.in_cooldown(action_num=12, cooldown_actions=5)

    def test_not_in_cooldown_when_expired(self):
        gs = GuidanceState(last_guidance_action_num=10)
        assert not gs.in_cooldown(action_num=16, cooldown_actions=5)


class TestEscalationLadder:
    def test_escalation_from_0_to_1(self):
        gs = GuidanceState(escalation_level=0)
        gs2 = gs.escalate(max_level=3)
        assert gs2.escalation_level == 1

    def test_resets_on_improvement(self):
        gs = GuidanceState(escalation_level=2, ignore_count=2)
        gs2 = gs.reset_escalation()
        assert gs2.escalation_level == 0


class TestThrottleEnforcement:
    def test_throttled_tool(self):
        gs = GuidanceState(escalation_level=3, throttled_tool="Bash", throttle_remaining=3)
        assert gs.throttled_tool == "Bash"
        assert gs.throttle_remaining > 0

    def test_investigation_tools_never_throttled(self):
        assert "Read" in INVESTIGATION_TOOLS
        assert "Grep" in INVESTIGATION_TOOLS
        assert "Glob" in INVESTIGATION_TOOLS

    def test_throttle_decrements_and_resets(self):
        gs = GuidanceState(escalation_level=3, throttled_tool="Bash", throttle_remaining=1)
        gs2 = gs.decrement_throttle()
        assert gs2.throttle_remaining == 0
        gs3 = gs2.reset_after_throttle()
        assert gs3.escalation_level == 1
        assert gs3.throttled_tool == ""
