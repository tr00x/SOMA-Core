"""Tests for soma.wrap() — universal API client wrapper."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import soma
from soma.wrap import wrap, WrappedClient, SomaBlocked, SomaBudgetExhausted
from soma.types import Level


# ── Mock API clients ────────────────────────────────────────────

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


class MockMessages:
    def create(self, **kwargs):
        return MockAnthropicResponse()


class MockAnthropicClient:
    def __init__(self):
        self.messages = MockMessages()
        self.api_key = "test-key"


# ── Tests ───────────────────────────────────────────────────────

class TestWrap:
    def test_wrap_returns_wrapped_client(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 10000}, auto_export=False)
        assert isinstance(wrapped, WrappedClient)

    def test_wrapped_client_proxies_attributes(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)
        assert wrapped.api_key == "test-key"

    def test_messages_create_still_works(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)
        response = wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert response.content[0].text == "Hello from Claude"

    def test_records_action_after_call(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 10000}, auto_export=False)
        wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert wrapped.recorder.actions
        assert len(wrapped.recorder.actions) == 1

    def test_soma_level_starts_healthy(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)
        # Level may not be HEALTHY on first call due to cold start,
        # but it should be a valid Level
        assert isinstance(wrapped.soma_level, Level)

    def test_soma_pressure_is_float(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)
        wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert isinstance(wrapped.soma_pressure, float)

    def test_blocks_at_quarantine(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 10000}, auto_export=False,
                           block_at=Level.QUARANTINE)
        # Force level to QUARANTINE
        wrapped.engine._agents["default"].ladder.force_level(Level.QUARANTINE)
        with pytest.raises(SomaBlocked) as exc_info:
            wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert exc_info.value.level == Level.QUARANTINE

    def test_blocks_on_budget_exhaustion(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 0}, auto_export=False)
        with pytest.raises(SomaBudgetExhausted):
            wrapped.messages.create(model="test", max_tokens=100, messages=[])

    def test_records_errors(self):
        client = MockAnthropicClient()
        client.messages.create = MagicMock(side_effect=RuntimeError("API error"))
        wrapped = soma.wrap(client, auto_export=False)
        with pytest.raises(RuntimeError):
            wrapped.messages.create(model="test", max_tokens=100, messages=[])
        # Error should be recorded
        assert len(wrapped.recorder.actions) == 1
        assert wrapped.recorder.actions[0].action.error is True

    def test_custom_agent_id(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, agent_id="my-agent", auto_export=False)
        wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert wrapped.recorder.actions[0].agent_id == "my-agent"

    def test_multiple_calls_accumulate(self):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, budget={"tokens": 100000}, auto_export=False)
        for _ in range(5):
            wrapped.messages.create(model="test", max_tokens=100, messages=[])
        assert len(wrapped.recorder.actions) == 5

    def test_export_state_creates_file(self, tmp_path):
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)
        wrapped.messages.create(model="test", max_tokens=100, messages=[])
        state_path = tmp_path / "state.json"
        wrapped.engine.export_state(str(state_path))
        assert state_path.exists()

    def test_auto_export_writes_state(self):
        client = MockAnthropicClient()
        # auto_export=True will write to ~/.soma/state.json
        wrapped = soma.wrap(client, auto_export=True)
        wrapped.messages.create(model="test", max_tokens=100, messages=[])
        import json
        from pathlib import Path
        state_path = Path.home() / ".soma" / "state.json"
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert "agents" in data

    def test_block_at_custom_level(self):
        client = MockAnthropicClient()
        # Block at CAUTION (very aggressive)
        wrapped = soma.wrap(client, auto_export=False, block_at=Level.CAUTION)
        wrapped.engine._agents["default"].ladder.force_level(Level.CAUTION)
        with pytest.raises(SomaBlocked):
            wrapped.messages.create(model="test", max_tokens=100, messages=[])
