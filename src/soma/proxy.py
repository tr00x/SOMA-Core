"""soma.proxy — universal tool proxy for any agent framework.

Sits between any agent and its tools. Agent calls tool → SOMA intercepts →
records → checks reflexes → passes through → records result.

Works on ANY agent framework because it operates at the tool call level,
not the LLM level. No Claude Code hooks required.

Usage:
    engine = soma.quickstart()
    engine.register_agent("my-agent")
    proxy = SOMAProxy(engine, "my-agent")

    # Wrap individual tools
    safe_search = proxy.wrap_tool(search_function, "search")
    result = safe_search(query="hello")

    # Wrap a list of tools (LangChain style)
    safe_tools = proxy.wrap_tools(tools)

    # Spawn a monitored subagent
    child = proxy.spawn_subagent("child-agent")
    # child.engine has parent→child edge in graph.py
"""

from __future__ import annotations

import functools
import inspect
import threading
import time
from typing import Any, Callable

from soma.engine import SOMAEngine, ActionResult
from soma.errors import SOMAError
from soma.types import Action, ResponseMode


class SOMABlockError(SOMAError):
    """Raised when SOMA reflexes block a tool call."""

    def __init__(self, message: str, pressure: float, mode: ResponseMode) -> None:
        super().__init__(message)
        self.pressure = pressure
        self.mode = mode


class SOMAProxy:
    """Universal tool proxy — wraps any callable tool with SOMA monitoring.

    Thread-safe: multiple subagents can run concurrently. Each proxy
    instance tracks its own agent_id on a shared engine.
    """

    def __init__(
        self,
        engine: SOMAEngine,
        agent_id: str,
        *,
        block_on_warn: bool = False,
        parent_proxy: SOMAProxy | None = None,
    ) -> None:
        self.engine = engine
        self.agent_id = agent_id
        self._block_on_warn = block_on_warn
        self._parent_proxy = parent_proxy
        self._lock = threading.Lock()
        self._action_count = 0

        # Ensure agent is registered
        if agent_id not in engine._agents:
            engine.register_agent(agent_id)

    # ------------------------------------------------------------------
    # Core: wrap a single tool
    # ------------------------------------------------------------------

    def wrap_tool(
        self,
        tool: Callable,
        tool_name: str | None = None,
    ) -> Callable:
        """Wrap a callable tool with SOMA pre/post monitoring.

        Args:
            tool: Any callable (sync or async function).
            tool_name: Name for SOMA tracking. Defaults to function name.

        Returns:
            Wrapped callable with same signature. If SOMA crashes
            internally, the original tool executes normally.
        """
        name = tool_name or getattr(tool, "__name__", "tool")

        if inspect.iscoroutinefunction(tool):
            return self._wrap_async(tool, name)
        return self._wrap_sync(tool, name)

    def wrap_tools(self, tools: list) -> list:
        """Wrap a list of tools. Works with LangChain-style tool lists.

        Each tool can be:
        - A callable (wrapped by function name)
        - An object with .name and ._run/.run (LangChain BaseTool pattern)
        - A dict with "function" key
        """
        wrapped = []
        for tool in tools:
            if callable(tool) and not hasattr(tool, "_run"):
                wrapped.append(self.wrap_tool(tool))
            elif hasattr(tool, "_run"):
                # LangChain BaseTool — wrap _run method in-place
                name = getattr(tool, "name", type(tool).__name__)
                original_run = tool._run
                tool._run = self._wrap_sync(original_run, name)
                if hasattr(tool, "_arun") and inspect.iscoroutinefunction(tool._arun):
                    tool._arun = self._wrap_async(tool._arun, name)
                wrapped.append(tool)
            elif isinstance(tool, dict) and "function" in tool:
                fn = tool["function"]
                name = tool.get("name", getattr(fn, "__name__", "tool"))
                tool["function"] = self.wrap_tool(fn, name)
                wrapped.append(tool)
            else:
                wrapped.append(tool)
        return wrapped

    def wrap_agent(self, agent: Any) -> Any:
        """Wrap an agent object by monkey-patching its tool invocation.

        Supports patterns:
        - .execute_task() (CrewAI)
        - .generate_reply() (AutoGen)
        - .run() / .invoke() (generic)
        - .function_map dict (AutoGen function calling)

        Returns the same agent object (mutated in place).
        """
        # CrewAI pattern
        if hasattr(agent, "execute_task"):
            agent.execute_task = self._wrap_sync(
                agent.execute_task,
                f"task:{getattr(agent, 'role', 'agent')}",
            )

        # AutoGen pattern
        if hasattr(agent, "generate_reply"):
            agent.generate_reply = self._wrap_sync(
                agent.generate_reply, "generate_reply",
            )

        # AutoGen function_map
        if hasattr(agent, "function_map") and isinstance(agent.function_map, dict):
            for fname, fn in list(agent.function_map.items()):
                if callable(fn):
                    agent.function_map[fname] = self.wrap_tool(fn, fname)

        # Generic .run() / .invoke()
        for method_name in ("run", "invoke"):
            if hasattr(agent, method_name):
                original = getattr(agent, method_name)
                if callable(original):
                    setattr(agent, method_name, self._wrap_sync(original, method_name))

        return agent

    # ------------------------------------------------------------------
    # Subagent spawning
    # ------------------------------------------------------------------

    def spawn_subagent(
        self,
        agent_id: str,
        tools: list[str] | None = None,
    ) -> SOMAProxy:
        """Create a child proxy wired into graph.py.

        The parent→child edge in the pressure graph means:
        - Child pressure propagates to parent (damped)
        - If child error_rate spikes, parent pressure rises
        - Trust decays if child keeps failing

        Returns a new SOMAProxy configured for the subagent.
        """
        # Register child agent
        if agent_id not in self.engine._agents:
            self.engine.register_agent(agent_id, tools=tools)

        # Wire parent→child in graph
        graph = self.engine._graph
        graph.add_edge(agent_id, self.agent_id, trust=0.8)

        child = SOMAProxy(
            self.engine,
            agent_id,
            block_on_warn=self._block_on_warn,
            parent_proxy=self,
        )
        return child

    # ------------------------------------------------------------------
    # Internal: sync/async wrapping
    # ------------------------------------------------------------------

    def _pre_check(self, tool_name: str) -> tuple[float, ResponseMode]:
        """Pre-call check: get current pressure and mode.

        Returns (pressure, mode). Raises SOMABlockError if mode is BLOCK
        or (optionally) WARN.
        """
        try:
            snap = self.engine.get_snapshot(self.agent_id)
            pressure = snap["pressure"]
            mode = snap["level"]
            if not isinstance(mode, ResponseMode):
                mode = ResponseMode.OBSERVE

            if mode == ResponseMode.BLOCK:
                raise SOMABlockError(
                    f"SOMA blocked {tool_name}: pressure={pressure:.0%}, "
                    f"agent={self.agent_id}",
                    pressure=pressure,
                    mode=mode,
                )

            if self._block_on_warn and mode == ResponseMode.WARN:
                raise SOMABlockError(
                    f"SOMA warned on {tool_name}: pressure={pressure:.0%}, "
                    f"agent={self.agent_id}",
                    pressure=pressure,
                    mode=mode,
                )

            return pressure, mode
        except SOMABlockError:
            raise
        except Exception:
            return 0.0, ResponseMode.OBSERVE

    def _post_record(
        self,
        tool_name: str,
        output: str,
        error: bool,
        duration: float,
        token_count: int = 0,
    ) -> ActionResult:
        """Post-call: record action and propagate pressure."""
        try:
            action = Action(
                tool_name=tool_name,
                output_text=output[:4000],
                error=error,
                duration_sec=duration,
                token_count=token_count,
            )
            result = self.engine.record_action(self.agent_id, action)

            # If this is a subagent, propagate pressure to parent via graph
            if self._parent_proxy is not None:
                try:
                    graph = self.engine._graph
                    graph.set_internal_pressure(self.agent_id, result.pressure)
                    graph.propagate()
                except Exception:
                    pass

            with self._lock:
                self._action_count += 1

            return result
        except Exception:
            return ActionResult(
                mode=ResponseMode.OBSERVE,
                pressure=0.0,
                vitals=None,  # type: ignore[arg-type]
            )

    def _wrap_sync(self, fn: Callable, tool_name: str) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Pre-check (may raise SOMABlockError)
            try:
                self._pre_check(tool_name)
            except SOMABlockError:
                raise
            except Exception:
                pass  # SOMA crash → let tool run

            start = time.time()
            error = False
            output = ""
            try:
                result = fn(*args, **kwargs)
                output = str(result)[:4000] if result is not None else ""
                return result
            except SOMABlockError:
                raise
            except Exception as exc:
                error = True
                output = str(exc)
                raise
            finally:
                duration = time.time() - start
                try:
                    self._post_record(tool_name, output, error, duration)
                except Exception:
                    pass  # Never break the tool

        return wrapper

    def _wrap_async(self, fn: Callable, tool_name: str) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                self._pre_check(tool_name)
            except SOMABlockError:
                raise
            except Exception:
                pass

            start = time.time()
            error = False
            output = ""
            try:
                result = await fn(*args, **kwargs)
                output = str(result)[:4000] if result is not None else ""
                return result
            except SOMABlockError:
                raise
            except Exception as exc:
                error = True
                output = str(exc)
                raise
            finally:
                duration = time.time() - start
                try:
                    self._post_record(tool_name, output, error, duration)
                except Exception:
                    pass

        return wrapper

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def action_count(self) -> int:
        with self._lock:
            return self._action_count

    @property
    def pressure(self) -> float:
        try:
            return self.engine.get_snapshot(self.agent_id)["pressure"]
        except Exception:
            return 0.0

    @property
    def mode(self) -> ResponseMode:
        try:
            m = self.engine.get_snapshot(self.agent_id)["level"]
            return m if isinstance(m, ResponseMode) else ResponseMode.OBSERVE
        except Exception:
            return ResponseMode.OBSERVE
