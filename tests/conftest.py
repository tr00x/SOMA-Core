"""Shared test fixtures for SOMA Core."""

import pytest
from soma.types import Action


@pytest.fixture
def normal_actions():
    """10 normal, non-error actions with varied tools."""
    tools = ["search", "edit", "bash", "read", "search", "edit", "bash", "read", "search", "edit"]
    return [
        Action(
            tool_name=tools[i],
            output_text=f"Normal output from step {i}: " + "abcdefghij " * 5,
            token_count=100 + i * 10,
            cost=0.005,
            duration_sec=1.0 + i * 0.1,
        )
        for i in range(10)
    ]


@pytest.fixture
def error_actions():
    """10 error actions — all retries, same tool, repetitive output."""
    return [
        Action(
            tool_name="bash",
            output_text="error error error " * 10,
            token_count=200,
            cost=0.01,
            error=True,
            retried=True,
            duration_sec=0.5,
        )
        for _ in range(10)
    ]
