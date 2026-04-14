"""SOMA Guidance State — cooldown, escalation, and throttle tracking."""

from __future__ import annotations

from dataclasses import dataclass, replace


INVESTIGATION_TOOLS = frozenset({"Read", "Grep", "Glob"})

_SIGNAL_TOOL_MAP: dict[str, str] = {
    "error_rate": "Bash",
    "uncertainty": "Bash",
    "drift": "Agent",
}


@dataclass(frozen=True, slots=True)
class GuidanceState:
    """Per-agent guidance escalation state. Stored in circuit file."""

    dominant_signal: str = ""
    last_guidance_action_num: int = 0
    ignore_count: int = 0
    escalation_level: int = 0
    throttled_tool: str = ""
    throttle_remaining: int = 0

    def in_cooldown(self, action_num: int, cooldown_actions: int = 5) -> bool:
        if self.last_guidance_action_num == 0:
            return False
        return (action_num - self.last_guidance_action_num) < cooldown_actions

    def after_guidance(self, action_num: int, dominant_signal: str) -> GuidanceState:
        return replace(self, last_guidance_action_num=action_num, dominant_signal=dominant_signal)

    def escalate(self, max_level: int = 3) -> GuidanceState:
        new_level = min(self.escalation_level + 1, max_level)
        tool = ""
        remaining = 0
        if new_level >= 3:
            tool = _SIGNAL_TOOL_MAP.get(self.dominant_signal, "")
            remaining = 3 if tool else 0
            new_level = 3 if tool else min(new_level, 2)
        return replace(self, escalation_level=new_level, ignore_count=self.ignore_count + 1,
                       throttled_tool=tool, throttle_remaining=remaining)

    def reset_escalation(self) -> GuidanceState:
        return replace(self, escalation_level=0, ignore_count=0)

    def reset_after_throttle(self) -> GuidanceState:
        return replace(self, escalation_level=1, throttled_tool="", throttle_remaining=0)

    def decrement_throttle(self) -> GuidanceState:
        return replace(self, throttle_remaining=max(0, self.throttle_remaining - 1))

    def to_dict(self) -> dict:
        return {
            "dominant_signal": self.dominant_signal,
            "last_guidance_action_num": self.last_guidance_action_num,
            "ignore_count": self.ignore_count,
            "escalation_level": self.escalation_level,
            "throttled_tool": self.throttled_tool,
            "throttle_remaining": self.throttle_remaining,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GuidanceState:
        return cls(
            dominant_signal=data.get("dominant_signal", ""),
            last_guidance_action_num=data.get("last_guidance_action_num", 0),
            ignore_count=data.get("ignore_count", 0),
            escalation_level=data.get("escalation_level", 0),
            throttled_tool=data.get("throttled_tool", ""),
            throttle_remaining=data.get("throttle_remaining", 0),
        )
