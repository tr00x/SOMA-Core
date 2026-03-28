"""SOMA custom exceptions with helpful error messages."""

from __future__ import annotations


class SOMAError(Exception):
    """Base SOMA error with helpful message."""
    pass


class AgentNotFound(SOMAError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Agent '{agent_id}' not found. "
            f"Register it first: engine.register_agent('{agent_id}')"
        )


class NoBudget(SOMAError):
    def __init__(self) -> None:
        super().__init__(
            "No budget configured. "
            "Set one: SOMAEngine(budget={'tokens': 100000})"
        )
