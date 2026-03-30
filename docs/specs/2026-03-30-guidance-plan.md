# SOMA Guidance Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SOMA's blocking escalation system with a gradient guidance system that only blocks destructive operations at extreme pressure.

**Architecture:** New `guidance.py` module becomes the single decision point. `ResponseMode` enum replaces `Level`. Ladder class is deleted. Engine returns pressure + mode instead of level. All hooks call `guidance.evaluate()`.

**Tech Stack:** Python 3.11+, pytest, existing SOMA infrastructure (pressure/vitals/baseline unchanged).

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/soma/types.py` | Replace `Level` with `ResponseMode`, keep `Level` as deprecated alias |
| Create | `src/soma/guidance.py` | Central decision engine: pressure + context → GuidanceResponse |
| Delete | `src/soma/ladder.py` | Replaced by `guidance.pressure_to_mode()` |
| Rewrite | `src/soma/hooks/pre_tool_use.py` | Single call to `guidance.evaluate()` |
| Modify | `src/soma/hooks/notification.py` | Use ResponseMode for message tone |
| Modify | `src/soma/hooks/statusline.py` | New mode names/emojis |
| Modify | `src/soma/engine.py` | Remove Ladder, return ResponseMode in ActionResult |
| Modify | `src/soma/persistence.py` | Save/restore mode instead of level |
| Modify | `src/soma/hooks/common.py` | Remove SAFE_TOOLS references from get_engine |
| Modify | `src/soma/learning.py` | Adapt to ResponseMode (keep weight learning, drop threshold learning) |
| Modify | `src/soma/context_control.py` | Mode-based context control |
| Modify | `src/soma/wrap.py` | New API with ResponseMode |
| Modify | `src/soma/testing.py` | New API with ResponseMode |
| Modify | `src/soma/hooks/post_tool_use.py` | Update level references to mode |
| Modify | `src/soma/cli/tabs/*.py` | Update all 5 tabs for new modes |
| Modify | `src/soma/cli/replay_cli.py` | Update level colors/labels |
| Modify | `src/soma/commands.py` | Update CLI commands |
| Rewrite | `tests/test_ladder.py` → `tests/test_guidance.py` | Test new guidance module |
| Modify | `tests/test_*.py` | Update all test references |

---

## Chunk 1: Core Types & Guidance Module

### Task 1: Add ResponseMode to types.py, keep Level as deprecated alias

**Files:**
- Modify: `src/soma/types.py:10-38`
- Test: `tests/test_types.py`

- [ ] **Step 1: Write failing test for ResponseMode**

```python
# tests/test_types.py — add at top
from soma.types import ResponseMode

def test_response_mode_ordering():
    assert ResponseMode.OBSERVE.value == 0
    assert ResponseMode.GUIDE.value == 1
    assert ResponseMode.WARN.value == 2
    assert ResponseMode.BLOCK.value == 3

def test_response_mode_comparison():
    assert ResponseMode.OBSERVE < ResponseMode.BLOCK
    assert ResponseMode.WARN >= ResponseMode.GUIDE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest tests/test_types.py::test_response_mode_ordering -xvs`
Expected: ImportError — ResponseMode not defined

- [ ] **Step 3: Add ResponseMode enum and GuidanceResponse to types.py**

Replace the `Level` enum block (lines 10-37) with:

```python
class ResponseMode(Enum):
    """Guidance response modes — ordered by severity."""
    OBSERVE = 0   # p=0-25%: silent, metrics only
    GUIDE = 1     # p=25-50%: soft suggestions
    WARN = 2      # p=50-75%: insistent warnings
    BLOCK = 3     # p=75-100%: block destructive ops only

    def __lt__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: ResponseMode) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self.value >= other.value


# Deprecated alias — will be removed in 0.5.0
Level = ResponseMode
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest tests/test_types.py -xvs`
Expected: ALL PASS (old Level tests still work via alias)

- [ ] **Step 5: Commit**

```bash
git add src/soma/types.py tests/test_types.py
git commit -m "feat: add ResponseMode enum, alias Level for backward compat"
```

### Task 2: Create guidance.py — the decision engine

**Files:**
- Create: `src/soma/guidance.py`
- Create: `tests/test_guidance.py`

- [ ] **Step 1: Write failing tests for guidance module**

```python
# tests/test_guidance.py
import pytest
from soma.guidance import (
    GuidanceResponse, pressure_to_mode, evaluate,
    is_destructive_bash, is_sensitive_file,
)
from soma.types import ResponseMode


class TestPressureToMode:
    def test_observe(self):
        assert pressure_to_mode(0.0) == ResponseMode.OBSERVE
        assert pressure_to_mode(0.24) == ResponseMode.OBSERVE

    def test_guide(self):
        assert pressure_to_mode(0.25) == ResponseMode.GUIDE
        assert pressure_to_mode(0.49) == ResponseMode.GUIDE

    def test_warn(self):
        assert pressure_to_mode(0.50) == ResponseMode.WARN
        assert pressure_to_mode(0.74) == ResponseMode.WARN

    def test_block(self):
        assert pressure_to_mode(0.75) == ResponseMode.BLOCK
        assert pressure_to_mode(1.0) == ResponseMode.BLOCK


class TestIsDestructiveBash:
    def test_rm_rf(self):
        assert is_destructive_bash("rm -rf /tmp/foo")
        assert is_destructive_bash("rm -r ./build")
        assert is_destructive_bash("rm --recursive --force .")

    def test_git_destructive(self):
        assert is_destructive_bash("git reset --hard")
        assert is_destructive_bash("git push --force origin main")
        assert is_destructive_bash("git push -f")
        assert is_destructive_bash("git clean -f")
        assert is_destructive_bash("git checkout .")

    def test_chmod_kill(self):
        assert is_destructive_bash("chmod 777 /etc/passwd")
        assert is_destructive_bash("kill -9 1234")

    def test_safe_commands(self):
        assert not is_destructive_bash("ls -la")
        assert not is_destructive_bash("git status")
        assert not is_destructive_bash("git push origin main")
        assert not is_destructive_bash("rm file.txt")  # single file ok
        assert not is_destructive_bash("python -m pytest")
        assert not is_destructive_bash("git log --oneline")


class TestIsSensitiveFile:
    def test_env_files(self):
        assert is_sensitive_file(".env")
        assert is_sensitive_file("/app/.env.local")
        assert is_sensitive_file(".env.production")

    def test_credentials(self):
        assert is_sensitive_file("credentials.json")
        assert is_sensitive_file("/home/user/credentials")

    def test_keys(self):
        assert is_sensitive_file("server.pem")
        assert is_sensitive_file("private.key")

    def test_secrets(self):
        assert is_sensitive_file("secret.yaml")
        assert is_sensitive_file("/app/secrets/db.json")

    def test_normal_files(self):
        assert not is_sensitive_file("main.py")
        assert not is_sensitive_file("README.md")
        assert not is_sensitive_file("package.json")


class TestEvaluate:
    def test_observe_mode_silent(self):
        r = evaluate(pressure=0.10, tool_name="Write", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.OBSERVE
        assert r.allow is True
        assert r.message is None

    def test_guide_mode_allows_everything(self):
        r = evaluate(pressure=0.30, tool_name="Bash", tool_input={"command": "rm -rf /"}, action_log=[])
        assert r.mode == ResponseMode.GUIDE
        assert r.allow is True  # guide never blocks

    def test_warn_mode_allows_everything(self):
        r = evaluate(pressure=0.60, tool_name="Agent", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.WARN
        assert r.allow is True

    def test_block_mode_blocks_destructive_bash(self):
        r = evaluate(pressure=0.80, tool_name="Bash", tool_input={"command": "rm -rf /"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is False
        assert r.message is not None

    def test_block_mode_allows_normal_bash(self):
        r = evaluate(pressure=0.80, tool_name="Bash", tool_input={"command": "ls -la"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_block_mode_blocks_sensitive_write(self):
        r = evaluate(pressure=0.80, tool_name="Write",
                     tool_input={"file_path": "/app/.env"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is False

    def test_block_mode_allows_normal_write(self):
        r = evaluate(pressure=0.80, tool_name="Write",
                     tool_input={"file_path": "/app/main.py"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_block_mode_allows_agent(self):
        r = evaluate(pressure=0.80, tool_name="Agent", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True  # Agent never blocked

    def test_block_mode_allows_read(self):
        r = evaluate(pressure=0.99, tool_name="Read", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_gsd_context_reduces_drift(self):
        """When GSD is active, evaluate still works (context awareness)."""
        r = evaluate(pressure=0.30, tool_name="Agent", tool_input={},
                     action_log=[], gsd_active=True)
        assert r.mode == ResponseMode.GUIDE
        assert r.allow is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest tests/test_guidance.py -xvs`
Expected: ImportError — guidance module not found

- [ ] **Step 3: Implement guidance.py**

```python
# src/soma/guidance.py
"""SOMA Guidance Engine — the decision point.

Replaces the old Ladder-based blocking system with gradient response.
SOMA observes, suggests, warns — and only blocks truly destructive operations.

Response modes:
    OBSERVE  (p=0-25%):  Silent. Metrics only.
    GUIDE    (p=25-50%): Soft suggestions when patterns detected. Never blocks.
    WARN     (p=50-75%): Insistent warnings + alternatives. Never blocks.
    BLOCK    (p=75-100%): Blocks ONLY destructive operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from soma.types import ResponseMode


@dataclass(frozen=True, slots=True)
class GuidanceResponse:
    """Result of a guidance evaluation."""
    mode: ResponseMode
    allow: bool
    message: str | None = None
    suggestions: list[str] = field(default_factory=list)


# --- Destructive operation detection ---

DESTRUCTIVE_BASH_PATTERNS = [
    re.compile(r"\brm\s+.*-[rf]*r[rf]*\b"),           # rm -rf, rm -r, rm -fr
    re.compile(r"\brm\s+--recursive\b"),                # rm --recursive
    re.compile(r"\brm\s+--force\b.*--recursive\b"),     # rm --force --recursive
    re.compile(r"\bgit\s+reset\s+--hard\b"),            # git reset --hard
    re.compile(r"\bgit\s+push\s+.*(-f|--force)\b"),     # git push --force/-f
    re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"),         # git clean -f/-fd
    re.compile(r"\bgit\s+checkout\s+\.\s*$"),            # git checkout .
    re.compile(r"\bchmod\s+777\b"),                      # chmod 777
    re.compile(r"\bkill\s+-9\b"),                        # kill -9
]

SENSITIVE_FILE_PATTERNS = [
    re.compile(r"(^|/)\.env(\.|$)"),                     # .env, .env.local, .env.production
    re.compile(r"(^|/)credentials"),                      # credentials, credentials.json
    re.compile(r"\.pem$"),                                # *.pem
    re.compile(r"\.key$"),                                # *.key
    re.compile(r"(^|/)secret"),                           # secret*, secrets/
]


def is_destructive_bash(command: str) -> bool:
    """Check if a bash command is destructive."""
    return any(p.search(command) for p in DESTRUCTIVE_BASH_PATTERNS)


def is_sensitive_file(file_path: str) -> bool:
    """Check if a file path points to sensitive content."""
    return any(p.search(file_path) for p in SENSITIVE_FILE_PATTERNS)


def pressure_to_mode(pressure: float) -> ResponseMode:
    """Map pressure to response mode. No hysteresis needed."""
    if pressure >= 0.75:
        return ResponseMode.BLOCK
    if pressure >= 0.50:
        return ResponseMode.WARN
    if pressure >= 0.25:
        return ResponseMode.GUIDE
    return ResponseMode.OBSERVE


def _check_destructive(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """Check if this specific tool call is destructive.

    Returns (is_destructive, reason).
    """
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if is_destructive_bash(cmd):
            return True, f"destructive command: {cmd[:80]}"

    if tool_name in ("Write", "Edit", "NotebookEdit"):
        fp = tool_input.get("file_path", "")
        if fp and is_sensitive_file(fp):
            short = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            return True, f"sensitive file: {short}"

    return False, ""


def _build_suggestions(tool_name: str, action_log: list[dict]) -> list[str]:
    """Build context-aware suggestions based on action patterns."""
    suggestions: list[str] = []
    if not action_log:
        return suggestions

    recent = action_log[-10:]

    # File thrashing
    if tool_name in ("Write", "Edit"):
        edit_files = [e["file"] for e in recent if e["tool"] in ("Write", "Edit") and e.get("file")]
        if edit_files:
            from collections import Counter
            counts = Counter(edit_files)
            for fname, count in counts.most_common(1):
                if count >= 3:
                    short = fname.rsplit("/", 1)[-1] if "/" in fname else fname
                    suggestions.append(f"you've edited {short} {count}x — consider collecting all changes first")

    # Consecutive bash failures
    consecutive_failures = 0
    for entry in reversed(recent):
        if entry["tool"] == "Bash" and entry.get("error"):
            consecutive_failures += 1
        elif entry["tool"] == "Bash":
            break
    if consecutive_failures >= 2:
        suggestions.append(f"{consecutive_failures} bash failures in a row — check assumptions before retrying")

    # Many agents
    agent_calls = sum(1 for e in recent if e["tool"] == "Agent")
    if agent_calls >= 3:
        suggestions.append(f"{agent_calls} agents spawned recently — check for file conflicts")

    return suggestions


def evaluate(
    pressure: float,
    tool_name: str,
    tool_input: dict,
    action_log: list[dict],
    gsd_active: bool = False,
) -> GuidanceResponse:
    """Central guidance decision.

    Args:
        pressure: Current aggregate pressure (0.0 - 1.0)
        tool_name: Tool being called
        tool_input: Tool parameters (command, file_path, etc)
        action_log: Recent action history
        gsd_active: Whether GSD workflow is active (.planning/ exists)

    Returns:
        GuidanceResponse with mode, allow decision, and optional message/suggestions.
    """
    mode = pressure_to_mode(pressure)

    # OBSERVE — silent, everything allowed
    if mode == ResponseMode.OBSERVE:
        return GuidanceResponse(mode=mode, allow=True)

    # BLOCK — check destructive ops
    if mode == ResponseMode.BLOCK:
        is_destructive, reason = _check_destructive(tool_name, tool_input)
        if is_destructive:
            return GuidanceResponse(
                mode=mode,
                allow=False,
                message=f"SOMA blocked: {reason} (p={pressure:.0%})",
                suggestions=["pressure is very high — focus on safe, reversible actions"],
            )
        # Not destructive — allow with warning
        suggestions = _build_suggestions(tool_name, action_log)
        return GuidanceResponse(
            mode=mode,
            allow=True,
            message=f"SOMA warning: pressure at {pressure:.0%} — only destructive ops blocked",
            suggestions=suggestions,
        )

    # WARN — insistent warnings, never blocks
    if mode == ResponseMode.WARN:
        suggestions = _build_suggestions(tool_name, action_log)
        msg = None
        if suggestions:
            msg = f"SOMA warning (p={pressure:.0%}): {suggestions[0]}"
        else:
            msg = f"SOMA warning: pressure at {pressure:.0%} — slow down and verify"
        return GuidanceResponse(mode=mode, allow=True, message=msg, suggestions=suggestions)

    # GUIDE — soft suggestions only when patterns detected
    suggestions = _build_suggestions(tool_name, action_log)
    msg = None
    if suggestions:
        msg = f"SOMA suggestion: {suggestions[0]}"
    return GuidanceResponse(mode=mode, allow=True, message=msg, suggestions=suggestions)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest tests/test_guidance.py -xvs`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/soma/guidance.py tests/test_guidance.py
git commit -m "feat: guidance engine — central decision point replacing ladder"
```

---

## Chunk 2: Engine & Hooks Rewrite

### Task 3: Rewrite pre_tool_use.py to use guidance

**Files:**
- Rewrite: `src/soma/hooks/pre_tool_use.py`

- [ ] **Step 1: Rewrite pre_tool_use.py**

Replace entire file content:

```python
"""SOMA PreToolUse hook — guidance-based.

SOMA is a nervous system that GUIDES, not blocks.
Only truly destructive operations are blocked, and only at extreme pressure (75%+).

Exit codes:
    0 — allow tool call (with optional guidance message on stderr)
    2 — block tool call (destructive op at high pressure)
"""

from __future__ import annotations

import os
import sys

from soma.hooks.common import get_engine, read_stdin


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    snap = engine.get_snapshot(agent_id)
    pressure = snap["pressure"]

    data = read_stdin()
    tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", ""))
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    from soma.guidance import evaluate
    from soma.hooks.common import read_action_log

    action_log = read_action_log()

    # Detect GSD context
    gsd_active = False
    try:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
        gsd_active = os.path.isdir(os.path.join(cwd, ".planning"))
    except Exception:
        pass

    response = evaluate(
        pressure=pressure,
        tool_name=tool_name,
        tool_input=tool_input,
        action_log=action_log,
        gsd_active=gsd_active,
    )

    if response.message:
        print(response.message, file=sys.stderr)

    if not response.allow:
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run existing hook tests**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest tests/test_claude_code_layer.py -xvs -k "pre_tool" 2>&1 | head -60`
Expected: Some failures (tests reference old Level-based blocking). That's expected — we'll fix tests in Chunk 3.

- [ ] **Step 3: Commit**

```bash
git add src/soma/hooks/pre_tool_use.py
git commit -m "feat: rewrite pre_tool_use to use guidance engine"
```

### Task 4: Update engine.py — remove Ladder dependency

**Files:**
- Modify: `src/soma/engine.py`

- [ ] **Step 1: Update imports and ActionResult**

In `engine.py`, replace:
```python
from soma.types import Action, Level, AutonomyMode, VitalsSnapshot, AgentConfig, DriftMode
```
with:
```python
from soma.types import Action, ResponseMode, AutonomyMode, VitalsSnapshot, AgentConfig, DriftMode
```

Replace:
```python
from soma.ladder import Ladder
```
with:
```python
from soma.guidance import pressure_to_mode
```

Replace `ActionResult`:
```python
@dataclass(frozen=True, slots=True)
class ActionResult:
    mode: ResponseMode
    pressure: float
    vitals: VitalsSnapshot
    context_action: str = "pass"

    @property
    def level(self) -> ResponseMode:
        """Deprecated alias for mode."""
        return self.mode
```

- [ ] **Step 2: Remove Ladder from _AgentState**

Replace `_AgentState.__init__` — remove `self.ladder = Ladder()`, add `self.mode: ResponseMode = ResponseMode.OBSERVE`:

```python
class _AgentState:
    __slots__ = ("config", "ring_buffer", "baseline", "mode",
                 "known_tools", "baseline_vector", "action_count")

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.ring_buffer: RingBuffer[Action] = RingBuffer(capacity=10)
        self.baseline = Baseline()
        self.mode: ResponseMode = ResponseMode.OBSERVE
        self.known_tools: list[str] = list(config.tools_allowed) if config.tools_allowed else []
        self.baseline_vector: list[float] | None = None
        self.action_count = 0
```

- [ ] **Step 3: Update get_level and get_snapshot**

```python
def get_level(self, agent_id: str) -> ResponseMode:
    """Get current response mode (was: escalation level)."""
    if agent_id not in self._agents:
        raise AgentNotFound(agent_id)
    return self._agents[agent_id].mode

def get_snapshot(self, agent_id: str) -> dict[str, Any]:
    if agent_id not in self._agents:
        raise AgentNotFound(agent_id)
    s = self._agents[agent_id]
    pressure = self._graph.get_effective_pressure(agent_id)
    return {
        "mode": s.mode,
        "level": s.mode,  # backward compat
        "pressure": pressure,
        "vitals": {
            "uncertainty": s.baseline.get("uncertainty"),
            "drift": s.baseline.get("drift"),
            "error_rate": s.baseline.get("error_rate"),
            "cost": s.baseline.get("cost"),
            "token_usage": s.baseline.get("token_usage"),
        },
        "action_count": s.action_count,
        "budget_health": self._budget.health(),
    }
```

- [ ] **Step 4: Update export_state**

Replace `"level": s.ladder.current.name` with `"level": s.mode.name` (line ~146).

- [ ] **Step 5: Update record_action — replace ladder with pressure_to_mode**

Remove the entire ladder evaluation block (lines 349-404). Replace with:

```python
        # 10. Mode (replaces old Ladder evaluation)
        old_mode = s.mode
        new_mode = pressure_to_mode(effective)
        s.mode = new_mode

        # 11. Events + Learning
        if new_mode != old_mode:
            self._events.emit("level_changed", {
                "agent_id": agent_id,
                "old_level": old_mode,
                "new_level": new_mode,
                "pressure": effective,
            })
            self._learning.record_intervention(
                agent_id, old_mode, new_mode, effective, signal_pressures,
            )

        self._learning.evaluate(agent_id, effective, actions_since=1)

        # Context action based on mode
        context_action = "pass"
        if new_mode == ResponseMode.GUIDE:
            context_action = "guide"
        elif new_mode == ResponseMode.WARN:
            context_action = "warn"
        elif new_mode == ResponseMode.BLOCK:
            context_action = "block_destructive"

        result = ActionResult(
            mode=new_mode,
            pressure=effective,
            vitals=VitalsSnapshot(
                uncertainty=uncertainty, drift=drift, drift_mode=drift_mode,
                token_usage=rv.token_usage, cost=rv.cost, error_rate=rv.error_rate,
            ),
            context_action=context_action,
        )
```

- [ ] **Step 6: Update approve_escalation**

```python
def approve_escalation(self, agent_id: str) -> ResponseMode:
    """Human approves pending escalation. Re-evaluates mode."""
    s = self._agents[agent_id]
    snap = self.get_snapshot(agent_id)
    s.mode = pressure_to_mode(snap["pressure"])
    return s.mode
```

- [ ] **Step 7: Run basic engine test**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest tests/test_engine.py -xvs 2>&1 | head -40`
Expected: Some failures due to Level references in tests. We fix those in Chunk 3.

- [ ] **Step 8: Commit**

```bash
git add src/soma/engine.py
git commit -m "feat: engine uses ResponseMode + pressure_to_mode, removes Ladder"
```

### Task 5: Update notification.py for ResponseMode

**Files:**
- Modify: `src/soma/hooks/notification.py`

- [ ] **Step 1: Replace level-based findings with mode-based**

In `_collect_findings`, replace the level status block (lines 153-173) with:

```python
    # Mode status (priority 0 at elevated modes)
    from soma.types import ResponseMode
    try:
        mode = ResponseMode[level_name] if level_name in ResponseMode.__members__ else None
    except (KeyError, ValueError):
        mode = None

    if mode == ResponseMode.WARN:
        findings.append((0,
            "[status] WARN — pressure elevated. Slow down, verify each step"
        ))
    elif mode == ResponseMode.BLOCK:
        findings.append((0,
            "[status] BLOCK — destructive operations blocked. "
            "Normal Write/Edit/Bash/Agent still allowed"
        ))
```

Replace the prediction block that imports `THRESHOLDS` from ladder (lines 192-216):

```python
    if hook_config.get("predict", True):
        try:
            from soma.hooks.common import get_predictor
            predictor = get_predictor()
            if predictor._pressures:
                # Predict next mode boundary
                boundaries = [0.25, 0.50, 0.75]
                next_boundary = next((b for b in boundaries if b > pressure), None)
                if next_boundary:
                    pred = predictor.predict(next_boundary)
                    if pred.will_escalate:
                        reason = pred.dominant_reason
                        advice = {
                            "error_streak": "stop retrying the failing approach, try something different",
                            "blind_writes": "Read the target files before editing",
                            "thrashing": "plan the complete change first, then make one clean edit",
                            "retry_storm": "investigate the root cause instead of retrying",
                            "trend": "pressure is climbing — slow down and verify each step",
                        }.get(reason, "slow down and verify your approach")
                        findings.append((
                            1,
                            f"[predict] escalation in ~{pred.actions_ahead} actions "
                            f"({reason}) — {advice}"
                        ))
        except Exception:
            pass
```

Replace the silence condition (line 299):

```python
        if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.15 and not has_critical and not has_important:
            return
```

- [ ] **Step 2: Commit**

```bash
git add src/soma/hooks/notification.py
git commit -m "feat: notification uses ResponseMode, removes ladder import"
```

### Task 6: Update statusline.py for new modes

**Files:**
- Modify: `src/soma/hooks/statusline.py`

- [ ] **Step 1: Replace LEVEL_STYLE with MODE_STYLE**

```python
MODE_STYLE = {
    "OBSERVE":  ("✦", "observe"),
    "GUIDE":    ("💡", "guide"),
    "WARN":     ("⚡", "warn"),
    "BLOCK":    ("🚨", "block"),
    # Backward compat
    "HEALTHY":  ("✦", "observe"),
    "CAUTION":  ("💡", "guide"),
    "DEGRADE":  ("⚡", "warn"),
    "QUARANTINE": ("🚨", "block"),
    "RESTART":  ("🚨", "block"),
    "SAFE_MODE": ("🚨", "block"),
}
```

Update references from `LEVEL_STYLE` to `MODE_STYLE` in `main()`.

- [ ] **Step 2: Commit**

```bash
git add src/soma/hooks/statusline.py
git commit -m "feat: statusline uses new mode names and emojis"
```

### Task 7: Update persistence.py — save mode instead of ladder

**Files:**
- Modify: `src/soma/persistence.py`

- [ ] **Step 1: Update save_engine_state**

Replace `"level": s.ladder.current.name` (line 33) with `"level": s.mode.name`.

- [ ] **Step 2: Update load_engine_state**

Replace the level restoration block (lines 88-94):

```python
        # Restore mode
        from soma.types import ResponseMode
        level_name = agent_state.get("level", "OBSERVE")
        try:
            s.mode = ResponseMode[level_name]
        except (KeyError, ValueError):
            # Try old Level names
            old_to_new = {
                "HEALTHY": "OBSERVE", "CAUTION": "GUIDE",
                "DEGRADE": "WARN", "QUARANTINE": "BLOCK",
                "RESTART": "BLOCK", "SAFE_MODE": "BLOCK",
            }
            mapped = old_to_new.get(level_name, "OBSERVE")
            s.mode = ResponseMode[mapped]
```

- [ ] **Step 3: Commit**

```bash
git add src/soma/persistence.py
git commit -m "feat: persistence saves ResponseMode, migrates old Level names"
```

### Task 8: Update post_tool_use.py — remove ladder references

**Files:**
- Modify: `src/soma/hooks/post_tool_use.py`

- [ ] **Step 1: Find and replace ladder imports/references**

The post_tool_use.py imports `THRESHOLDS` from ladder for prediction. Replace with mode boundaries (same pattern as notification.py). Also update any `level` references to use `mode`.

Run: `cd /Users/timur/projectos/SOMA && grep -n "ladder\|Level\|level" src/soma/hooks/post_tool_use.py`

Update all references. The key changes:
- Replace `from soma.ladder import THRESHOLDS` with mode boundary list `[0.25, 0.50, 0.75]`
- Replace level name checks with mode name checks
- Replace `result.level` with `result.mode`

- [ ] **Step 2: Commit**

```bash
git add src/soma/hooks/post_tool_use.py
git commit -m "feat: post_tool_use uses ResponseMode, removes ladder import"
```

### Task 9: Update common.py and context_control.py

**Files:**
- Modify: `src/soma/hooks/common.py`
- Modify: `src/soma/context_control.py`

- [ ] **Step 1: Update common.py**

In `get_engine()`, replace `engine.get_level(agent_id)` with same call (it still works, returns ResponseMode now).

In `_inherit_baseline`, remove `from soma.baseline import Baseline` if already imported, and update any ladder references.

- [ ] **Step 2: Update context_control.py**

Replace all `Level.HEALTHY/CAUTION/DEGRADE/QUARANTINE/RESTART/SAFE_MODE` with `ResponseMode.OBSERVE/GUIDE/WARN/BLOCK`:

```python
from soma.types import ResponseMode

def apply_context_control(ctx, mode: ResponseMode):
    if mode == ResponseMode.OBSERVE:
        return ctx  # no changes
    elif mode == ResponseMode.GUIDE:
        # Light context hints
        ...
    elif mode == ResponseMode.WARN:
        # Truncate verbose outputs
        ...
    elif mode == ResponseMode.BLOCK:
        # Minimal context
        ...
```

- [ ] **Step 3: Commit**

```bash
git add src/soma/hooks/common.py src/soma/context_control.py
git commit -m "feat: common.py and context_control use ResponseMode"
```

### Task 10: Update learning.py, wrap.py, testing.py

**Files:**
- Modify: `src/soma/learning.py`
- Modify: `src/soma/wrap.py`
- Modify: `src/soma/testing.py`

- [ ] **Step 1: Update learning.py**

Replace `from soma.types import InterventionOutcome, Level` with `from soma.types import InterventionOutcome, ResponseMode`.

Replace all `Level` references with `ResponseMode`. The `record_intervention` method takes `(old_level, new_level)` — these become `(old_mode, new_mode)` of type `ResponseMode`.

- [ ] **Step 2: Update wrap.py**

Replace `from soma.types import Action, Level` with `from soma.types import Action, ResponseMode`.

Replace `block_at: Level = Level.QUARANTINE` with `block_at: ResponseMode = ResponseMode.BLOCK`.

Update all Level references.

- [ ] **Step 3: Update testing.py**

Replace `Level` with `ResponseMode`. Update `assert_below` to work with ResponseMode values.

- [ ] **Step 4: Commit**

```bash
git add src/soma/learning.py src/soma/wrap.py src/soma/testing.py
git commit -m "feat: learning/wrap/testing use ResponseMode"
```

### Task 11: Delete ladder.py

**Files:**
- Delete: `src/soma/ladder.py`

- [ ] **Step 1: Delete ladder.py**

```bash
git rm src/soma/ladder.py
```

- [ ] **Step 2: Verify no remaining imports**

Run: `cd /Users/timur/projectos/SOMA && grep -r "from soma.ladder" src/`
Expected: No results

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: delete ladder.py — replaced by guidance.py"
```

---

## Chunk 3: CLI & Tests Update

### Task 12: Update CLI tabs

**Files:**
- Modify: `src/soma/cli/tabs/dashboard.py`
- Modify: `src/soma/cli/tabs/agents.py`
- Modify: `src/soma/cli/tabs/config_tab.py`
- Modify: `src/soma/cli/tabs/replay_tab.py`
- Modify: `src/soma/cli/replay_cli.py`
- Modify: `src/soma/commands.py`

- [ ] **Step 1: Update all CLI Level references to ResponseMode**

Each tab file has `Level` imports and color/label mappings. Replace all with:

```python
from soma.types import ResponseMode

MODE_COLORS = {
    ResponseMode.OBSERVE:  "#22c55e",
    ResponseMode.GUIDE:    "#eab308",
    ResponseMode.WARN:     "#f97316",
    ResponseMode.BLOCK:    "#ef4444",
}

MODE_LABELS = {
    ResponseMode.OBSERVE:  "OK",
    ResponseMode.GUIDE:    "GUIDE",
    ResponseMode.WARN:     "WARN",
    ResponseMode.BLOCK:    "BLOCK",
}
```

For `replay_cli.py`:
```python
MODE_COLORS = {
    ResponseMode.OBSERVE: "green",
    ResponseMode.GUIDE:   "yellow",
    ResponseMode.WARN:    "dark_orange",
    ResponseMode.BLOCK:   "red",
}
```

For `config_tab.py`, update the `_level_for_pressure` function:
```python
def _mode_for_pressure(p: float) -> ResponseMode:
    from soma.guidance import pressure_to_mode
    return pressure_to_mode(p)
```

For `commands.py`, update quarantine/release to use ResponseMode.

- [ ] **Step 2: Commit**

```bash
git add src/soma/cli/ src/soma/commands.py
git commit -m "feat: CLI tabs use ResponseMode"
```

### Task 13: Update all tests

**Files:**
- Rename: `tests/test_ladder.py` → `tests/test_guidance.py` (already created in Task 2)
- Modify: `tests/test_engine.py`
- Modify: `tests/test_persistence.py`
- Modify: `tests/test_types.py`
- Modify: `tests/test_wrap.py`
- Modify: `tests/test_testing.py`
- Modify: `tests/test_learning.py`
- Modify: `tests/test_edge_cases.py`
- Modify: `tests/test_stress.py`
- Modify: `tests/test_context_control.py`
- Modify: `tests/test_coverage_gaps.py`
- Modify: `tests/test_claude_code_layer.py`
- Delete: `tests/test_ladder.py`

- [ ] **Step 1: Delete test_ladder.py**

```bash
git rm tests/test_ladder.py
```

- [ ] **Step 2: Update test_engine.py**

Replace all `Level.HEALTHY` → `ResponseMode.OBSERVE`, `Level.CAUTION` → `ResponseMode.GUIDE`, etc.
Replace `r.level` → `r.mode`.
Remove `Level.SAFE_MODE` tests (budget exhaustion now just means BLOCK mode).

- [ ] **Step 3: Update test_persistence.py**

Replace `ladder.force_level(Level.CAUTION)` with `s.mode = ResponseMode.GUIDE`.
Replace `get_level("agent-x") == Level.CAUTION` with `get_level("agent-x") == ResponseMode.GUIDE`.

- [ ] **Step 4: Update test_edge_cases.py**

Replace Level references. SAFE_MODE tests → BLOCK mode tests.
Replace `ladder.force_level(Level.X)` with `s.mode = ResponseMode.X`.

- [ ] **Step 5: Update test_stress.py**

Replace Level references in assertions.

- [ ] **Step 6: Update test_learning.py**

Replace all `Level.HEALTHY/CAUTION/DEGRADE` with `ResponseMode.OBSERVE/GUIDE/WARN`.

- [ ] **Step 7: Update test_wrap.py**

Replace `block_at=Level.QUARANTINE` with `block_at=ResponseMode.BLOCK`.
Replace `ladder.force_level` with direct mode assignment.

- [ ] **Step 8: Update test_context_control.py**

Replace all Level references with ResponseMode.

- [ ] **Step 9: Update test_claude_code_layer.py**

This is the biggest test file. Replace:
- All `ladder.force_level(Level.X)` with `s.mode = ResponseMode.X`
- All Level-based blocking tests with guidance-based tests
- Remove tests for CAUTION "read before write" enforcement
- Add tests for destructive op blocking at BLOCK mode
- Keep tests for notification patterns

- [ ] **Step 10: Update test_coverage_gaps.py and test_testing.py**

Replace Level references.

- [ ] **Step 11: Update test_types.py**

Update Level tests to use ResponseMode. The alias means old tests should still pass, but update them for clarity.

- [ ] **Step 12: Run full test suite**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest -x --tb=short 2>&1 | tail -20`
Expected: ALL PASS

- [ ] **Step 13: Commit**

```bash
git add tests/
git commit -m "test: update all tests for ResponseMode guidance system"
```

---

## Chunk 4: Cleanup & Version Bump

### Task 14: Version bump and cleanup

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/soma/__init__.py` (if version is there)

- [ ] **Step 1: Bump version to 0.4.0**

Find version string and update to 0.4.0.

- [ ] **Step 2: Verify no remaining Level imports (except alias)**

Run: `cd /Users/timur/projectos/SOMA && grep -rn "from soma.ladder" src/ tests/`
Expected: No results

Run: `cd /Users/timur/projectos/SOMA && grep -rn "Level\." src/ tests/ | grep -v "ResponseMode\|Level = ResponseMode\|# Deprecated"`
Expected: Only backward-compat alias usage, no direct Level enum usage

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/timur/projectos/SOMA && python -m pytest --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: bump version to 0.4.0 — guidance system release"
```

### Task 15: Final integration smoke test

- [ ] **Step 1: Test hook pipeline manually**

```bash
cd /Users/timur/projectos/SOMA
# Clear old state
rm -f ~/.soma/engine_state.json ~/.soma/action_log.json

# Test PreToolUse — should allow everything at p=0%
echo '{"tool_name": "Write", "tool_input": {"file_path": "test.py"}}' | \
  CLAUDE_HOOK=PreToolUse python -m soma.hooks.claude_code

# Test statusline
python -m soma.hooks.statusline

# Test notification
python -m soma.hooks.notification
```

- [ ] **Step 2: Verify the pipeline works end-to-end**

Expected:
- PreToolUse: exit code 0 (allow), no blocking
- Statusline: shows `🧠 SOMA ✦ observe ░░░░░░░░░░  0%`
- Notification: silent (pressure < 15%)
