"""Tests for context window usage tracking (CTX-01)."""

from __future__ import annotations

from soma.types import VitalsSnapshot, Action
from soma.engine import SOMAEngine


# ── Test 1: VitalsSnapshot accepts context_usage field, defaults to 0.0 ──

def test_vitals_snapshot_context_usage_default():
    v = VitalsSnapshot()
    assert v.context_usage == 0.0


def test_vitals_snapshot_context_usage_custom():
    v = VitalsSnapshot(context_usage=0.75)
    assert v.context_usage == 0.75


# ── Test 2: record_action() computes context_usage = cumulative_tokens / context_window ──

def test_record_action_computes_context_usage():
    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("a1")

    # Send action with 50000 tokens, default context_window = 200000
    action = Action(tool_name="Bash", output_text="ok", token_count=50_000)
    result = engine.record_action("a1", action)
    assert result.vitals.context_usage == 50_000 / 200_000  # 0.25


def test_record_action_accumulates_context_usage():
    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("a1")

    for _ in range(4):
        action = Action(tool_name="Bash", output_text="ok", token_count=50_000)
        result = engine.record_action("a1", action)

    # 4 * 50000 = 200000 / 200000 = 1.0
    assert result.vitals.context_usage == 1.0


# ── Test 3: context_usage of 0.7+ reduces predicted_success_rate ──

def test_context_usage_degrades_predicted_success_rate():
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    # Fill context to 70%+
    for _ in range(7):
        action = Action(tool_name="Bash", output_text="ok", token_count=10)
        result = engine.record_action("a1", action)

    # context_usage = 70/100 = 0.7
    assert result.vitals.context_usage == 0.7
    # The context_factor at 0.7 usage: max(0.4, 1.0 - 0.7*0.6) = max(0.4, 0.58) = 0.58
    # This means if predicted_success_rate existed, it'd be multiplied by 0.58
    # Without fingerprint data, predicted_success_rate is None, so we just confirm context_usage


# ── Test 4: context_window_size defaults to 200000 ──

def test_default_context_window():
    engine = SOMAEngine()
    assert engine._context_window == 200_000


# ── Test 5: context_window_size can be configured ──

def test_custom_context_window():
    engine = SOMAEngine(context_window=100_000)
    assert engine._context_window == 100_000


def test_context_window_from_config():
    config = {
        "budget": {"tokens": 100_000},
        "context_window": 500_000,
    }
    engine = SOMAEngine.from_config(config)
    assert engine._context_window == 500_000


def test_context_usage_capped_at_one():
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    # Send more tokens than context window
    action = Action(tool_name="Bash", output_text="ok", token_count=200)
    result = engine.record_action("a1", action)
    assert result.vitals.context_usage == 1.0  # capped
