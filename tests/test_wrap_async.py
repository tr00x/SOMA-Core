"""Tests for soma.wrap() — async client support."""

from __future__ import annotations

import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import soma
from soma.wrap import wrap, WrappedClient, SomaBlocked, SomaBudgetExhausted
from soma.types import ResponseMode


# ── Mock Async API clients ──────────────────────────────────────

@dataclass
class MockUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class MockContentBlock:
    text: str = "Hello from Claude"
    type: str = "text"


@dataclass
class MockAnthropicResponse:
    content: list = None
    usage: MockUsage = None

    def __post_init__(self):
        if self.content is None:
            self.content = [MockContentBlock()]
        if self.usage is None:
            self.usage = MockUsage()


class MockAsyncMessages:
    async def create(self, **kwargs):
        return MockAnthropicResponse()


class MockAsyncAnthropicClient:
    def __init__(self):
        self.messages = MockAsyncMessages()
        self.api_key = "test-key-async"


# ── Mock Async OpenAI ───────────────────────────────────────────

@dataclass
class MockOpenAIMessage:
    content: str = "Hello from GPT"


@dataclass
class MockOpenAIChoice:
    message: MockOpenAIMessage = None

    def __post_init__(self):
        if self.message is None:
            self.message = MockOpenAIMessage()


@dataclass
class MockOpenAIUsage:
    total_tokens: int = 200


@dataclass
class MockOpenAIResponse:
    choices: list = None
    usage: MockOpenAIUsage = None

    def __post_init__(self):
        if self.choices is None:
            self.choices = [MockOpenAIChoice()]
        if self.usage is None:
            self.usage = MockOpenAIUsage()


class MockAsyncCompletions:
    async def create(self, **kwargs):
        return MockOpenAIResponse()


class MockAsyncChat:
    def __init__(self):
        self.completions = MockAsyncCompletions()


class MockAsyncOpenAIClient:
    def __init__(self):
        self.chat = MockAsyncChat()
        self.api_key = "test-key-openai-async"


# ── Tests ───────────────────────────────────────────────────────

class TestAsyncWrap:
    @pytest.mark.asyncio
    async def test_wrap_async_client_returns_wrapped_client(self):
        """Test 1: soma.wrap(async_anthropic_client) returns WrappedClient."""
        client = MockAsyncAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 10000}, auto_export=False)
        assert isinstance(wrapped, WrappedClient)

    @pytest.mark.asyncio
    async def test_await_messages_create_returns_response_and_records(self):
        """Test 2: await wrapped.messages.create() returns response and records action."""
        client = MockAsyncAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 10000}, auto_export=False)
        response = await wrapped.messages.create(
            model="test", max_tokens=100, messages=[]
        )
        assert response.content[0].text == "Hello from Claude"
        assert len(wrapped.recorder.actions) == 1

    @pytest.mark.asyncio
    async def test_async_wrapper_raises_soma_blocked(self):
        """Test 3: Async wrapper raises SomaBlocked when mode >= block_at."""
        client = MockAsyncAnthropicClient()
        wrapped = soma.wrap(
            client,
            budget={"tokens": 10000},
            auto_export=False,
            block_at=ResponseMode.BLOCK,
        )
        wrapped.engine._agents["default"].mode = ResponseMode.BLOCK
        with pytest.raises(SomaBlocked) as exc_info:
            await wrapped.messages.create(
                model="test", max_tokens=100, messages=[]
            )
        assert exc_info.value.level == ResponseMode.BLOCK

    @pytest.mark.asyncio
    async def test_async_wrapper_raises_soma_budget_exhausted(self):
        """Test 4: Async wrapper raises SomaBudgetExhausted when budget exhausted."""
        client = MockAsyncAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 0}, auto_export=False)
        with pytest.raises(SomaBudgetExhausted):
            await wrapped.messages.create(
                model="test", max_tokens=100, messages=[]
            )

    @pytest.mark.asyncio
    async def test_async_api_error_records_error_true(self):
        """Test 5: API error during async call records error=True, re-raises."""
        client = MockAsyncAnthropicClient()

        async def failing_create(**kwargs):
            raise RuntimeError("Async API error")

        client.messages.create = failing_create
        wrapped = soma.wrap(client, auto_export=False)
        with pytest.raises(RuntimeError, match="Async API error"):
            await wrapped.messages.create(
                model="test", max_tokens=100, messages=[]
            )
        assert len(wrapped.recorder.actions) == 1
        assert wrapped.recorder.actions[0].action.error is True

    @pytest.mark.asyncio
    async def test_multiple_async_calls_accumulate(self):
        """Test 6: Multiple async calls accumulate in recorder."""
        client = MockAsyncAnthropicClient()
        wrapped = soma.wrap(
            client, budget={"tokens": 100000}, auto_export=False
        )
        for _ in range(5):
            await wrapped.messages.create(
                model="test", max_tokens=100, messages=[]
            )
        assert len(wrapped.recorder.actions) == 5

    @pytest.mark.asyncio
    async def test_async_openai_client_intercepted(self):
        """Test 7: Async OpenAI client (chat.completions.create) also intercepted."""
        client = MockAsyncOpenAIClient()
        wrapped = soma.wrap(
            client, budget={"tokens": 10000}, auto_export=False
        )
        response = await wrapped.chat.completions.create(
            model="gpt-4", messages=[]
        )
        assert response.choices[0].message.content == "Hello from GPT"
        assert len(wrapped.recorder.actions) == 1

    def test_existing_sync_tests_pattern_unchanged(self):
        """Test 8: Sync wrapping still works (no regression)."""
        from tests.test_wrap import MockAnthropicClient as SyncClient

        client = SyncClient()
        wrapped = soma.wrap(client, auto_export=False)
        response = wrapped.messages.create(
            model="test", max_tokens=100, messages=[]
        )
        assert response.content[0].text == "Hello from Claude"
        assert len(wrapped.recorder.actions) == 1
