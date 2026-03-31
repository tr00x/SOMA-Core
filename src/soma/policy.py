"""SOMA Policy Engine — declarative behavioral rules (POL-01, POL-02, POL-03).

Policies define when/do rules that fire independently of pressure thresholds,
giving operators fine-grained control over agent behavior.

Usage (YAML policy file — POL-01):

    # soma.yaml
    version: "1"
    policies:
      - name: "high-error-guard"
        when:
          - field: "error_rate"
            op: ">="
            value: 0.3
        do:
          action: "warn"
          message: "Error rate exceeds 30%"

Usage (Python guardrail decorator — POL-02):

    @soma.guardrail(engine, "agent-1", threshold=0.6)
    def delete_files(path: str) -> None:
        os.remove(path)

Usage (community policy pack from URL — POL-03):

    policy_engine = PolicyEngine.from_url(
        "https://raw.githubusercontent.com/example/soma-policies/main/default.yaml"
    )
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Callable

from soma.types import VitalsSnapshot
from soma.engine import SOMAEngine


# ---------------------------------------------------------------------------
# Rule building blocks
# ---------------------------------------------------------------------------

_OPERATORS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    "<":  lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

# Fields exposed to policy conditions
_VITALS_FIELDS = frozenset({
    "pressure", "uncertainty", "drift", "error_rate",
    "token_usage", "cost", "calibration_score",
})


@dataclass(frozen=True)
class PolicyCondition:
    """A single condition in a policy rule."""
    field: str
    op: str
    value: float


@dataclass(frozen=True)
class PolicyAction:
    """The action to take when a rule fires."""
    action: str          # "warn", "block", "guide", "log"
    message: str = ""


@dataclass
class Rule:
    """A named policy rule with AND-joined conditions and a single action."""
    name: str
    conditions: list[PolicyCondition]
    action: PolicyAction


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Evaluates declarative policy rules against agent vitals.

    Rules use AND logic across conditions. First matching rule wins when
    checking for blocking actions; all matching rules return their actions
    in evaluate().
    """

    def __init__(self, rules: list[Rule]) -> None:
        self.rules = rules

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        vitals: VitalsSnapshot,
        pressure: float,
    ) -> list[PolicyAction]:
        """Evaluate all rules and return actions for every matching rule."""
        context = self._build_context(vitals, pressure)
        return [
            rule.action
            for rule in self.rules
            if self._matches(rule.conditions, context)
        ]

    def _build_context(self, vitals: VitalsSnapshot, pressure: float) -> dict[str, float]:
        ctx: dict[str, float] = {
            "pressure": pressure,
            "uncertainty": vitals.uncertainty,
            "drift": vitals.drift,
            "error_rate": vitals.error_rate,
            "token_usage": vitals.token_usage,
            "cost": vitals.cost,
        }
        if vitals.calibration_score is not None:
            ctx["calibration_score"] = vitals.calibration_score
        return ctx

    def _matches(
        self,
        conditions: list[PolicyCondition],
        context: dict[str, float],
    ) -> bool:
        for cond in conditions:
            val = context.get(cond.field)
            if val is None:
                return False
            op_fn = _OPERATORS.get(cond.op)
            if op_fn is None or not op_fn(val, cond.value):
                return False
        return True

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyEngine":
        """Build a PolicyEngine from a parsed config dict."""
        rules: list[Rule] = []
        for entry in data.get("policies", []):
            conditions = [
                PolicyCondition(
                    field=c["field"],
                    op=c.get("op", c.get("operator", ">=")),
                    value=float(c["value"]),
                )
                for c in entry.get("when", [])
            ]
            do = entry.get("do", {})
            action = PolicyAction(
                action=do.get("action", "log"),
                message=do.get("message", ""),
            )
            rules.append(Rule(
                name=entry.get("name", "unnamed"),
                conditions=conditions,
                action=action,
            ))
        return cls(rules)

    @classmethod
    def from_file(cls, path: str) -> "PolicyEngine":
        """Load policy from a local .yaml/.yml or .toml file.

        YAML requires PyYAML (pip install pyyaml).
        TOML uses the built-in tomllib (Python 3.11+).
        """
        from pathlib import Path
        raw = Path(path).read_text()
        return cls.from_dict(_parse_policy_text(raw, path))

    @classmethod
    def from_url(cls, url: str) -> "PolicyEngine":
        """Load policy pack from a URL (POL-03).

        Supports .yaml/.yml and .toml files.
        Uses only stdlib urllib — no extra dependencies required.
        """
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
        return cls.from_dict(_parse_policy_text(raw, url))


def _parse_policy_text(text: str, source: str) -> dict[str, Any]:
    """Parse policy text as YAML or TOML based on file extension."""
    source_lower = source.lower()
    if source_lower.endswith((".yaml", ".yml")):
        try:
            import yaml  # PyYAML
            return yaml.safe_load(text) or {}
        except ImportError:
            raise ImportError(
                "PyYAML is required to load .yaml policy files. "
                "Install it with: pip install pyyaml"
            )
    # Default: TOML
    import tomllib
    return tomllib.loads(text)


# ---------------------------------------------------------------------------
# @soma.guardrail decorator (POL-02)
# ---------------------------------------------------------------------------

def guardrail(
    engine: SOMAEngine,
    agent_id: str,
    threshold: float = 0.5,
) -> Callable:
    """Decorator that blocks a function when agent pressure exceeds threshold.

    Works with both synchronous and async functions. Raises SomaBlocked
    when the agent's current effective pressure >= threshold.

    Args:
        engine:    SOMAEngine instance to check pressure against.
        agent_id:  Registered agent to check.
        threshold: Pressure level that triggers the block (default 0.5).

    Example::

        @soma.guardrail(engine, "agent-1", threshold=0.6)
        def delete_files(path: str) -> None:
            os.remove(path)
    """
    import asyncio
    from soma.wrap import SomaBlocked

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            snap = engine.get_snapshot(agent_id)
            if snap["pressure"] >= threshold:
                raise SomaBlocked(agent_id, snap["level"], snap["pressure"])
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            snap = engine.get_snapshot(agent_id)
            if snap["pressure"] >= threshold:
                raise SomaBlocked(agent_id, snap["level"], snap["pressure"])
            return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
