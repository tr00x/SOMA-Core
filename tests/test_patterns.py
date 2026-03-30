"""Tests for soma/patterns.py — core pattern analysis."""

from soma.patterns import analyze, PatternResult


class TestBlindEdits:
    def test_detected(self):
        log = [
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/src/b.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/src/c.py", "ts": 3},
        ]
        results = analyze(log)
        assert any(r.kind == "blind_edits" for r in results)

    def test_not_detected_after_read(self):
        log = [
            {"tool": "Read", "error": False, "file": "/src/a.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 4},
        ]
        results = analyze(log)
        assert not any(r.kind == "blind_edits" for r in results)

    def test_directory_read_covers_files(self):
        log = [
            {"tool": "Read", "error": False, "file": "/src/auth/login.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/src/auth/middleware.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/src/auth/types.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/src/auth/login.py", "ts": 4},
        ]
        results = analyze(log)
        assert not any(r.kind == "blind_edits" for r in results)

    def test_grep_provides_context(self):
        log = [
            {"tool": "Grep", "error": False, "file": "/src/a.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 3},
            {"tool": "Edit", "error": False, "file": "/src/a.py", "ts": 4},
        ]
        results = analyze(log)
        assert not any(r.kind == "blind_edits" for r in results)


class TestBashFailures:
    def test_detected(self):
        log = [
            {"tool": "Bash", "error": True, "file": "", "ts": 1},
            {"tool": "Bash", "error": True, "file": "", "ts": 2},
        ]
        results = analyze(log)
        assert any(r.kind == "bash_failures" for r in results)

    def test_not_detected_if_one(self):
        log = [{"tool": "Bash", "error": True, "file": "", "ts": 1}]
        results = analyze(log)
        assert not any(r.kind == "bash_failures" for r in results)


class TestErrorRate:
    def test_detected(self):
        log = [{"tool": "Read", "error": False, "file": "", "ts": i} for i in range(3)]
        log += [{"tool": "Bash", "error": True, "file": "", "ts": i + 3} for i in range(4)]
        results = analyze(log)
        assert any(r.kind == "error_rate" for r in results)


class TestThrashing:
    def test_detected(self):
        log = [{"tool": "Edit", "error": False, "file": "/foo/bar.py", "ts": i} for i in range(4)]
        results = analyze(log)
        assert any(r.kind == "thrashing" for r in results)
        assert "bar.py" in [r for r in results if r.kind == "thrashing"][0].action


class TestWorkflowSuppression:
    def test_agent_spam_suppressed_in_plan(self):
        log = [{"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)]
        results = analyze(log, workflow_mode="plan")
        assert not any(r.kind == "agent_spam" for r in results)

    def test_agent_spam_shown_in_default(self):
        log = [{"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)]
        results = analyze(log, workflow_mode="")
        assert any(r.kind == "agent_spam" for r in results)

    def test_research_stall_suppressed_in_discuss(self):
        log = [{"tool": "Read", "error": False, "file": f"/f{i}.py", "ts": i} for i in range(10)]
        results = analyze(log, workflow_mode="discuss")
        assert not any(r.kind == "research_stall" for r in results)

    def test_no_checkin_suppressed_in_execute(self):
        log = [{"tool": "Edit", "error": False, "file": f"/f{i}.py", "ts": i} for i in range(35)]
        results = analyze(log, workflow_mode="execute")
        assert not any(r.kind == "no_checkin" for r in results)


class TestPositivePatterns:
    def test_read_edit_streak(self):
        log = []
        for i in range(5):
            log.append({"tool": "Read", "error": False, "file": f"/src/f{i}.py", "ts": i * 2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/f{i}.py", "ts": i * 2 + 1})
        results = analyze(log)
        assert any(r.kind == "good_read_edit" and r.severity == "positive" for r in results)

    def test_clean_streak(self):
        log = [{"tool": "Bash", "error": False, "file": "", "ts": i} for i in range(12)]
        results = analyze(log)
        assert any(r.kind == "good_clean_streak" and r.severity == "positive" for r in results)

    def test_no_positive_when_negative_present(self):
        log = [
            {"tool": "Edit", "error": False, "file": f"/other/dir/f{i}.py", "ts": i}
            for i in range(5)
        ]
        results = analyze(log)
        assert not any(r.severity == "positive" for r in results)


class TestStructure:
    def test_empty_log(self):
        assert analyze([]) == []

    def test_max_3_results(self):
        log = [
            {"tool": "Bash", "error": True, "file": "", "ts": 1},
            {"tool": "Bash", "error": True, "file": "", "ts": 2},
            {"tool": "Write", "error": False, "file": "/x/y.py", "ts": 3},
            {"tool": "Write", "error": False, "file": "/x/y.py", "ts": 4},
            {"tool": "Write", "error": False, "file": "/x/y.py", "ts": 5},
        ]
        results = analyze(log)
        assert len(results) <= 3

    def test_result_is_pattern_result(self):
        log = [{"tool": "Bash", "error": True, "file": "", "ts": i} for i in range(3)]
        results = analyze(log)
        for r in results:
            assert isinstance(r, PatternResult)
            assert r.kind
            assert r.severity in ("positive", "info", "warning", "critical")
            assert r.action
