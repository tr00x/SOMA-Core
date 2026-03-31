"""soma.wrap() — Universal API client wrapper. SOMA sits ABOVE all agents.

Usage:
    import anthropic
    import soma

    client = soma.wrap(anthropic.Anthropic(), budget={"tokens": 50000})

    # Every API call is now monitored and controlled by SOMA.
    # If pressure is too high — call is blocked.
    # If budget is exhausted — call is blocked.
    # Dashboard shows everything in real time.
"""

from __future__ import annotations

import time
import inspect
import functools
from typing import Any

from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode
from soma.recorder import SessionRecorder


class SomaBlocked(Exception):
    """Raised when SOMA blocks an API call due to high pressure."""
    def __init__(self, agent_id: str, level: ResponseMode, pressure: float):
        self.agent_id = agent_id
        self.level = level
        self.pressure = pressure
        super().__init__(
            f"SOMA blocked call for '{agent_id}': "
            f"level={level.name}, pressure={pressure:.3f}"
        )


class SomaBudgetExhausted(Exception):
    """Raised when SOMA blocks an API call due to exhausted budget."""
    def __init__(self, dimension: str):
        self.dimension = dimension
        super().__init__(f"SOMA budget exhausted: {dimension}")


class SomaStreamContext:
    """Sync context manager that wraps an Anthropic streaming response.

    Accumulates text chunks and records a single Action when the stream
    completes (or errors).
    """

    def __init__(self, stream: Any, wrapped_client: WrappedClient, tool_name: str) -> None:
        self._stream = stream
        self._wrapped = wrapped_client
        self._tool_name = tool_name
        self._accumulated_text = ""
        self._start: float = 0.0
        self._error = False

    def __enter__(self) -> SomaStreamContext:
        self._start = time.time()
        self._stream.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self._error = True
        try:
            self._stream.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._record_stream_action()

    @property
    def text_stream(self) -> Any:
        """Yields text chunks from the underlying stream, accumulating text."""
        try:
            for chunk in self._stream.text_stream:
                self._accumulated_text += chunk
                yield chunk
        except Exception:
            self._error = True
            raise

    def get_final_message(self) -> Any:
        """Delegate to underlying stream's get_final_message."""
        return self._stream.get_final_message()

    def _record_stream_action(self) -> None:
        """Record the accumulated stream as a single Action."""
        duration = time.time() - self._start
        # Try to get token count from final message
        token_count = 0
        try:
            final = self._stream.get_final_message()
            _, token_count = self._wrapped._extract_response_data(final)
        except Exception:
            pass

        text = self._accumulated_text or ""

        # Fallback: estimate tokens from text
        if token_count == 0 and text:
            token_count = len(text) // 4

        action = Action(
            tool_name=self._tool_name,
            output_text=text[:1000],
            token_count=token_count,
            cost=self._wrapped._estimate_cost(token_count),
            error=self._error,
            duration_sec=duration,
        )
        result = self._wrapped._engine.record_action(self._wrapped._agent_id, action)
        self._wrapped._pending_context_action = result.context_action
        self._wrapped._recorder.record(self._wrapped._agent_id, action)


class AsyncSomaStreamContext:
    """Async context manager that wraps an Anthropic async streaming response."""

    def __init__(self, stream: Any, wrapped_client: WrappedClient, tool_name: str) -> None:
        self._stream = stream
        self._wrapped = wrapped_client
        self._tool_name = tool_name
        self._accumulated_text = ""
        self._start: float = 0.0
        self._error = False

    async def __aenter__(self) -> AsyncSomaStreamContext:
        self._start = time.time()
        await self._stream.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self._error = True
        try:
            await self._stream.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self._record_stream_action()

    @property
    def text_stream(self) -> Any:
        """Returns an async generator that yields text chunks."""
        return self._async_text_stream()

    async def _async_text_stream(self) -> Any:
        async for chunk in self._stream.text_stream:
            self._accumulated_text += chunk
            yield chunk

    def get_final_message(self) -> Any:
        return self._stream.get_final_message()

    def _record_stream_action(self) -> None:
        duration = time.time() - self._start
        token_count = 0
        try:
            final = self._stream.get_final_message()
            _, token_count = self._wrapped._extract_response_data(final)
        except Exception:
            pass

        text = self._accumulated_text or ""
        if token_count == 0 and text:
            token_count = len(text) // 4

        action = Action(
            tool_name=self._tool_name,
            output_text=text[:1000],
            token_count=token_count,
            cost=self._wrapped._estimate_cost(token_count),
            error=self._error,
            duration_sec=duration,
        )
        result = self._wrapped._engine.record_action(self._wrapped._agent_id, action)
        self._wrapped._pending_context_action = result.context_action
        self._wrapped._recorder.record(self._wrapped._agent_id, action)


class SomaStreamIterator:
    """Wraps an OpenAI streaming iterator, accumulates chunks, records Action when done."""

    def __init__(self, iterator: Any, wrapped_client: WrappedClient, tool_name: str) -> None:
        self._iterator = iterator
        self._wrapped = wrapped_client
        self._tool_name = tool_name
        self._accumulated_text = ""
        self._start = time.time()
        self._recorded = False

    def __iter__(self) -> SomaStreamIterator:
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._iterator)
            # Accumulate delta content
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    self._accumulated_text += delta.content
            return chunk
        except StopIteration:
            self._record()
            raise

    def _record(self) -> None:
        if self._recorded:
            return
        self._recorded = True
        duration = time.time() - self._start
        text = self._accumulated_text
        token_count = len(text) // 4 if text else 0

        action = Action(
            tool_name=self._tool_name,
            output_text=text[:1000],
            token_count=token_count,
            cost=self._wrapped._estimate_cost(token_count),
            error=False,
            duration_sec=duration,
        )
        result = self._wrapped._engine.record_action(self._wrapped._agent_id, action)
        self._wrapped._pending_context_action = result.context_action
        self._wrapped._recorder.record(self._wrapped._agent_id, action)


class WrappedClient:
    """Proxy around an API client. Intercepts all LLM calls."""

    def __init__(
        self,
        client: Any,
        engine: SOMAEngine,
        agent_id: str = "default",
        auto_export: bool = True,
        block_at: ResponseMode = ResponseMode.BLOCK,
    ) -> None:
        self._client = client
        self._engine = engine
        self._agent_id = agent_id
        self._auto_export = auto_export
        self._block_at = block_at
        self._recorder = SessionRecorder()
        self._pending_context_action = "pass"

        # Push auto_export into the engine so record_action() handles it
        self._engine._auto_export = auto_export

        # Register agent if not already
        from soma.errors import AgentNotFound
        try:
            engine.get_level(agent_id)
        except (KeyError, AgentNotFound):
            engine.register_agent(agent_id)

        # Wrap the API methods
        self._wrap_client()

    @property
    def engine(self) -> SOMAEngine:
        return self._engine

    @property
    def recorder(self) -> SessionRecorder:
        return self._recorder

    @property
    def soma_level(self) -> ResponseMode:
        return self._engine.get_level(self._agent_id)

    @property
    def soma_pressure(self) -> float:
        return self._engine.get_snapshot(self._agent_id)["pressure"]

    def _wrap_client(self) -> None:
        """Detect client type and wrap the appropriate methods."""
        client = self._client

        # Anthropic SDK: client.messages.create(...)
        if hasattr(client, "messages") and hasattr(client.messages, "create"):
            original_create = client.messages.create
            if inspect.iscoroutinefunction(original_create):
                client.messages.create = self._make_async_wrapper(original_create, "messages.create")
            else:
                client.messages.create = self._make_wrapper(original_create, "messages.create")

        # Anthropic SDK: client.messages.stream(...) — streaming context manager
        if hasattr(client, "messages") and hasattr(client.messages, "stream"):
            original_stream = client.messages.stream
            client.messages.stream = self._wrap_stream_method(original_stream, "messages.stream")

        # OpenAI SDK: client.chat.completions.create(...)
        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            if hasattr(client.chat.completions, "create"):
                original_create = client.chat.completions.create
                if inspect.iscoroutinefunction(original_create):
                    client.chat.completions.create = self._make_async_wrapper(
                        original_create, "chat.completions.create"
                    )
                else:
                    client.chat.completions.create = self._make_wrapper(
                        original_create, "chat.completions.create"
                    )

    def _make_wrapper(self, original_fn: Any, tool_name: str) -> Any:
        """Create a wrapped version of an API method."""

        @functools.wraps(original_fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 0. Apply pending context action to messages
            if self._pending_context_action and self._pending_context_action != "pass":
                messages = kwargs.get("messages", [])
                if messages and self._pending_context_action == "truncate_20":
                    # Keep newest 80% of messages
                    keep = max(1, int(len(messages) * 0.80))
                    kwargs["messages"] = messages[-keep:]
                elif self._pending_context_action == "truncate_50_block_tools":
                    keep = max(1, int(len(messages) * 0.50))
                    kwargs["messages"] = messages[-keep:]
                    # Can't block tools via API, but we truncate more aggressively
                elif self._pending_context_action in ("block_destructive", "quarantine", "restart", "safe_mode"):
                    # Keep only system message if present
                    kwargs["messages"] = [m for m in messages if m.get("role") == "system"][:1] or messages[-1:]
                self._pending_context_action = "pass"

            # 1. Pre-check: should we block?
            level = self._engine.get_level(self._agent_id)
            if level >= self._block_at:
                snap = self._engine.get_snapshot(self._agent_id)
                raise SomaBlocked(self._agent_id, level, snap["pressure"])

            # 2. Check budget
            if self._engine.budget.is_exhausted():
                raise SomaBudgetExhausted("budget")

            # 3. OpenAI streaming: detect stream=True in kwargs
            if kwargs.get("stream"):
                response = original_fn(*args, **kwargs)
                return SomaStreamIterator(response, self, tool_name)

            # 4. Execute the real API call (non-streaming)
            start = time.time()
            error = False
            output_text = ""
            token_count = 0

            try:
                response = original_fn(*args, **kwargs)
                duration = time.time() - start

                # Extract data from response
                output_text, token_count = self._extract_response_data(response)

                return response

            except (SomaBlocked, SomaBudgetExhausted):
                raise  # Don't catch our own exceptions

            except Exception as e:
                duration = time.time() - start
                error = True
                output_text = str(e)
                raise

            finally:
                # 5. Record the action in SOMA
                action = Action(
                    tool_name=tool_name,
                    output_text=output_text[:1000],  # cap for vitals
                    token_count=token_count,
                    cost=self._estimate_cost(token_count),
                    error=error,
                    duration_sec=duration,
                )

                result = self._engine.record_action(self._agent_id, action)
                self._pending_context_action = result.context_action
                self._recorder.record(self._agent_id, action)
                # export_state() is now handled by engine.record_action() when auto_export=True

        return wrapper

    def _make_async_wrapper(self, original_fn: Any, tool_name: str) -> Any:
        """Create an async wrapped version of an API method."""

        @functools.wraps(original_fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 0. Apply pending context action to messages
            if self._pending_context_action and self._pending_context_action != "pass":
                messages = kwargs.get("messages", [])
                if messages and self._pending_context_action == "truncate_20":
                    keep = max(1, int(len(messages) * 0.80))
                    kwargs["messages"] = messages[-keep:]
                elif self._pending_context_action == "truncate_50_block_tools":
                    keep = max(1, int(len(messages) * 0.50))
                    kwargs["messages"] = messages[-keep:]
                elif self._pending_context_action in ("block_destructive", "quarantine", "restart", "safe_mode"):
                    kwargs["messages"] = [m for m in messages if m.get("role") == "system"][:1] or messages[-1:]
                self._pending_context_action = "pass"

            # 1. Pre-check: should we block?
            level = self._engine.get_level(self._agent_id)
            if level >= self._block_at:
                snap = self._engine.get_snapshot(self._agent_id)
                raise SomaBlocked(self._agent_id, level, snap["pressure"])

            # 2. Check budget
            if self._engine.budget.is_exhausted():
                raise SomaBudgetExhausted("budget")

            # 3. Execute the real async API call
            start = time.time()
            error = False
            output_text = ""
            token_count = 0

            try:
                response = await original_fn(*args, **kwargs)
                duration = time.time() - start

                output_text, token_count = self._extract_response_data(response)

                return response

            except (SomaBlocked, SomaBudgetExhausted):
                raise

            except Exception:
                duration = time.time() - start
                error = True
                raise

            finally:
                # 4. Record the action in SOMA
                action = Action(
                    tool_name=tool_name,
                    output_text=output_text[:1000],
                    token_count=token_count,
                    cost=self._estimate_cost(token_count),
                    error=error,
                    duration_sec=duration,
                )

                result = self._engine.record_action(self._agent_id, action)
                self._pending_context_action = result.context_action
                self._recorder.record(self._agent_id, action)

        return wrapper

    def _wrap_stream_method(self, original_fn: Any, tool_name: str) -> Any:
        """Wrap an Anthropic .stream() method to return a SOMA stream context."""

        @functools.wraps(original_fn)
        def stream_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Pre-check: should we block?
            level = self._engine.get_level(self._agent_id)
            if level >= self._block_at:
                snap = self._engine.get_snapshot(self._agent_id)
                raise SomaBlocked(self._agent_id, level, snap["pressure"])

            # Check budget
            if self._engine.budget.is_exhausted():
                raise SomaBudgetExhausted("budget")

            # Call original stream and wrap it
            underlying = original_fn(*args, **kwargs)

            # Detect if the underlying stream is async (has __aenter__)
            if hasattr(underlying, "__aenter__"):
                return AsyncSomaStreamContext(underlying, self, tool_name)
            return SomaStreamContext(underlying, self, tool_name)

        return stream_wrapper

    def _extract_response_data(self, response: Any) -> tuple[str, int]:
        """Extract text and token count from API response."""
        text = ""
        tokens = 0

        # Anthropic response
        if hasattr(response, "content"):
            # response.content is a list of content blocks
            parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            text = "\n".join(parts)

        if hasattr(response, "usage"):
            usage = response.usage
            if hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
                tokens = usage.input_tokens + usage.output_tokens
            elif hasattr(usage, "total_tokens"):
                tokens = usage.total_tokens

        # OpenAI response
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                text = choice.message.content or ""

        # Fallback: estimate tokens from text
        if tokens == 0 and text:
            tokens = len(text) // 4

        return text, tokens

    def _estimate_cost(self, tokens: int) -> float:
        """Rough cost estimate. Real pricing depends on model."""
        return tokens * 0.5 / 1_000_000  # ~$0.50 per 1M tokens average

    def __getattr__(self, name: str) -> Any:
        """Proxy all other attributes to the original client."""
        return getattr(self._client, name)


def wrap(
    client: Any,
    budget: dict[str, float] | None = None,
    agent_id: str = "default",
    auto_export: bool = True,
    block_at: ResponseMode = ResponseMode.BLOCK,
    engine: SOMAEngine | None = None,
) -> WrappedClient:
    """Wrap an API client with SOMA monitoring and control.

    Args:
        client: An Anthropic or OpenAI client instance.
        budget: Budget limits (e.g., {"tokens": 50000, "cost_usd": 1.0}).
        agent_id: Name for this agent in the SOMA dashboard.
        auto_export: Write state to ~/.soma/state.json after each call.
        block_at: ResponseMode at which to block API calls (default: BLOCK).
        engine: Optional shared SOMAEngine. If provided, budget is ignored.
            Pass the same engine to multiple wrap() calls so agents share
            pressure state and can propagate signals to each other.

    Returns:
        A WrappedClient that proxies all calls through SOMA.

    Example:
        import anthropic
        import soma

        client = soma.wrap(
            anthropic.Anthropic(),
            budget={"tokens": 50000},
            agent_id="my-agent",
        )

        # This call is now monitored and controlled by SOMA
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Check SOMA status
        print(client.soma_level)     # ResponseMode.OBSERVE
        print(client.soma_pressure)  # 0.03
    """
    if engine is None:
        engine = SOMAEngine(budget=budget or {"tokens": 100_000})
    return WrappedClient(
        client=client,
        engine=engine,
        agent_id=agent_id,
        auto_export=auto_export,
        block_at=block_at,
    )
