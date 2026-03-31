"""Comprehensive tests for soma.vitals."""

from __future__ import annotations

import math

import pytest

from soma.types import Action, DriftMode
from soma.vitals import (
    ResourceVitals,
    compute_behavior_vector,
    compute_drift,
    compute_format_deviation,
    compute_output_entropy,
    compute_resource_vitals,
    compute_retry_rate,
    compute_tool_call_deviation,
    compute_uncertainty,
    cosine_similarity,
    determine_drift_mode,
    sigmoid_clamp,
)


# ---------------------------------------------------------------------------
# sigmoid_clamp
# ---------------------------------------------------------------------------

class TestSigmoidClamp:
    def test_negative_input(self):
        assert sigmoid_clamp(-5.0) == 0.0

    def test_zero_input(self):
        assert sigmoid_clamp(0.0) == 0.0

    def test_above_six_clamps_to_one(self):
        assert sigmoid_clamp(7.0) == 1.0
        assert sigmoid_clamp(100.0) == 1.0

    def test_exactly_six_is_sigmoid(self):
        # x=6: 1/(1+exp(-6+3)) = 1/(1+exp(-3)) ≈ 0.9526
        result = sigmoid_clamp(6.0)
        assert abs(result - 1.0 / (1.0 + math.exp(-3))) < 1e-9

    def test_midpoint_at_three(self):
        # x=3: 1/(1+exp(0)) = 0.5
        assert abs(sigmoid_clamp(3.0) - 0.5) < 1e-9

    def test_one_sigma_approx(self):
        # x=1: 1/(1+exp(-1+3)) = 1/(1+exp(2)) ≈ 0.119
        expected = 1.0 / (1.0 + math.exp(2))
        assert abs(sigmoid_clamp(1.0) - expected) < 1e-9

    def test_five_sigma_approx(self):
        # x=5: 1/(1+exp(-5+3)) = 1/(1+exp(-2)) ≈ 0.881
        expected = 1.0 / (1.0 + math.exp(-2))
        assert abs(sigmoid_clamp(5.0) - expected) < 1e-9

    def test_output_range(self):
        for x in [-1, 0, 1, 2, 3, 4, 5, 6, 7]:
            result = sigmoid_clamp(x)
            assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# compute_retry_rate
# ---------------------------------------------------------------------------

class TestRetryRate:
    def test_empty_actions(self):
        assert compute_retry_rate([]) == 0.0

    def test_no_retries(self, normal_actions):
        assert compute_retry_rate(normal_actions) == 0.0

    def test_all_retried(self, error_actions):
        assert compute_retry_rate(error_actions) == 1.0

    def test_mixed_retries(self):
        actions = [
            Action(tool_name="bash", output_text="ok", retried=True),
            Action(tool_name="bash", output_text="ok", retried=False),
            Action(tool_name="bash", output_text="ok", retried=True),
            Action(tool_name="bash", output_text="ok", retried=False),
        ]
        assert compute_retry_rate(actions) == 0.5

    def test_single_retry(self):
        actions = [Action(tool_name="bash", output_text="x", retried=True)]
        assert compute_retry_rate(actions) == 1.0

    def test_single_no_retry(self):
        actions = [Action(tool_name="bash", output_text="x", retried=False)]
        assert compute_retry_rate(actions) == 0.0


# ---------------------------------------------------------------------------
# compute_output_entropy
# ---------------------------------------------------------------------------

class TestOutputEntropy:
    def test_empty_text(self):
        assert compute_output_entropy("") == 0.0

    def test_single_char(self):
        assert compute_output_entropy("a") == 0.0

    def test_two_same_chars_zero_entropy(self):
        # Only one unique bigram → 0 entropy
        assert compute_output_entropy("aa") == 0.0

    def test_repetitive_text_low_entropy(self):
        # Very repetitive text: few unique bigrams
        result = compute_output_entropy("aaaaaaaaaa")
        assert result == 0.0

    def test_varied_text_higher_entropy(self):
        varied = "the quick brown fox jumps over the lazy dog"
        repetitive = "aaaaaaaaaa"
        assert compute_output_entropy(varied) > compute_output_entropy(repetitive)

    def test_returns_float_in_range(self):
        texts = [
            "hello world",
            "abcdefghijklmnopqrstuvwxyz",
            "aababcabcdabcde",
        ]
        for text in texts:
            result = compute_output_entropy(text)
            assert isinstance(result, float)
            assert 0.0 <= result <= 1.0

    def test_error_actions_lower_entropy(self, error_actions, normal_actions):
        error_text = " ".join(a.output_text for a in error_actions)
        normal_text = " ".join(a.output_text for a in normal_actions)
        assert compute_output_entropy(error_text) < compute_output_entropy(normal_text)

    def test_two_chars_full_entropy_possible(self):
        # "ab" has one bigram "ab" → entropy = 0 / log2(1) — but max_entropy is log2(1)=0
        # so result = 0.0 (edge case, only one bigram possible)
        assert compute_output_entropy("ab") == 0.0

    def test_three_unique_bigrams(self):
        # "abcd" → bigrams: ab, bc, cd — all unique → entropy = log2(3)/log2(3) = 1.0
        result = compute_output_entropy("abcd")
        assert abs(result - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# compute_tool_call_deviation
# ---------------------------------------------------------------------------

class TestToolCallDeviation:
    def test_at_baseline_zero_deviation(self):
        actions = [Action(tool_name="bash", output_text="x")] * 5
        assert compute_tool_call_deviation(actions, 5.0, 2.0) == 0.0

    def test_above_baseline(self):
        actions = [Action(tool_name="bash", output_text="x")] * 10
        result = compute_tool_call_deviation(actions, 5.0, 2.0)
        assert result == pytest.approx(2.5)

    def test_zero_std_returns_zero(self):
        actions = [Action(tool_name="bash", output_text="x")] * 3
        assert compute_tool_call_deviation(actions, 3.0, 0.0) == 0.0

    def test_below_baseline(self):
        actions = [Action(tool_name="bash", output_text="x")] * 2
        result = compute_tool_call_deviation(actions, 7.0, 2.5)
        assert result == pytest.approx(2.0)

    def test_empty_actions(self):
        result = compute_tool_call_deviation([], 5.0, 2.0)
        assert result == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# compute_format_deviation
# ---------------------------------------------------------------------------

class TestFormatDeviation:
    def test_no_expected_format(self):
        assert compute_format_deviation("any output", []) == 0.0

    def test_full_match(self):
        output = "line1\nline2\nline3"
        expected = ["line1", "line2", "line3"]
        assert compute_format_deviation(output, expected) == 0.0

    def test_no_match(self):
        output = "completely different text"
        expected = ["line1", "line2", "line3", "line4"]
        assert compute_format_deviation(output, expected) == 1.0

    def test_partial_match(self):
        output = "line1 is here but not the others"
        expected = ["line1", "line2", "line3", "line4"]
        result = compute_format_deviation(output, expected)
        assert result == pytest.approx(0.75)

    def test_empty_output(self):
        expected = ["line1", "line2"]
        assert compute_format_deviation("", expected) == 1.0


# ---------------------------------------------------------------------------
# compute_uncertainty
# ---------------------------------------------------------------------------

class TestUncertainty:
    def test_normal_actions_low_uncertainty(self, normal_actions):
        result = compute_uncertainty(
            normal_actions,
            baseline_tool_calls_avg=10.0,
            baseline_tool_calls_std=2.0,
            baseline_entropy=0.8,
            baseline_entropy_std=0.1,
            expected_format=[],
        )
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_error_actions_higher_uncertainty(self, error_actions, normal_actions):
        normal_uncertainty = compute_uncertainty(
            normal_actions,
            baseline_tool_calls_avg=10.0,
            baseline_tool_calls_std=2.0,
            baseline_entropy=0.8,
            baseline_entropy_std=0.1,
            expected_format=[],
        )
        error_uncertainty = compute_uncertainty(
            error_actions,
            baseline_tool_calls_avg=10.0,
            baseline_tool_calls_std=2.0,
            baseline_entropy=0.8,
            baseline_entropy_std=0.1,
            expected_format=[],
        )
        assert error_uncertainty >= normal_uncertainty

    def test_empty_actions(self):
        result = compute_uncertainty(
            [],
            baseline_tool_calls_avg=5.0,
            baseline_tool_calls_std=1.0,
            baseline_entropy=0.5,
            baseline_entropy_std=0.1,
            expected_format=[],
        )
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_returns_value_in_range(self, normal_actions):
        result = compute_uncertainty(
            normal_actions,
            baseline_tool_calls_avg=5.0,
            baseline_tool_calls_std=1.0,
            baseline_entropy=0.5,
            baseline_entropy_std=0.2,
            expected_format=["step complete", "result:"],
        )
        assert 0.0 <= result <= 1.0

    def test_high_retry_increases_uncertainty(self):
        retried = [Action(tool_name="bash", output_text="x", retried=True)] * 10
        not_retried = [Action(tool_name="bash", output_text="x", retried=False)] * 10
        r1 = compute_uncertainty(retried, 10.0, 1.0, 0.5, 0.1, [])
        r2 = compute_uncertainty(not_retried, 10.0, 1.0, 0.5, 0.1, [])
        assert r1 > r2


# ---------------------------------------------------------------------------
# compute_behavior_vector
# ---------------------------------------------------------------------------

class TestBehaviorVector:
    KNOWN_TOOLS = ["search", "edit", "bash", "read"]

    def test_returns_floats(self, normal_actions):
        vec = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        assert all(isinstance(v, float) for v in vec)

    def test_deterministic(self, normal_actions):
        v1 = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        v2 = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        assert v1 == v2

    def test_empty_actions(self):
        vec = compute_behavior_vector([], self.KNOWN_TOOLS)
        assert len(vec) == 4 + len(self.KNOWN_TOOLS)
        assert all(v == 0.0 for v in vec)

    def test_length_correct(self, normal_actions):
        vec = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        # 4 base features + one per known tool
        assert len(vec) == 4 + len(self.KNOWN_TOOLS)

    def test_tool_dist_sums_to_one(self, normal_actions):
        vec = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        tool_dist = vec[4:]
        assert abs(sum(tool_dist) - 1.0) < 1e-9

    def test_avg_output_len_positive(self, normal_actions):
        vec = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        assert vec[1] > 0.0

    def test_error_actions_different_vector(self, normal_actions, error_actions):
        v_normal = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        v_error = compute_behavior_vector(error_actions, self.KNOWN_TOOLS)
        assert v_normal != v_error


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-9

    def test_zero_vector_a(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_zero_vector_b(self):
        assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0

    def test_both_zero_vectors(self):
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-9

    def test_range(self):
        import random
        random.seed(42)
        for _ in range(10):
            a = [random.random() for _ in range(5)]
            b = [random.random() for _ in range(5)]
            result = cosine_similarity(a, b)
            assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# compute_drift
# ---------------------------------------------------------------------------

class TestDrift:
    KNOWN_TOOLS = ["search", "edit", "bash", "read"]

    def test_same_behavior_near_zero(self, normal_actions):
        baseline = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        drift = compute_drift(normal_actions, baseline, self.KNOWN_TOOLS)
        assert drift < 0.05

    def test_different_behavior_positive_drift(self, normal_actions, error_actions):
        baseline = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        drift = compute_drift(error_actions, baseline, self.KNOWN_TOOLS)
        assert drift > 0.3

    def test_empty_actions(self):
        baseline = [1.0, 100.0, 1.5, 1.5, 0.3, 0.3, 0.2, 0.2]
        drift = compute_drift([], baseline, self.KNOWN_TOOLS)
        # Empty vs non-empty — drift should be computable (0.0 if zero vector)
        assert isinstance(drift, float)
        assert 0.0 <= drift <= 2.0  # Can exceed 1 if baseline includes negative-going

    def test_drift_non_negative(self, normal_actions, error_actions):
        baseline = compute_behavior_vector(normal_actions, self.KNOWN_TOOLS)
        drift = compute_drift(error_actions, baseline, self.KNOWN_TOOLS)
        assert drift >= 0.0


# ---------------------------------------------------------------------------
# determine_drift_mode
# ---------------------------------------------------------------------------

class TestDriftMode:
    def test_informational_by_default_low_drift(self):
        mode = determine_drift_mode(
            drift=0.1,
            drift_threshold=0.5,
            error_rate=0.01,
            error_rate_baseline=0.05,
            progress_stalled=False,
            uncertainty=0.2,
            uncertainty_threshold=0.7,
        )
        assert mode == DriftMode.INFORMATIONAL

    def test_informational_high_drift_no_confirmation(self):
        # Drift exceeds threshold but no confirmatory signals
        mode = determine_drift_mode(
            drift=0.8,
            drift_threshold=0.5,
            error_rate=0.01,      # below baseline
            error_rate_baseline=0.05,
            progress_stalled=False,
            uncertainty=0.2,
            uncertainty_threshold=0.7,
        )
        assert mode == DriftMode.INFORMATIONAL

    def test_directive_high_drift_with_errors(self):
        mode = determine_drift_mode(
            drift=0.8,
            drift_threshold=0.5,
            error_rate=0.3,
            error_rate_baseline=0.05,
            progress_stalled=False,
            uncertainty=0.2,
            uncertainty_threshold=0.7,
        )
        assert mode == DriftMode.DIRECTIVE

    def test_directive_high_drift_with_stall(self):
        mode = determine_drift_mode(
            drift=0.8,
            drift_threshold=0.5,
            error_rate=0.01,
            error_rate_baseline=0.05,
            progress_stalled=True,
            uncertainty=0.2,
            uncertainty_threshold=0.7,
        )
        assert mode == DriftMode.DIRECTIVE

    def test_directive_high_drift_with_uncertainty(self):
        mode = determine_drift_mode(
            drift=0.8,
            drift_threshold=0.5,
            error_rate=0.01,
            error_rate_baseline=0.05,
            progress_stalled=False,
            uncertainty=0.9,
            uncertainty_threshold=0.7,
        )
        assert mode == DriftMode.DIRECTIVE

    def test_informational_drift_at_exactly_threshold(self):
        # drift == threshold is NOT > threshold, so informational
        mode = determine_drift_mode(
            drift=0.5,
            drift_threshold=0.5,
            error_rate=0.9,
            error_rate_baseline=0.05,
            progress_stalled=True,
            uncertainty=0.99,
            uncertainty_threshold=0.7,
        )
        assert mode == DriftMode.INFORMATIONAL


# ---------------------------------------------------------------------------
# compute_resource_vitals
# ---------------------------------------------------------------------------

class TestResourceVitals:
    def test_normal_usage(self):
        rv = compute_resource_vitals(
            token_used=500,
            token_limit=1000,
            cost_spent=5.0,
            cost_budget=10.0,
            errors_in_window=1,
            actions_in_window=10,
        )
        assert isinstance(rv, ResourceVitals)
        assert rv.token_usage == pytest.approx(0.5)
        assert rv.cost == pytest.approx(0.5)
        assert rv.error_rate == pytest.approx(0.1)

    def test_at_limit(self):
        rv = compute_resource_vitals(
            token_used=1000,
            token_limit=1000,
            cost_spent=10.0,
            cost_budget=10.0,
            errors_in_window=10,
            actions_in_window=10,
        )
        assert rv.token_usage == pytest.approx(1.0)
        assert rv.cost == pytest.approx(1.0)
        assert rv.error_rate == pytest.approx(1.0)

    def test_over_limit_clamps_to_one(self):
        rv = compute_resource_vitals(
            token_used=2000,
            token_limit=1000,
            cost_spent=20.0,
            cost_budget=10.0,
            errors_in_window=20,
            actions_in_window=10,
        )
        assert rv.token_usage == pytest.approx(1.0)
        assert rv.cost == pytest.approx(1.0)
        assert rv.error_rate == pytest.approx(1.0)

    def test_zero_limit_yields_zero(self):
        rv = compute_resource_vitals(
            token_used=500,
            token_limit=0,
            cost_spent=5.0,
            cost_budget=0,
            errors_in_window=5,
            actions_in_window=0,
        )
        assert rv.token_usage == 0.0
        assert rv.cost == 0.0
        assert rv.error_rate == 0.0

    def test_all_values_in_range(self):
        for token_used in [0, 500, 1000, 1500]:
            rv = compute_resource_vitals(
                token_used=token_used,
                token_limit=1000,
                cost_spent=5.0,
                cost_budget=10.0,
                errors_in_window=2,
                actions_in_window=10,
            )
            assert 0.0 <= rv.token_usage <= 1.0
            assert 0.0 <= rv.cost <= 1.0
            assert 0.0 <= rv.error_rate <= 1.0

    def test_zero_errors(self):
        rv = compute_resource_vitals(
            token_used=100,
            token_limit=1000,
            cost_spent=1.0,
            cost_budget=10.0,
            errors_in_window=0,
            actions_in_window=10,
        )
        assert rv.error_rate == 0.0


# ---------------------------------------------------------------------------
# Goal coherence (VIT-01) — stubs, implemented in Plan 02
# ---------------------------------------------------------------------------

class TestGoalCoherence:
    def test_coherence_same_task_high(self):
        from soma.vitals import compute_goal_coherence
        actions = [Action(tool_name="Bash", output_text=f"output {i}") for i in range(10)]
        initial_vec = compute_behavior_vector(actions[:5], ["Bash"])
        result = compute_goal_coherence(actions[5:], initial_vec, ["Bash"])
        assert result > 0.7

    def test_coherence_different_task_low(self):
        from soma.vitals import compute_goal_coherence
        # Short bash outputs → small avg_output_len, Bash in tool_dist
        bash_actions = [Action(tool_name="Bash", output_text=f"ok {i}") for i in range(5)]
        # Very long write outputs → large avg_output_len, Bash absent in tool_dist
        # Divergent output_len pulls cosine similarity below 0.35
        write_actions = [Action(tool_name="Write", output_text="x" * 5000) for _ in range(5)]
        initial_vec = compute_behavior_vector(bash_actions, ["Bash"])
        result = compute_goal_coherence(write_actions, initial_vec, ["Bash"])
        assert result < 0.35

    def test_coherence_uses_frozen_tools(self):
        from soma.vitals import compute_goal_coherence
        initial_known_tools = ["Bash"]
        actions = [Action(tool_name="Bash", output_text=f"cmd {i}") for i in range(5)]
        initial_vec = compute_behavior_vector(actions, initial_known_tools)
        # Even if live known_tools grew, we use the frozen snapshot
        result = compute_goal_coherence(actions, initial_vec, initial_known_tools)
        # Vector length stays 5 (4 base + 1 tool), not 7 (4 base + 3 tools)
        assert len(initial_vec) == 5
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Baseline integrity (VIT-03) — stubs, implemented in Plan 03
# ---------------------------------------------------------------------------

class TestBaselineIntegrity:
    def test_integrity_intact_when_normal(self):
        from soma.vitals import compute_baseline_integrity
        result = compute_baseline_integrity(
            baseline_error_rate=0.05,
            current_error_rate=0.05,
            fingerprint_avg_error_rate=0.04,
            fingerprint_sample_count=15,
            min_samples=10,
            error_ratio_threshold=2.0,
            min_current_error_rate=0.20,
        )
        assert result is True

    def test_integrity_false_when_corrupted(self):
        from soma.vitals import compute_baseline_integrity
        result = compute_baseline_integrity(
            baseline_error_rate=0.50,
            current_error_rate=0.40,
            fingerprint_avg_error_rate=0.05,
            fingerprint_sample_count=20,
            min_samples=10,
            error_ratio_threshold=2.0,
            min_current_error_rate=0.20,
        )
        assert result is False

    def test_integrity_true_insufficient_history(self):
        from soma.vitals import compute_baseline_integrity
        result = compute_baseline_integrity(
            baseline_error_rate=0.50,
            current_error_rate=0.40,
            fingerprint_avg_error_rate=0.05,
            fingerprint_sample_count=5,
            min_samples=10,
            error_ratio_threshold=2.0,
            min_current_error_rate=0.20,
        )
        assert result is True

    def test_integrity_true_no_historical_errors(self):
        from soma.vitals import compute_baseline_integrity
        result = compute_baseline_integrity(
            baseline_error_rate=0.50,
            current_error_rate=0.40,
            fingerprint_avg_error_rate=0.0,
            fingerprint_sample_count=20,
            min_samples=10,
            error_ratio_threshold=2.0,
            min_current_error_rate=0.20,
        )
        assert result is True

    def test_integrity_true_when_recovered(self):
        from soma.vitals import compute_baseline_integrity
        # Baseline drifted but current errors recovered — not corruption
        result = compute_baseline_integrity(
            baseline_error_rate=0.50,
            current_error_rate=0.10,
            fingerprint_avg_error_rate=0.05,
            fingerprint_sample_count=20,
            min_samples=10,
            error_ratio_threshold=2.0,
            min_current_error_rate=0.20,
        )
        assert result is True

    def test_integrity_true_baseline_within_ratio(self):
        from soma.vitals import compute_baseline_integrity
        # 0.08 / 0.05 = 1.6x — below 2.0 threshold
        result = compute_baseline_integrity(
            baseline_error_rate=0.08,
            current_error_rate=0.30,
            fingerprint_avg_error_rate=0.05,
            fingerprint_sample_count=20,
            min_samples=10,
            error_ratio_threshold=2.0,
            min_current_error_rate=0.20,
        )
        assert result is True
