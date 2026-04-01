"""Tests for notification — findings collection + formatting.

Pattern analysis is tested in test_patterns.py.
This file tests _collect_findings integration and output formatting.
"""

from soma.hooks.notification import _collect_findings


class TestCollectFindings:
    """Test _collect_findings with current level names."""

    _MINIMAL_CONFIG = {
        "quality": False, "predict": False,
        "task_tracking": False, "fingerprint": False,
    }

    def test_warn_level_produces_status_finding(self):
        findings = _collect_findings([], {}, 0.55, "WARN", 50, self._MINIMAL_CONFIG)
        status = [m for _, m in findings if "p=" in m and "status" in m.lower() or "55%" in m]
        assert len(status) >= 1

    def test_block_level_produces_status_finding(self):
        findings = _collect_findings([], {}, 0.80, "BLOCK", 100, self._MINIMAL_CONFIG)
        status = [m for _, m in findings if "blocked" in m.lower() or "p=" in m]
        assert len(status) >= 1

    def test_observe_no_status_finding(self):
        findings = _collect_findings([], {}, 0.10, "OBSERVE", 20, self._MINIMAL_CONFIG)
        status = [m for _, m in findings if "WARN" in m or "BLOCK" in m]
        assert len(status) == 0

    def test_guide_no_status_finding(self):
        findings = _collect_findings([], {}, 0.30, "GUIDE", 30, self._MINIMAL_CONFIG)
        status = [m for _, m in findings if "WARN" in m or "BLOCK" in m]
        assert len(status) == 0

    def test_patterns_integrated(self):
        """Pattern results from core module appear in findings."""
        log = [
            {"tool": "Edit", "error": False, "file": f"/x/f{i}.py", "ts": i}
            for i in range(5)
        ]
        findings = _collect_findings(log, {}, 0.30, "GUIDE", 30, self._MINIMAL_CONFIG)
        pattern_msgs = [m for _, m in findings if "pattern" in m.lower() or "blind" in m.lower()]
        assert len(pattern_msgs) >= 1  # blind edits detected

    def test_positive_pattern_in_findings(self):
        """Positive feedback from core module appears in findings."""
        log = []
        for i in range(5):
            log.append({"tool": "Read", "error": False, "file": f"/src/f{i}.py", "ts": i * 2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/f{i}.py", "ts": i * 2 + 1})
        findings = _collect_findings(log, {}, 0.05, "OBSERVE", 50, self._MINIMAL_CONFIG)
        positive = [m for _, m in findings if "✓" in m]
        assert len(positive) >= 1

    def test_positive_format_uses_checkmark(self):
        """Positive findings use [✓] prefix."""
        log = []
        for i in range(5):
            log.append({"tool": "Read", "error": False, "file": f"/src/f{i}.py", "ts": i * 2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/f{i}.py", "ts": i * 2 + 1})
        findings = _collect_findings(log, {}, 0.05, "OBSERVE", 50, self._MINIMAL_CONFIG)
        positive = [m for _, m in findings if "✓" in m]
        assert all(m.startswith("[✓]") for m in positive)

    def test_negative_format_reports_data(self):
        """Negative findings report pattern data, not instructions."""
        log = [
            {"tool": "Edit", "error": False, "file": f"/other/f{i}.py", "ts": i}
            for i in range(5)
        ]
        findings = _collect_findings(log, {}, 0.30, "GUIDE", 30, self._MINIMAL_CONFIG)
        data_msgs = [m for _, m in findings if "pattern=" in m or "blind" in m.lower()]
        assert len(data_msgs) >= 1


class TestActionableMetrics:
    def test_efficiency_read_heavy(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        for i in range(10):
            tt.record("Read", f"/src/file{i}.py")
        for i in range(5):
            tt.record("Edit", f"/src/file{i}.py")
        m = tt.get_efficiency()
        assert m["context_efficiency"] == 1.0

    def test_efficiency_write_heavy(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        for i in range(2):
            tt.record("Read", f"/src/file{i}.py")
        for i in range(10):
            tt.record("Edit", f"/src/file{i}.py")
        m = tt.get_efficiency()
        assert m["context_efficiency"] < 0.5

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
        assert m["focus"] >= 0.7

    def test_empty_tracker(self):
        from soma.task_tracker import TaskTracker
        tt = TaskTracker()
        m = tt.get_efficiency()
        assert m == {}
