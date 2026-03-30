# SOMA 0.4.x Improvement Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden SOMA core, fix remaining inconsistencies, improve test coverage on critical paths, and make the notification system genuinely useful for real agent work.

**Version:** All changes within 0.4.9 (single release, no micro-bumps).

**Source:** Post-implementation audit of 0.4.1-0.4.8 changes + coverage analysis.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/soma/guidance.py` | Deduplicate with notification, thresholds in docstring |
| Modify | `src/soma/hooks/notification.py` | Positive findings as priority 2, verbosity respect |
| Modify | `src/soma/hooks/statusline.py` | Actionable metrics guard, warming-up state |
| Modify | `src/soma/engine.py` | Pass thresholds to pressure_to_mode consistently |
| Modify | `src/soma/cli/config_loader.py` | DEFAULT_THRESHOLDS sync with guidance.py |
| Modify | `tests/test_guidance.py` | Test threshold propagation through engine |
| Modify | `tests/test_notification.py` | Test _collect_findings with new level names |
| Modify | `tests/test_claude_code_layer.py` | Test actionable metrics in statusline |

---

## Chunk 1: Consistency & Correctness

### Task 1: Sync threshold defaults everywhere

**Problem:** `DEFAULT_THRESHOLDS` in guidance.py is `{guide: 0.25, warn: 0.50, block: 0.75}` but `CLAUDE_CODE_CONFIG` in config_loader.py uses `{guide: 0.40, warn: 0.60, block: 0.80}`. The engine gets `custom_thresholds` from config, but `pressure_to_mode` uses its own `DEFAULT_THRESHOLDS` as fallback. These should be the same conceptual defaults.

**Files:**
- Modify: `src/soma/guidance.py`

- [ ] **Step 1: Update guidance.py docstring to reflect configurable thresholds**

The module docstring says fixed ranges (0-25%, 25-50%, etc). These are now configurable. Update docstring:

```python
"""SOMA Guidance Engine — the decision point.

Response modes (defaults — configurable via soma.toml):
    OBSERVE  (below guide):  Silent. Metrics only.
    GUIDE    (guide-warn):   Soft suggestions. Never blocks.
    WARN     (warn-block):   Insistent warnings. Never blocks.
    BLOCK    (above block):  Blocks ONLY destructive operations.
"""
```

- [ ] **Step 2: Commit**

### Task 2: Test _collect_findings with current level names

**Problem:** We fixed the stale level names in _collect_findings, but there's no test verifying WARN/BLOCK findings actually appear.

**Files:**
- Modify: `tests/test_notification.py`

- [ ] **Step 1: Add tests for _collect_findings**

```python
from soma.hooks.notification import _collect_findings

class TestCollectFindings:
    def test_warn_level_produces_status_finding(self):
        findings = _collect_findings([], {}, 0.55, "WARN", 50, {"quality": False, "predict": False, "task_tracking": False, "fingerprint": False})
        status_findings = [m for _, m in findings if "[status]" in m]
        assert len(status_findings) == 1
        assert "WARN" in status_findings[0]

    def test_block_level_produces_status_finding(self):
        findings = _collect_findings([], {}, 0.80, "BLOCK", 100, {"quality": False, "predict": False, "task_tracking": False, "fingerprint": False})
        status_findings = [m for _, m in findings if "[status]" in m]
        assert len(status_findings) == 1
        assert "BLOCK" in status_findings[0]

    def test_observe_no_status_finding(self):
        findings = _collect_findings([], {}, 0.10, "OBSERVE", 20, {"quality": False, "predict": False, "task_tracking": False, "fingerprint": False})
        status_findings = [m for _, m in findings if "[status]" in m]
        assert len(status_findings) == 0

    def test_guide_no_status_finding(self):
        findings = _collect_findings([], {}, 0.30, "GUIDE", 30, {"quality": False, "predict": False, "task_tracking": False, "fingerprint": False})
        status_findings = [m for _, m in findings if "[status]" in m]
        assert len(status_findings) == 0
```

- [ ] **Step 2: Run tests, commit**

### Task 3: Positive findings respect verbosity

**Problem:** Positive feedback `[✓]` is added to patterns (priority 1) and shows in normal verbosity. But at p<0.25 with no critical findings, notification returns early (line 355). So positive feedback would need p>=0.25 to show — but at that pressure, there ARE usually negative findings. Net result: positive feedback almost never shown.

**Fix:** Move the early return check AFTER pattern collection, so positive findings still get collected. Then: if ONLY positive findings, show them even at low pressure.

**Files:**
- Modify: `src/soma/hooks/notification.py`

- [ ] **Step 1: Write failing test**

```python
class TestPositiveFeedbackVisible:
    def test_positive_feedback_shown_at_low_pressure(self):
        """Positive feedback should be visible even at low pressure."""
        from unittest.mock import patch
        import soma.hooks.notification as notif

        # Simulate: low pressure, lots of good read-before-edit pairs
        log = []
        for i in range(12):
            log.append({"tool": "Read", "error": False, "file": f"/src/f{i}.py", "ts": i*2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/f{i}.py", "ts": i*2+1})

        findings = _collect_findings(
            log, {}, 0.05, "OBSERVE", 50,
            {"quality": False, "predict": False, "task_tracking": False, "fingerprint": False}
        )
        positive = [m for _, m in findings if "✓" in m]
        assert len(positive) >= 1
```

- [ ] **Step 2: Fix the early-return logic in main()**

Move the `p<0.25 and not has_critical` check to also allow positive findings through. Adjust: if findings contain ONLY positive (`[✓]`) items, don't suppress.

```python
# In OBSERVE mode with low pressure, only show if critical or positive findings
if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.25:
    has_positive = any("[✓]" in m for _, m in findings)
    if not has_critical and not has_positive:
        return
```

- [ ] **Step 3: Run tests, commit**

### Task 4: Statusline actionable metrics guard

**Problem:** Status line calls `_metrics_display` which calls `get_task_tracker()` without cwd. Tracker data may be stale or empty. Should have same `actions >= 10` guard.

**Files:**
- Modify: `src/soma/hooks/statusline.py`

- [ ] **Step 1: Add guard in _metrics_display**

```python
def _metrics_display(vitals: dict, actions: int, pressure: float) -> str:
    if pressure >= 0.25 or actions < 10:
        return _vitals_compact(vitals, actions)
    # ... rest unchanged
```

- [ ] **Step 2: Commit**

---

## Chunk 2: Test Coverage for Critical Paths

### Task 5: Test engine threshold propagation

**Problem:** engine.py passes `self._custom_thresholds` to `pressure_to_mode()`. If thresholds are `None` (no config), defaults kick in. If thresholds have old keys (caution/degrade), migration didn't happen. Need tests.

**Files:**
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Add threshold propagation tests**

```python
class TestEngineThresholds:
    def test_custom_thresholds_affect_mode(self):
        """Engine with custom thresholds should use them for mode transitions."""
        from soma.engine import SOMAEngine
        from soma.types import Action, ResponseMode

        # Very high block threshold — nothing should reach BLOCK
        engine = SOMAEngine(custom_thresholds={"guide": 0.90, "warn": 0.95, "block": 0.99})
        engine.register_agent("test")

        # Record many error actions to push pressure up
        for i in range(20):
            action = Action(tool_name="Bash", output_text="error", error=True,
                          token_count=100, cost=0.01, duration_sec=1.0)
            result = engine.record_action("test", action)

        # With default thresholds this would be WARN or BLOCK
        # With custom high thresholds it should still be OBSERVE or GUIDE
        snap = engine.get_snapshot("test")
        assert snap["mode"] in (ResponseMode.OBSERVE, ResponseMode.GUIDE)

    def test_none_thresholds_use_defaults(self):
        """Engine with no custom thresholds uses guidance.py defaults."""
        from soma.engine import SOMAEngine
        from soma.guidance import DEFAULT_THRESHOLDS

        engine = SOMAEngine(custom_thresholds=None)
        engine.register_agent("test")
        # Just verify it doesn't crash
        snap = engine.get_snapshot("test")
        assert snap["mode"] == ResponseMode.OBSERVE
```

- [ ] **Step 2: Run tests, commit**

### Task 6: Test config migration end-to-end

**Problem:** migrate_config is tested in isolation, but not through load_config → engine flow.

**Files:**
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add end-to-end migration test**

```python
class TestMigrationEndToEnd:
    def test_load_config_with_old_keys_returns_new(self, tmp_path):
        """load_config auto-migrates old threshold keys."""
        import tomli_w
        old_config = {
            "thresholds": {"caution": 0.35, "degrade": 0.55, "quarantine": 0.75, "restart": 0.90},
            "budget": {"tokens": 100000},
        }
        path = str(tmp_path / "soma.toml")
        with open(path, "wb") as f:
            tomli_w.dump(old_config, f)

        from soma.cli.config_loader import load_config
        result = load_config(path)
        assert "guide" in result["thresholds"]
        assert "caution" not in result["thresholds"]
        assert "restart" not in result["thresholds"]
        assert result["thresholds"]["guide"] == 0.35

    def test_engine_from_migrated_config(self, tmp_path):
        """Engine created from migrated config uses new threshold keys."""
        import tomli_w
        old_config = {
            "thresholds": {"caution": 0.35, "degrade": 0.55, "quarantine": 0.75, "restart": 0.90},
            "budget": {"tokens": 100000},
        }
        path = str(tmp_path / "soma.toml")
        with open(path, "wb") as f:
            tomli_w.dump(old_config, f)

        from soma.cli.config_loader import load_config, create_engine_from_config
        config = load_config(path)
        engine = create_engine_from_config(config)
        assert engine._custom_thresholds["guide"] == 0.35
```

- [ ] **Step 2: Run tests, commit**

---

## Chunk 3: Version Bump & Reinstall

### Task 7: Bump to 0.4.9, reinstall, verify

- [ ] **Step 1: Bump version in pyproject.toml and __init__.py**
- [ ] **Step 2: Update CHANGELOG.md**
- [ ] **Step 3: Run full suite + ruff**
- [ ] **Step 4: Commit**
- [ ] **Step 5: Reinstall globally**

```bash
uv tool install --force soma-ai --from /Users/timur/projectos/SOMA
```

- [ ] **Step 6: Verify with doctor**

```bash
soma doctor
```
