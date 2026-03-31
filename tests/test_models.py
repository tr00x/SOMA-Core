"""Tests for model context window lookup."""

from __future__ import annotations

from soma.models import get_context_window


def test_known_model_lookup():
    assert get_context_window("claude-3-opus-20240229") == 200_000


def test_openai_model_lookup():
    assert get_context_window("gpt-4") == 8_192


def test_prefix_match():
    assert get_context_window("claude-3-opus-20240229-beta") == 200_000


def test_unknown_model_returns_default():
    assert get_context_window("unknown-model") == 200_000


def test_gpt4_turbo():
    assert get_context_window("gpt-4-turbo") == 128_000


def test_o3_mini():
    assert get_context_window("o3-mini") == 200_000
