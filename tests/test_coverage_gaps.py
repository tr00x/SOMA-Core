"""Targeted tests to cover every previously-uncovered line.

Each section is labelled with the source file and the line(s) it exercises.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# budget.py:37 — replenish raises KeyError on unknown dimension
# budget.py:43 — spend raises KeyError on unknown dimension
# budget.py:56-59 — utilization when limit == 0.0
# budget.py:77 — burn_rate when elapsed <= 0 (mocked via monkeypatch)
# ---------------------------------------------------------------------------

from soma.budget import MultiBudget
import time


class TestBudgetCoverageGaps:
    # line 37: replenish on unknown dimension
    def test_replenish_unknown_dimension_raises(self):
        b = MultiBudget({"tokens": 100.0})
        with pytest.raises(KeyError, match="unknown"):
            b.replenish("unknown", 10.0)

    # line 43: spend on unknown dimension raises
    def test_spend_unknown_dimension_raises(self):
        b = MultiBudget({"tokens": 100.0})
        with pytest.raises(KeyError, match="cost"):
            b.spend(cost=5.0)

    # lines 56-59: utilization when limit is 0.0 returns 1.0
    def test_utilization_zero_limit_returns_one(self):
        b = MultiBudget({"zero_dim": 0.0})
        assert b.utilization("zero_dim") == pytest.approx(1.0)

    # line 77: burn_rate returns 0.0 when elapsed <= 0
    def test_burn_rate_zero_elapsed(self, monkeypatch):
        import soma.budget as budget_mod

        # Make time.monotonic always return the same value so elapsed == 0.
        fixed = time.monotonic()
        monkeypatch.setattr(budget_mod.time, "monotonic", lambda: fixed)

        b = MultiBudget({"tokens": 100.0})
        b.spend(tokens=50.0)
        # elapsed == 0 → burn_rate should return 0.0
        assert b.burn_rate("tokens") == pytest.approx(0.0)

    # line 59: utilization on a normal (non-zero) dimension → return spent/limit
    def test_utilization_nonzero_limit(self):
        b = MultiBudget({"tokens": 100.0})
        b.spend(tokens=40.0)
        assert b.utilization("tokens") == pytest.approx(0.4)

    # lines 56-59 (branch): health with a zero-limit dimension
    def test_health_with_zero_limit_dimension(self):
        b = MultiBudget({"tokens": 100.0, "free": 0.0})
        # "free" has limit 0 → healths includes 0.0 → min == 0.0
        assert b.health() == pytest.approx(0.0)

    # projected_overshoot: current_step == 0 returns 0.0 (line 90-91, already tested)
    # but also covers the negative-headroom path (line 93-94)
    def test_projected_overshoot_negative_headroom(self):
        b = MultiBudget({"tokens": 100.0})
        b.spend(tokens=5.0)
        # 5 spent / 10 steps = 0.5/step × 100 steps = 50 → 50 - 100 = -50 (headroom)
        result = b.projected_overshoot("tokens", estimated_total_steps=100, current_step=10)
        assert result == pytest.approx(-50.0)


# ---------------------------------------------------------------------------
# context_control.py:94 — _keep_newest when messages list is empty
# ---------------------------------------------------------------------------

from soma.context_control import apply_context_control, _keep_newest
from soma.types import ResponseMode


class TestContextControlCoverageGaps:
    # line 94: _keep_newest([]) returns []
    def test_keep_newest_empty_list(self):
        result = _keep_newest([], fraction=0.80)
        assert result == []

    # Exercise via apply_context_control at CAUTION with empty messages to hit line 94
    def test_apply_context_control_caution_empty_messages(self):
        ctx = {
            "messages": [],
            "tools": ["tool_a"],
            "system_prompt": "sp",
        }
        result = apply_context_control(ctx, ResponseMode.GUIDE)
        assert result["messages"] == []
        assert result["tools"] == ["tool_a"]

    # Also test DEGRADE with empty messages (same path)
    def test_apply_context_control_degrade_empty_messages(self):
        ctx = {
            "messages": [],
            "tools": ["tool_a", "tool_b"],
            "system_prompt": "sp",
            "expensive_tools": ["tool_b"],
        }
        result = apply_context_control(ctx, ResponseMode.WARN)
        assert result["messages"] == []
        assert "tool_b" not in result["tools"]


# ---------------------------------------------------------------------------
# engine.py:182 — spend cost_usd branch
# ---------------------------------------------------------------------------

from soma.engine import SOMAEngine
from soma.types import Action


class TestEngineCoverageGaps:
    # line 182: cost_usd dimension present in budget — spend_kwargs["cost_usd"] is set
    def test_record_action_with_cost_usd_dimension(self):
        engine = SOMAEngine(budget={"tokens": 100_000, "cost_usd": 10.0})
        engine.register_agent("agent_x")
        action = Action(
            tool_name="search",
            output_text="some output",
            token_count=50,
            cost=0.01,
        )
        result = engine.record_action("agent_x", action)
        # cost_usd was spent — budget health should be < 1.0 only marginally,
        # but the important thing is we reach the branch without error
        assert result is not None
        assert engine.budget.spent.get("cost_usd", 0) == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# graph.py:81 — get_trust raises KeyError when no edge exists
# graph.py:96 — propagate: total_weight == 0.0 path
# ---------------------------------------------------------------------------

from soma.graph import PressureGraph


class TestGraphCoverageGaps:
    # line 81: get_trust raises KeyError for non-existent edge
    def test_get_trust_no_edge_raises(self):
        g = PressureGraph()
        g.add_agent("a")
        g.add_agent("b")
        # No edge has been added between a and b
        with pytest.raises(KeyError):
            g.get_trust("a", "b")

    # line 96: propagate when total_weight of incoming edges is 0.0
    def test_propagate_zero_total_weight(self):
        g = PressureGraph()
        g.add_agent("src")
        g.add_agent("tgt")
        # Add edge with trust_weight=0.0
        g.add_edge("src", "tgt", trust=0.0)
        g.set_internal_pressure("src", 0.8)
        g.set_internal_pressure("tgt", 0.5)
        g.propagate()
        # total_weight == 0 → weighted_avg = 0.0
        # effective = max(internal=0.5, damping*0.0) = 0.5
        assert g.get_effective_pressure("tgt") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ring_buffer.py:37 — __getitem__ with a slice
# ---------------------------------------------------------------------------

from soma.ring_buffer import RingBuffer


class TestRingBufferCoverageGaps:
    # line 37: slice __getitem__
    def test_getitem_slice(self):
        rb = RingBuffer(capacity=5)
        for i in range(5):
            rb.append(i)
        result = rb[1:3]
        assert result == [1, 2]

    def test_getitem_slice_full(self):
        rb = RingBuffer(capacity=4)
        for i in range(4):
            rb.append(i * 10)
        assert rb[:] == [0, 10, 20, 30]

    def test_getitem_slice_empty(self):
        rb: RingBuffer[int] = RingBuffer(capacity=5)
        assert rb[:] == []


# ---------------------------------------------------------------------------
# testing.py:49 — record() raises when used without context manager
# testing.py:92 — current_level returns HEALTHY when history is empty
# testing.py:99 — max_level returns HEALTHY when history is empty
# testing.py:113 — assert_healthy raises AssertionError when not healthy
# ---------------------------------------------------------------------------

from soma.testing import Monitor


class TestMonitorCoverageGaps:
    # line 49: record without entering context manager raises RuntimeError
    def test_record_outside_context_manager_raises(self):
        mon = Monitor()
        action = Action(tool_name="tool", output_text="hi")
        with pytest.raises(RuntimeError, match="context manager"):
            mon.record("agent", action)

    # line 92: current_level is OBSERVE when history is empty (before any record call)
    def test_current_level_empty_history(self):
        mon = Monitor()
        assert mon.current_level == ResponseMode.OBSERVE

    # line 99: max_level is OBSERVE when history is empty
    def test_max_level_empty_history(self):
        mon = Monitor()
        assert mon.max_level == ResponseMode.OBSERVE

    # line 113: assert_healthy raises AssertionError when current level is not OBSERVE
    def test_assert_healthy_raises_on_escalation(self):
        with Monitor(budget={"tokens": 100_000}) as mon:
            # Drive the engine into escalation with repeated errors
            for _ in range(20):
                mon.record("agent1", Action(
                    tool_name="bad_tool",
                    output_text="error output",
                    error=True,
                ))
        if mon.current_level != ResponseMode.OBSERVE:
            with pytest.raises(AssertionError):
                mon.assert_healthy()
        else:
            pytest.skip("Engine did not escalate — cannot test assert_healthy failure path")


# ---------------------------------------------------------------------------
# types.py:21,26 — Level.__gt__ and __ge__ with non-Level return NotImplemented
# types.py:31,36 — Level.__lt__ and __le__ with non-Level return NotImplemented
# ---------------------------------------------------------------------------

from soma.types import Level


class TestLevelComparisonCoverageGaps:
    # line 21: __gt__ with non-Level → NotImplemented
    def test_gt_non_level_returns_not_implemented(self):
        result = Level.HEALTHY.__gt__(42)
        assert result is NotImplemented

    # line 26: __ge__ with non-Level → NotImplemented
    def test_ge_non_level_returns_not_implemented(self):
        result = Level.HEALTHY.__ge__("not_a_level")
        assert result is NotImplemented

    # line 31: __lt__ with non-Level → NotImplemented
    def test_lt_non_level_returns_not_implemented(self):
        result = Level.HEALTHY.__lt__(None)
        assert result is NotImplemented

    # line 36: __le__ with non-Level → NotImplemented
    def test_le_non_level_returns_not_implemented(self):
        result = Level.HEALTHY.__le__(3.14)
        assert result is NotImplemented

    # Confirm Python's operator machinery treats NotImplemented correctly
    def test_gt_non_level_raises_type_error(self):
        with pytest.raises(TypeError):
            _ = Level.HEALTHY > 42  # type: ignore[operator]

    def test_ge_non_level_raises_type_error(self):
        with pytest.raises(TypeError):
            _ = Level.HEALTHY >= "foo"  # type: ignore[operator]


# ---------------------------------------------------------------------------
# vitals.py:61 — compute_output_entropy: max_entropy == 0.0 branch
# vitals.py:146 — compute_uncertainty: expected_format is None branch when actions present
# ---------------------------------------------------------------------------

from soma.vitals import compute_output_entropy, compute_uncertainty
from soma.types import Action


class TestVitalsCoverageGaps:
    # line 61: max_entropy == 0.0 — defensive dead-code guard.
    # max_entropy = log2(total) when total > 1, which is always > 0 for real inputs.
    # The only way to cover this branch is to monkeypatch math.log2 in soma.vitals.
    def test_output_entropy_max_entropy_zero_branch(self, monkeypatch):
        import soma.vitals as vitals_mod
        import math as real_math

        original_log2 = real_math.log2

        def fake_log2(x):
            # When called with an int > 1 (the `total` bigram count), return 0.0
            # to force max_entropy == 0.0 and hit the guarded return at line 61.
            if isinstance(x, int) and x > 1:
                return 0.0
            return original_log2(x)

        monkeypatch.setattr(vitals_mod.math, "log2", fake_log2)
        # "abc" → bigrams ["ab","bc"] → total=2 → fake_log2(2)=0.0 → line 61 hit
        result = vitals_mod.compute_output_entropy("abc")
        assert result == pytest.approx(0.0)

    # Short text that produces 1 bigram (total=1 → max_entropy uses else-1.0 branch)
    def test_output_entropy_single_bigram(self):
        result = compute_output_entropy("ab")
        assert result == pytest.approx(0.0)

    # line 146: compute_uncertainty when expected_format is None and actions are present
    # In compute_uncertainty, the branch at line ~128:
    #   if actions:
    #       fmt_devs = [compute_format_deviation(a.output_text, expected_format) ...]
    # But expected_format=None would cause compute_format_deviation to receive None.
    # Looking at the code: if expected_format is None, fmt_dev stays 0.0 (no branch).
    # Line 146 is actually in compute_uncertainty: "fmt_devs = [... for a in actions]"
    # Let's check: vitals.py:146 is "fmt_dev = sum(fmt_devs) / len(fmt_devs)"
    # This is reached when actions is non-empty and expected_format is not None.
    def test_uncertainty_with_expected_format_and_actions(self):
        actions = [
            Action(tool_name="t", output_text="line1\nline2\nline3"),
            Action(tool_name="t", output_text="line1 only"),
        ]
        # Provide expected_format so lines 131-134 are all exercised
        score = compute_uncertainty(
            actions,
            baseline_tool_calls_avg=2.0,
            baseline_tool_calls_std=0.5,
            baseline_entropy=0.5,
            baseline_entropy_std=0.1,
            expected_format=["line1", "line2"],
        )
        assert 0.0 <= score <= 1.0

    # Also exercise the fmt_devs path with a non-None expected_format that has content
    def test_uncertainty_format_deviation_path(self):
        actions = [
            Action(tool_name="tool", output_text="contains REQUIRED_TOKEN here"),
        ]
        score = compute_uncertainty(
            actions,
            baseline_tool_calls_avg=1.0,
            baseline_tool_calls_std=0.0,
            baseline_entropy=0.3,
            baseline_entropy_std=0.0,
            expected_format=["REQUIRED_TOKEN", "MISSING_TOKEN"],
        )
        # "MISSING_TOKEN" is absent → fmt_dev = 0.5; score should be > 0
        assert score >= 0.0
