"""Claude Code managed wrapper for SOMA Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from soma.engine import SOMAEngine, ActionResult
from soma.types import Action, Level, AutonomyMode
from soma.recorder import SessionRecorder


@dataclass(frozen=True, slots=True)
class WrapperResult:
    level: Level
    pressure: float
    vitals: Any
    context_action: str  # "pass" | "truncate" | "block_tools" | "restart"
    blocked_tools: list[str]


_CONTEXT_ACTIONS: dict[Level, str] = {
    Level.HEALTHY: "pass",
    Level.CAUTION: "truncate",
    Level.DEGRADE: "block_tools",
    Level.QUARANTINE: "restart",
    Level.RESTART: "restart",
    Level.SAFE_MODE: "restart",
}


class ClaudeCodeWrapper:
    """Managed wrapper for Claude Code — persistent middleware."""

    def __init__(self, budget: dict[str, float] | None = None) -> None:
        self._engine = SOMAEngine(budget=budget)
        self._recorder = SessionRecorder()
        # Store per-agent expensive_tools for tool blocking decisions
        self._expensive_tools: dict[str, list[str]] = {}

    def register_agent(
        self,
        agent_id: str,
        autonomy: AutonomyMode = AutonomyMode.HUMAN_ON_THE_LOOP,
        tools: list[str] | None = None,
        expensive_tools: list[str] | None = None,
    ) -> None:
        self._engine.register_agent(agent_id, autonomy=autonomy, tools=tools)
        self._expensive_tools[agent_id] = expensive_tools or []

    def add_edge(self, source: str, target: str, trust_weight: float = 0.8) -> None:
        self._engine.add_edge(source, target, trust_weight)

    def get_level(self, agent_id: str) -> Level:
        return self._engine.get_level(agent_id)

    def on_action(self, agent_id: str, action: Action) -> WrapperResult:
        """Record action in engine and recorder; map level to context_action."""
        # Record in session recorder
        self._recorder.record(agent_id, action)

        # Process through engine
        result: ActionResult = self._engine.record_action(agent_id, action)

        level = result.level
        context_action = _CONTEXT_ACTIONS[level]

        # Determine blocked tools based on level
        blocked: list[str] = []
        if level >= Level.DEGRADE:
            blocked = list(self._expensive_tools.get(agent_id, []))

        return WrapperResult(
            level=level,
            pressure=result.pressure,
            vitals=result.vitals,
            context_action=context_action,
            blocked_tools=blocked,
        )

    def should_block_tool(self, agent_id: str, tool_name: str) -> bool:
        """Return True if the tool should be blocked for the given agent."""
        level = self._engine.get_level(agent_id)
        if level < Level.DEGRADE:
            return False
        return tool_name in self._expensive_tools.get(agent_id, [])

    def get_recording(self) -> SessionRecorder:
        return self._recorder

    def get_snapshot(self, agent_id: str) -> dict[str, Any]:
        return self._engine.get_snapshot(agent_id)

    @property
    def events(self):
        return self._engine.events

    @property
    def budget(self):
        return self._engine.budget
