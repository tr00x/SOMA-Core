"""Tests for advanced_signal_reflexes — throttle, anomaly, context overflow."""

from __future__ import annotations

from soma.advanced_signal_reflexes import (
    evaluate_context_overflow,
    evaluate_fingerprint_anomaly,
    evaluate_smart_throttle,
)
from soma.types import ResponseMode


# ── Smart throttle ───────────────────────────────────────────────────


def test_throttle_observe_no_injection():
    """OBSERVE mode -> no injection."""
    result = evaluate_smart_throttle(ResponseMode.OBSERVE)
    assert result.allow is True
    assert result.inject_message is None


def test_throttle_guide_keep_focused():
    """GUIDE mode -> inject 'Keep responses focused'."""
    result = evaluate_smart_throttle(ResponseMode.GUIDE)
    assert result.allow is True
    assert "Keep responses focused" in result.inject_message
    assert result.reflex_kind == "smart_throttle"


def test_throttle_warn_max_tokens():
    """WARN mode -> inject 'Max 500 tokens'."""
    result = evaluate_smart_throttle(ResponseMode.WARN)
    assert result.allow is True
    assert "Max 500 tokens" in result.inject_message
    assert result.reflex_kind == "smart_throttle"


def test_throttle_block_one_sentence():
    """BLOCK mode -> inject 'One sentence only'."""
    result = evaluate_smart_throttle(ResponseMode.BLOCK)
    assert result.allow is True
    assert "One sentence only" in result.inject_message
    assert result.reflex_kind == "smart_throttle"


# ── Fingerprint anomaly ─────────────────────────────────────────────


def test_anomaly_fires_above_2x_baseline():
    """Divergence > 2x baseline_divergence -> alert."""
    result = evaluate_fingerprint_anomaly(0.5, baseline_divergence=0.2)
    assert result.allow is True
    assert result.reflex_kind == "fingerprint_anomaly"
    assert "Behavioral anomaly" in result.inject_message


def test_anomaly_silent_below_2x():
    """Divergence < 2x -> no alert."""
    result = evaluate_fingerprint_anomaly(0.3, baseline_divergence=0.2)
    assert result.allow is True
    assert result.inject_message is None


def test_anomaly_message_matches_spec():
    """Alert message contains explanation text."""
    result = evaluate_fingerprint_anomaly(
        0.6, baseline_divergence=0.2, explanation="tool distribution shifted"
    )
    assert "tool distribution shifted" in result.inject_message
    assert "divergence=0.60" in result.detail


# ── Context overflow ─────────────────────────────────────────────────


def test_context_overflow_at_85_percent():
    """85% -> checkpoint message."""
    result = evaluate_context_overflow(0.85)
    assert result.allow is True
    assert result.reflex_kind == "context_overflow"
    assert "Checkpoint" in result.inject_message
    assert "85%" in result.inject_message


def test_context_overflow_at_96_percent():
    """96% -> CRITICAL message."""
    result = evaluate_context_overflow(0.96)
    assert result.allow is True
    assert result.reflex_kind == "context_overflow"
    assert "CRITICAL" in result.inject_message
    assert "/clear" in result.inject_message


def test_context_overflow_at_70_percent_no_injection():
    """70% -> no injection."""
    result = evaluate_context_overflow(0.70)
    assert result.allow is True
    assert result.inject_message is None


def test_context_overflow_at_exactly_80_percent():
    """Boundary: exactly 80% -> checkpoint message."""
    result = evaluate_context_overflow(0.80)
    assert result.allow is True
    assert result.reflex_kind == "context_overflow"
    assert "Checkpoint" in result.inject_message
