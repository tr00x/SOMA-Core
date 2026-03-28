"""Tests for SOMA wrappers (stateless + Claude Code)."""

from __future__ import annotations

import pytest

from soma.types import Action, Level, VitalsSnapshot
from soma.wrappers.stateless import StatelessWrapper
from soma.wrappers.claude_code import ClaudeCodeWrapper, WrapperResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action(tool: str = "bash", text: str = "ok", tokens: int = 10) -> Action:
    return Action(tool_name=tool, output_text=text, token_count=tokens)


def _make_context() -> dict:
    return {
        "messages": [{"role": "user", "content": f"msg {i}"} for i in range(10)],
        "tools": ["bash", "read_file", "write_file"],
        "system_prompt": "You are a helpful agent.",
        "expensive_tools": ["write_file"],
        "minimal_tools": ["read_file"],
    }


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------

def test_stateless_wrap_returns_correct_keys():
    """wrap() must return a dict with exactly the documented keys."""
    wrapper = StatelessWrapper()
    context = _make_context()
    action = _make_action()

    result = wrapper.wrap("agent-1", context, action)

    assert set(result.keys()) == {"context", "level", "pressure", "vitals", "state"}


def test_stateless_wrap_level_is_Level():
    wrapper = StatelessWrapper()
    result = wrapper.wrap("agent-1", _make_context(), _make_action())
    assert isinstance(result["level"], Level)


def test_stateless_wrap_pressure_is_float():
    wrapper = StatelessWrapper()
    result = wrapper.wrap("agent-1", _make_context(), _make_action())
    assert isinstance(result["pressure"], float)
    assert result["pressure"] >= 0.0


def test_stateless_wrap_vitals_is_VitalsSnapshot():
    wrapper = StatelessWrapper()
    result = wrapper.wrap("agent-1", _make_context(), _make_action())
    assert isinstance(result["vitals"], VitalsSnapshot)


def test_stateless_wrap_context_is_dict():
    wrapper = StatelessWrapper()
    result = wrapper.wrap("agent-1", _make_context(), _make_action())
    assert isinstance(result["context"], dict)
    # context_control preserves system_prompt
    assert result["context"]["system_prompt"] == "You are a helpful agent."


def test_stateless_wrap_state_is_dict():
    wrapper = StatelessWrapper()
    result = wrapper.wrap("agent-1", _make_context(), _make_action())
    assert isinstance(result["state"], dict)


# ---------------------------------------------------------------------------
# State passing across calls
# ---------------------------------------------------------------------------

def test_stateless_wrap_state_passes_across_calls():
    """Passing state from one call to the next should work without error."""
    wrapper = StatelessWrapper(budget={"tokens": 100_000})
    context = _make_context()

    state = None
    for i in range(5):
        action = _make_action(tool=f"tool_{i}", text=f"output {i}", tokens=50)
        result = wrapper.wrap("agent-1", context, action, state=state)
        state = result["state"]

    # After 5 calls we still get a valid level.
    assert isinstance(result["level"], Level)


def test_stateless_wrap_history_capped_at_20():
    """State history must never exceed 20 entries."""
    wrapper = StatelessWrapper(budget={"tokens": 1_000_000})
    context = _make_context()

    state = None
    for i in range(25):
        action = _make_action(tokens=10)
        result = wrapper.wrap("agent-1", context, action, state=state)
        state = result["state"]

    assert len(state["history"]) <= 20


def test_stateless_first_call_no_state():
    """First call with state=None should not raise."""
    wrapper = StatelessWrapper()
    result = wrapper.wrap("agent-1", _make_context(), _make_action(), state=None)
    assert "state" in result


def test_stateless_multiple_agents_independent():
    """Two agents can each maintain independent state threads."""
    wrapper = StatelessWrapper(budget={"tokens": 100_000})
    context = _make_context()

    state_a = None
    state_b = None
    for _ in range(3):
        res_a = wrapper.wrap("agent-a", context, _make_action(tool="tool_a"), state=state_a)
        res_b = wrapper.wrap("agent-b", context, _make_action(tool="tool_b"), state=state_b)
        state_a = res_a["state"]
        state_b = res_b["state"]

    assert isinstance(res_a["level"], Level)
    assert isinstance(res_b["level"], Level)


# ---------------------------------------------------------------------------
# Budget serialisation round-trip
# ---------------------------------------------------------------------------

def test_stateless_budget_persists_across_calls():
    """Spent tokens should accumulate correctly across stateless calls."""
    wrapper = StatelessWrapper(budget={"tokens": 10_000})
    context = _make_context()

    state = None
    for _ in range(3):
        result = wrapper.wrap(
            "agent-1", context,
            _make_action(tokens=100),
            state=state,
        )
        state = result["state"]

    # The budget spent should be reflected in state.
    assert state["budget"]["spent"]["tokens"] > 0


# ===========================================================================
# Claude Code Wrapper Tests
# ===========================================================================

class TestClaudeCodeWrapper:
    def test_create_and_register(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        w.register_agent("main")
        assert w.get_level("main") == Level.HEALTHY

    def test_on_action_returns_wrapper_result(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        w.register_agent("main")
        result = w.on_action("main", Action(tool_name="bash", output_text="ls output", token_count=200))
        assert isinstance(result, WrapperResult)
        assert result.context_action in ("pass", "truncate", "block_tools", "restart")

    def test_multi_agent_graph(self):
        w = ClaudeCodeWrapper(budget={"tokens": 500000})
        w.register_agent("orch")
        w.register_agent("sub")
        w.add_edge("orch", "sub")
        for _ in range(15):
            w.on_action("orch", Action(
                tool_name="bash", output_text="err " * 50,
                token_count=100, error=True, retried=True,
            ))
        r = w.on_action("sub", Action(tool_name="search", output_text="ok", token_count=50))
        assert r.pressure >= 0.0

    def test_should_block_tool_at_healthy(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        w.register_agent("main", expensive_tools=["bash"])
        assert not w.should_block_tool("main", "bash")

    def test_recording(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        w.register_agent("main")
        w.on_action("main", Action(tool_name="bash", output_text="ok", token_count=100))
        w.on_action("main", Action(tool_name="edit", output_text="ok", token_count=100))
        rec = w.get_recording()
        assert len(rec.actions) == 2

    def test_events_property(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        assert w.events is not None

    def test_budget_property(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        assert w.budget is not None

    def test_get_snapshot(self):
        w = ClaudeCodeWrapper(budget={"tokens": 100000})
        w.register_agent("main")
        w.on_action("main", Action(tool_name="bash", output_text="hello", token_count=50))
        snap = w.get_snapshot("main")
        assert "level" in snap
