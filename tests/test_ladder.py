"""Tests for soma.ladder.Ladder."""

from __future__ import annotations

import pytest

from soma.ladder import Ladder
from soma.types import AutonomyMode, Level


def fresh() -> Ladder:
    return Ladder()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_healthy():
    ladder = fresh()
    level = ladder.evaluate(pressure=0.0, budget_health=1.0)
    assert level is Level.HEALTHY


# ---------------------------------------------------------------------------
# Escalation sequence
# ---------------------------------------------------------------------------

def test_escalation_caution():
    ladder = fresh()
    level = ladder.evaluate(pressure=0.30, budget_health=1.0)
    assert level is Level.CAUTION


def test_escalation_degrade():
    ladder = fresh()
    ladder.evaluate(pressure=0.30, budget_health=1.0)  # → CAUTION
    level = ladder.evaluate(pressure=0.55, budget_health=1.0)
    assert level is Level.DEGRADE


def test_escalation_quarantine():
    ladder = fresh()
    ladder.evaluate(pressure=0.30, budget_health=1.0)
    ladder.evaluate(pressure=0.55, budget_health=1.0)
    level = ladder.evaluate(pressure=0.80, budget_health=1.0)
    assert level is Level.QUARANTINE


def test_escalation_restart():
    ladder = fresh()
    ladder.evaluate(pressure=0.30, budget_health=1.0)
    ladder.evaluate(pressure=0.55, budget_health=1.0)
    ladder.evaluate(pressure=0.80, budget_health=1.0)
    level = ladder.evaluate(pressure=0.92, budget_health=1.0)
    assert level is Level.RESTART


# ---------------------------------------------------------------------------
# SAFE_MODE
# ---------------------------------------------------------------------------

def test_safe_mode_on_zero_budget():
    ladder = fresh()
    level = ladder.evaluate(pressure=0.0, budget_health=0.0)
    assert level is Level.SAFE_MODE


def test_safe_mode_latches_below_exit_threshold():
    ladder = fresh()
    ladder.evaluate(pressure=0.0, budget_health=0.0)   # enter safe mode
    level = ladder.evaluate(pressure=0.0, budget_health=0.05)  # below exit threshold
    assert level is Level.SAFE_MODE


def test_safe_mode_exits_above_threshold():
    ladder = fresh()
    ladder.evaluate(pressure=0.0, budget_health=0.0)   # enter safe mode
    level = ladder.evaluate(pressure=0.0, budget_health=0.15)  # above 0.10
    assert level is Level.HEALTHY


# ---------------------------------------------------------------------------
# Hysteresis
# ---------------------------------------------------------------------------

def test_hysteresis_holds_at_caution():
    """pressure=0.22 is above caution escalate (0.25 not met? No—0.22 < 0.25 so
    actually stays HEALTHY. Let's use a value that already brought us to CAUTION
    and then sits between de-escalate and escalate thresholds."""
    ladder = fresh()
    ladder.evaluate(pressure=0.30, budget_health=1.0)  # → CAUTION
    # 0.22 is above de-escalate threshold (0.20) → should hold at CAUTION
    level = ladder.evaluate(pressure=0.22, budget_health=1.0)
    assert level is Level.CAUTION


def test_hysteresis_releases_to_healthy():
    ladder = fresh()
    ladder.evaluate(pressure=0.30, budget_health=1.0)  # → CAUTION
    # 0.18 is below de-escalate threshold (0.20) → drop one level → HEALTHY
    level = ladder.evaluate(pressure=0.18, budget_health=1.0)
    assert level is Level.HEALTHY


# ---------------------------------------------------------------------------
# Force override
# ---------------------------------------------------------------------------

def test_force_level_override():
    ladder = fresh()
    ladder.force_level(Level.QUARANTINE)
    level = ladder.evaluate(pressure=0.0, budget_health=1.0)
    assert level is Level.QUARANTINE


# ---------------------------------------------------------------------------
# Spike — skip levels
# ---------------------------------------------------------------------------

def test_spike_skips_levels():
    """A sudden pressure of 0.95 from HEALTHY should jump straight to RESTART."""
    ladder = fresh()
    level = ladder.evaluate(pressure=0.95, budget_health=1.0)
    assert level is Level.RESTART


# ---------------------------------------------------------------------------
# requires_approval / autonomy
# ---------------------------------------------------------------------------

def test_fully_autonomous_never_needs_approval():
    ladder = fresh()
    for level in Level:
        assert not ladder.requires_approval(level, AutonomyMode.FULLY_AUTONOMOUS)


def test_human_in_loop_blocks_quarantine():
    ladder = fresh()
    assert ladder.requires_approval(Level.QUARANTINE, AutonomyMode.HUMAN_IN_THE_LOOP)


def test_human_in_loop_blocks_restart():
    ladder = fresh()
    assert ladder.requires_approval(Level.RESTART, AutonomyMode.HUMAN_IN_THE_LOOP)


def test_human_in_loop_blocks_safe_mode():
    ladder = fresh()
    assert ladder.requires_approval(Level.SAFE_MODE, AutonomyMode.HUMAN_IN_THE_LOOP)


def test_human_in_loop_does_not_block_lower_levels():
    ladder = fresh()
    for level in (Level.HEALTHY, Level.CAUTION, Level.DEGRADE):
        assert not ladder.requires_approval(level, AutonomyMode.HUMAN_IN_THE_LOOP)


def test_human_on_loop_never_blocks():
    ladder = fresh()
    for level in Level:
        assert not ladder.requires_approval(level, AutonomyMode.HUMAN_ON_THE_LOOP)
