"""Vitals computation for SOMA Core behavioral monitoring."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from soma.types import Action, DriftMode


# ---------------------------------------------------------------------------
# Sigmoid clamp
# ---------------------------------------------------------------------------

def sigmoid_clamp(x: float) -> float:
    """Sigmoid with hard clamps: 0 if x<=0, 1 if x>6, else 1/(1+exp(-x+3))."""
    if x <= 0:
        return 0.0
    if x > 6:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x + 3))


# ---------------------------------------------------------------------------
# Retry rate
# ---------------------------------------------------------------------------

def compute_retry_rate(actions: Sequence[Action]) -> float:
    """Fraction of actions that were retried. Returns 0.0 for empty."""
    if not actions:
        return 0.0
    return sum(1 for a in actions if a.retried) / len(actions)


# ---------------------------------------------------------------------------
# Output entropy
# ---------------------------------------------------------------------------

def compute_output_entropy(text: str) -> float:
    """Normalized Shannon entropy over character bigrams (n=2).

    Returns a value in [0, 1]. Empty text or text shorter than 2 chars
    yields 0.0.
    """
    if len(text) < 2:
        return 0.0

    bigrams = [text[i : i + 2] for i in range(len(text) - 1)]
    total = len(bigrams)
    counts = Counter(bigrams)

    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)

    max_entropy = math.log2(total) if total > 1 else 1.0
    if max_entropy == 0.0:
        return 0.0
    return entropy / max_entropy


# ---------------------------------------------------------------------------
# Tool-call deviation
# ---------------------------------------------------------------------------

def compute_tool_call_deviation(
    actions: Sequence[Action],
    baseline_avg: float,
    baseline_std: float,
) -> float:
    """Absolute z-score of len(actions) relative to baseline.

    Returns 0.0 when baseline_std is 0 (or actions is empty and baseline is 0).
    """
    if baseline_std == 0.0:
        return 0.0
    return abs(len(actions) - baseline_avg) / baseline_std


# ---------------------------------------------------------------------------
# Format deviation
# ---------------------------------------------------------------------------

def compute_format_deviation(output: str, expected_format: list[str]) -> float:
    """Fraction of expected lines that are missing from output.

    Returns 0.0 when expected_format is empty.
    """
    if not expected_format:
        return 0.0
    missing = sum(1 for line in expected_format if line not in output)
    return missing / len(expected_format)


# ---------------------------------------------------------------------------
# Composite uncertainty
# ---------------------------------------------------------------------------

def compute_uncertainty(
    actions: Sequence[Action],
    baseline_tool_calls_avg: float,
    baseline_tool_calls_std: float,
    baseline_entropy: float,
    baseline_entropy_std: float,
    expected_format: list[str] | None,
    weights: tuple[float, float, float, float] = (0.30, 0.25, 0.20, 0.25),
) -> float:
    """Composite uncertainty score in [0, 1].

    Components (weighted sum, then sigmoid_clamp):
      w0: retry_rate
      w1: tool_call_deviation (sigmoid-clamped z-score)
      w2: format_deviation
      w3: entropy deviation from baseline (sigmoid-clamped z-score)
    """
    w_retry, w_tool, w_fmt, w_entropy = weights

    retry = compute_retry_rate(actions)

    tool_dev = compute_tool_call_deviation(
        actions, baseline_tool_calls_avg, baseline_tool_calls_std
    )
    tool_component = sigmoid_clamp(tool_dev)

    fmt_dev = 0.0
    if actions:
        # Average format deviation across all actions
        fmt_devs = [
            compute_format_deviation(a.output_text, expected_format) for a in actions
        ]
        fmt_dev = sum(fmt_devs) / len(fmt_devs)

    # Entropy deviation
    if actions:
        combined_text = " ".join(a.output_text for a in actions)
        current_entropy = compute_output_entropy(combined_text)
    else:
        current_entropy = 0.0

    if baseline_entropy_std > 0.0:
        entropy_z = abs(current_entropy - baseline_entropy) / baseline_entropy_std
    else:
        entropy_z = 0.0
    entropy_component = sigmoid_clamp(entropy_z)

    score = (
        w_retry * retry
        + w_tool * tool_component
        + w_fmt * fmt_dev
        + w_entropy * entropy_component
    )
    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Behavior vector
# ---------------------------------------------------------------------------

def compute_behavior_vector(
    actions: Sequence[Action],
    known_tools: list[str],
) -> list[float]:
    """Compute a behavior feature vector.

    Features:
      [0] avg_tool_calls  — mean number of tool calls per action (always len/len = 1 if any)
      [1] avg_output_len  — mean output text length
      [2] avg_response_time — mean duration_sec
      [3] pattern_entropy — entropy of tool sequence
      [*] tool_dist       — fraction of actions using each known tool
    """
    n = len(actions)

    if n == 0:
        base = [0.0, 0.0, 0.0, 0.0]
        tool_dist = [0.0] * len(known_tools)
        return base + tool_dist

    avg_tool_calls = 1.0  # Each action IS a tool call
    # Normalize avg_output_len to [0, 1] range using a reference scale of 1000 chars
    avg_output_len = sum(len(a.output_text) for a in actions) / n / 1000.0
    avg_response_time = sum(a.duration_sec for a in actions) / n

    # Pattern entropy over tool sequence
    tool_counts = Counter(a.tool_name for a in actions)
    pattern_entropy = 0.0
    for count in tool_counts.values():
        p = count / n
        pattern_entropy -= p * math.log2(p)

    # Tool distribution
    tool_dist = [tool_counts.get(tool, 0) / n for tool in known_tools]

    return [avg_tool_calls, avg_output_len, avg_response_time, pattern_entropy] + tool_dist


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 for zero vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Goal coherence
# ---------------------------------------------------------------------------

def compute_goal_coherence(
    current_actions: Sequence[Action],
    initial_task_vector: list[float],
    initial_known_tools: list[str],
) -> float:
    """Cosine similarity between current behavior and initial task signature.

    Returns float in [0, 1]. Higher = agent still working on original task.
    Uses initial_known_tools (frozen at signature capture time) to ensure
    consistent vector dimensionality.
    """
    current_vec = compute_behavior_vector(current_actions, initial_known_tools)
    return cosine_similarity(current_vec, initial_task_vector)


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def compute_drift(
    actions: Sequence[Action],
    baseline_vector: list[float],
    known_tools: list[str],
) -> float:
    """Behavioral drift = 1 - cosine_similarity(current_vector, baseline_vector)."""
    current = compute_behavior_vector(actions, known_tools)
    return 1.0 - cosine_similarity(current, baseline_vector)


# ---------------------------------------------------------------------------
# Drift mode
# ---------------------------------------------------------------------------

def determine_drift_mode(
    drift: float,
    drift_threshold: float,
    error_rate: float,
    error_rate_baseline: float,
    progress_stalled: bool,
    uncertainty: float,
    uncertainty_threshold: float,
) -> DriftMode:
    """Determine drift mode.

    Returns DIRECTIVE if drift exceeds threshold AND at least one
    confirmatory signal (elevated error rate, stalled progress, or
    elevated uncertainty) is present. Otherwise INFORMATIONAL.
    """
    if drift > drift_threshold:
        elevated_errors = error_rate > error_rate_baseline
        elevated_uncertainty = uncertainty > uncertainty_threshold
        if elevated_errors or progress_stalled or elevated_uncertainty:
            return DriftMode.DIRECTIVE
    return DriftMode.INFORMATIONAL


# ---------------------------------------------------------------------------
# Resource vitals
# ---------------------------------------------------------------------------

@dataclass
class ResourceVitals:
    """Resource usage vitals, all values in [0, 1]."""
    token_usage: float
    cost: float
    error_rate: float


def compute_resource_vitals(
    token_used: float,
    token_limit: float,
    cost_spent: float,
    cost_budget: float,
    errors_in_window: int,
    actions_in_window: int,
) -> ResourceVitals:
    """Compute resource vitals, all clamped to [0, 1].

    Zero limits yield 0.0 (no resource consumed).
    """
    token_usage = min(1.0, token_used / token_limit) if token_limit > 0 else 0.0
    cost = min(1.0, cost_spent / cost_budget) if cost_budget > 0 else 0.0
    error_rate = (
        min(1.0, errors_in_window / actions_in_window)
        if actions_in_window > 0
        else 0.0
    )
    return ResourceVitals(
        token_usage=max(0.0, token_usage),
        cost=max(0.0, cost),
        error_rate=max(0.0, error_rate),
    )
