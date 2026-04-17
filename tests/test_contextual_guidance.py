"""Tests for SOMA contextual guidance — pattern-based actionable messages."""

from __future__ import annotations

import pytest

from soma.contextual_guidance import ContextualGuidance, GuidanceMessage, _suggest_for_error


@pytest.fixture
def cg():
    return ContextualGuidance(cooldown_actions=5)


# ── Blind Edit ──


def test_blind_edit_detected(cg):
    action_log = [
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Edit",
        current_input={"file_path": "/src/foo.py"},
        vitals={},
    )
    assert msg is not None
    assert msg.pattern == "blind_edit"
    assert "foo.py" in msg.message
    assert "without reading" in msg.message


def test_blind_edit_not_fired_when_file_was_read(cg):
    action_log = [
        {"tool": "Read", "error": False, "file": "/src/foo.py"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Edit",
        current_input={"file_path": "/src/foo.py"},
        vitals={},
    )
    assert msg is None or msg.pattern != "blind_edit"


def test_blind_edit_includes_file_content(cg, tmp_path):
    """When blind_edit fires and file exists, message includes file content."""
    target = tmp_path / "foo.py"
    target.write_text("def hello():\n    return 'world'\n\ndef broken():\n    pass\n")
    action_log = [{"tool": "Bash", "error": False, "file": ""}]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Edit",
        current_input={"file_path": str(target)},
        vitals={},
    )
    assert msg is not None
    assert msg.pattern == "blind_edit"
    assert "def hello" in msg.message  # file content injected
    assert "foo.py" in msg.message


def test_blind_edit_not_fired_for_non_edit_tools(cg):
    action_log = [{"tool": "Bash", "error": False, "file": ""}]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={"command": "ls"},
        vitals={},
    )
    assert msg is None or msg.pattern != "blind_edit"


# ── Retry Storm ──


def test_retry_storm_detected(cg):
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "permission denied"},
        {"tool": "Bash", "error": True, "file": "", "output": "permission denied"},
        {"tool": "Bash", "error": True, "file": "", "output": "permission denied"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={"command": "rm /etc/foo"},
        vitals={},
    )
    assert msg is not None
    assert msg.pattern == "retry_storm"
    assert "3 times" in msg.message
    assert "permission" in msg.message.lower() or "permission" in msg.suggestion


def test_retry_storm_not_fired_for_different_tool(cg):
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "error"},
        {"tool": "Bash", "error": True, "file": "", "output": "error"},
        {"tool": "Bash", "error": True, "file": "", "output": "error"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Read",  # different tool
        current_input={},
        vitals={},
    )
    assert msg is None or msg.pattern != "retry_storm"


def test_retry_storm_not_fired_under_threshold(cg):
    action_log = [
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={},
    )
    assert msg is None or msg.pattern != "retry_storm"


def test_retry_storm_includes_lesson(tmp_path):
    """If a lesson exists for the error, include it in the message."""
    from soma.lessons import LessonStore
    store = LessonStore(path=tmp_path / "lessons.json")
    store.record(
        pattern="permission_denied",
        error_text="Permission denied: /etc/shadow",
        fix_text="Run with sudo or check file ownership",
        tool="Bash",
    )
    cg = ContextualGuidance(lesson_store=store)

    action_log = [
        {"tool": "Bash", "error": True, "output": "Permission denied: /etc/config"},
        {"tool": "Bash", "error": True, "output": "Permission denied: /etc/config"},
        {"tool": "Bash", "error": True, "output": "Permission denied: /etc/config"},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is not None
    assert "sudo" in msg.message.lower() or "ownership" in msg.message.lower()


# ── Error Cascade ──


def test_error_cascade_3_errors(cg):
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "fail 1"},
        {"tool": "Edit", "error": True, "file": "/f.py", "output": "fail 2"},
        {"tool": "Bash", "error": True, "file": "", "output": "fail 3"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={},
    )
    assert msg is not None
    assert msg.pattern == "error_cascade"
    assert "3 errors" in msg.message


def test_error_cascade_5_is_critical(cg):
    action_log = [{"tool": "Bash", "error": True, "file": "", "output": f"err {i}"} for i in range(5)]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={},
    )
    assert msg is not None
    assert msg.severity == "critical"


def test_error_cascade_not_fired_when_success_breaks_streak(cg):
    action_log = [
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},  # breaks streak
        {"tool": "Bash", "error": True, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={},
    )
    assert msg is None or msg.pattern != "error_cascade"


def test_error_cascade_suppressed_when_within_baseline():
    """If agent's baseline error_rate is high, 3 errors shouldn't trigger."""
    from soma.baseline import Baseline
    baseline = Baseline(alpha=0.08, min_samples=3)
    # Train baseline: agent normally has ~40% error rate
    for _ in range(10):
        baseline.update("error_rate", 0.4)

    cg = ContextualGuidance(baseline=baseline)

    # 3 errors in 10 actions = 30% — below agent's normal 40%
    action_log = [
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    # Should NOT fire error_cascade — this is within agent's baseline
    assert msg is None or msg.pattern != "error_cascade"


# ── Budget Warning ──


def test_budget_warning_low(cg):
    msg = cg.evaluate(
        action_log=[],
        current_tool="Bash",
        current_input={},
        vitals={},
        budget_health=0.10,
    )
    assert msg is not None
    assert msg.pattern == "budget"
    assert "10%" in msg.message


def test_budget_critical(cg):
    msg = cg.evaluate(
        action_log=[],
        current_tool="Bash",
        current_input={},
        vitals={},
        budget_health=0.03,
    )
    assert msg is not None
    assert msg.severity == "critical"


def test_budget_ok(cg):
    msg = cg.evaluate(
        action_log=[],
        current_tool="Bash",
        current_input={},
        vitals={},
        budget_health=0.5,
    )
    assert msg is None or msg.pattern != "budget"


# ── Context Window ──


def test_context_window_warning(cg):
    msg = cg.evaluate(
        action_log=[],
        current_tool="Bash",
        current_input={},
        vitals={"token_usage": 0.85},
    )
    assert msg is not None
    assert msg.pattern == "context"
    assert "85%" in msg.message


def test_context_window_critical(cg):
    msg = cg.evaluate(
        action_log=[],
        current_tool="Bash",
        current_input={},
        vitals={"token_usage": 0.97},
    )
    assert msg is not None
    assert msg.severity == "critical"


def test_context_window_ok(cg):
    msg = cg.evaluate(
        action_log=[],
        current_tool="Bash",
        current_input={},
        vitals={"token_usage": 0.5},
    )
    assert msg is None or msg.pattern != "context"


# ── Drift ──


def test_drift_detected_with_tool_shift(cg):
    action_log = (
        [{"tool": "Read", "error": False, "file": ""} for _ in range(5)]
        + [{"tool": "Bash", "error": False, "file": ""} for _ in range(5)]
    )
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={"drift": 0.4},
    )
    assert msg is not None
    assert msg.pattern == "drift"
    assert "Read" in msg.message
    assert "Bash" in msg.message


def test_drift_not_fired_low_drift(cg):
    action_log = [{"tool": "Bash", "error": False, "file": ""} for _ in range(10)]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={"drift": 0.1},
    )
    assert msg is None or msg.pattern != "drift"


# ── Cost Spiral ──


def test_cost_spiral_detected(cg):
    """Detect expensive retry loop — many errors + high token usage."""
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={"token_usage": 0.6},
        budget_health=0.3,
    )
    assert msg is not None
    assert msg.pattern == "cost_spiral"
    assert "cheaper" in msg.message.lower() or "debug" in msg.message.lower()


def test_cost_spiral_not_fired_when_healthy(cg):
    """No cost spiral when budget is healthy."""
    action_log = [
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
        {"tool": "Bash", "error": True, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={"token_usage": 0.2},
        budget_health=0.8,
    )
    # Should fire retry_storm or error_cascade, not cost_spiral
    assert msg is None or msg.pattern != "cost_spiral"


# ── Cooldown ──


def test_cooldown_suppresses_repeated_pattern(cg):
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "err"},
        {"tool": "Bash", "error": True, "file": "", "output": "err"},
        {"tool": "Bash", "error": True, "file": "", "output": "err"},
    ]
    # First fire
    msg1 = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={},
        vitals={}, action_number=10,
    )
    assert msg1 is not None

    # Same action_number range — should be suppressed
    msg2 = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={},
        vitals={}, action_number=12,
    )
    assert msg2 is None or msg2.pattern != msg1.pattern

    # After cooldown
    msg3 = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={},
        vitals={}, action_number=16,
    )
    assert msg3 is not None


# ── Severity Priority ──


def test_highest_severity_wins(cg):
    # Both error_cascade (warn) and budget (critical) should fire,
    # budget (critical) wins
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "err"},
        {"tool": "Bash", "error": True, "file": "", "output": "err"},
        {"tool": "Bash", "error": True, "file": "", "output": "err"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={},
        budget_health=0.03,
    )
    assert msg is not None
    assert msg.severity == "critical"


# ── Error Suggestion Mapping ──


def test_suggest_permission_denied():
    assert "permission" in _suggest_for_error("Permission denied: /etc/foo")


def test_suggest_not_found():
    assert "path" in _suggest_for_error("No such file or directory: /foo/bar")


def test_suggest_syntax_error():
    assert "read" in _suggest_for_error("SyntaxError: unexpected indent")


def test_suggest_test_failure():
    assert "expected" in _suggest_for_error("AssertionError: expected 5 but got 3").lower() or \
           "test" in _suggest_for_error("AssertionError: expected 5 but got 3").lower()


def test_suggest_fallback():
    result = _suggest_for_error("something completely unknown went wrong")
    assert "different approach" in result


# ── GuidanceMessage immutability ──


def test_guidance_message_is_frozen():
    msg = GuidanceMessage(pattern="test", severity="info", message="hello")
    with pytest.raises(AttributeError):
        msg.pattern = "other"


# ── Edge cases ──


def test_empty_action_log(cg):
    msg = cg.evaluate(
        action_log=[], current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is None or msg.pattern in ("budget", "context")


def test_no_false_positives_on_clean_session(cg):
    action_log = [
        {"tool": "Read", "error": False, "file": "/src/foo.py"},
        {"tool": "Edit", "error": False, "file": "/src/foo.py"},
        {"tool": "Read", "error": False, "file": "/src/bar.py"},
        {"tool": "Edit", "error": False, "file": "/src/bar.py"},
        {"tool": "Bash", "error": False, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={"drift": 0.0, "token_usage": 0.3},
        budget_health=0.8,
    )
    assert msg is None


# ---------------------------------------------------------------------------
# Healing Transition Prescriptions
# ---------------------------------------------------------------------------

def test_healing_transition_suggested_after_bash_error(cg):
    """After Bash errors, guidance should suggest Read (historically reduces pressure)."""
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
        {"tool": "Bash", "error": True, "file": "", "output": "test failed"},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is not None
    # Should mention Read as healing transition with data (in suggestion or message)
    combined = msg.suggestion + " " + msg.message
    assert "Read" in combined or "read" in combined.lower()
    assert "7%" in combined or "pressure" in combined.lower()


# ---------------------------------------------------------------------------
# Pattern 8: Entropy Drop (monotool tunnel vision)
# ---------------------------------------------------------------------------

def test_entropy_drop_detected(cg):
    """Low tool entropy (monotool) triggers warning."""
    action_log = [
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Bash", "error": False, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is not None
    assert msg.pattern == "entropy_drop"
    assert "Bash" in msg.message


def test_entropy_drop_not_fired_with_diverse_tools(cg):
    """Diverse tool usage = healthy, no warning."""
    action_log = [
        {"tool": "Read", "error": False, "file": "/src/a.py"},
        {"tool": "Grep", "error": False, "file": ""},
        {"tool": "Edit", "error": False, "file": "/src/a.py"},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Read", "error": False, "file": "/src/b.py"},
        {"tool": "Glob", "error": False, "file": ""},
        {"tool": "Edit", "error": False, "file": "/src/b.py"},
        {"tool": "Bash", "error": False, "file": ""},
        {"tool": "Read", "error": False, "file": "/src/c.py"},
        {"tool": "Write", "error": False, "file": "/src/c.py"},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is None or msg.pattern != "entropy_drop"


# ---------------------------------------------------------------------------
# Pattern 9: Bash Retry Intercept
# ---------------------------------------------------------------------------

def test_bash_retry_intercepted(cg):
    """After Bash error, trying Bash again should trigger warning."""
    action_log = [
        {"tool": "Read", "error": False, "file": "/src/a.py"},
        {"tool": "Bash", "error": True, "file": "", "output": "Error: test failed"},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is not None
    assert msg.pattern == "bash_retry"
    assert "Read" in msg.message or "error" in msg.message.lower()


def test_bash_retry_not_fired_after_success(cg):
    """After successful Bash, another Bash is fine."""
    action_log = [
        {"tool": "Bash", "error": False, "file": ""},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is None or msg.pattern != "bash_retry"


def test_bash_retry_not_fired_for_different_tool(cg):
    """After Bash error, using Read is fine — no warning."""
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "Error: failed"},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Read", current_input={}, vitals={},
    )
    assert msg is None or msg.pattern != "bash_retry"
