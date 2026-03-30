# SOMA Extract to Core — Layer-Agnostic Intelligence

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move pattern analysis, findings collection, workflow context, and positive feedback from Claude Code hooks into SOMA core. Any future layer (Cursor, Windsurf, OpenCode, custom agents) gets the same intelligence without reimplementing it.

**Problem:** 60% of SOMA's useful intelligence lives in `src/soma/hooks/notification.py` — a Claude Code-specific file. New layers would need to copy-paste or reimplement pattern detection, read-context tracking, workflow severity, positive reinforcement, and actionable metrics.

**Architecture after this plan:**

```
Core (any layer uses):                    Layer (format-specific):
  soma/patterns.py   — pattern detection    hooks/notification.py — Claude Code output format
  soma/findings.py   — finding collection   hooks/statusline.py   — Claude Code status line
  soma/context.py    — workflow + cwd        (future) cursor/...   — Cursor output format
  soma/task_tracker.py — efficiency metrics  (future) opencode/... — OpenCode output format
  soma/guidance.py   — pressure → mode
  soma/engine.py     — the pipeline
```

**Principle:** Core produces structured data (findings list, pattern results, metrics dict). Layers format it for their specific output channel (stderr, stdout, status bar, LSP, etc).

**Version:** 0.4.10 (single release).

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/soma/patterns.py` | Pattern analysis engine — extracted from notification.py |
| Create | `src/soma/findings.py` | Findings collector — extracted from notification.py |
| Create | `src/soma/context.py` | Workflow mode detection + session context |
| Modify | `src/soma/hooks/notification.py` | Thin wrapper: calls core, formats for Claude Code |
| Modify | `src/soma/hooks/statusline.py` | Uses core metrics, formats for Claude Code |
| Modify | `src/soma/hooks/common.py` | Remove detect_workflow_mode (moved to context.py) |
| Modify | `tests/test_notification.py` | Tests point at core modules |
| Create | `tests/test_patterns.py` | Focused tests for pattern engine |
| Create | `tests/test_findings.py` | Focused tests for findings collector |

---

## Chunk 1: Extract Pattern Analysis (soma/patterns.py)

### Task 1: Create soma/patterns.py from notification.py

**Extract:** `_analyze_patterns()` becomes the public `analyze()` function in a new core module.

**Files:**
- Create: `src/soma/patterns.py`
- Modify: `src/soma/hooks/notification.py`
- Create: `tests/test_patterns.py`

- [ ] **Step 1: Create soma/patterns.py**

Extract `_analyze_patterns` logic into a structured core module. Return structured data, not formatted strings:

```python
"""SOMA Pattern Analysis — detect behavioral patterns in agent action logs.

Core module: layer-agnostic. Returns structured PatternResult objects.
Layers format these for their specific output channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PatternResult:
    """A detected behavioral pattern."""
    kind: str           # "blind_edits", "bash_failures", "error_rate", "thrashing",
                        # "agent_spam", "research_stall", "no_checkin",
                        # "good_read_edit", "good_clean_streak"
    severity: str       # "positive", "info", "warning", "critical"
    action: str         # What the agent should DO: "Read before editing"
    detail: str         # Context: "3 edits to files you haven't read"
    data: dict = field(default_factory=dict)  # Machine-readable: {"count": 3, "files": [...]}


def analyze(
    action_log: list[dict],
    workflow_mode: str = "",
) -> list[PatternResult]:
    """Analyze action log for behavioral patterns.

    Args:
        action_log: List of action dicts with keys: tool, error, file, ts
        workflow_mode: "" (default), "plan", "execute", "discuss", "fast"

    Returns:
        List of PatternResult, max 3, sorted by severity (critical first).
    """
    if not action_log:
        return []

    results: list[PatternResult] = []
    recent = action_log[-10:]

    # ── Pattern 1: Blind edits ──
    # [existing _analyze_patterns Pattern 1 logic, returns PatternResult]

    # ── Pattern 2: Consecutive Bash failures ──
    # [existing logic]

    # ── Pattern 3: High error rate ──
    # [existing logic]

    # ── Pattern 4: File thrashing ──
    # [existing logic]

    # ── Pattern 5: Agent spam (suppressed in plan/discuss) ──
    # [existing logic]

    # ── Pattern 6: Research stall (suppressed in plan/discuss) ──
    # [existing logic]

    # ── Pattern 7: No user check-in (suppressed in execute/plan) ──
    # [existing logic]

    # ── Positive patterns (only if no negative) ──
    # [existing logic]

    return results[:3]
```

- [ ] **Step 2: Write tests/test_patterns.py**

Test the core module directly with structured PatternResult:

```python
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

class TestWorkflowSuppression:
    def test_agent_spam_suppressed_in_plan(self):
        log = [{"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)]
        results = analyze(log, workflow_mode="plan")
        assert not any(r.kind == "agent_spam" for r in results)

class TestPositivePatterns:
    def test_read_edit_streak(self):
        log = []
        for i in range(12):
            log.append({"tool": "Read", "error": False, "file": f"/src/f{i}.py", "ts": i*2})
            log.append({"tool": "Edit", "error": False, "file": f"/src/f{i}.py", "ts": i*2+1})
        results = analyze(log)
        assert any(r.kind == "good_read_edit" and r.severity == "positive" for r in results)

    def test_clean_streak(self):
        log = [{"tool": "Bash", "error": False, "file": "", "ts": i} for i in range(20)]
        results = analyze(log)
        assert any(r.kind == "good_clean_streak" and r.severity == "positive" for r in results)
```

- [ ] **Step 3: Move logic from notification.py _analyze_patterns into patterns.py**

Keep the full logic. Each pattern creates a `PatternResult` instead of a formatted string.

- [ ] **Step 4: Update notification.py to use patterns.py**

```python
from soma.patterns import analyze as analyze_patterns

# In _collect_findings:
pattern_results = analyze_patterns(action_log, workflow_mode=workflow_mode)
for pr in pattern_results:
    if pr.severity == "positive":
        findings.append((2, f"[✓] {pr.action} ({pr.detail})"))
    else:
        findings.append((1, f"[do] {pr.action} — {pr.detail}"))
```

`_analyze_patterns` in notification.py becomes a thin formatter that calls `patterns.analyze()`.

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -x --tb=short`

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor: extract pattern analysis to soma/patterns.py (core)"
```

---

## Chunk 2: Extract Findings Collection (soma/findings.py)

### Task 2: Create soma/findings.py from notification.py

**Extract:** `_collect_findings()` becomes `collect()` in core. Returns structured data. Layer formats.

**Files:**
- Create: `src/soma/findings.py`
- Modify: `src/soma/hooks/notification.py`
- Create: `tests/test_findings.py`

- [ ] **Step 1: Create soma/findings.py**

```python
"""SOMA Findings Collector — gather all monitoring insights.

Core module: layer-agnostic. Collects pattern results, quality info,
predictions, scope drift, fingerprint divergence, and RCA into a
structured findings list.

Layers call collect() and format the results for their output channel.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """A single monitoring finding."""
    priority: int       # 0=critical (always show), 1=important, 2=informational
    category: str       # "status", "quality", "predict", "pattern", "scope",
                        # "fingerprint", "rca", "positive"
    message: str        # Human-readable message
    action: str = ""    # What to do about it (empty = informational only)


def collect(
    action_log: list[dict],
    vitals: dict,
    pressure: float,
    level_name: str,
    actions: int,
    hook_config: dict,
) -> list[Finding]:
    """Collect all monitoring findings.

    Returns sorted list of Finding objects (critical first).
    """
    findings: list[Finding] = []

    # Level status
    if level_name == "WARN":
        findings.append(Finding(
            priority=0, category="status",
            message=f"Pressure elevated (p={pressure:.0%})",
            action="Slow down. Read→Think→Act, not Act→Fix→Retry",
        ))
    elif level_name == "BLOCK":
        findings.append(Finding(
            priority=0, category="status",
            message=f"Destructive ops blocked (p={pressure:.0%})",
            action="Normal Read/Write/Edit/Bash/Agent still allowed",
        ))

    # Quality
    # [extracted from _collect_findings]

    # Prediction
    # [extracted from _collect_findings]

    # Patterns (via soma.patterns.analyze)
    # [extracted]

    # Scope drift
    # [extracted]

    # Fingerprint
    # [extracted]

    # RCA
    # [extracted]

    findings.sort(key=lambda f: f.priority)
    return findings
```

- [ ] **Step 2: Write tests/test_findings.py**

```python
from soma.findings import collect, Finding

class TestFindings:
    _MIN_CONFIG = {"quality": False, "predict": False, "task_tracking": False, "fingerprint": False}

    def test_warn_finding(self):
        results = collect([], {}, 0.55, "WARN", 50, self._MIN_CONFIG)
        assert any(f.category == "status" and "WARN" in f.message.upper() for f in results if f.priority == 0)

    def test_observe_no_status(self):
        results = collect([], {}, 0.10, "OBSERVE", 20, self._MIN_CONFIG)
        assert not any(f.category == "status" for f in results)

    def test_patterns_included(self):
        log = [{"tool": "Edit", "error": False, "file": f"/x/{i}.py", "ts": i} for i in range(5)]
        results = collect(log, {}, 0.30, "GUIDE", 30, self._MIN_CONFIG)
        pattern_findings = [f for f in results if f.category == "pattern"]
        # May or may not have patterns depending on log content
        assert isinstance(pattern_findings, list)
```

- [ ] **Step 3: Move _collect_findings logic into findings.py**

- [ ] **Step 4: Update notification.py**

```python
from soma.findings import collect as collect_findings, Finding

# In main():
findings = collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)

# Format for Claude Code output:
for f in findings:
    if f.category == "positive":
        lines.append(f"[✓] {f.message}")
    elif f.action:
        lines.append(f"[do] {f.action} — {f.message}")
    elif f.category == "status":
        if f.priority == 0 and level_name == "WARN":
            lines.append(f"[⚡ WARN] {f.action}")
        elif f.priority == 0 and level_name == "BLOCK":
            lines.append(f"[🚨 BLOCK] {f.action}")
    else:
        lines.append(f"[{f.category}] {f.message}")
```

- [ ] **Step 5: Run tests, commit**

```bash
git commit -m "refactor: extract findings collection to soma/findings.py (core)"
```

---

## Chunk 3: Extract Context (soma/context.py)

### Task 3: Create soma/context.py

**Extract:** `detect_workflow_mode()` from common.py + session context builder.

**Files:**
- Create: `src/soma/context.py`
- Modify: `src/soma/hooks/common.py`
- Modify: `src/soma/hooks/notification.py`

- [ ] **Step 1: Create soma/context.py**

```python
"""SOMA Context — session and workflow awareness.

Core module: provides structured context about the agent's working environment.
Used by patterns, findings, and layers for context-aware behavior.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    """Current session context."""
    cwd: str                    # Working directory
    workflow_mode: str          # "", "plan", "execute", "discuss", "fast"
    gsd_active: bool            # .planning/ directory exists
    action_count: int           # Total actions in session
    pressure: float             # Current pressure level


def detect_workflow_mode(cwd: str = "") -> str:
    """Detect GSD workflow mode from .planning/STATE.md.

    Returns: "" (default), "plan", "execute", "discuss", "fast"
    """
    if not cwd:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", "")
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            return ""
    planning_dir = os.path.join(cwd, ".planning")
    if not os.path.isdir(planning_dir):
        return ""
    state_path = os.path.join(planning_dir, "STATE.md")
    if not os.path.exists(state_path):
        return ""
    try:
        with open(state_path) as f:
            content = f.read(500)
        lower = content.lower()
        if "executing" in lower:
            return "execute"
        if "planning" in lower or "discussing" in lower:
            return "plan"
    except Exception:
        pass
    return ""


def get_session_context(
    cwd: str = "",
    action_count: int = 0,
    pressure: float = 0.0,
) -> SessionContext:
    """Build current session context."""
    if not cwd:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", "")
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            cwd = ""

    gsd_active = bool(cwd) and os.path.isdir(os.path.join(cwd, ".planning"))
    workflow_mode = detect_workflow_mode(cwd) if gsd_active else ""

    return SessionContext(
        cwd=cwd,
        workflow_mode=workflow_mode,
        gsd_active=gsd_active,
        action_count=action_count,
        pressure=pressure,
    )
```

- [ ] **Step 2: Update common.py — delegate to context.py**

```python
# Replace detect_workflow_mode in common.py with:
def detect_workflow_mode() -> str:
    from soma.context import detect_workflow_mode as _detect
    return _detect()
```

This keeps backward compat for any code importing from common.py.

- [ ] **Step 3: Update patterns.py and findings.py to accept SessionContext**

```python
# patterns.py
from soma.context import SessionContext

def analyze(action_log: list[dict], ctx: SessionContext | None = None) -> list[PatternResult]:
    workflow_mode = ctx.workflow_mode if ctx else ""
    # ... rest unchanged
```

- [ ] **Step 4: Run tests, commit**

```bash
git commit -m "refactor: extract workflow/session context to soma/context.py (core)"
```

---

## Chunk 4: Slim Down notification.py

### Task 4: notification.py becomes pure formatter

After chunks 1-3, notification.py should be ~80 lines: import core, format for Claude Code.

**Files:**
- Modify: `src/soma/hooks/notification.py`

- [ ] **Step 1: Rewrite notification.py as thin layer**

```python
"""SOMA Notification — Claude Code output formatter.

Thin layer: calls core (patterns, findings, context), formats for
Claude Code's UserPromptSubmit hook (stdout injection).
"""

from __future__ import annotations
import time


def _format_finding(f) -> str:
    """Format a Finding for Claude Code output."""
    from soma.findings import Finding
    if f.category == "positive":
        return f"[✓] {f.message}"
    if f.category == "status":
        if "WARN" in f.message.upper():
            return f"[⚡ WARN] {f.action}"
        if "BLOCK" in f.message.upper():
            return f"[🚨 BLOCK] {f.action}"
    if f.action:
        return f"[do] {f.action} — {f.message}"
    return f"[{f.category}] {f.message}"


def main():
    try:
        from soma.hooks.common import get_engine, read_action_log, get_hook_config
        from soma.findings import collect as collect_findings
        from soma.context import get_session_context

        engine, agent_id = get_engine()
        if engine is None:
            return

        snap = engine.get_snapshot(agent_id)
        level_name = snap["level"].name if hasattr(snap["level"], "name") else str(snap["level"])
        pressure = snap["pressure"]
        actions = snap["action_count"]
        vitals = snap.get("vitals", {})

        hook_config = get_hook_config()
        verbosity = hook_config.get("verbosity", "normal")
        action_log = read_action_log()

        # Stale session cleanup
        # [keep existing logic]

        # Skip at very low pressure
        if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.10:
            return

        # Collect findings (core)
        findings = collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)

        # Check if worth showing
        has_critical = any(f.priority == 0 for f in findings)
        has_positive = any(f.category == "positive" for f in findings)
        if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.25:
            if not has_critical and not has_positive:
                return

        # Build header
        ctx = get_session_context(action_count=actions, pressure=pressure)
        phase_str = ""
        # [phase + metrics header logic]

        # Format findings for Claude Code
        lines = [header_line]
        for f in findings:
            if verbosity == "minimal" and f.priority > 0:
                continue
            if verbosity == "normal" and f.priority > 1:
                continue
            lines.append(_format_finding(f))
            if len(lines) > 4:
                break

        print("\n".join(lines))

    except Exception:
        pass
```

- [ ] **Step 2: Verify notification.py < 100 lines**

- [ ] **Step 3: Run all tests**

Existing tests may need to import from `soma.patterns` or `soma.findings` instead of `soma.hooks.notification`. Update imports.

- [ ] **Step 4: Run full suite + ruff**

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor: notification.py is now a thin Claude Code formatter"
```

---

## Chunk 5: Version Bump & Verify

### Task 5: Bump to 0.4.10, reinstall, verify

- [ ] **Step 1: Bump version**
- [ ] **Step 2: Update CHANGELOG**

```markdown
## [0.4.10] — 2026-03-xx

### Changed
- Pattern analysis extracted to `soma/patterns.py` (core) — reusable by any layer
- Findings collection extracted to `soma/findings.py` (core) — structured Finding objects
- Workflow/session context extracted to `soma/context.py` (core) — SessionContext dataclass
- `notification.py` is now a thin Claude Code formatter (~80 lines)
- New layers get pattern detection, severity, positive feedback for free

### Added
- `PatternResult` dataclass — structured, machine-readable pattern output
- `Finding` dataclass — structured, prioritized finding output
- `SessionContext` dataclass — workflow mode, cwd, gsd_active
- `patterns.analyze()` — public API for pattern detection
- `findings.collect()` — public API for finding collection
- `context.get_session_context()` — public API for session awareness
```

- [ ] **Step 3: Commit, reinstall, verify**

```bash
uv tool install --force soma-ai --from /Users/timur/projectos/SOMA
soma doctor
```

---

## What This Enables

After this refactor, building a new layer (e.g., for Cursor) looks like:

```python
from soma.engine import SOMAEngine
from soma.patterns import analyze
from soma.findings import collect
from soma.context import get_session_context

# Get data
ctx = get_session_context()
findings = collect(action_log, vitals, pressure, level_name, actions, config)

# Format for Cursor's output (LSP diagnostic? sidebar? inline hint?)
for f in findings:
    cursor_show(f.priority, f.message, f.action)
```

No copy-paste from Claude Code hooks. Intelligence lives in core.
