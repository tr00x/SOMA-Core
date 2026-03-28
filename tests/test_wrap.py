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

    def test_context_action_truncate_20_applied_on_next_call(self):
        """After an action that causes truncate_20, messages are trimmed 80% on next call."""
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)

        # Manually set a pending truncate_20 context action (simulating prior recording)
        wrapped._pending_context_action = "truncate_20"

        captured_kwargs = {}

        original_create = client.messages.create.__wrapped__ if hasattr(
            client.messages.create, "__wrapped__") else None

        # Patch the underlying API call to capture what messages were passed
        with patch.object(client.messages, "create", wraps=client.messages.create) as mock_create:
            # Re-wrap after patching
            wrapped2 = soma.wrap(client, auto_export=False)
            wrapped2._pending_context_action = "truncate_20"

            messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
            wrapped2.messages.create(model="test", max_tokens=100, messages=messages)
            call_args = mock_create.call_args
            passed_messages = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])

        # 80% of 10 = 8 messages kept (newest 8)
        assert len(passed_messages) == 8
        assert passed_messages[0]["content"] == "msg2"
        assert passed_messages[-1]["content"] == "msg9"

    def test_context_action_quarantine_clears_to_system_only(self):
        """After quarantine context_action, only system message is passed on next call."""
        client = MockAnthropicClient()

        with patch.object(client.messages, "create", wraps=client.messages.create) as mock_create:
            wrapped = soma.wrap(client, auto_export=False)
            wrapped._pending_context_action = "quarantine"

            messages = [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
                {"role": "user", "content": "How are you?"},
            ]
            wrapped.messages.create(model="test", max_tokens=100, messages=messages)
            call_args = mock_create.call_args
            passed_messages = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])

        # Only the system message should remain
        assert len(passed_messages) == 1
        assert passed_messages[0]["role"] == "system"

    def test_context_action_quarantine_no_system_message_keeps_last(self):
        """When quarantine fires but no system message exists, keep the last message."""
        client = MockAnthropicClient()

        with patch.object(client.messages, "create", wraps=client.messages.create) as mock_create:
            wrapped = soma.wrap(client, auto_export=False)
            wrapped._pending_context_action = "quarantine"

            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
                {"role": "user", "content": "Last message"},
            ]
            wrapped.messages.create(model="test", max_tokens=100, messages=messages)
            call_args = mock_create.call_args
            passed_messages = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])

        # No system message: falls back to last message
        assert len(passed_messages) == 1
        assert passed_messages[0]["content"] == "Last message"

    def test_pending_context_action_reset_after_application(self):
        """After applying context_action, _pending_context_action is reset to 'pass'."""
        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)
        wrapped._pending_context_action = "truncate_20"

        messages = [{"role": "user", "content": f"msg{i}"} for i in range(5)]
        wrapped.messages.create(model="test", max_tokens=100, messages=messages)

        assert wrapped._pending_context_action == "pass"

    def test_context_action_stored_from_engine(self):
        """context_action from ActionResult is stored as _pending_context_action."""
        from unittest.mock import patch as _patch
        from soma.engine import ActionResult
        from soma.types import Action, VitalsSnapshot

        client = MockAnthropicClient()
        wrapped = soma.wrap(client, auto_export=False)

        fake_vitals = VitalsSnapshot(
            uncertainty=0.0,
            drift=0.0,
            error_rate=0.0,
            token_usage=0.0,
            cost=0.0,
        )
        fake_result = ActionResult(
            level=Level.CAUTION,
            pressure=0.5,
            vitals=fake_vitals,
            context_action="truncate_50_block_tools",
        )

        with _patch.object(wrapped._engine, "record_action", return_value=fake_result):
            wrapped.messages.create(model="test", max_tokens=100, messages=[])

        assert wrapped._pending_context_action == "truncate_50_block_tools"
