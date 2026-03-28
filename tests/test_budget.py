"""Tests for soma.budget.MultiBudget."""

from __future__ import annotations

import time

import pytest

from soma.budget import MultiBudget


def make_budget(**limits: float) -> MultiBudget:
    return MultiBudget(limits)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_health_is_1():
    b = make_budget(tokens=100.0, cost=10.0)
    assert b.health() == pytest.approx(1.0)


def test_empty_budget_health_is_1():
    b = MultiBudget({})
    assert b.health() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# spend
# ---------------------------------------------------------------------------

def test_spend_reduces_health():
    b = make_budget(tokens=100.0)
    b.spend(tokens=50.0)
    assert b.health() == pytest.approx(0.5)


def test_overspend_clamps_to_zero_health():
    b = make_budget(tokens=100.0)
    b.spend(tokens=200.0)
    assert b.health() == pytest.approx(0.0)
    assert b.remaining("tokens") == pytest.approx(0.0)
    assert b.spent["tokens"] == pytest.approx(100.0)


def test_bottleneck_dim_determines_health():
    """health() is the *minimum* across all dims."""
    b = make_budget(tokens=100.0, cost=10.0)
    b.spend(tokens=20.0, cost=9.0)  # tokens=80% remaining, cost=10% remaining
    assert b.health() == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# replenish
# ---------------------------------------------------------------------------

def test_replenish_increases_remaining():
    b = make_budget(tokens=100.0)
    b.spend(tokens=60.0)
    b.replenish("tokens", 20.0)
    assert b.remaining("tokens") == pytest.approx(60.0)


def test_replenish_clamps_at_zero_spent():
    b = make_budget(tokens=100.0)
    b.spend(tokens=10.0)
    b.replenish("tokens", 999.0)
    assert b.spent["tokens"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# burn_rate
# ---------------------------------------------------------------------------

def test_burn_rate_positive_after_spend():
    b = make_budget(tokens=100.0)
    b.spend(tokens=50.0)
    time.sleep(0.01)
    assert b.burn_rate("tokens") > 0.0


# ---------------------------------------------------------------------------
# projected_overshoot
# ---------------------------------------------------------------------------

def test_projected_overshoot_no_overshoot():
    b = make_budget(tokens=100.0)
    b.spend(tokens=10.0)
    # 10 spent after 10 steps → 1/step * 100 steps = 100 = limit → 0 overshoot
    overshoot = b.projected_overshoot("tokens", estimated_total_steps=100, current_step=10)
    assert overshoot == pytest.approx(0.0)


def test_projected_overshoot_positive():
    b = make_budget(tokens=100.0)
    b.spend(tokens=20.0)
    # 20 spent after 10 steps → 2/step * 100 steps = 200 → 100 overshoot
    overshoot = b.projected_overshoot("tokens", estimated_total_steps=100, current_step=10)
    assert overshoot == pytest.approx(100.0)


def test_projected_overshoot_zero_current_step():
    b = make_budget(tokens=100.0)
    assert b.projected_overshoot("tokens", estimated_total_steps=100, current_step=0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# is_exhausted
# ---------------------------------------------------------------------------

def test_is_exhausted_false_initially():
    b = make_budget(tokens=100.0)
    assert not b.is_exhausted()


def test_is_exhausted_true_when_spent():
    b = make_budget(tokens=100.0)
    b.spend(tokens=100.0)
    assert b.is_exhausted()


# ---------------------------------------------------------------------------
# Properties return copies
# ---------------------------------------------------------------------------

def test_limits_property_returns_copy():
    b = make_budget(tokens=100.0)
    copy = b.limits
    copy["tokens"] = 999.0
    assert b.limits["tokens"] == pytest.approx(100.0)


def test_spent_property_returns_copy():
    b = make_budget(tokens=100.0)
    b.spend(tokens=30.0)
    copy = b.spent
    copy["tokens"] = 999.0
    assert b.spent["tokens"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Serialization roundtrip
# ---------------------------------------------------------------------------

def test_serialization_roundtrip():
    b = make_budget(tokens=100.0, cost=5.0)
    b.spend(tokens=40.0, cost=2.5)
    data = b.to_dict()
    b2 = MultiBudget.from_dict(data)
    assert b2.limits == b.limits
    assert b2.spent == b.spent
    assert b2.health() == pytest.approx(b.health())
