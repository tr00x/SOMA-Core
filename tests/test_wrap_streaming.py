"""Tests for soma.wrap() — streaming interception for Anthropic and OpenAI."""

from __future__ import annotations

import pytest
from dataclasses import dataclass

import soma
from soma.wrap import wrap, WrappedClient, SomaBlocked, SomaBudgetExhausted
from soma.types import ResponseMode


# ── Mock Anthropic Streaming ───────────────────────────────────

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


class MockStreamResponse:
    """Simulates Anthropic's sync streaming context manager."""

    def __init__(self, chunks: list[str] | None = None, error_at: int | None = None):
        self._chunks = chunks or ["Hello", " from", " Claude"]
        self._error_at = error_at
        self._accumulated = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    @property
    def text_stream(self):
        for i, chunk in enumerate(self._chunks):
            if self._error_at is not None and i == self._error_at:
                raise ConnectionError("Stream disconnected")
            self._accumulated += chunk
            yield chunk

    def get_final_message(self):
        return MockAnthropicResponse(
            content=[MockContentBlock(text=self._accumulated or "Hello from Claude")],
            usage=MockUsage(input_tokens=100, output_tokens=50),
        )


class MockAsyncStreamResponse:
    """Simulates Anthropic's async streaming context manager."""

    def __init__(self, chunks: list[str] | None = None):
        self._chunks = chunks or ["Hello", " from", " Claude"]
        self._accumulated = ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @property
    def text_stream(self):
        return self._async_text_stream()

    async def _async_text_stream(self):
        for chunk in self._chunks:
            self._accumulated += chunk
            yield chunk

    def get_final_message(self):
        return MockAnthropicResponse(
            content=[MockContentBlock(text=self._accumulated or "Hello from Claude")],
            usage=MockUsage(input_tokens=100, output_tokens=50),
        )


class MockStreamMessages:
    """Messages namespace with both create (sync) and stream methods."""

    def create(self, **kwargs):
        return MockAnthropicResponse()

    def stream(self, **kwargs):
        return MockStreamResponse()


class MockAsyncStreamMessages:
    """Messages namespace with async create and stream methods."""

    async def create(self, **kwargs):
        return MockAnthropicResponse()

    def stream(self, **kwargs):
        return MockAsyncStreamResponse()


class MockStreamAnthropicClient:
    def __init__(self):
        self.messages = MockStreamMessages()
        self.api_key = "test-key"


class MockAsyncStreamAnthropicClient:
    def __init__(self):
        self.messages = MockAsyncStreamMessages()
        self.api_key = "test-key-async"


# ── Mock OpenAI Streaming ──────────────────────────────────────

@dataclass
class MockChunkDelta:
    content: str | None = None


@dataclass
class MockChunkChoice:
    delta: MockChunkDelta = None

    def __post_init__(self):
        if self.delta is None:
            self.delta = MockChunkDelta()


@dataclass
class MockCompletionChunk:
    choices: list = None

    def __post_init__(self):
        if self.choices is None:
            self.choices = [MockChunkChoice()]


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


class MockStreamingCompletions:
    """OpenAI completions with stream=True support."""

    def create(self, **kwargs):
        if kwargs.get("stream"):
            chunks = [
                MockCompletionChunk(choices=[MockChunkChoice(delta=MockChunkDelta(content="Hello"))]),
                MockCompletionChunk(choices=[MockChunkChoice(delta=MockChunkDelta(content=" from"))]),
                MockCompletionChunk(choices=[MockChunkChoice(delta=MockChunkDelta(content=" GPT"))]),
            ]
            return iter(chunks)
        return MockOpenAIResponse()


class MockStreamingChat:
    def __init__(self):
        self.completions = MockStreamingCompletions()


class MockStreamingOpenAIClient:
    def __init__(self):
        self.chat = MockStreamingChat()
        self.api_key = "test-key-openai"


# ── Tests ───────────────────────────────────────────────────────

class TestAnthropicSyncStream:
    def test_stream_records_one_action(self):
        """Test 1: Anthropic sync stream records exactly one Action with accumulated text."""
        client = MockStreamAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        collected = []
        with wrapped.messages.stream(model="test", max_tokens=100, messages=[]) as stream:
            for text in stream.text_stream:
                collected.append(text)
        assert collected == ["Hello", " from", " Claude"]
        assert len(wrapped.recorder.actions) == 1
        action = wrapped.recorder.actions[0].action
        assert "Hello from Claude" in action.output_text
        assert action.token_count > 0
        assert action.error is False


class TestAnthropicAsyncStream:
    @pytest.mark.asyncio
    async def test_async_stream_records_one_action(self):
        """Test 2: Anthropic async stream records exactly one Action."""
        client = MockAsyncStreamAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        collected = []
        async with wrapped.messages.stream(model="test", max_tokens=100, messages=[]) as stream:
            async for text in stream.text_stream:
                collected.append(text)
        assert collected == ["Hello", " from", " Claude"]
        assert len(wrapped.recorder.actions) == 1
        action = wrapped.recorder.actions[0].action
        assert "Hello from Claude" in action.output_text
        assert action.token_count > 0


class TestOpenAISyncStream:
    def test_openai_stream_records_one_action(self):
        """Test 3: OpenAI sync stream (stream=True) records one Action with accumulated text."""
        client = MockStreamingOpenAIClient()
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        collected = []
        for chunk in wrapped.chat.completions.create(model="gpt-4", messages=[], stream=True):
            if chunk.choices[0].delta.content:
                collected.append(chunk.choices[0].delta.content)
        assert collected == ["Hello", " from", " GPT"]
        assert len(wrapped.recorder.actions) == 1
        action = wrapped.recorder.actions[0].action
        assert "Hello from GPT" in action.output_text


class TestStreamErrors:
    def test_stream_error_records_error_true(self):
        """Test 4: Mid-stream error records error=True Action."""
        client = MockStreamAnthropicClient()
        # Override stream to return error-producing stream
        client.messages.stream = lambda **kwargs: MockStreamResponse(
            chunks=["Hello", " from", " Claude"], error_at=1
        )
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        with pytest.raises(ConnectionError):
            with wrapped.messages.stream(model="test", max_tokens=100, messages=[]) as stream:
                for text in stream.text_stream:
                    pass
        assert len(wrapped.recorder.actions) == 1
        action = wrapped.recorder.actions[0].action
        assert action.error is True


class TestStreamPreCheck:
    def test_stream_blocked_raises_before_streaming(self):
        """Test 5: SomaBlocked raised before streaming starts when mode >= block_at."""
        client = MockStreamAnthropicClient()
        wrapped = soma.wrap(
            client,
            budget={"tokens": 100000},
            auto_export=False,
            block_at=ResponseMode.BLOCK,
        )
        wrapped.engine._agents["default"].mode = ResponseMode.BLOCK
        with pytest.raises(SomaBlocked):
            with wrapped.messages.stream(model="test", max_tokens=100, messages=[]) as stream:
                for text in stream.text_stream:
                    pass


class TestStreamTokenCount:
    def test_stream_records_correct_token_count(self):
        """Test 6: Stream records correct token count from final message usage."""
        client = MockStreamAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        with wrapped.messages.stream(model="test", max_tokens=100, messages=[]) as stream:
            for _ in stream.text_stream:
                pass
        action = wrapped.recorder.actions[0].action
        # MockUsage: input_tokens=100 + output_tokens=50 = 150
        assert action.token_count == 150


class TestStreamNoRegression:
    def test_non_streaming_still_works(self):
        """Test 7: Non-streaming calls still work after stream wrapping."""
        client = MockStreamAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        # Regular (non-stream) create call
        response = wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert response.content[0].text == "Hello from Claude"
        assert len(wrapped.recorder.actions) == 1
        action = wrapped.recorder.actions[0].action
        assert action.error is False
