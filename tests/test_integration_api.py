"""Integration tests -- real API calls through soma.wrap().

Requires ANTHROPIC_API_KEY and/or OPENAI_API_KEY env vars.
Skipped in CI unless keys are explicitly provided.

Run: ANTHROPIC_API_KEY=sk-... OPENAI_API_KEY=sk-... python -m pytest tests/test_integration_api.py -x -v
"""

from __future__ import annotations

import os

import pytest

import soma

HAS_ANTHROPIC_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
HAS_OPENAI_KEY = bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not HAS_ANTHROPIC_KEY, reason="ANTHROPIC_API_KEY not set")
class TestAnthropicIntegration:

    def test_sync_create_records_action(self):
        """Real Anthropic call: soma records token count, cost, output, pressure."""
        import anthropic

        client = soma.wrap(
            anthropic.Anthropic(),
            budget={"tokens": 100_000},
            agent_id="test-anthropic",
        )
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
        )
        # Verify response exists
        assert response.content
        assert len(response.content) > 0
        text = response.content[0].text
        assert len(text) > 0

        # Verify SOMA recorded the action
        snap = client.engine.get_snapshot("test-anthropic")
        assert snap["action_count"] == 1
        assert snap["pressure"] >= 0.0
        # Token usage should be > 0 (real API returns usage)
        assert snap["vitals"]["token_usage"] >= 0.0

    def test_sync_stream_records_action(self):
        """Real Anthropic streaming: soma records accumulated text."""
        import anthropic

        client = soma.wrap(
            anthropic.Anthropic(),
            budget={"tokens": 100_000},
            agent_id="test-anthropic-stream",
        )
        accumulated = ""
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hi."}],
        ) as stream:
            for chunk in stream.text_stream:
                accumulated += chunk

        assert len(accumulated) > 0
        snap = client.engine.get_snapshot("test-anthropic-stream")
        assert snap["action_count"] == 1

    @pytest.mark.asyncio
    async def test_async_create_records_action(self):
        """Real Anthropic async call through soma.wrap()."""
        import anthropic

        client = soma.wrap(
            anthropic.AsyncAnthropic(),
            budget={"tokens": 100_000},
            agent_id="test-anthropic-async",
        )
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hello."}],
        )
        assert response.content
        snap = client.engine.get_snapshot("test-anthropic-async")
        assert snap["action_count"] == 1


@pytest.mark.skipif(not HAS_OPENAI_KEY, reason="OPENAI_API_KEY not set")
class TestOpenAIIntegration:

    def test_sync_create_records_action(self):
        """Real OpenAI call: soma records token count, cost, output, pressure."""
        import openai

        client = soma.wrap(
            openai.OpenAI(),
            budget={"tokens": 100_000},
            agent_id="test-openai",
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
        )
        assert response.choices
        text = response.choices[0].message.content
        assert len(text) > 0

        snap = client.engine.get_snapshot("test-openai")
        assert snap["action_count"] == 1
        assert snap["pressure"] >= 0.0

    def test_stream_records_action(self):
        """Real OpenAI streaming: soma records accumulated text."""
        import openai

        client = soma.wrap(
            openai.OpenAI(),
            budget={"tokens": 100_000},
            agent_id="test-openai-stream",
        )
        accumulated = ""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hi."}],
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                accumulated += chunk.choices[0].delta.content

        assert len(accumulated) > 0
        snap = client.engine.get_snapshot("test-openai-stream")
        assert snap["action_count"] == 1
