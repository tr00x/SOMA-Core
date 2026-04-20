"""Integration: CalibrationProfile gates ContextualGuidance.

Day 2 of v2026.5.0 — warmup silence + adaptive-phase auto-silence
must wire cleanly through the public evaluate() path without breaking
the legacy always-armed behavior.
"""

from __future__ import annotations

from soma.calibration import (
    CALIBRATED_EXIT_ACTIONS,
    CalibrationProfile,
    WARMUP_EXIT_ACTIONS,
)
from soma.contextual_guidance import ContextualGuidance


def _blind_edit_setup(tmp_path=None) -> tuple[list[dict], dict]:
    """Minimal inputs that normally fire the blind_edit pattern.

    v2026.5.3: blind_edit now requires Write on an *existing* file
    (Edit is gated by Claude Code itself). We create a temp file so
    the pattern actually fires end-to-end.
    """
    import os
    import tempfile
    # Best-effort: create a real file so the pattern's existence check
    # passes. Tests that don't care about content can still pass a
    # file_path that exists.
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"x = 1\n")
    os.close(fd)
    action_log = [{"tool": "Grep"}, {"tool": "Read"}]
    current_input = {"file_path": path}
    return action_log, current_input


def _vitals(token_usage: float = 0.0) -> dict:
    return {
        "uncertainty": 0.0, "drift": 0.0, "error_rate": 0.0,
        "token_usage": token_usage, "context_usage": token_usage,
    }


# ── Warmup gate ──────────────────────────────────────────────────────

def test_warmup_profile_silences_all_patterns():
    profile = CalibrationProfile(family="cc", action_count=0)  # warmup
    cg = ContextualGuidance(profile=profile)
    action_log, current_input = _blind_edit_setup()
    msg = cg.evaluate(
        action_log=action_log, current_tool="Write",
        current_input=current_input, vitals=_vitals(),
        budget_health=1.0, action_number=2,
    )
    assert msg is None, "warmup phase must return no guidance"


def test_warmup_last_action_still_silenced():
    profile = CalibrationProfile(family="cc", action_count=WARMUP_EXIT_ACTIONS - 1)
    cg = ContextualGuidance(profile=profile)
    action_log, current_input = _blind_edit_setup()
    msg = cg.evaluate(
        action_log=action_log, current_tool="Write",
        current_input=current_input, vitals=_vitals(),
        budget_health=1.0, action_number=2,
    )
    assert msg is None


def test_calibrated_phase_fires_normally():
    """At exactly action_count = 100 the profile flips to calibrated."""
    profile = CalibrationProfile(family="cc", action_count=WARMUP_EXIT_ACTIONS)
    assert profile.phase == "calibrated"
    cg = ContextualGuidance(profile=profile)
    action_log, current_input = _blind_edit_setup()
    msg = cg.evaluate(
        action_log=action_log, current_tool="Write",
        current_input=current_input, vitals=_vitals(),
        budget_health=1.0, action_number=2,
    )
    assert msg is not None
    assert msg.pattern == "blind_edit"


def test_legacy_no_profile_behavior_unchanged():
    """profile=None is the pre-calibration default — must keep firing."""
    cg = ContextualGuidance()  # no profile passed
    action_log, current_input = _blind_edit_setup()
    msg = cg.evaluate(
        action_log=action_log, current_tool="Write",
        current_input=current_input, vitals=_vitals(),
        budget_health=1.0, action_number=2,
    )
    assert msg is not None
    assert msg.pattern == "blind_edit"


# ── Adaptive auto-silence ────────────────────────────────────────────

def test_adaptive_silence_drops_target_pattern():
    profile = CalibrationProfile(
        family="cc", action_count=CALIBRATED_EXIT_ACTIONS,
        silenced_patterns=["blind_edit"],
    )
    assert profile.phase == "adaptive"
    cg = ContextualGuidance(profile=profile)
    action_log, current_input = _blind_edit_setup()
    msg = cg.evaluate(
        action_log=action_log, current_tool="Write",
        current_input=current_input, vitals=_vitals(),
        budget_health=1.0, action_number=2,
    )
    assert msg is None, "silenced pattern must not fire in adaptive phase"


def test_adaptive_does_not_silence_unlisted_patterns():
    """Only the silenced pattern drops; others still fire."""
    profile = CalibrationProfile(
        family="cc", action_count=CALIBRATED_EXIT_ACTIONS,
        silenced_patterns=["drift"],  # unrelated pattern
    )
    cg = ContextualGuidance(profile=profile)
    action_log, current_input = _blind_edit_setup()
    msg = cg.evaluate(
        action_log=action_log, current_tool="Write",
        current_input=current_input, vitals=_vitals(),
        budget_health=1.0, action_number=2,
    )
    assert msg is not None
    assert msg.pattern == "blind_edit"


# ── Profile counter advance (sanity) ────────────────────────────────

def test_profile_phase_flip_is_idempotent_at_boundary():
    """Advancing to exactly the warmup boundary flips the phase once."""
    p = CalibrationProfile(family="cc")
    p.advance(WARMUP_EXIT_ACTIONS - 1)
    assert p.phase == "warmup"
    p.advance(1)
    assert p.phase == "calibrated"
    p.advance(1)
    assert p.phase == "calibrated"  # still inside the calibrated band
