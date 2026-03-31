"""SOMA Half-Life Estimator — temporal success rate modeling (HLF-01, HLF-02).

Models how an agent's success rate decays as a session grows longer.
Uses fingerprint history to calibrate the decay rate per agent.

The model: P(success at t) = exp(-ln(2) * t / half_life)
where t = action count and half_life = actions at which P = 0.5.

Agents with high historical error rates have shorter effective half-lives
because they degrade faster as context fills.
"""

from __future__ import annotations

import math


def compute_half_life(
    avg_session_length: float,
    avg_error_rate: float,
    min_half_life: float = 10.0,
) -> float:
    """Estimate agent half-life in actions.

    Uses historical avg_session_length as the base, scaled down by error rate.
    High-error agents degrade faster → shorter effective half-life.

    Returns at least min_half_life to avoid division-by-zero edge cases.
    """
    # Error penalty: avg_error_rate=0 → factor=1.0; avg_error_rate=0.5 → factor=0.5
    error_penalty = max(0.3, 1.0 - avg_error_rate)
    return max(min_half_life, avg_session_length * error_penalty)


def predict_success_rate(action_count: int, half_life: float) -> float:
    """Exponential decay: P(t) = exp(-ln(2) * t / half_life).

    Returns 1.0 at t=0, 0.5 at t=half_life, approaching 0 asymptotically.
    """
    if half_life <= 0 or action_count < 0:
        return 0.0
    return math.exp(-math.log(2) * action_count / half_life)


def predict_actions_to_threshold(
    action_count: int,
    half_life: float,
    threshold: float = 0.5,
) -> int | None:
    """Number of additional actions until predicted success rate crosses threshold.

    Returns 0 if already below threshold.
    Returns None if threshold is unreachable (e.g., threshold >= 1.0).
    """
    if threshold <= 0 or threshold >= 1.0:
        return None
    current = predict_success_rate(action_count, half_life)
    if current <= threshold:
        return 0
    # Solve: exp(-ln(2) * t_cross / hl) = threshold → t_cross = -hl * ln(threshold) / ln(2)
    t_cross = -half_life * math.log(threshold) / math.log(2)
    remaining = max(0, math.ceil(t_cross - action_count))
    return remaining


def generate_handoff_suggestion(
    agent_id: str,
    action_count: int,
    half_life: float,
    predicted_success: float,
) -> str:
    """Generate a handoff suggestion message for an agent approaching its half-life.

    Returns a concise human-readable suggestion.
    """
    remaining = predict_actions_to_threshold(action_count, half_life)
    if remaining == 0:
        urgency = f"passed (at {action_count} actions, predicted reliability {predicted_success:.0%})"
    else:
        urgency = f"~{remaining} actions away (currently {predicted_success:.0%} reliability)"

    return (
        f"Agent '{agent_id}' half-life boundary {urgency}. "
        "Recommend: checkpoint progress, summarize state, hand off to fresh context."
    )
