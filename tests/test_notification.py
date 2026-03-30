"""Tests for notification improvements — read context, severity, positive feedback."""

from soma.hooks.notification import _analyze_patterns


class TestReadContextAwareness:
    def test_edit_after_read_same_file_no_warning(self):
        """Editing a file that was recently Read should NOT warn."""
        log = [
            {"tool": "Read", "error": False, "file": "/project/src/auth.py", "ts": 1},
            {"tool": "Read", "error": False, "file": "/project/src/models.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/project/src/models.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 5},
            {"tool": "Edit", "error": False, "file": "/project/src/models.py", "ts": 6},
        ]
        tips = _analyze_patterns(log)
        assert not any("edit" in t.lower() and "without" in t.lower() for t in tips)
        assert not any("blind" in t.lower() for t in tips)

    def test_edit_without_read_warns(self):
        """Editing files never Read SHOULD warn."""
        log = [
            {"tool": "Edit", "error": False, "file": "/project/src/new.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/project/src/other.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/third.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert any("blind" in t.lower() or ("edit" in t.lower() and "without" in t.lower()) for t in tips)

    def test_read_directory_covers_files(self):
        """Reading files in a directory covers edits to other files in same dir."""
        log = [
            {"tool": "Read", "error": False, "file": "/project/src/auth/login.py", "ts": 1},
            {"tool": "Read", "error": False, "file": "/project/src/auth/types.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/auth/middleware.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/project/src/auth/login.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "/project/src/auth/types.py", "ts": 5},
        ]
        tips = _analyze_patterns(log)
        assert not any("blind" in t.lower() for t in tips)

    def test_write_new_file_no_warning(self):
        """Write (creating new files) should never trigger 'edit without read'."""
        log = [
            {"tool": "Write", "error": False, "file": "/project/new_file.py", "ts": 1},
            {"tool": "Write", "error": False, "file": "/project/another.py", "ts": 2},
            {"tool": "Write", "error": False, "file": "/project/third.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert not any("blind" in t.lower() for t in tips)

class TestWorkflowSeverity:
    def test_agent_spam_suppressed_in_planning(self):
        """Agent spawns during planning workflows should not warn."""
        log = [
            {"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)
        ]
        tips = _analyze_patterns(log, workflow_mode="plan")
        assert not any("agent" in t.lower() for t in tips)

    def test_agent_spam_warns_in_default_mode(self):
        """Agent spawns without workflow context should still warn."""
        log = [
            {"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)
        ]
        tips = _analyze_patterns(log, workflow_mode="")
        assert any("agent" in t.lower() for t in tips)

    def test_read_stall_suppressed_in_planning(self):
        """Research paralysis pattern is expected during planning."""
        log = [
            {"tool": "Read", "error": False, "file": f"/src/f{i}.py", "ts": i}
            for i in range(10)
        ]
        tips = _analyze_patterns(log, workflow_mode="plan")
        assert not any("read" in t.lower() and "write" in t.lower() for t in tips)

    def test_long_sequence_suppressed_in_execute(self):
        """Long sequence without user check-in is expected during execution."""
        log = [
            {"tool": "Edit", "error": False, "file": f"/src/f{i}.py", "ts": i}
            for i in range(35)
        ]
        tips = _analyze_patterns(log, workflow_mode="execute")
        assert not any("user check-in" in t.lower() for t in tips)


class TestPositiveFeedback:
    def test_read_before_edit_streak(self):
        """Consistent read-before-edit pattern gets positive feedback."""
        log = []
        for i in range(12):
            log.append({"tool": "Read", "error": False, "file": f"/src/file{i}.py", "ts": i * 2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/file{i}.py", "ts": i * 2 + 1})
        tips = _analyze_patterns(log)
        assert any("read-before-edit" in t.lower() or "✓" in t for t in tips)

    def test_no_positive_if_negative_present(self):
        """Don't mix positive and negative — negative takes priority."""
        log = []
        for i in range(6):
            log.append({"tool": "Read", "error": False, "file": f"/src/file{i}.py", "ts": i * 2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/file{i}.py", "ts": i * 2 + 1})
        # Then 3 blind edits in a DIFFERENT directory (never read)
        for i in range(3):
            log.append({"tool": "Edit", "error": False, "file": f"/other/dir/new{i}.py", "ts": 20 + i})
        tips = _analyze_patterns(log)
        assert not any("✓" in t for t in tips)

    def test_zero_error_streak(self):
        """Long streak with zero errors gets positive feedback."""
        log = [
            {"tool": "Bash", "error": False, "file": "", "ts": i}
            for i in range(20)
        ]
        tips = _analyze_patterns(log)
        assert any("clean" in t.lower() or "✓" in t for t in tips)

    def test_no_positive_when_errors_present(self):
        """No positive feedback if there are errors."""
        log = [{"tool": "Bash", "error": False, "file": "", "ts": i} for i in range(15)]
        log.append({"tool": "Bash", "error": True, "file": "", "ts": 16})
        log.append({"tool": "Bash", "error": True, "file": "", "ts": 17})
        log.append({"tool": "Bash", "error": True, "file": "", "ts": 18})
        tips = _analyze_patterns(log)
        # Should have error warning, not positive feedback
        assert not any("✓" in t for t in tips)


class TestActionableMetrics:
    def test_efficiency_read_heavy(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        for i in range(10):
            tt.record("Read", f"/src/file{i}.py")
        for i in range(5):
            tt.record("Edit", f"/src/file{i}.py")
        m = tt.get_efficiency()
        assert m["context_efficiency"] == 1.0  # 10:5 = 2:1, capped at 1.0

    def test_efficiency_write_heavy(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        for i in range(2):
            tt.record("Read", f"/src/file{i}.py")
        for i in range(10):
            tt.record("Edit", f"/src/file{i}.py")
        m = tt.get_efficiency()
        assert m["context_efficiency"] < 0.5  # 2:10 = 0.2 ratio

    def test_success_rate(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        for i in range(8):
            tt.record("Bash", "", error=False)
        for i in range(2):
            tt.record("Bash", "", error=True)
        m = tt.get_efficiency()
        assert m["success_rate"] == 0.8

    def test_focus_score(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        for i in range(25):
            tt.record("Read", f"/project/src/auth/file{i % 3}.py")
        m = tt.get_efficiency()
        assert m["focus"] >= 0.7  # All in same area = high focus

    def test_empty_tracker(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        m = tt.get_efficiency()
        assert m == {}


class TestExistingPatterns:
    """Ensure existing patterns still work."""

    def test_grep_counts_as_read_context(self):
        """Grep/Glob provide read context too."""
        log = [
            {"tool": "Grep", "error": False, "file": "/project/src/auth.py", "ts": 1},
            {"tool": "Glob", "error": False, "file": "/project/src/models.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/project/src/models.py", "ts": 4},
            {"tool": "Edit", "error": False, "file": "/project/src/auth.py", "ts": 5},
        ]
        tips = _analyze_patterns(log)
        assert not any("blind" in t.lower() for t in tips)
