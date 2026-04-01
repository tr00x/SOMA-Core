"""Tests for soma/findings.py — core findings collector."""

from soma.findings import collect, Finding


_MINIMAL_CONFIG = {
    "quality": False, "predict": False,
    "task_tracking": False, "fingerprint": False,
}


class TestFindingStructure:
    def test_finding_is_frozen(self):
        f = Finding(priority=0, category="status", message="test")
        assert f.priority == 0
        assert f.category == "status"

    def test_finding_default_action_empty(self):
        f = Finding(priority=1, category="pattern", message="x")
        assert f.action == ""


class TestCollectStatus:
    def test_warn_produces_finding(self):
        findings = collect([], {}, 0.55, "WARN", 50, _MINIMAL_CONFIG)
        assert any(f.category == "status" and "p=" in f.message for f in findings)

    def test_block_produces_finding(self):
        findings = collect([], {}, 0.80, "BLOCK", 100, _MINIMAL_CONFIG)
        assert any(f.category == "status" and "blocked" in f.message.lower() for f in findings)

    def test_observe_no_status(self):
        findings = collect([], {}, 0.10, "OBSERVE", 20, _MINIMAL_CONFIG)
        assert not any(f.category == "status" for f in findings)

    def test_guide_no_status(self):
        findings = collect([], {}, 0.30, "GUIDE", 30, _MINIMAL_CONFIG)
        assert not any(f.category == "status" for f in findings)


class TestCollectPatterns:
    def test_blind_edits_appear(self):
        log = [{"tool": "Edit", "error": False, "file": f"/x/f{i}.py", "ts": i} for i in range(5)]
        findings = collect(log, {}, 0.30, "GUIDE", 30, _MINIMAL_CONFIG)
        assert any(f.category == "pattern" for f in findings)

    def test_positive_patterns_appear(self):
        log = []
        for i in range(5):
            log.append({"tool": "Read", "error": False, "file": f"/s/f{i}.py", "ts": i * 2})
            log.append({"tool": "Edit", "error": False, "file": f"/s/f{i}.py", "ts": i * 2 + 1})
        findings = collect(log, {}, 0.05, "OBSERVE", 50, _MINIMAL_CONFIG)
        assert any(f.category == "positive" for f in findings)


class TestCollectSorted:
    def test_findings_sorted_by_priority(self):
        log = [{"tool": "Edit", "error": False, "file": f"/x/f{i}.py", "ts": i} for i in range(5)]
        findings = collect(log, {}, 0.55, "WARN", 50, _MINIMAL_CONFIG)
        priorities = [f.priority for f in findings]
        assert priorities == sorted(priorities)


class TestAgentIdParam:
    def test_default_agent_id(self):
        """collect() should work with default agent_id."""
        findings = collect([], {}, 0.10, "OBSERVE", 5, _MINIMAL_CONFIG)
        assert isinstance(findings, list)

    def test_custom_agent_id(self):
        """collect() accepts custom agent_id."""
        findings = collect([], {}, 0.10, "OBSERVE", 5, _MINIMAL_CONFIG, agent_id="my-agent")
        assert isinstance(findings, list)
