"""SomaLangChainCallback — instrument LangChain agents transparently.

Requires: langchain-core (pip install langchain-core)

Usage:
    from langchain_openai import ChatOpenAI
    from soma.sdk.langchain import SomaLangChainCallback

    engine = soma.quickstart(budget={"tokens": 50000})
    engine.register_agent("lc-agent")

    llm = ChatOpenAI(callbacks=[SomaLangChainCallback(engine, "lc-agent")])
    # Every LLM call and tool use is now monitored by SOMA.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from soma.engine import SOMAEngine
from soma.types import Action

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    # Stub so the class definition doesn't fail at import time
    BaseCallbackHandler = object  # type: ignore[assignment,misc]
    _LANGCHAIN_AVAILABLE = False


def _require_langchain() -> None:
    if not _LANGCHAIN_AVAILABLE:
        raise ImportError(
            "langchain-core is required for SomaLangChainCallback. "
            "Install it with: pip install langchain-core"
        )


class SomaLangChainCallback(BaseCallbackHandler):
    """LangChain callback handler that records every LLM call and tool use.

    Attach to any LangChain LLM, chain, or agent as a callback.
    SOMA receives one Action per LLM invocation and per tool use.
    """

    def __init__(self, engine: SOMAEngine, agent_id: str) -> None:
        _require_langchain()
        super().__init__()
        self._engine = engine
        self._agent_id = agent_id
        # run_id → (start_time, tool_name)
        self._pending: dict[str, tuple[float, str]] = {}

    # ------------------------------------------------------------------
    # LLM callbacks
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._pending[str(run_id)] = (time.time(), "llm")

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start, tool_name = self._pending.pop(str(run_id), (time.time(), "llm"))
        duration = time.time() - start

        # Extract token count and output text from LLMResult
        token_count = 0
        output_text = ""
        try:
            if hasattr(response, "generations"):
                for gen_list in response.generations:
                    for gen in gen_list:
                        output_text += getattr(gen, "text", "")
            if hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                token_count = usage.get("total_tokens", 0)
        except Exception:
            pass

        self._engine.record_action(
            self._agent_id,
            Action(
                tool_name=tool_name,
                output_text=output_text[:4000],
                token_count=token_count,
                duration_sec=duration,
            ),
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start, tool_name = self._pending.pop(str(run_id), (time.time(), "llm"))
        self._engine.record_action(
            self._agent_id,
            Action(
                tool_name=tool_name,
                output_text=str(error),
                error=True,
                duration_sec=time.time() - start,
            ),
        )

    # ------------------------------------------------------------------
    # Tool callbacks
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "tool")
        self._pending[str(run_id)] = (time.time(), tool_name)

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start, tool_name = self._pending.pop(str(run_id), (time.time(), "tool"))
        self._engine.record_action(
            self._agent_id,
            Action(
                tool_name=tool_name,
                output_text=str(output)[:4000],
                duration_sec=time.time() - start,
            ),
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start, tool_name = self._pending.pop(str(run_id), (time.time(), "tool"))
        self._engine.record_action(
            self._agent_id,
            Action(
                tool_name=tool_name,
                output_text=str(error),
                error=True,
                duration_sec=time.time() - start,
            ),
        )
