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


def test_blind_edit_not_fired_on_write_to_nonexistent_file(cg, tmp_path):
    """Write to a non-existing path is a create — nothing to read — skip."""
    missing = tmp_path / "brand_new_file.py"
    assert not missing.exists()
    action_log = [{"tool": "Bash", "error": False, "file": ""}]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Write",
        current_input={"file_path": str(missing), "content": "x"},
        vitals={},
    )
    assert msg is None or msg.pattern != "blind_edit"


def test_blind_edit_fires_on_write_to_existing_file(cg, tmp_path):
    """Write to an existing file without Read is still a blind edit."""
    existing = tmp_path / "already_there.py"
    existing.write_text("original\n")
    action_log = [{"tool": "Bash", "error": False, "file": ""}]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Write",
        current_input={"file_path": str(existing), "content": "x"},
        vitals={},
    )
    assert msg is not None
    assert msg.pattern == "blind_edit"


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


def test_panic_detected_low_entropy_fast_velocity(cg):
    """Low entropy + fast actions = panic, should escalate to critical.

    With 7 Bash + 1 Read, entropy ≈ 0.54 (normally "warn").
    Fast velocity (1s gaps) should escalate to "critical".
    """
    import time
    now = time.time()
    action_log = [
        {"tool": "Read", "error": False, "file": "/f.py", "ts": now - 8},
        {"tool": "Bash", "error": True, "file": "", "ts": now - 7},
        {"tool": "Bash", "error": False, "file": "", "ts": now - 6},
        {"tool": "Bash", "error": True, "file": "", "ts": now - 5},
        {"tool": "Bash", "error": False, "file": "", "ts": now - 4},
        {"tool": "Bash", "error": True, "file": "", "ts": now - 3},
        {"tool": "Bash", "error": False, "file": "", "ts": now - 2},
        {"tool": "Bash", "error": True, "file": "", "ts": now - 1},
    ]
    msg = cg.evaluate(
        action_log=action_log, current_tool="Bash", current_input={}, vitals={},
    )
    assert msg is not None
    assert msg.pattern == "entropy_drop"
    assert msg.severity == "critical"  # Panic: low entropy + fast velocity


def test_entropy_warn_without_velocity(cg):
    """Same low entropy but no timestamps = stays at warn, not critical."""
    action_log = [
        {"tool": "Read", "error": False, "file": "/f.py"},
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
    assert msg.severity == "warn"  # No velocity data = stays warn


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


# ---------------------------------------------------------------------------
# check_followthrough — blind_edit
# ---------------------------------------------------------------------------

def test_followthrough_blind_edit_followed():
    """Reading the suggested file counts as following blind_edit guidance."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "blind_edit", "file": "/src/foo.py", "actions_since": 0}
    result = check_followthrough(pending, "Read", {}, "/src/foo.py", error=False)
    assert result is True


def test_followthrough_blind_edit_ignored():
    """Editing again without reading means guidance was ignored."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "blind_edit", "file": "/src/foo.py", "actions_since": 0}
    result = check_followthrough(pending, "Edit", {"file_path": "/src/foo.py"}, "/src/foo.py", error=False)
    assert result is False


def test_followthrough_blind_edit_waiting():
    """Using an unrelated tool (Grep on a different file) is inconclusive."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "blind_edit", "file": "/src/foo.py", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {"command": "ls"}, "", error=False)
    assert result is None


# ---------------------------------------------------------------------------
# check_followthrough — error_cascade
# ---------------------------------------------------------------------------

def test_followthrough_error_cascade_followed():
    """Next action succeeding means agent broke the cascade."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "error_cascade", "actions_since": 0}
    result = check_followthrough(pending, "Read", {}, "/src/foo.py", error=False)
    assert result is True


def test_followthrough_error_cascade_waiting():
    """Still erroring is inconclusive (agent may recover next action)."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "error_cascade", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {"command": "make"}, "", error=True)
    assert result is None


# ---------------------------------------------------------------------------
# check_followthrough — budget
# ---------------------------------------------------------------------------

def test_followthrough_budget_followed():
    """Running git commit means agent is wrapping up as suggested."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "budget", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {"command": "git commit -m 'save'"}, "", error=False)
    assert result is True


def test_followthrough_budget_waiting():
    """Using Edit (not git commit) is inconclusive for budget guidance."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "budget", "actions_since": 0}
    result = check_followthrough(pending, "Edit", {"file_path": "/src/foo.py"}, "/src/foo.py", error=False)
    assert result is None


# ---------------------------------------------------------------------------
# check_followthrough — entropy_drop
# ---------------------------------------------------------------------------

def test_followthrough_entropy_drop_followed():
    """Switching to a different tool means agent diversified."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "entropy_drop", "tool": "Bash", "actions_since": 0}
    result = check_followthrough(pending, "Read", {}, "/src/foo.py", error=False)
    assert result is True


def test_followthrough_entropy_drop_ignored():
    """Same tool 3+ actions after guidance means agent ignored it."""
    from soma.contextual_guidance import check_followthrough

    # actions_since will be incremented to 3 inside check_followthrough
    pending = {"pattern": "entropy_drop", "tool": "Bash", "actions_since": 2}
    result = check_followthrough(pending, "Bash", {"command": "ls"}, "", error=False)
    assert result is False


# ---------------------------------------------------------------------------
# check_followthrough — bash_retry
# ---------------------------------------------------------------------------

def test_followthrough_bash_retry_followed():
    """Switching away from Bash to Read means agent followed guidance."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "bash_retry", "tool": "Bash", "actions_since": 0}
    result = check_followthrough(pending, "Read", {}, "/src/foo.py", error=False)
    assert result is True


def test_followthrough_bash_retry_succeeded():
    """Bash succeeding counts as positive outcome."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "bash_retry", "tool": "Bash", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {"command": "make test"}, "", error=False)
    assert result is True


def test_followthrough_bash_retry_ignored():
    """Bash still erroring means guidance was ignored."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "bash_retry", "tool": "Bash", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {"command": "make test"}, "", error=True)
    assert result is False


# ---------------------------------------------------------------------------
# check_followthrough — timeout & unknown
# ---------------------------------------------------------------------------

def test_followthrough_timeout():
    """More than 5 actions since guidance means gave up waiting."""
    from soma.contextual_guidance import check_followthrough

    # actions_since=5 will be incremented to 6 inside, triggering timeout
    pending = {"pattern": "blind_edit", "file": "/src/foo.py", "actions_since": 5}
    result = check_followthrough(pending, "Read", {}, "/src/foo.py", error=False)
    assert result is False


def test_followthrough_unknown_pattern():
    """Unknown pattern returns None (inconclusive)."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "totally_unknown_pattern", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {}, "", error=False)
    assert result is None


# ---------------------------------------------------------------------------
# Guidance outcome analytics bridge
# ---------------------------------------------------------------------------

def test_record_outcome_writes_to_analytics_when_followed(tmp_path):
    """When followthrough is detected, outcome must be persisted to
    analytics.db.guidance_outcomes so dashboard ROI page can see it."""
    from soma.hooks.post_tool_use import _record_outcome_if_resolved
    from soma.analytics import AnalyticsStore

    db_path = tmp_path / "analytics.db"
    pending = {
        "pattern": "bash_retry",
        "suggestion": "Read next",
        "tool": "Bash",
        "actions_since": 0,
        "pressure_at_injection": 0.7,
    }

    _record_outcome_if_resolved(
        agent_id="cc-test",
        pending=pending,
        followed=True,
        pressure_after=0.15,
        analytics_path=db_path,
    )

    store = AnalyticsStore(path=db_path)
    rows = store._conn.execute(
        "SELECT pattern_key, helped, pressure_at_injection, pressure_after "
        "FROM guidance_outcomes WHERE agent_id=?",
        ("cc-test",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == ("bash_retry", 1, 0.7, 0.15)


def test_record_outcome_writes_failure_when_ignored(tmp_path):
    """Ignored guidance must be recorded as helped=0."""
    from soma.hooks.post_tool_use import _record_outcome_if_resolved
    from soma.analytics import AnalyticsStore

    db_path = tmp_path / "analytics.db"
    pending = {
        "pattern": "blind_edit",
        "actions_since": 0,
        "pressure_at_injection": 0.55,
    }

    _record_outcome_if_resolved(
        agent_id="cc-ignored",
        pending=pending,
        followed=False,
        pressure_after=0.60,
        analytics_path=db_path,
    )

    rows = AnalyticsStore(path=db_path)._conn.execute(
        "SELECT pattern_key, helped FROM guidance_outcomes WHERE agent_id=?",
        ("cc-ignored",),
    ).fetchall()
    assert rows == [("blind_edit", 0)]


# ---------------------------------------------------------------------------
# check_followthrough — pressure-based resolution for non-explicit patterns
# ---------------------------------------------------------------------------

def test_followthrough_cost_spiral_resolved_by_pressure_drop():
    """cost_spiral had no branch at all — pressure drop resolves it."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "cost_spiral", "actions_since": 0, "pressure_at_injection": 0.75}
    result = check_followthrough(pending, "Bash", {}, "", error=False, pressure_after=0.45)
    assert result is True


def test_followthrough_context_resolved_by_pressure_drop():
    """context pattern also resolves via pressure drop if no explicit compact."""
    from soma.contextual_guidance import check_followthrough

    pending = {"pattern": "context", "actions_since": 1, "pressure_at_injection": 0.60}
    result = check_followthrough(pending, "Read", {}, "", error=False, pressure_after=0.28)
    assert result is True


def test_followthrough_pressure_signal_ignored_when_absent():
    """Without pressure_after, fall back to existing pattern-specific logic."""
    from soma.contextual_guidance import check_followthrough

    # drift with no pressure data = keep waiting (None) until timeout
    pending = {"pattern": "drift", "actions_since": 0}
    result = check_followthrough(pending, "Bash", {}, "", error=False)
    assert result is None
