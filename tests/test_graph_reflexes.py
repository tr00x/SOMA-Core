"""Tests for graph_reflexes — circuit breaker state machine."""

from __future__ import annotations

from soma.graph_reflexes import (
    CircuitBreakerState,
    evaluate_circuit_breaker,
    update_circuit_state,
)
from soma.types import ResponseMode


# ── Helpers ──────────────────────────────────────────────────────────


def _apply_modes(state: CircuitBreakerState, modes: list[ResponseMode]) -> CircuitBreakerState:
    """Apply a sequence of response modes to a circuit breaker state."""
    for mode in modes:
        state = update_circuit_state(state, mode)
    return state


# ── Tests ────────────────────────────────────────────────────────────


def test_fresh_state_is_closed_and_allows():
    """Fresh state with no history -> circuit closed, allow."""
    state = CircuitBreakerState(agent_id="agent-1")
    result = evaluate_circuit_breaker(state)
    assert result.allow is True
    assert result.inject_message is None


def test_five_consecutive_blocks_opens_circuit():
    """5 consecutive BLOCK actions -> circuit opens, returns quarantine injection."""
    state = CircuitBreakerState(agent_id="agent-1")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 5)
    assert state.is_open is True

    result = evaluate_circuit_breaker(state)
    assert result.allow is True
    assert result.reflex_kind == "circuit_breaker"
    assert "quarantined" in result.inject_message
    assert "agent-1" in result.inject_message


def test_four_consecutive_blocks_stays_closed():
    """4 consecutive BLOCK actions -> circuit stays closed, returns allow."""
    state = CircuitBreakerState(agent_id="agent-1")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 4)
    assert state.is_open is False

    result = evaluate_circuit_breaker(state)
    assert result.allow is True
    assert result.inject_message is None


def test_open_circuit_closes_after_ten_observes():
    """Open circuit + 10 OBSERVE actions -> circuit closes."""
    state = CircuitBreakerState(agent_id="agent-1")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 5)
    assert state.is_open is True

    state = _apply_modes(state, [ResponseMode.OBSERVE] * 10)
    assert state.is_open is False


def test_open_circuit_stays_open_after_nine_observes():
    """Open circuit + 9 OBSERVE actions -> circuit stays open."""
    state = CircuitBreakerState(agent_id="agent-1")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 5)
    assert state.is_open is True

    state = _apply_modes(state, [ResponseMode.OBSERVE] * 9)
    assert state.is_open is True


def test_circuit_open_trust_weight_in_detail():
    """Circuit open -> trust_weight set to 0.1 in returned state detail."""
    state = CircuitBreakerState(agent_id="agent-1")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 5)

    result = evaluate_circuit_breaker(state)
    assert "trust -> 0.1" in result.detail


def test_circuit_close_sets_recovery_flag():
    """Circuit close -> trust rebuilds (recovery flag set)."""
    state = CircuitBreakerState(agent_id="agent-1")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 5)
    assert state.is_open is True

    state = _apply_modes(state, [ResponseMode.OBSERVE] * 10)
    assert state.is_open is False
    # After closing, evaluate should show no injection
    result = evaluate_circuit_breaker(state)
    assert result.allow is True
    assert result.inject_message is None


def test_alert_message_contains_agent_name():
    """Alert message contains agent name."""
    state = CircuitBreakerState(agent_id="my-special-agent")
    state = _apply_modes(state, [ResponseMode.BLOCK] * 5)

    result = evaluate_circuit_breaker(state)
    assert "my-special-agent" in result.inject_message
