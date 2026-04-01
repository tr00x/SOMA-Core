"""SOMA Planner — session capacity data for agent self-awareness.

NOT a task parser. NOT an LLM call. ONLY computed state data.

Outputs a single line of agent capacity metrics from existing modules:
- session_capacity: actions before predicted pressure > 0.6
- half_life_remaining: estimated actions of effective work left
- historical context: similar past sessions summary

The agent reads this data and decides how to structure its work.
"""

from __future__ import annotations


def compute_session_capacity(
    current_pressure: float,
    action_count: int,
    avg_error_rate: float,
    avg_session_length: float = 50.0,
) -> dict:
    """Compute session capacity metrics from existing modules.

    Returns dict with:
        capacity_actions: estimated actions before pressure > 0.6
        half_life: actions at which success rate = 50%
        success_rate: current predicted success rate
        similar_sessions: count of similar past sessions
        avg_historical_success: average success rate from similar sessions
    """
    from soma.halflife import compute_half_life, predict_success_rate, predict_actions_to_threshold

    half_life = compute_half_life(avg_session_length, avg_error_rate)
    success_rate = predict_success_rate(action_count, half_life)
    actions_to_50 = predict_actions_to_threshold(action_count, half_life, 0.5)

    # Estimate actions until pressure > 0.6 using linear extrapolation
    capacity_actions: int | None = None
    if current_pressure > 0 and action_count > 3:
        pressure_per_action = current_pressure / action_count
        if pressure_per_action > 0:
            remaining = (0.6 - current_pressure) / pressure_per_action
            capacity_actions = max(0, int(remaining))

    return {
        "capacity_actions": capacity_actions,
        "half_life": half_life,
        "success_rate": success_rate,
        "actions_to_50pct": actions_to_50,
    }


def format_capacity_line(
    capacity: dict,
    similar_sessions: int = 0,
    avg_historical_success: float = 0.0,
) -> str:
    """Format capacity data as a single injection line.

    Example output:
        [SOMA] capacity=~43actions half_life=51 success_rate=78%
               similar_sessions=12 avg_success=71%
    """
    parts = ["[SOMA]"]

    cap = capacity.get("capacity_actions")
    if cap is not None:
        parts.append(f"capacity=~{cap}actions")

    hl = capacity.get("half_life", 0)
    parts.append(f"half_life={hl:.0f}")

    sr = capacity.get("success_rate", 1.0)
    parts.append(f"success_rate={sr:.0%}")

    if similar_sessions > 0:
        parts.append(f"similar_sessions={similar_sessions}")
        parts.append(f"avg_success={avg_historical_success:.0%}")

    return " ".join(parts)
