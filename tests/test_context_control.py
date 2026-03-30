"""Tests for soma.context_control.apply_context_control."""

from __future__ import annotations

import pytest

from soma.context_control import apply_context_control
from soma.types import ResponseMode


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_context(
    n_messages: int = 10,
    tools: list[str] | None = None,
    system_prompt: str = "You are a helpful agent.",
    expensive_tools: list[str] | None = None,
    minimal_tools: list[str] | None = None,
) -> dict:
    messages = list(range(n_messages))  # simple ints; 0 is oldest, n-1 is newest
    return {
        "messages": messages,
        "tools": tools if tools is not None else ["tool_a", "tool_b", "tool_c"],
        "system_prompt": system_prompt,
        "expensive_tools": expensive_tools if expensive_tools is not None else ["tool_c"],
        "minimal_tools": minimal_tools if minimal_tools is not None else ["tool_a"],
    }


# ---------------------------------------------------------------------------
# OBSERVE
# ---------------------------------------------------------------------------

class TestObserve:
    def test_returns_full_context(self):
        ctx = make_context(n_messages=10)
        result = apply_context_control(ctx, ResponseMode.OBSERVE)
        assert result["messages"] == list(range(10))
        assert result["tools"] == ["tool_a", "tool_b", "tool_c"]

    def test_does_not_mutate_original(self):
        ctx = make_context(n_messages=5)
        original_messages = list(ctx["messages"])
        apply_context_control(ctx, ResponseMode.OBSERVE)
        assert ctx["messages"] == original_messages

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Keep this.")
        result = apply_context_control(ctx, ResponseMode.OBSERVE)
        assert result["system_prompt"] == "Keep this."


# ---------------------------------------------------------------------------
# GUIDE
# ---------------------------------------------------------------------------

class TestGuide:
    def test_keeps_80_percent_of_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        assert len(result["messages"]) == 80

    def test_keeps_newest_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        # Messages are 0..99; newest 80 % starts at index 20
        assert result["messages"][-1] == 99

    def test_keeps_oldest_of_kept_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        assert result["messages"][0] == 20  # first of the newest 80

    def test_keeps_all_tools(self):
        ctx = make_context(n_messages=10, tools=["t1", "t2", "t3"])
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        assert result["tools"] == ["t1", "t2", "t3"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Stay cautious.")
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        assert result["system_prompt"] == "Stay cautious."

    def test_rounds_up_for_non_divisible(self):
        # 10 messages, 80 % -> ceil(8.0) = 8
        ctx = make_context(n_messages=10)
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        assert len(result["messages"]) == 8


# ---------------------------------------------------------------------------
# WARN
# ---------------------------------------------------------------------------

class TestWarn:
    def test_keeps_50_percent_of_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, ResponseMode.WARN)
        assert len(result["messages"]) == 50

    def test_keeps_newest_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, ResponseMode.WARN)
        assert result["messages"][-1] == 99

    def test_removes_expensive_tools(self):
        ctx = make_context(
            tools=["tool_a", "tool_b", "tool_c"],
            expensive_tools=["tool_c"],
        )
        result = apply_context_control(ctx, ResponseMode.WARN)
        assert "tool_c" not in result["tools"]
        assert "tool_a" in result["tools"]
        assert "tool_b" in result["tools"]

    def test_blocks_all_expensive_tools(self):
        ctx = make_context(
            tools=["t1", "t2", "t3", "t4"],
            expensive_tools=["t2", "t4"],
        )
        result = apply_context_control(ctx, ResponseMode.WARN)
        assert result["tools"] == ["t1", "t3"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Warn carefully.")
        result = apply_context_control(ctx, ResponseMode.WARN)
        assert result["system_prompt"] == "Warn carefully."


# ---------------------------------------------------------------------------
# BLOCK
# ---------------------------------------------------------------------------

class TestBlock:
    def test_zero_messages(self):
        ctx = make_context(n_messages=50)
        result = apply_context_control(ctx, ResponseMode.BLOCK)
        assert result["messages"] == []

    def test_only_minimal_tools(self):
        ctx = make_context(
            tools=["tool_a", "tool_b", "tool_c"],
            minimal_tools=["tool_a"],
        )
        result = apply_context_control(ctx, ResponseMode.BLOCK)
        assert result["tools"] == ["tool_a"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Block active.")
        result = apply_context_control(ctx, ResponseMode.BLOCK)
        assert result["system_prompt"] == "Block active."
