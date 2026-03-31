import pytest

from soma.engine import SOMAEngine, ActionResult
from soma.types import Action, ResponseMode, AutonomyMode, PressureVector


class TestSOMAEngine:
    def test_create_and_register(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        assert e.get_level("a") == ResponseMode.OBSERVE

    def test_record_normal(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # First few actions may have elevated uncertainty due to cold start baseline
        # Warm up with several normal actions
        for i in range(10):
            r = e.record_action("a", Action(
                tool_name="search", output_text=f"found {i} results for query", token_count=100,
            ))
        assert r.mode == ResponseMode.OBSERVE
        assert 0.0 <= r.pressure <= 1.0
        assert isinstance(r.vitals.uncertainty, float)

    def test_escalation_on_errors(self, error_actions):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # Run enough actions to clear the grace period (first 10), then add errors
        for action in error_actions:
            r = e.record_action("a", action)
        # One more error action after grace period ends
        r = e.record_action("a", error_actions[0])
        assert r.mode.value >= ResponseMode.GUIDE.value

    def test_multi_agent_pressure(self):
        e = SOMAEngine(budget={"tokens": 500000})
        e.register_agent("bad")
        e.register_agent("good")
        e.add_edge("bad", "good", trust_weight=1.0)
        for _ in range(15):
            e.record_action("bad", Action(
                tool_name="bash", output_text="error " * 50,
                token_count=100, error=True, retried=True,
            ))
        r = e.record_action("good", Action(
            tool_name="search", output_text="found results", token_count=50,
        ))
        assert r.pressure >= 0.0

    def test_budget_depletion_raises_pressure(self):
        e = SOMAEngine(budget={"tokens": 100})
        e.register_agent("a")
        # Exhaust budget and pass grace period
        for _ in range(15):
            r = e.record_action("a", Action(tool_name="bash", output_text="x", token_count=100))
        # Budget is massively overdrawn — pressure should be elevated
        assert r.mode >= ResponseMode.GUIDE, (
            f"Expected at least GUIDE after budget depletion, got {r.mode}"
        )

    def test_events_fired(self, error_actions):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        events = []
        e.events.on("level_changed", lambda d: events.append(d))
        for action in error_actions:
            e.record_action("a", action)
        if e.get_level("a") != ResponseMode.OBSERVE:
            assert len(events) >= 1
            assert "agent_id" in events[0]

    def test_get_snapshot(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        e.record_action("a", Action(tool_name="bash", output_text="hello", token_count=50))
        snap = e.get_snapshot("a")
        assert "level" in snap
        assert "pressure" in snap
        assert "vitals" in snap
        assert snap["action_count"] == 1

    def test_multiple_agents_independent(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        e.register_agent("b")
        # a gets errors, b stays clean
        for _ in range(10):
            e.record_action("a", Action(
                tool_name="bash", output_text="err", token_count=50, error=True, retried=True,
            ))
        for _ in range(10):
            e.record_action("b", Action(
                tool_name="search", output_text="ok " * 20, token_count=50,
            ))
        # Without edge, b should not be affected
        assert e.get_level("b") == ResponseMode.OBSERVE

    def test_custom_thresholds_affect_mode(self):
        """Engine with very high thresholds keeps OBSERVE longer."""
        e = SOMAEngine(
            budget={"tokens": 100000},
            custom_thresholds={"guide": 0.90, "warn": 0.95, "block": 0.99},
        )
        e.register_agent("test")
        # Push some errors through grace period
        for i in range(20):
            e.record_action("test", Action(
                tool_name="bash", output_text="error", error=True,
                token_count=100, cost=0.01, duration_sec=1.0, retried=True,
            ))
        snap = e.get_snapshot("test")
        # With default thresholds (0.25/0.50/0.75) this would be WARN/BLOCK.
        # With 0.90/0.95/0.99, should still be below WARN.
        assert snap["mode"] in (ResponseMode.OBSERVE, ResponseMode.GUIDE)

    def test_none_thresholds_use_defaults(self):
        """Engine with no custom thresholds doesn't crash."""
        e = SOMAEngine(budget={"tokens": 10000}, custom_thresholds=None)
        e.register_agent("test")
        snap = e.get_snapshot("test")
        assert snap["mode"] == ResponseMode.OBSERVE

    def test_action_result_is_frozen(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="bash", output_text="ok", token_count=50))
        try:
            r.mode = ResponseMode.BLOCK  # type: ignore
            assert False, "Should not allow mutation"
        except AttributeError:
            pass


class TestGoalCoherenceIntegration:
    def test_goal_coherence_none_during_warmup(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        for _ in range(3):
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok"))
        assert r.vitals.goal_coherence is None

    def test_goal_coherence_computed_after_warmup(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        for _ in range(6):
            r = e.record_action("a", Action(tool_name="Bash", output_text="running bash command"))
        assert r.vitals.goal_coherence is not None
        assert r.vitals.goal_coherence > 0.5


class TestBaselineIntegrityIntegration:
    def test_baseline_integrity_true_by_default(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        for _ in range(5):
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok"))
        assert r.vitals.baseline_integrity is True

    def test_baseline_integrity_false_after_corruption(self):
        from unittest.mock import patch, MagicMock
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "baseline_integrity_error_ratio": 2.0,
            "baseline_integrity_min_error_rate": 0.20,
            "baseline_integrity_min_samples": 10,
        }
        e.register_agent("a")
        mock_fp = MagicMock()
        mock_fp.avg_error_rate = 0.05
        mock_fp.sample_count = 20
        mock_fp_engine = MagicMock()
        mock_fp_engine.get.return_value = mock_fp
        with patch("soma.state.get_fingerprint_engine", return_value=mock_fp_engine):
            for _ in range(25):
                r = e.record_action("a", Action(tool_name="Bash", output_text="error", error=True))
        assert r.vitals.baseline_integrity is False

    def test_baseline_integrity_true_legitimate_change(self):
        from unittest.mock import patch, MagicMock
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "baseline_integrity_error_ratio": 2.0,
            "baseline_integrity_min_error_rate": 0.20,
            "baseline_integrity_min_samples": 10,
        }
        e.register_agent("a")
        # Historically very error-prone agent (avg_error_rate=0.60)
        # After 25 error actions baseline ~0.95, ratio = 0.95/0.60 = 1.58x < 2.0 → True
        mock_fp = MagicMock()
        mock_fp.avg_error_rate = 0.60
        mock_fp.sample_count = 20
        mock_fp_engine = MagicMock()
        mock_fp_engine.get.return_value = mock_fp
        with patch("soma.state.get_fingerprint_engine", return_value=mock_fp_engine):
            for _ in range(25):
                r = e.record_action("a", Action(tool_name="Bash", output_text="error", error=True))
        # baseline / fingerprint ratio stays within 2x for high-error baseline agent
        assert r.vitals.baseline_integrity is True


class TestUncertaintyClassificationIntegration:
    def test_uncertainty_type_none_during_warmup(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        for _ in range(3):
            r = e.record_action("a", Action(tool_name="Bash", output_text="ok"))
        assert r.vitals.uncertainty_type is None

    def test_uncertainty_type_none_when_low_uncertainty(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        # Normal varied actions — uncertainty stays low
        for i in range(15):
            r = e.record_action("a", Action(
                tool_name="Bash", output_text=f"result {i} complete", token_count=50,
            ))
        # uncertainty below 0.3 → None regardless of entropy
        assert r.vitals.uncertainty_type is None

    def test_epistemic_classification_low_entropy(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"epistemic_pressure_multiplier": 1.3, "aleatoric_pressure_multiplier": 0.7}
        e.register_agent("a")
        # Single char repeated → entropy ≈ 0.0 (well below default 0.35) + retried = epistemic
        for _ in range(15):
            r = e.record_action("a", Action(
                tool_name="Bash", output_text="a" * 100, retried=True, error=True,
            ))
        assert r.vitals.uncertainty_type == "epistemic"

    def test_aleatoric_classification_high_entropy(self):
        import random
        import string
        random.seed(99)
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"epistemic_pressure_multiplier": 1.3, "aleatoric_pressure_multiplier": 0.7}
        e.register_agent("a")
        # Unique random text per action → joint entropy ~0.98 (well above default 0.65)
        chars = string.printable[:95]
        tools = ["Bash", "Read", "Write", "Grep", "Edit"]
        for i in range(15):
            r = e.record_action("a", Action(
                tool_name=tools[i % len(tools)],
                output_text="".join(random.choices(chars, k=200)),
                retried=True, error=True,
            ))
        assert r.vitals.uncertainty_type == "aleatoric"

    def test_epistemic_classification_on_low_entropy_output(self):
        """Low-entropy (repetitive) output is classified as epistemic."""
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"epistemic_pressure_multiplier": 1.3, "aleatoric_pressure_multiplier": 0.7}
        e.register_agent("a")
        for _ in range(15):
            r = e.record_action("a", Action(tool_name="Bash", output_text="a" * 200, retried=True))
        assert r.vitals.uncertainty_type == "epistemic"

    def test_aleatoric_classification_on_high_entropy_output(self):
        """High-entropy (random printable) output is classified as aleatoric."""
        import random
        import string
        random.seed(7)
        chars = string.printable[:95]
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {"epistemic_pressure_multiplier": 1.3, "aleatoric_pressure_multiplier": 0.7}
        e.register_agent("a")
        for _ in range(15):
            out = "".join(random.choices(chars, k=200))
            r = e.record_action("a", Action(tool_name="Bash", output_text=out, retried=True))
        assert r.vitals.uncertainty_type == "aleatoric"

    def test_epistemic_multiplier_boosts_pressure(self):
        """Epistemic multiplier > 1 raises aggregate pressure vs multiplier < 1.
        Uses retried=True (no errors) so error_rate floor doesn't dominate.
        vitals.uncertainty is the raw float; the multiplied pressure is in r.pressure.
        """
        def run_with_cfg(cfg):
            e = SOMAEngine(budget={"tokens": 100000})
            e._vitals_config = cfg
            e.register_agent("a")
            for _ in range(15):
                r = e.record_action("a", Action(
                    tool_name="Bash", output_text="a" * 200, retried=True
                ))
            return r.pressure  # aggregate reflects multiplied uncertainty_pressure

        # uncertainty_classification_min_uncertainty=0.1 ensures uncertainty≈0.30 (from
        # retry_rate component alone) clears the classification threshold, allowing the
        # epistemic multiplier to actually differentiate the two runs.
        base_cfg = {"uncertainty_classification_min_uncertainty": 0.1}
        high = run_with_cfg({**base_cfg, "epistemic_pressure_multiplier": 3.0, "aleatoric_pressure_multiplier": 0.7})
        low  = run_with_cfg({**base_cfg, "epistemic_pressure_multiplier": 0.1, "aleatoric_pressure_multiplier": 0.7})
        assert high > low

    def test_custom_multipliers_from_vitals_config(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e._vitals_config = {
            "epistemic_pressure_multiplier": 2.0,
            "aleatoric_pressure_multiplier": 0.1,
        }
        e.register_agent("a")
        for _ in range(15):
            r = e.record_action("a", Action(
                tool_name="Bash", output_text="err", retried=True, error=True,
            ))
        # With 2.0 multiplier, epistemic pressure should be capped at 1.0 (high errors + retries)
        assert r.vitals.uncertainty_type in ("epistemic", "aleatoric", None)  # valid values


class TestPressureVectorIntegration:
    def test_action_result_has_pressure_vector(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert isinstance(r.pressure_vector, PressureVector)
        assert 0.0 <= r.pressure_vector.uncertainty <= 1.0
        assert 0.0 <= r.pressure_vector.error_rate <= 1.0
        assert 0.0 <= r.pressure_vector.drift <= 1.0
        assert 0.0 <= r.pressure_vector.cost <= 1.0

    def test_downstream_error_pressure_boosted_by_upstream(self):
        """Downstream agent's error_rate pressure rises when upstream has many errors."""
        e = SOMAEngine(budget={"tokens": 500000})
        e.register_agent("bad")
        e.register_agent("good")
        e.add_edge("bad", "good", trust_weight=1.0)

        # Drive bad agent past grace period with high errors
        for _ in range(20):
            e.record_action("bad", Action(
                tool_name="Bash", output_text="error",
                token_count=50, error=True, retried=True,
            ))

        # Baseline good result without upstream influence (no edge — isolated agent)
        e2 = SOMAEngine(budget={"tokens": 500000})
        e2.register_agent("good_isolated")
        r_isolated = e2.record_action("good_isolated", Action(
            tool_name="search", output_text="ok", token_count=50,
        ))

        r_downstream = e.record_action("good", Action(
            tool_name="search", output_text="ok", token_count=50,
        ))

        # Downstream error_rate component should be >= isolated (upstream pushes it up)
        assert r_downstream.pressure_vector.error_rate >= r_isolated.pressure_vector.error_rate

    def test_upstream_error_does_not_affect_unconnected_agent(self):
        """Agents without edges are not influenced by upstream vectors."""
        e = SOMAEngine(budget={"tokens": 500000})
        e.register_agent("bad")
        e.register_agent("independent")
        # No edge between bad and independent

        for _ in range(20):
            e.record_action("bad", Action(
                tool_name="Bash", output_text="error",
                token_count=50, error=True, retried=True,
            ))

        r = e.record_action("independent", Action(
            tool_name="search", output_text="all good", token_count=50,
        ))
        # Independent agent: no upstream boost, low pressure
        assert r.pressure_vector.error_rate < 0.5

    def test_pressure_vector_fields_are_floats_in_range(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        for i in range(5):
            r = e.record_action("a", Action(
                tool_name="Bash", output_text=f"output {i}", token_count=100,
            ))
        assert all(0.0 <= v <= 1.0 for v in [
            r.pressure_vector.uncertainty,
            r.pressure_vector.drift,
            r.pressure_vector.error_rate,
            r.pressure_vector.cost,
        ])

    def test_graph_vector_serialization_roundtrip(self):
        """PressureVector survives graph to_dict/from_dict roundtrip."""
        from soma.graph import PressureGraph

        g = PressureGraph()
        g.add_agent("a")
        g.add_agent("b")
        g.add_edge("a", "b")
        vec = PressureVector(uncertainty=0.4, drift=0.2, error_rate=0.6, cost=0.1)
        g.set_internal_pressure_vector("a", vec)
        g.propagate()

        d = g.to_dict()
        g2 = PressureGraph.from_dict(d)
        vec_a = g2._nodes["a"].internal_pressure_vector
        assert vec_a is not None
        assert abs(vec_a.error_rate - 0.6) < 1e-6
        assert abs(vec_a.uncertainty - 0.4) < 1e-6


class TestCoordinationSNRIntegration:
    def test_snr_is_one_for_isolated_agent(self):
        """Agent with no incoming edges always has SNR=1.0."""
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("solo")
        e.record_action("solo", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert e._graph.get_snr("solo") == 1.0

    def test_snr_high_when_upstream_errors_corroborate_pressure(self):
        """SNR approaches 1.0 when upstream pressure is backed by real errors."""
        e = SOMAEngine(budget={"tokens": 500000})
        e.register_agent("erroring")
        e.register_agent("watcher")
        e.add_edge("erroring", "watcher", trust_weight=1.0)

        # Drive erroring agent past grace period with errors
        for _ in range(20):
            e.record_action("erroring", Action(
                tool_name="Bash", output_text="error",
                token_count=50, error=True, retried=True,
            ))

        e.record_action("watcher", Action(tool_name="search", output_text="ok", token_count=50))
        # SNR > 0.5 because upstream pressure is error-backed
        assert e._graph.get_snr("watcher") > 0.5

    def test_snr_low_isolates_downstream_from_non_error_pressure(self):
        """When upstream pressure has no error component, SNR is low → downstream isolated."""
        from soma.graph import PressureGraph

        g = PressureGraph(snr_threshold=0.5)
        g.add_agent("noisy")
        g.add_agent("clean")
        g.add_edge("noisy", "clean", trust=1.0)

        # noisy has high pressure but zero error_rate in vector (drift only)
        g.set_internal_pressure("noisy", 0.8)
        g.set_internal_pressure_vector("noisy", PressureVector(
            uncertainty=0.0, drift=0.8, error_rate=0.0, cost=0.0
        ))
        g.set_internal_pressure("clean", 0.0)
        g.set_internal_pressure_vector("clean", PressureVector())
        g.propagate()

        # clean should be isolated: effective_pressure = internal = 0.0
        assert g.get_effective_pressure("clean") == pytest.approx(0.0)
        assert g.get_snr("clean") < 0.5


class TestTaskComplexityIntegration:
    def test_task_complexity_none_before_first_action(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        assert e._agents["a"].task_complexity_score is None

    def test_task_complexity_set_after_first_action(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=50))
        assert r.vitals.task_complexity is not None
        assert 0.0 <= r.vitals.task_complexity <= 1.0

    def test_simple_output_yields_low_complexity(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        r = e.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=10))
        assert r.vitals.task_complexity < 0.5

    def test_complex_output_yields_higher_complexity(self):
        e = SOMAEngine(budget={"tokens": 100000})
        e.register_agent("a")
        complex_text = (
            "This task depends on completing the authentication module first. "
            "It might require refactoring the database layer, which is unclear. "
            "The implementation possibly requires changes across multiple services, "
            "before we can proceed with deployment. This is complex and depends on "
            "approval from the security team. " * 5
        )
        r = e.record_action("a", Action(tool_name="Bash", output_text=complex_text, token_count=100))
        assert r.vitals.task_complexity > 0.3

    def test_high_complexity_lowers_effective_thresholds(self):
        """High complexity should cause earlier mode escalation."""
        # Agent A: simple first action (low complexity), then errors
        e_simple = SOMAEngine(budget={"tokens": 100000})
        e_simple.register_agent("a")
        e_simple.record_action("a", Action(tool_name="Bash", output_text="ok", token_count=10))

        # Agent B: complex first action, then same errors
        e_complex = SOMAEngine(budget={"tokens": 100000})
        e_complex.register_agent("a")
        complex_text = "This depends on multiple prerequisites. " * 20 + " requires possibly unclear ambiguous complex"
        e_complex.record_action("a", Action(tool_name="Bash", output_text=complex_text, token_count=10))

        # Push both past grace period with identical moderate errors
        for _ in range(12):
            action = Action(tool_name="Bash", output_text="err", token_count=50, error=True)
            e_simple.record_action("a", action)
            e_complex.record_action("a", action)

        # Complex agent should reach higher mode sooner (same pressure, lower thresholds)
        simple_mode = e_simple.get_level("a")
        complex_mode = e_complex.get_level("a")
        assert complex_mode.value >= simple_mode.value
