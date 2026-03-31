"""SomaCrewObserver — instrument CrewAI crews transparently.

Requires: crewai (pip install crewai)

Usage:
    from crewai import Crew, Agent, Task
    from soma.sdk.crewai import SomaCrewObserver

    engine = soma.quickstart(budget={"tokens": 100000})
    observer = SomaCrewObserver(engine)

    crew = Crew(agents=[...], tasks=[...])
    observer.attach(crew)
    result = crew.kickoff()
"""

from __future__ import annotations

import time
from typing import Any

from soma.engine import SOMAEngine
from soma.types import Action

try:
    import crewai  # noqa: F401
    _CREWAI_AVAILABLE = True
except ImportError:
    _CREWAI_AVAILABLE = False


def _require_crewai() -> None:
    if not _CREWAI_AVAILABLE:
        raise ImportError(
            "crewai is required for SomaCrewObserver. "
            "Install it with: pip install crewai"
        )


class SomaCrewObserver:
    """Instruments a CrewAI crew by patching agent task execution.

    Each agent's ``execute_task()`` method is wrapped to record start time,
    output text, and errors into SOMA. One Action is recorded per task
    execution per agent.

    The agent_id in SOMA is derived from the CrewAI agent's ``role`` attribute.
    All observed agents are auto-registered on first use.
    """

    def __init__(self, engine: SOMAEngine) -> None:
        _require_crewai()
        self._engine = engine
        self._patched: set[int] = set()  # object ids of patched agents

    def attach(self, crew: Any) -> None:
        """Patch all agents in a Crew to record their task executions."""
        for agent in getattr(crew, "agents", []):
            self._patch_agent(agent)

    def _patch_agent(self, agent: Any) -> None:
        if id(agent) in self._patched:
            return
        self._patched.add(id(agent))

        original_execute = agent.execute_task

        # Register in SOMA using agent role as ID
        agent_id = getattr(agent, "role", f"crewai-agent-{id(agent)}")
        if agent_id not in self._engine._agents:
            self._engine.register_agent(agent_id)

        engine = self._engine

        def _wrapped_execute(task: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.time()
            tool_name = f"task:{getattr(task, 'description', 'unknown')[:40]}"
            error = False
            output = ""
            try:
                result = original_execute(task, *args, **kwargs)
                output = str(result)[:4000]
                return result
            except Exception as exc:
                error = True
                output = str(exc)
                raise
            finally:
                engine.record_action(
                    agent_id,
                    Action(
                        tool_name=tool_name,
                        output_text=output,
                        error=error,
                        duration_sec=time.time() - start,
                    ),
                )

        agent.execute_task = _wrapped_execute
