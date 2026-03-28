"""Shared types for SOMA Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Level(Enum):
    """Escalation levels — ordered by severity."""
    HEALTHY = 0
    CAUTION = 1
    DEGRADE = 2
    QUARANTINE = 3
    RESTART = 4
    SAFE_MODE = 5

    def __lt__(self, other: Level) -> bool:
        if not isinstance(other, Level):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: Level) -> bool:
        if not isinstance(other, Level):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: Level) -> bool:
        if not isinstance(other, Level):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: Level) -> bool:
        if not isinstance(other, Level):
            return NotImplemented
        return self.value >= other.value


class AutonomyMode(Enum):
    FULLY_AUTONOMOUS = "fully_autonomous"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    HUMAN_ON_THE_LOOP = "human_on_the_loop"


class DriftMode(Enum):
    INFORMATIONAL = "informational"
    DIRECTIVE = "directive"


class InterventionOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class Action:
    """A single agent action recorded by SOMA."""
    tool_name: str
    output_text: str
    token_count: int = 0
    cost: float = 0.0
    error: bool = False
    retried: bool = False
    duration_sec: float = 0.0
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VitalsSnapshot:
    """All vitals at a point in time."""
    uncertainty: float = 0.0
    drift: float = 0.0
    drift_mode: DriftMode = DriftMode.INFORMATIONAL
    token_usage: float = 0.0
    cost: float = 0.0
    error_rate: float = 0.0


@dataclass
class AgentConfig:
    """Configuration for a monitored agent."""
    agent_id: str
    autonomy: AutonomyMode = AutonomyMode.HUMAN_ON_THE_LOOP
    system_prompt: str = ""
    tools_allowed: list[str] = field(default_factory=list)
    expensive_tools: list[str] = field(default_factory=list)
    minimal_tools: list[str] = field(default_factory=list)
