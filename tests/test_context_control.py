"""Tests for soma.context_control.apply_context_control."""

from __future__ import annotations

import pytest

from soma.context_control import apply_context_control
from soma.types import Level


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
# HEALTHY
# ---------------------------------------------------------------------------

class TestHealthy:
    def test_returns_full_context(self):
        ctx = make_context(n_messages=10)
        result = apply_context_control(ctx, Level.HEALTHY)
        assert result["messages"] == list(range(10))
        assert result["tools"] == ["tool_a", "tool_b", "tool_c"]

    def test_does_not_mutate_original(self):
        ctx = make_context(n_messages=5)
        original_messages = list(ctx["messages"])
        apply_context_control(ctx, Level.HEALTHY)
        assert ctx["messages"] == original_messages

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Keep this.")
        result = apply_context_control(ctx, Level.HEALTHY)
        assert result["system_prompt"] == "Keep this."


# ---------------------------------------------------------------------------
# CAUTION
# ---------------------------------------------------------------------------

class TestCaution:
    def test_keeps_80_percent_of_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, Level.CAUTION)
        assert len(result["messages"]) == 80

    def test_keeps_newest_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, Level.CAUTION)
        # Messages are 0..99; newest 80 % starts at index 20
        assert result["messages"][-1] == 99

    def test_keeps_oldest_of_kept_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, Level.CAUTION)
        assert result["messages"][0] == 20  # first of the newest 80

    def test_keeps_all_tools(self):
        ctx = make_context(n_messages=10, tools=["t1", "t2", "t3"])
        result = apply_context_control(ctx, Level.CAUTION)
        assert result["tools"] == ["t1", "t2", "t3"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Stay cautious.")
        result = apply_context_control(ctx, Level.CAUTION)
        assert result["system_prompt"] == "Stay cautious."

    def test_rounds_up_for_non_divisible(self):
        # 10 messages, 80 % → ceil(8.0) = 8
        ctx = make_context(n_messages=10)
        result = apply_context_control(ctx, Level.CAUTION)
        assert len(result["messages"]) == 8


# ---------------------------------------------------------------------------
# DEGRADE
# ---------------------------------------------------------------------------

class TestDegrade:
    def test_keeps_50_percent_of_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, Level.DEGRADE)
        assert len(result["messages"]) == 50

    def test_keeps_newest_messages(self):
        ctx = make_context(n_messages=100)
        result = apply_context_control(ctx, Level.DEGRADE)
        assert result["messages"][-1] == 99

    def test_removes_expensive_tools(self):
        ctx = make_context(
            tools=["tool_a", "tool_b", "tool_c"],
            expensive_tools=["tool_c"],
        )
        result = apply_context_control(ctx, Level.DEGRADE)
        assert "tool_c" not in result["tools"]
        assert "tool_a" in result["tools"]
        assert "tool_b" in result["tools"]

    def test_blocks_all_expensive_tools(self):
        ctx = make_context(
            tools=["t1", "t2", "t3", "t4"],
            expensive_tools=["t2", "t4"],
        )
        result = apply_context_control(ctx, Level.DEGRADE)
        assert result["tools"] == ["t1", "t3"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Degrade carefully.")
        result = apply_context_control(ctx, Level.DEGRADE)
        assert result["system_prompt"] == "Degrade carefully."


# ---------------------------------------------------------------------------
# QUARANTINE
# ---------------------------------------------------------------------------

class TestQuarantine:
    def test_zero_messages(self):
        ctx = make_context(n_messages=50)
        result = apply_context_control(ctx, Level.QUARANTINE)
        assert result["messages"] == []

    def test_only_minimal_tools(self):
        ctx = make_context(
            tools=["tool_a", "tool_b", "tool_c"],
            minimal_tools=["tool_a"],
        )
        result = apply_context_control(ctx, Level.QUARANTINE)
        assert result["tools"] == ["tool_a"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Quarantine active.")
        result = apply_context_control(ctx, Level.QUARANTINE)
        assert result["system_prompt"] == "Quarantine active."


# ---------------------------------------------------------------------------
# RESTART
# ---------------------------------------------------------------------------

class TestRestart:
    def test_zero_messages(self):
        ctx = make_context(n_messages=50)
        result = apply_context_control(ctx, Level.RESTART)
        assert result["messages"] == []

    def test_keeps_full_tools(self):
        ctx = make_context(tools=["t1", "t2", "t3"])
        result = apply_context_control(ctx, Level.RESTART)
        assert result["tools"] == ["t1", "t2", "t3"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Restarting now.")
        result = apply_context_control(ctx, Level.RESTART)
        assert result["system_prompt"] == "Restarting now."


# ---------------------------------------------------------------------------
# SAFE_MODE
# ---------------------------------------------------------------------------

class TestSafeMode:
    def test_zero_messages(self):
        ctx = make_context(n_messages=50)
        result = apply_context_control(ctx, Level.SAFE_MODE)
        assert result["messages"] == []

    def test_only_minimal_tools(self):
        ctx = make_context(
            tools=["tool_a", "tool_b", "tool_c"],
            minimal_tools=["tool_a"],
        )
        result = apply_context_control(ctx, Level.SAFE_MODE)
        assert result["tools"] == ["tool_a"]

    def test_system_prompt_preserved(self):
        ctx = make_context(system_prompt="Safe mode engaged.")
        result = apply_context_control(ctx, Level.SAFE_MODE)
        assert result["system_prompt"] == "Safe mode engaged."
