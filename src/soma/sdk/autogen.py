"""SomaAutoGenMonitor — instrument AutoGen agents transparently.

Requires: pyautogen (pip install pyautogen)

Usage:
    from autogen import ConversableAgent
    from soma.sdk.autogen import SomaAutoGenMonitor

    engine = soma.quickstart(budget={"tokens": 100000})
    monitor = SomaAutoGenMonitor(engine)

    assistant = ConversableAgent("assistant", ...)
    user = ConversableAgent("user_proxy", ...)

    monitor.attach(assistant)
    monitor.attach(user)

    user.initiate_chat(assistant, message="Do the task")
"""

from __future__ import annotations

import time
from typing import Any

from soma.engine import SOMAEngine
from soma.types import Action

try:
    import autogen  # noqa: F401
    _AUTOGEN_AVAILABLE = True
except ImportError:
    _AUTOGEN_AVAILABLE = False


def _require_autogen() -> None:
    if not _AUTOGEN_AVAILABLE:
        raise ImportError(
            "pyautogen is required for SomaAutoGenMonitor. "
            "Install it with: pip install pyautogen"
        )


class SomaAutoGenMonitor:
    """Instruments AutoGen ConversableAgents by patching message generation.

    Each agent's ``generate_reply()`` call is wrapped to record the
    conversation turn into SOMA. One Action is recorded per reply.

    The agent_id in SOMA is derived from the AutoGen agent's ``name``
    attribute. All monitored agents are auto-registered on first use.
    """

    def __init__(self, engine: SOMAEngine) -> None:
        _require_autogen()
        self._engine = engine
        self._patched: set[int] = set()

    def attach(self, agent: Any) -> None:
        """Wrap an AutoGen agent's generate_reply() to record actions."""
        if id(agent) in self._patched:
            return
        self._patched.add(id(agent))

        original_generate = agent.generate_reply
        agent_id = getattr(agent, "name", f"autogen-agent-{id(agent)}")

        if agent_id not in self._engine._agents:
            self._engine.register_agent(agent_id)

        engine = self._engine

        def _wrapped_generate(
            messages: list[dict] | None = None,
            sender: Any = None,
            **kwargs: Any,
        ) -> Any:
            start = time.time()
            error = False
            output = ""
            try:
                reply = original_generate(messages=messages, sender=sender, **kwargs)
                if isinstance(reply, str):
                    output = reply[:4000]
                elif isinstance(reply, dict):
                    output = str(reply.get("content", ""))[:4000]
                return reply
            except Exception as exc:
                error = True
                output = str(exc)
                raise
            finally:
                # Estimate token count from message length
                total_chars = sum(len(str(m.get("content", ""))) for m in (messages or []))
                token_estimate = total_chars // 4

                engine.record_action(
                    agent_id,
                    Action(
                        tool_name="generate_reply",
                        output_text=output,
                        error=error,
                        token_count=token_estimate,
                        duration_sec=time.time() - start,
                    ),
                )

        agent.generate_reply = _wrapped_generate
