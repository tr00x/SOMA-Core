"""Tests for soma.planner — session capacity computation."""

from __future__ import annotations

import pytest

from soma.planner import compute_session_capacity, format_capacity_line


class TestComputeSessionCapacity:
    def test_basic_capacity(self):
        result = compute_session_capacity(
            current_pressure=0.30,
            action_count=10,
            avg_error_rate=0.15,
        )
        assert "capacity_actions" in result
        assert "half_life" in result
        assert "success_rate" in result
        assert "actions_to_50pct" in result
        assert result["success_rate"] > 0
        assert result["half_life"] > 0

    def test_zero_pressure(self):
        result = compute_session_capacity(
            current_pressure=0.0,
            action_count=5,
            avg_error_rate=0.10,
        )
        # Can't estimate capacity from zero pressure
        assert result["capacity_actions"] is None

    def test_high_pressure(self):
        result = compute_session_capacity(
            current_pressure=0.70,
            action_count=20,
            avg_error_rate=0.30,
        )
        # Already past 0.6 threshold — capacity should be 0
        assert result["capacity_actions"] == 0

    def test_zero_error_rate(self):
        result = compute_session_capacity(
            current_pressure=0.10,
            action_count=10,
            avg_error_rate=0.0,
        )
        assert result["success_rate"] > 0.8
        assert result["half_life"] > 0

    def test_few_actions_no_capacity_estimate(self):
        result = compute_session_capacity(
            current_pressure=0.05,
            action_count=2,
            avg_error_rate=0.10,
        )
        # Too few actions for linear extrapolation
        assert result["capacity_actions"] is None


class TestFormatCapacityLine:
    def test_basic_format(self):
        cap = {
            "capacity_actions": 43,
            "half_life": 51.0,
            "success_rate": 0.78,
            "actions_to_50pct": 20,
        }
        line = format_capacity_line(cap)
        assert "[SOMA]" in line
        assert "capacity=~43actions" in line
        assert "half_life=51" in line
        assert "success_rate=78%" in line

    def test_with_historical(self):
        cap = {"half_life": 50.0, "success_rate": 0.80}
        line = format_capacity_line(cap, similar_sessions=12, avg_historical_success=0.71)
        assert "similar_sessions=12" in line
        assert "avg_success=71%" in line

    def test_no_capacity(self):
        cap = {"capacity_actions": None, "half_life": 50.0, "success_rate": 1.0}
        line = format_capacity_line(cap)
        assert "capacity=" not in line
        assert "half_life=50" in line

    def test_empty_capacity(self):
        cap = {}
        line = format_capacity_line(cap)
        assert "[SOMA]" in line
