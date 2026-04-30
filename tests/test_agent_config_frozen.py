"""
Regression for v2026.6.x fix #8 — AgentConfig must be frozen+slots
to match the value-object pattern of the other dataclasses in
types.py (Action, VitalsSnapshot, PressureVector are all frozen+slots).

Mutable AgentConfig was a footgun for shared default lists (`field(
default_factory=list)`) and for any caller that thought "config is a
value object, I can pass it around safely."
"""
from __future__ import annotations

import dataclasses

import pytest

from soma.types import AgentConfig, AutonomyMode


def test_agent_config_is_frozen() -> None:
    cfg = AgentConfig(agent_id="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.agent_id = "y"  # type: ignore[misc]


def test_agent_config_uses_slots() -> None:
    cfg = AgentConfig(agent_id="x")
    # Frozen+slots dataclasses reject ad-hoc attribute assignment.
    # The exact exception varies by Python version (FrozenInstanceError
    # for known fields, TypeError for unknown slots due to a quirk in
    # the generated __setattr__/super interaction).
    with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
        cfg.unknown_field = 42  # type: ignore[attr-defined]
    # And the slots are real — no __dict__.
    assert not hasattr(cfg, "__dict__"), (
        "AgentConfig has __dict__ — slots=True wasn't applied"
    )


def test_agent_config_rejects_empty_agent_id() -> None:
    with pytest.raises(ValueError):
        AgentConfig(agent_id="")


def test_agent_config_default_lists_are_independent() -> None:
    """Sanity — even with frozen, mutable default factories must not
    share state across instances."""
    a = AgentConfig(agent_id="a")
    b = AgentConfig(agent_id="b")
    assert a.tools_allowed is not b.tools_allowed
    # And each instance gets a fresh list, not a shared sentinel.
    assert a.tools_allowed == []
    assert b.tools_allowed == []
