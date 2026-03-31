"""soma.track() — universal context manager for recording any agent action.

Drop-in for any Python agent framework. No external dependencies.

Usage:
    engine = soma.quickstart(budget={"tokens": 50000})
    engine.register_agent("my-agent")

    with soma.track(engine, "my-agent", "bash") as t:
        result = subprocess.run(["ls"], capture_output=True, text=True)
        t.set_output(result.stdout)
        t.set_error(result.returncode != 0)

    print(t.result.mode)   # ResponseMode.OBSERVE / GUIDE / WARN / BLOCK
    print(t.result.pressure)
"""

from __future__ import annotations

import time
from typing import Any

from soma.types import Action
from soma.engine import SOMAEngine, ActionResult


class SomaTracker:
    """Context manager that records a single agent action when it exits.

    Set output_text, error, token_count, and cost during execution.
    After the block, .result contains the full ActionResult.
    """

    def __init__(
        self,
        engine: SOMAEngine,
        agent_id: str,
        tool_name: str,
        token_count: int = 0,
        cost: float = 0.0,
    ) -> None:
        self._engine = engine
        self._agent_id = agent_id
        self._tool_name = tool_name
        self._output_text: str = ""
        self._error: bool = False
        self._retried: bool = False
        self._token_count: int = token_count
        self._cost: float = cost
        self._start_time: float = 0.0
        self.result: ActionResult | None = None

    # ------------------------------------------------------------------
    # Setters — call inside the with-block
    # ------------------------------------------------------------------

    def set_output(self, text: str) -> None:
        """Set the action's output text."""
        self._output_text = text

    def set_error(self, error: bool) -> None:
        """Mark the action as errored."""
        self._error = error

    def set_retried(self, retried: bool) -> None:
        """Mark the action as a retry."""
        self._retried = retried

    def set_tokens(self, count: int) -> None:
        """Set the token count for this action."""
        self._token_count = count

    def set_cost(self, cost: float) -> None:
        """Set the cost incurred by this action."""
        self._cost = cost

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "SomaTracker":
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        duration = time.time() - self._start_time
        if exc_type is not None:
            self._error = True
            if not self._output_text:
                self._output_text = str(exc_val)
        self.result = self._engine.record_action(
            self._agent_id,
            Action(
                tool_name=self._tool_name,
                output_text=self._output_text,
                error=self._error,
                retried=self._retried,
                token_count=self._token_count,
                cost=self._cost,
                duration_sec=duration,
            ),
        )
        return False  # never suppress exceptions


def track(
    engine: SOMAEngine,
    agent_id: str,
    tool_name: str,
    token_count: int = 0,
    cost: float = 0.0,
) -> SomaTracker:
    """Return a context manager that records a single agent action.

    Args:
        engine:     SOMAEngine instance to record into.
        agent_id:   Registered agent identifier.
        tool_name:  Name of the tool or operation being executed.
        token_count: Optional pre-known token count (can also be set via tracker.set_tokens()).
        cost:       Optional pre-known cost in USD.

    Example::

        with soma.track(engine, "agent-1", "Bash") as t:
            out = subprocess.run(cmd, capture_output=True, text=True)
            t.set_output(out.stdout)
            t.set_error(out.returncode != 0)
        # t.result is now available
    """
    return SomaTracker(engine, agent_id, tool_name, token_count=token_count, cost=cost)
