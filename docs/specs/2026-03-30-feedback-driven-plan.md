# SOMA Feedback-Driven Improvements Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SOMA smarter, less noisy, and more useful. Based on real feedback from a Claude agent using SOMA in production.

**Source:** Feedback from Claude working on a GSD project — SOMA is active and visible, patterns useful but noisy, no positive feedback, pressure metric uninformative.

**Architecture:** notification.py gets read-context tracking (eliminates "edit without read" false positives), severity levels based on workflow context, positive reinforcement system, and actionable metrics replacing raw pressure display. task_tracker.py gets workflow mode awareness. New positive_feedback module tracks good patterns.

**Tech Stack:** Python 3.11+, pytest, existing SOMA infrastructure.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/soma/hooks/notification.py` | Read-context tracking, severity levels, positive feedback, actionable metrics |
| Modify | `src/soma/hooks/post_tool_use.py` | Track read targets for context awareness |
| Modify | `src/soma/hooks/common.py` | Read context store, workflow mode detection |
| Modify | `src/soma/task_tracker.py` | Workflow mode field, positive pattern tracking |
| Modify | `src/soma/hooks/statusline.py` | Show actionable metrics instead of raw pressure |
| Modify | `tests/test_claude_code_layer.py` | Tests for new features |
| Create | `tests/test_notification.py` | Focused tests for notification improvements |

---

## Chunk 1: Read-Context Awareness (0.4.5)

**Problem:** "5 edits without a Read" fires when agent read a template/file recently and is filling it in. SOMA doesn't track what was read — it just counts sequential edits.

### Task 1: Track read targets in action log

**Files:**
- Modify: `src/soma/hooks/post_tool_use.py`
- Modify: `src/soma/hooks/common.py`

The action log already has `file` field. We need to track which files were Read recently so notification.py can check "was this file (or its directory) read before editing?"

- [ ] **Step 1: Write failing test**

```python
# tests/test_notification.py (new file)
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

    def test_edit_without_read_warns(self):
        """Editing files never Read SHOULD warn."""
        log = [
            {"tool": "Edit", "error": False, "file": "/project/src/new.py", "ts": 1},
            {"tool": "Edit", "error": False, "file": "/project/src/other.py", "ts": 2},
            {"tool": "Edit", "error": False, "file": "/project/src/third.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert any("edit" in t.lower() for t in tips)

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
        assert not any("edit" in t.lower() and "without" in t.lower() for t in tips)

    def test_write_new_file_no_warning(self):
        """Write (creating new files) should never trigger 'edit without read'."""
        log = [
            {"tool": "Write", "error": False, "file": "/project/new_file.py", "ts": 1},
            {"tool": "Write", "error": False, "file": "/project/another.py", "ts": 2},
            {"tool": "Write", "error": False, "file": "/project/third.py", "ts": 3},
        ]
        tips = _analyze_patterns(log)
        assert not any("edit" in t.lower() and "without" in t.lower() for t in tips)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_notification.py -xvs`
Expected: First test fails — current code doesn't check if file was recently read

- [ ] **Step 3: Rewrite _analyze_patterns Pattern 1 with read-context**

Replace the "edits without Reads" check with a smarter version:

```python
# Pattern 1: Blind edits — editing files without reading them first
# Check the FULL log (not just recent) for reads of edited files
edits_without_read = 0
blind_files: list[str] = []

# Build set of recently-read files and directories (from full log, last 30)
read_context = set()
read_dirs = set()
for entry in action_log[-30:]:
    if entry["tool"] in ("Read", "Grep", "Glob"):
        f = entry.get("file", "")
        if f:
            read_context.add(f)
            # Also add the parent directory
            if "/" in f:
                read_dirs.add(f.rsplit("/", 1)[0])

for entry in reversed(recent):
    if entry["tool"] in ("Edit", "NotebookEdit"):
        f = entry.get("file", "")
        if not f:
            continue
        # Check if this file or its directory was read
        if f in read_context:
            continue
        parent = f.rsplit("/", 1)[0] if "/" in f else ""
        if parent and parent in read_dirs:
            continue
        edits_without_read += 1
        blind_files.append(f.rsplit("/", 1)[-1])
    elif entry["tool"] == "Read":
        break  # Stop at most recent Read

if edits_without_read >= 3:
    files_hint = f" ({', '.join(dict.fromkeys(blind_files[:3]))})" if blind_files else ""
    tips.append(
        f"[pattern] {edits_without_read} blind edits{files_hint} — "
        f"Read the target file first to understand current state"
    )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_notification.py -xvs`
Expected: ALL PASS

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x --tb=short`

- [ ] **Step 6: Commit**

```bash
git add src/soma/hooks/notification.py tests/test_notification.py
git commit -m "feat: read-context awareness — no false positives for edits after reads"
```

### Task 2: Version bump to 0.4.5

- [ ] **Step 1: Bump version, CHANGELOG, commit**
- [ ] **Step 2: Reinstall globally**

---

## Chunk 2: Severity Levels & Workflow Mode (0.4.6)

**Problem:** All warnings have same weight. "Scope drift" during plan-phase = noise. Same warning during /gsd:fast = real problem.

### Task 3: Detect workflow mode from environment

**Files:**
- Modify: `src/soma/hooks/common.py`
- Modify: `src/soma/hooks/notification.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_notification.py, add:
class TestWorkflowSeverity:
    def test_agent_spam_suppressed_in_planning(self):
        """Agent spawns during planning workflows should not warn."""
        log = [
            {"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)
        ]
        tips = _analyze_patterns(log, workflow_mode="plan")
        assert not any("agent" in t.lower() for t in tips)

    def test_agent_spam_warns_in_fast_mode(self):
        """Agent spawns during /gsd:fast should still warn."""
        log = [
            {"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)
        ]
        tips = _analyze_patterns(log, workflow_mode="fast")
        assert any("agent" in t.lower() for t in tips)

    def test_scope_drift_suppressed_in_planning(self):
        """Scope drift warning is noise during plan-phase."""
        # This is tested at the _collect_findings level
        pass
```

- [ ] **Step 2: Add workflow_mode parameter to _analyze_patterns**

```python
def _analyze_patterns(action_log: list[dict], workflow_mode: str = "") -> list[str]:
```

Workflow modes detected from environment:
- `""` — unknown/default, all warnings active
- `"plan"` — planning phase (suppress scope drift, agent spam)
- `"execute"` — execution phase (all warnings active)
- `"fast"` — quick task (heighten scope drift sensitivity)
- `"discuss"` — discussion (suppress most warnings)

- [ ] **Step 3: Add workflow mode detection to common.py**

```python
def detect_workflow_mode() -> str:
    """Detect current GSD workflow mode from .planning/ state."""
    import os
    cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
    planning_dir = os.path.join(cwd, ".planning")
    if not os.path.isdir(planning_dir):
        return ""
    # Check STATE.md for current phase status
    state_path = os.path.join(planning_dir, "STATE.md")
    if not os.path.exists(state_path):
        return ""
    try:
        with open(state_path) as f:
            content = f.read(500)  # Only read first 500 chars
        if "executing" in content.lower():
            return "execute"
        if "planning" in content.lower() or "discussing" in content.lower():
            return "plan"
    except Exception:
        pass
    return ""
```

- [ ] **Step 4: Apply severity modifiers in notification.py**

In `_collect_findings`, apply workflow-based suppression:

```python
workflow_mode = detect_workflow_mode()

# Suppress scope drift during planning
if workflow_mode == "plan":
    findings = [(p, m) for p, m in findings if "[scope]" not in m or p == 0]

# Suppress agent spam during planning
if workflow_mode in ("plan", "discuss"):
    findings = [(p, m) for p, m in findings if "Agent" not in m or p == 0]
```

- [ ] **Step 5: Pass workflow_mode to _analyze_patterns**

In _analyze_patterns, skip agent spam warning when `workflow_mode == "plan"`:

```python
# Pattern 5: Agent/subagent spam
if workflow_mode not in ("plan", "discuss"):
    agent_calls = sum(1 for e in recent if e["tool"] == "Agent")
    if agent_calls >= 3:
        tips.append(...)
```

- [ ] **Step 6: Run tests, commit**

```bash
git commit -m "feat: workflow-aware severity — suppress noise during planning"
```

### Task 4: Version bump to 0.4.6

---

## Chunk 3: Positive Feedback (0.4.7)

**Problem:** SOMA only warns. Agent doesn't know which patterns are working well. Positive reinforcement helps models maintain good habits.

### Task 5: Track positive patterns in task_tracker

**Files:**
- Modify: `src/soma/task_tracker.py`
- Modify: `src/soma/hooks/notification.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_notification.py, add:
class TestPositiveFeedback:
    def test_read_before_edit_streak(self):
        """Consistent read-before-edit pattern gets positive feedback."""
        log = []
        for i in range(12):
            log.append({"tool": "Read", "error": False, "file": f"/src/file{i}.py", "ts": i*2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/file{i}.py", "ts": i*2+1})
        tips = _analyze_patterns(log)
        assert any("good" in t.lower() or "✓" in t for t in tips)

    def test_no_positive_feedback_if_negative_present(self):
        """Don't mix positive and negative — negative takes priority."""
        log = []
        # Good pattern followed by bad
        for i in range(6):
            log.append({"tool": "Read", "error": False, "file": f"/src/file{i}.py", "ts": i*2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/file{i}.py", "ts": i*2+1})
        # Then 3 blind edits
        for i in range(3):
            log.append({"tool": "Edit", "error": False, "file": f"/src/new{i}.py", "ts": 20+i})
        tips = _analyze_patterns(log)
        # Should have the negative warning, not positive
        assert not any("good" in t.lower() for t in tips)

    def test_zero_error_streak(self):
        """Long streak with zero errors gets positive feedback."""
        log = [
            {"tool": "Bash", "error": False, "file": "", "ts": i}
            for i in range(20)
        ]
        tips = _analyze_patterns(log)
        assert any("good" in t.lower() or "✓" in t for t in tips)
```

- [ ] **Step 2: Implement positive pattern detection in _analyze_patterns**

Add at the END of `_analyze_patterns`, BEFORE `return tips[:3]`:

```python
# ── Positive feedback (only if no negative tips) ──
if not tips:
    # Check for read-before-edit streak
    read_edit_pairs = 0
    read_files = set()
    for entry in action_log[-20:]:
        if entry["tool"] in ("Read", "Grep"):
            f = entry.get("file", "")
            if f:
                read_files.add(f)
        elif entry["tool"] in ("Edit", "Write") and entry.get("file", "") in read_files:
            read_edit_pairs += 1

    if read_edit_pairs >= 5:
        tips.append(f"[✓] read-before-edit maintained ({read_edit_pairs} pairs) — keep it up")

    # Check for zero-error streak
    elif len(action_log) >= 15:
        recent_errors = sum(1 for e in action_log[-15:] if e.get("error"))
        if recent_errors == 0:
            tips.append(f"[✓] clean streak — {len(action_log[-15:])} actions, 0 errors")
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat: positive feedback — reinforce good patterns"
```

### Task 6: Version bump to 0.4.7

---

## Chunk 4: Actionable Metrics (0.4.8)

**Problem:** `p=0%` is displayed 95% of the time and means nothing. The status line and notification should show metrics the agent can act on.

### Task 7: Replace raw pressure with actionable metrics in status line

**Files:**
- Modify: `src/soma/hooks/statusline.py`
- Modify: `src/soma/hooks/notification.py`
- Modify: `src/soma/task_tracker.py`

- [ ] **Step 1: Add context_efficiency to task_tracker**

```python
# In TaskTracker, add:
def get_efficiency(self) -> dict[str, float]:
    """Compute actionable metrics from action history."""
    if not self._all_tools:
        return {}

    total = len(self._all_tools)
    metrics = {}

    # Read-to-write ratio: how much reading before writing
    reads = sum(1 for t in self._all_tools if t in ("Read", "Grep", "Glob"))
    writes = sum(1 for t in self._all_tools if t in ("Write", "Edit"))
    if writes > 0:
        # Ideal ratio is ~2:1 reads:writes. Below 1:1 is "shooting blind"
        ratio = reads / writes
        metrics["context_efficiency"] = min(ratio / 2.0, 1.0)

    # Error-free rate
    errors = sum(1 for e in self._all_errors if e)
    metrics["success_rate"] = 1.0 - (errors / total) if total > 0 else 1.0

    # Focus score (inverse of scope drift)
    ctx = self.get_context()
    metrics["focus"] = 1.0 - ctx.scope_drift

    return metrics
```

- [ ] **Step 2: Update status line to show actionable metrics**

Replace `_vitals_compact` output with actionable labels when pressure is low:

```python
def _metrics_display(vitals: dict, actions: int, pressure: float) -> str:
    """Show actionable metrics when healthy, vital signals when stressed."""
    if pressure >= 0.25:
        # Stressed — show what's driving pressure
        return _vitals_compact(vitals, actions)

    # Healthy — show actionable metrics
    try:
        from soma.hooks.common import get_task_tracker
        tracker = get_task_tracker()
        m = tracker.get_efficiency()
        parts = []
        if "context_efficiency" in m:
            pct = int(m["context_efficiency"] * 100)
            label = "high" if pct >= 70 else "mid" if pct >= 40 else "low"
            parts.append(f"ctx:{label}")
        if "focus" in m:
            label = "high" if m["focus"] >= 0.7 else "mid" if m["focus"] >= 0.4 else "drift"
            parts.append(f"focus:{label}")
        if parts:
            return " ".join(parts)
    except Exception:
        pass
    return _vitals_compact(vitals, actions)
```

- [ ] **Step 3: Update notification header line**

Replace `SOMA: p=0% #3 [u=0.17 d=0.04 e=0.01]` with:

```python
# At low pressure, show actionable metrics instead of raw vitals
if pressure < 0.25:
    try:
        from soma.hooks.common import get_task_tracker
        tracker = get_task_tracker()
        m = tracker.get_efficiency()
        ctx_pct = int(m.get("context_efficiency", 0) * 100)
        focus_label = "focused" if m.get("focus", 1) >= 0.7 else "drifting" if m.get("focus", 1) < 0.4 else "ok"
        lines.append(f"SOMA: #{actions} ctx={ctx_pct}% focus={focus_label}")
    except Exception:
        lines.append(f"SOMA: p={pressure:.0%} #{actions} [u={u:.2f} d={d:.2f} e={e:.2f}]")
else:
    lines.append(f"SOMA: p={pressure:.0%} #{actions} [u={u:.2f} d={d:.2f} e={e:.2f}]")
```

- [ ] **Step 4: Write tests**

```python
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
```

- [ ] **Step 5: Run full suite, commit**

```bash
git commit -m "feat: actionable metrics — context efficiency and focus replace raw pressure"
```

### Task 8: Version bump to 0.4.8, global reinstall

- [ ] **Step 1: Bump, changelog, commit**
- [ ] **Step 2: Reinstall globally**

```bash
uv tool install --force soma-ai --from /Users/timur/projectos/SOMA
```

- [ ] **Step 3: Verify with doctor**

```bash
soma doctor
```
