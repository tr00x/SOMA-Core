"""Tests for SOMA threshold tuner — percentile-based threshold optimization."""

from __future__ import annotations

from soma.threshold_tuner import compute_optimal_thresholds


def _make_run(per_action: list[dict]) -> dict:
    """Create a synthetic benchmark run result."""
    return {"per_action": per_action}


def test_returns_guide_warn_block_keys():
    """compute_optimal_thresholds returns dict with guide, warn, block keys."""
    result = compute_optimal_thresholds([])
    assert set(result.keys()) == {"guide", "warn", "block"}


def test_no_false_positives_returns_defaults():
    """Tuner with no false positives returns default thresholds."""
    # All GUIDE actions are true positives (error in next 3)
    actions = [
        {"pressure": 0.3, "mode": "GUIDE", "error": False},
        {"pressure": 0.35, "mode": "OBSERVE", "error": True},  # error within 3
        {"pressure": 0.1, "mode": "OBSERVE", "error": False},
    ]
    result = compute_optimal_thresholds([_make_run(actions)])
    assert result == {"guide": 0.25, "warn": 0.50, "block": 0.75}


def test_many_false_positives_raises_guide():
    """Tuner with many false positives at low pressure raises guide threshold."""
    # Many GUIDE triggers with no subsequent error = false positives
    actions = []
    for i in range(20):
        actions.append({"pressure": 0.3 + i * 0.01, "mode": "GUIDE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})

    result = compute_optimal_thresholds([_make_run(actions)])
    assert result["guide"] > 0.25  # Should be raised above default


def test_warn_block_spacing():
    """warn = guide + 0.25, block = guide + 0.50 always."""
    # Create scenario with known false positive distribution
    actions = []
    for i in range(30):
        actions.append({"pressure": 0.35 + i * 0.005, "mode": "GUIDE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})

    result = compute_optimal_thresholds([_make_run(actions)])
    guide = result["guide"]
    assert abs(result["warn"] - min(guide + 0.25, 0.90)) < 1e-10
    assert abs(result["block"] - min(guide + 0.50, 0.95)) < 1e-10


def test_respects_target_false_positive_rate():
    """Tuner respects target_false_positive_rate parameter."""
    actions = []
    for i in range(50):
        p = 0.2 + i * 0.01
        actions.append({"pressure": p, "mode": "GUIDE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})

    strict = compute_optimal_thresholds([_make_run(actions)], target_false_positive_rate=0.01)
    lenient = compute_optimal_thresholds([_make_run(actions)], target_false_positive_rate=0.20)
    assert strict["guide"] >= lenient["guide"]


def test_empty_runs_returns_defaults():
    """Empty run list returns default thresholds."""
    result = compute_optimal_thresholds([])
    assert result == {"guide": 0.25, "warn": 0.50, "block": 0.75}


def test_guide_clamped_to_safety_bounds():
    """Guide threshold is clamped between 0.10 and 0.60."""
    # All false positives at very high pressure
    actions = []
    for _ in range(20):
        actions.append({"pressure": 0.9, "mode": "WARN", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})
        actions.append({"pressure": 0.1, "mode": "OBSERVE", "error": False})

    result = compute_optimal_thresholds([_make_run(actions)])
    assert result["guide"] <= 0.60
    assert result["guide"] >= 0.10
