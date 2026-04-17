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
