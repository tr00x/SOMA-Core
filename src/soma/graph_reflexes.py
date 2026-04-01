"""SOMA Graph Reflexes — circuit breaker for agent pressure graph.

Pure function module. Tracks consecutive BLOCK/OBSERVE actions to open/close
a circuit breaker per agent. No I/O, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from soma.reflexes import ReflexResult
from soma.types import ResponseMode


@dataclass(frozen=True, slots=True)
class CircuitBreakerState:
    """Immutable state for a per-agent circuit breaker."""

    agent_id: str
    consecutive_block: int = 0
    consecutive_observe: int = 0
    is_open: bool = False


# ── Thresholds ───────────────────────────────────────────────────────

_OPEN_THRESHOLD = 5    # consecutive BLOCKs to trip
_CLOSE_THRESHOLD = 10  # consecutive OBSERVEs to recover


# ── State machine ────────────────────────────────────────────────────


def update_circuit_state(
    state: CircuitBreakerState,
    mode: ResponseMode,
) -> CircuitBreakerState:
    """Return a new CircuitBreakerState after observing *mode*.

    Pure function — no mutation of *state*.
    """
    consecutive_block = state.consecutive_block
    consecutive_observe = state.consecutive_observe
    is_open = state.is_open

    if mode == ResponseMode.BLOCK:
        consecutive_block += 1
        consecutive_observe = 0
    elif mode == ResponseMode.OBSERVE and is_open:
        consecutive_observe += 1
        consecutive_block = 0
    else:
        consecutive_block = 0
        consecutive_observe = 0

    # Trip the breaker
    if consecutive_block >= _OPEN_THRESHOLD:
        is_open = True

    # Recover the breaker
    if consecutive_observe >= _CLOSE_THRESHOLD and is_open:
        is_open = False

    return CircuitBreakerState(
        agent_id=state.agent_id,
        consecutive_block=consecutive_block,
        consecutive_observe=consecutive_observe,
        is_open=is_open,
    )


def evaluate_circuit_breaker(state: CircuitBreakerState) -> ReflexResult:
    """Evaluate the circuit breaker state and return a ReflexResult.

    When open: injects quarantine guidance (never blocks — injection only).
    When closed: allows silently.
    """
    if state.is_open:
        return ReflexResult(
            allow=True,
            reflex_kind="circuit_breaker",
            inject_message=(
                f"[SOMA] Agent {state.agent_id} quarantined "
                "-- sustained high pressure"
            ),
            detail=(
                f"consecutive_block={state.consecutive_block}, "
                "trust -> 0.1"
            ),
        )

    return ReflexResult(allow=True)
