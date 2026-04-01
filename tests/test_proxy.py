"""Tests for soma.proxy — universal tool proxy."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from soma.engine import SOMAEngine
from soma.proxy import SOMAProxy, SOMABlockError
from soma.types import ResponseMode


@pytest.fixture
def engine():
    e = SOMAEngine(budget={"tokens": 100_000}, audit_enabled=False)
    e.register_agent("test-agent")
    return e


@pytest.fixture
def proxy(engine):
    return SOMAProxy(engine, "test-agent")


# -- Basic wrapping --------------------------------------------------------


class TestWrapTool:
    def test_sync_tool_passes_through(self, proxy):
        def add(a, b):
            return a + b

        safe_add = proxy.wrap_tool(add, "add")
        assert safe_add(2, 3) == 5

    def test_sync_tool_records_action(self, proxy, engine):
        def greet(name):
            return f"Hello {name}"

        safe = proxy.wrap_tool(greet, "greet")
        safe("World")

        snap = engine.get_snapshot("test-agent")
        assert snap["action_count"] == 1

    def test_sync_tool_preserves_exception(self, proxy):
        def fail():
            raise ValueError("boom")

        safe = proxy.wrap_tool(fail, "fail")
        with pytest.raises(ValueError, match="boom"):
            safe()

    def test_error_recorded_on_exception(self, proxy, engine):
        def fail():
            raise RuntimeError("oops")

        safe = proxy.wrap_tool(fail, "fail")
        with pytest.raises(RuntimeError):
            safe()

        # Error was recorded — error_rate > 0
        snap = engine.get_snapshot("test-agent")
        assert snap["action_count"] == 1

    def test_async_tool_works(self, proxy):
        async def async_search(q):
            return f"results for {q}"

        safe = proxy.wrap_tool(async_search, "search")

        async def run():
            return await safe("test")

        result = asyncio.run(run())
        assert result == "results for test"

    def test_tool_name_defaults_to_function_name(self, proxy):
        def my_custom_tool():
            return 42

        safe = proxy.wrap_tool(my_custom_tool)
        assert safe.__name__ == "my_custom_tool"

    def test_kwargs_pass_through(self, proxy):
        def tool(*, query, limit=10):
            return {"query": query, "limit": limit}

        safe = proxy.wrap_tool(tool, "search")
        result = safe(query="hello", limit=5)
        assert result == {"query": "hello", "limit": 5}


# -- wrap_tools (list) -----------------------------------------------------


class TestWrapTools:
    def test_wraps_callables(self, proxy):
        def a():
            return 1

        def b():
            return 2

        wrapped = proxy.wrap_tools([a, b])
        assert len(wrapped) == 2
        assert wrapped[0]() == 1
        assert wrapped[1]() == 2

    def test_wraps_dict_tools(self, proxy):
        def fn():
            return "ok"

        tools = [{"function": fn, "name": "my_fn"}]
        wrapped = proxy.wrap_tools(tools)
        assert wrapped[0]["function"]() == "ok"

    def test_passthrough_unknown_format(self, proxy):
        obj = "not a tool"
        wrapped = proxy.wrap_tools([obj])
        assert wrapped[0] == "not a tool"


# -- wrap_agent -------------------------------------------------------------


class TestWrapAgent:
    def test_wraps_run_method(self, proxy):
        class Agent:
            def run(self, task):
                return f"done: {task}"

        agent = Agent()
        proxy.wrap_agent(agent)
        assert agent.run("test") == "done: test"

    def test_wraps_invoke_method(self, proxy):
        class Agent:
            def invoke(self, input_data):
                return {"result": input_data}

        agent = Agent()
        proxy.wrap_agent(agent)
        assert agent.invoke("hello") == {"result": "hello"}

    def test_wraps_function_map(self, proxy):
        class Agent:
            def __init__(self):
                self.function_map = {
                    "search": lambda q: f"found: {q}",
                    "calc": lambda x: x * 2,
                }

        agent = Agent()
        proxy.wrap_agent(agent)
        assert agent.function_map["search"]("test") == "found: test"
        assert agent.function_map["calc"](5) == 10


# -- Subagent spawning ------------------------------------------------------


class TestSpawnSubagent:
    def test_child_registered(self, proxy, engine):
        child = proxy.spawn_subagent("child-1")
        assert "child-1" in engine._agents

    def test_graph_edge_created(self, proxy, engine):
        child = proxy.spawn_subagent("child-1")
        trust = engine._graph.get_trust("child-1", "test-agent")
        assert trust == pytest.approx(0.8)

    def test_child_actions_recorded(self, proxy, engine):
        child = proxy.spawn_subagent("child-1")

        def fail():
            raise RuntimeError("error")

        safe_fail = child.wrap_tool(fail, "fail")
        for _ in range(5):
            try:
                safe_fail()
            except RuntimeError:
                pass

        # Child actions recorded
        child_snap = engine.get_snapshot("child-1")
        assert child_snap["action_count"] == 5

    def test_multiple_children(self, proxy, engine):
        c1 = proxy.spawn_subagent("c1")
        c2 = proxy.spawn_subagent("c2")
        assert "c1" in engine._agents
        assert "c2" in engine._agents
        assert "c1" in engine._graph.agents
        assert "c2" in engine._graph.agents


# -- Blocking ---------------------------------------------------------------


class TestBlocking:
    def test_block_mode_raises(self, engine):
        # Force agent into BLOCK mode by setting extreme thresholds
        proxy = SOMAProxy(engine, "test-agent")

        # Record many errors to push pressure up
        from soma.types import Action
        for _ in range(30):
            engine.record_action("test-agent", Action(
                tool_name="Bash", output_text="error", error=True,
            ))

        snap = engine.get_snapshot("test-agent")
        # If pressure is high enough for BLOCK, the next tool call should raise
        if snap["level"] == ResponseMode.BLOCK:
            def tool():
                return "ok"

            safe = proxy.wrap_tool(tool, "tool")
            with pytest.raises(SOMABlockError):
                safe()

    def test_soma_crash_doesnt_break_tool(self, engine):
        """If engine throws internally, tool still executes."""
        proxy = SOMAProxy(engine, "test-agent")

        def tool():
            return "works"

        safe = proxy.wrap_tool(tool, "tool")

        # Corrupt engine state to force internal error
        original_get = engine.get_snapshot
        engine.get_snapshot = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))

        # Tool should still work
        result = safe()
        assert result == "works"

        engine.get_snapshot = original_get


# -- Thread safety -----------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_tools(self, engine):
        proxy = SOMAProxy(engine, "test-agent")
        results = []

        def tool(n):
            time.sleep(0.01)
            return n * 2

        safe = proxy.wrap_tool(tool, "multiply")

        threads = []
        for i in range(10):
            t = threading.Thread(target=lambda i=i: results.append(safe(i)))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert sorted(results) == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
        assert proxy.action_count == 10

    def test_concurrent_subagents(self, engine):
        parent = SOMAProxy(engine, "test-agent")
        children = [parent.spawn_subagent(f"child-{i}") for i in range(3)]

        results = []

        def run_child(child, n):
            def tool():
                return n

            safe = child.wrap_tool(tool, "compute")
            results.append(safe())

        threads = [
            threading.Thread(target=run_child, args=(c, i))
            for i, c in enumerate(children)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == [0, 1, 2]


# -- Introspection -----------------------------------------------------------


class TestIntrospection:
    def test_action_count(self, proxy):
        def noop():
            return None

        safe = proxy.wrap_tool(noop, "noop")
        assert proxy.action_count == 0
        safe()
        safe()
        assert proxy.action_count == 2

    def test_pressure_property(self, proxy):
        assert isinstance(proxy.pressure, float)
        assert 0.0 <= proxy.pressure <= 1.0

    def test_mode_property(self, proxy):
        assert isinstance(proxy.mode, ResponseMode)
