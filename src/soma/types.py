"""Shared types for SOMA Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResponseMode(Enum):
    """Guidance response modes — ordered by severity."""
    OBSERVE = 0   # p=0-25%: silent, metrics only
    GUIDE = 1     # p=25-50%: soft suggestions
    WARN = 2      # p=50-75%: insistent warnings
    BLOCK = 3     # p=75-100%: block destructive ops only

    # Legacy aliases — map old names to new values. Remove in 0.5.0.
    HEALTHY = 0       # → OBSERVE
    CAUTION = 1       # → GUIDE
    DEGRADE = 2       # → WARN
    QUARANTINE = 3    # → BLOCK
    RESTART = 3       # → BLOCK (restart removed, map to highest)
    SAFE_MODE = 3     # → BLOCK (safe_mode removed, map to highest)

    def __lt__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value >= other.value


# Deprecated alias — will be removed in 0.5.0
Level = ResponseMode


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
class PressureVector:
    """Per-signal pressure components propagated through the trust graph.

    Allows downstream agents to react precisely to the *cause* of upstream
    pressure rather than only to the aggregate scalar.
    """
    uncertainty: float = 0.0
    drift: float = 0.0
    error_rate: float = 0.0
    cost: float = 0.0

    def to_dict(self) -> "dict[str, float]":
        return {
            "uncertainty": self.uncertainty,
            "drift": self.drift,
            "error_rate": self.error_rate,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, d: "dict[str, float]") -> "PressureVector":
        return cls(
            uncertainty=d.get("uncertainty", 0.0),
            drift=d.get("drift", 0.0),
            error_rate=d.get("error_rate", 0.0),
            cost=d.get("cost", 0.0),
        )


@dataclass(frozen=True, slots=True)
class VitalsSnapshot:
    """All vitals at a point in time."""
    uncertainty: float = 0.0
    drift: float = 0.0
    drift_mode: DriftMode = DriftMode.INFORMATIONAL
    token_usage: float = 0.0
    cost: float = 0.0
    error_rate: float = 0.0
    goal_coherence: float | None = None        # None during warmup (< 5 actions)
    baseline_integrity: bool = True            # True = baseline is healthy
    uncertainty_type: str | None = None        # "epistemic", "aleatoric", or None
    task_complexity: float | None = None       # None until first action sets it
    predicted_success_rate: float | None = None  # None when no fingerprint history
    half_life_warning: bool = False            # True when approaching/past half-life
    calibration_score: float | None = None    # None during warmup (< 3 actions)
    verbal_behavioral_divergence: bool = False  # True = confident language + high pressure


@dataclass
class AgentConfig:
    """Configuration for a monitored agent."""
    agent_id: str
    autonomy: AutonomyMode = AutonomyMode.HUMAN_ON_THE_LOOP
    system_prompt: str = ""
    tools_allowed: list[str] = field(default_factory=list)
    expensive_tools: list[str] = field(default_factory=list)
    minimal_tools: list[str] = field(default_factory=list)
