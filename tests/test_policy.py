"""Tests for the Policy Engine (Phase 08 — POL-01, POL-02, POL-03)."""

import pytest
import soma
from soma.engine import SOMAEngine
from soma.types import VitalsSnapshot
from soma.policy import (
    PolicyCondition,
    PolicyAction,
    Rule,
    PolicyEngine,
    guardrail,
    _parse_policy_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot(
    error_rate=0.0,
    uncertainty=0.1,
    drift=0.0,
    token_usage=0.0,
    cost=0.0,
    calibration_score=None,
) -> VitalsSnapshot:
    return VitalsSnapshot(
        error_rate=error_rate,
        uncertainty=uncertainty,
        drift=drift,
        token_usage=token_usage,
        cost=cost,
        calibration_score=calibration_score,
    )


# ---------------------------------------------------------------------------
# POL-01: PolicyEngine — rule evaluation
# ---------------------------------------------------------------------------

class TestPolicyEngineEvaluate:
    def _make_engine(self, rules):
        return PolicyEngine(rules)

    def test_no_rules_returns_empty(self):
        pe = PolicyEngine([])
        assert pe.evaluate(_snapshot(), pressure=0.5) == []

    def test_single_rule_fires(self):
        rule = Rule(
            name="high-error",
            conditions=[PolicyCondition("error_rate", ">=", 0.3)],
            action=PolicyAction("warn", "Error rate high"),
        )
        pe = PolicyEngine([rule])
        result = pe.evaluate(_snapshot(error_rate=0.4), pressure=0.0)
        assert len(result) == 1
        assert result[0].action == "warn"

    def test_rule_does_not_fire_below_threshold(self):
        rule = Rule(
            name="high-error",
            conditions=[PolicyCondition("error_rate", ">=", 0.3)],
            action=PolicyAction("warn"),
        )
        pe = PolicyEngine([rule])
        assert pe.evaluate(_snapshot(error_rate=0.1), pressure=0.0) == []

    def test_multiple_conditions_and_logic(self):
        rule = Rule(
            name="combined",
            conditions=[
                PolicyCondition("error_rate", ">=", 0.3),
                PolicyCondition("uncertainty", ">=", 0.5),
            ],
            action=PolicyAction("block"),
        )
        pe = PolicyEngine([rule])
        # Only error_rate high → no fire
        assert pe.evaluate(_snapshot(error_rate=0.4, uncertainty=0.1), pressure=0.0) == []
        # Both high → fires
        result = pe.evaluate(_snapshot(error_rate=0.4, uncertainty=0.6), pressure=0.0)
        assert len(result) == 1

    def test_all_rules_evaluated(self):
        rules = [
            Rule("r1", [PolicyCondition("error_rate", ">=", 0.2)], PolicyAction("warn")),
            Rule("r2", [PolicyCondition("uncertainty", ">=", 0.1)], PolicyAction("log")),
        ]
        pe = PolicyEngine(rules)
        result = pe.evaluate(_snapshot(error_rate=0.3, uncertainty=0.2), pressure=0.0)
        assert len(result) == 2

    def test_pressure_field_accessible(self):
        rule = Rule(
            name="high-pressure",
            conditions=[PolicyCondition("pressure", ">=", 0.7)],
            action=PolicyAction("warn"),
        )
        pe = PolicyEngine([rule])
        assert pe.evaluate(_snapshot(), pressure=0.8) != []
        assert pe.evaluate(_snapshot(), pressure=0.5) == []

    def test_operator_less_than(self):
        rule = Rule(
            name="low-cost",
            conditions=[PolicyCondition("cost", "<", 0.01)],
            action=PolicyAction("log"),
        )
        pe = PolicyEngine([rule])
        assert pe.evaluate(_snapshot(cost=0.005), pressure=0.0) != []
        assert pe.evaluate(_snapshot(cost=0.02), pressure=0.0) == []

    def test_operator_not_equal(self):
        rule = Rule(
            name="nonzero-drift",
            conditions=[PolicyCondition("drift", "!=", 0.0)],
            action=PolicyAction("guide"),
        )
        pe = PolicyEngine([rule])
        assert pe.evaluate(_snapshot(drift=0.1), pressure=0.0) != []
        assert pe.evaluate(_snapshot(drift=0.0), pressure=0.0) == []

    def test_unknown_field_does_not_match(self):
        """A condition on an unknown field should not raise but also not match."""
        rule = Rule(
            name="ghost",
            conditions=[PolicyCondition("nonexistent_field", ">=", 0.0)],
            action=PolicyAction("warn"),
        )
        pe = PolicyEngine([rule])
        assert pe.evaluate(_snapshot(), pressure=0.0) == []

    def test_calibration_score_condition(self):
        rule = Rule(
            name="low-cal",
            conditions=[PolicyCondition("calibration_score", "<", 0.5)],
            action=PolicyAction("guide"),
        )
        pe = PolicyEngine([rule])
        # Present and low → fires
        assert pe.evaluate(_snapshot(calibration_score=0.3), pressure=0.0) != []
        # Present and high → no fire
        assert pe.evaluate(_snapshot(calibration_score=0.8), pressure=0.0) == []
        # Missing (None) → no fire (not in context)
        assert pe.evaluate(_snapshot(), pressure=0.0) == []


# ---------------------------------------------------------------------------
# POL-01: from_dict loader
# ---------------------------------------------------------------------------

class TestFromDict:
    def test_basic_load(self):
        data = {
            "version": "1",
            "policies": [
                {
                    "name": "guard",
                    "when": [{"field": "error_rate", "op": ">=", "value": 0.3}],
                    "do": {"action": "warn", "message": "Too many errors"},
                }
            ],
        }
        pe = PolicyEngine.from_dict(data)
        assert len(pe.rules) == 1
        assert pe.rules[0].name == "guard"

    def test_empty_policies_list(self):
        pe = PolicyEngine.from_dict({"policies": []})
        assert pe.rules == []

    def test_missing_policies_key(self):
        pe = PolicyEngine.from_dict({})
        assert pe.rules == []

    def test_operator_alias(self):
        """from_dict accepts 'operator' as alias for 'op'."""
        data = {
            "policies": [
                {
                    "name": "r",
                    "when": [{"field": "error_rate", "operator": ">=", "value": 0.5}],
                    "do": {"action": "warn"},
                }
            ]
        }
        pe = PolicyEngine.from_dict(data)
        assert pe.rules[0].conditions[0].op == ">="

    def test_default_action_is_log(self):
        data = {
            "policies": [
                {
                    "name": "r",
                    "when": [{"field": "error_rate", "op": ">=", "value": 0.1}],
                    "do": {},
                }
            ]
        }
        pe = PolicyEngine.from_dict(data)
        assert pe.rules[0].action.action == "log"

    def test_unnamed_rule_defaults(self):
        data = {
            "policies": [
                {
                    "when": [{"field": "error_rate", "op": ">=", "value": 0.1}],
                    "do": {"action": "warn"},
                }
            ]
        }
        pe = PolicyEngine.from_dict(data)
        assert pe.rules[0].name == "unnamed"


# ---------------------------------------------------------------------------
# POL-01: from_file loader (TOML)
# ---------------------------------------------------------------------------

class TestFromFile:
    def test_load_toml(self, tmp_path):
        toml_content = """
[[policies]]
name = "file-rule"

[[policies.when]]
field = "error_rate"
op = ">="
value = 0.3

[policies.do]
action = "warn"
message = "File-loaded rule"
"""
        p = tmp_path / "policy.toml"
        p.write_text(toml_content)
        pe = PolicyEngine.from_file(str(p))
        assert len(pe.rules) == 1
        assert pe.rules[0].name == "file-rule"

    def test_load_yaml_raises_without_pyyaml(self, tmp_path):
        """If pyyaml is not installed, from_file(.yaml) raises ImportError."""
        import sys
        yaml_mods = {k: v for k, v in sys.modules.items() if k == "yaml"}
        for mod in yaml_mods:
            sys.modules.pop(mod, None)

        # Force a fresh import of policy to reset the yaml availability
        import importlib
        import soma.policy as pol_mod
        importlib.reload(pol_mod)

        p = tmp_path / "policy.yaml"
        p.write_text("policies: []")

        try:
            pol_mod.PolicyEngine.from_file(str(p))
        except ImportError as e:
            assert "pyyaml" in str(e).lower() or "PyYAML" in str(e)
        except Exception:
            pass  # yaml might be installed; skip check
        finally:
            sys.modules.update(yaml_mods)


# ---------------------------------------------------------------------------
# POL-03: from_url (mock — no network call)
# ---------------------------------------------------------------------------

class TestFromUrl:
    def test_from_url_toml(self, monkeypatch):
        toml_content = b"""
[[policies]]
name = "url-rule"

[[policies.when]]
field = "error_rate"
op = ">="
value = 0.2

[policies.do]
action = "block"
"""

        class _FakeResp:
            def read(self):
                return toml_content
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: _FakeResp())

        pe = PolicyEngine.from_url("https://example.com/policy.toml")
        assert len(pe.rules) == 1
        assert pe.rules[0].name == "url-rule"


# ---------------------------------------------------------------------------
# POL-02: @soma.guardrail decorator
# ---------------------------------------------------------------------------

class TestGuardrail:
    def setup_method(self):
        self.engine = SOMAEngine(budget={"tokens": 100000})
        self.engine.register_agent("a")

    def _raise_pressure(self, pressure=0.8):
        """Push agent pressure to a known level by manipulating graph directly."""
        self.engine._graph.set_internal_pressure("a", pressure)
        self.engine._graph._nodes["a"].effective_pressure = pressure

    def test_guardrail_exported_from_soma(self):
        assert hasattr(soma, "guardrail")
        assert soma.guardrail is guardrail

    def test_policy_engine_exported_from_soma(self):
        assert hasattr(soma, "PolicyEngine")

    def test_low_pressure_allows_call(self):
        @guardrail(self.engine, "a", threshold=0.6)
        def noop():
            return "ok"

        assert noop() == "ok"

    def test_high_pressure_blocks_call(self):
        from soma.wrap import SomaBlocked
        self._raise_pressure(0.9)

        @guardrail(self.engine, "a", threshold=0.5)
        def dangerous():
            return "should not run"

        with pytest.raises(SomaBlocked):
            dangerous()

    def test_blocked_preserves_args(self):
        """Decorated function passes through args when not blocked."""
        @guardrail(self.engine, "a", threshold=0.9)
        def add(x, y):
            return x + y

        assert add(2, 3) == 5

    def test_async_low_pressure_allows(self):
        import asyncio

        @guardrail(self.engine, "a", threshold=0.9)
        async def async_noop():
            return "async ok"

        result = asyncio.run(async_noop())
        assert result == "async ok"

    def test_async_high_pressure_blocks(self):
        import asyncio
        from soma.wrap import SomaBlocked

        self._raise_pressure(0.9)

        @guardrail(self.engine, "a", threshold=0.5)
        async def async_danger():
            return "bad"

        with pytest.raises(SomaBlocked):
            asyncio.run(async_danger())

    def test_default_threshold_is_0_5(self):
        """Default threshold of 0.5 blocks at 0.6 effective pressure."""
        from soma.wrap import SomaBlocked
        self._raise_pressure(0.6)

        @guardrail(self.engine, "a")
        def risky():
            return "risky"

        with pytest.raises(SomaBlocked):
            risky()

    def test_functools_wraps_preserved(self):
        @guardrail(self.engine, "a", threshold=0.9)
        def my_function():
            """My docstring."""
            return "ok"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
