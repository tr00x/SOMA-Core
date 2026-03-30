# SOMA Core Polish Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all hardcoded values from SOMA core, eliminate false positives, make first-run experience bulletproof.

**Architecture:** Mode thresholds, stale timeout, and drift settings move to soma.toml via config_loader.py. guidance.py and notification.py read from config instead of hardcoded constants. task_tracker.py gets smarter scope drift using cwd-relative paths. setup_claude.py becomes idempotent. New `soma doctor` command validates installation.

**Tech Stack:** Python 3.11+, pytest, tomli_w, existing SOMA infrastructure.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/soma/cli/config_loader.py` | Rename threshold keys, add guidance config, config migration |
| Modify | `src/soma/guidance.py` | Read thresholds from config, use gsd_active |
| Modify | `src/soma/hooks/common.py` | Pass config to guidance, load guidance thresholds |
| Modify | `src/soma/hooks/pre_tool_use.py` | Pass thresholds to guidance.evaluate() |
| Modify | `src/soma/hooks/notification.py` | Read stale_timeout from config, skip patterns at low pressure |
| Modify | `src/soma/task_tracker.py` | cwd-relative scope drift |
| Modify | `src/soma/hooks/post_tool_use.py` | Pass cwd to task tracker |
| Modify | `src/soma/cli/setup_claude.py` | Idempotent hook installation |
| Modify | `src/soma/cli/main.py` | Add `soma doctor` command |
| Modify | `soma.toml` | New key names, new guidance section |
| Modify | `tests/test_guidance.py` | Test configurable thresholds |
| Modify | `tests/test_claude_code_layer.py` | Test scope drift, notification silence |
| Create | `.github/workflows/ci.yml` | GitHub Actions CI |

---

## Chunk 1: Configurable Mode Thresholds (0.4.1)

### Task 1: Rename config keys and add migration

**Files:**
- Modify: `src/soma/cli/config_loader.py:15-47` (DEFAULT_CONFIG)
- Modify: `src/soma/cli/config_loader.py:59-106` (CLAUDE_CODE_CONFIG)
- Modify: `src/soma/cli/config_loader.py:109-179` (MODE_PRESETS)
- Test: `tests/test_guidance.py`

- [ ] **Step 1: Write failing test for config migration**

```python
# tests/test_config.py (new file)
from soma.cli.config_loader import migrate_config

class TestConfigMigration:
    def test_old_keys_migrated(self):
        old = {"thresholds": {"caution": 0.40, "degrade": 0.60, "quarantine": 0.80, "restart": 0.95}}
        result = migrate_config(old)
        assert result["thresholds"] == {"guide": 0.40, "warn": 0.60, "block": 0.80}
        assert "caution" not in result["thresholds"]
        assert "restart" not in result["thresholds"]

    def test_new_keys_untouched(self):
        new = {"thresholds": {"guide": 0.30, "warn": 0.55, "block": 0.80}}
        result = migrate_config(new)
        assert result["thresholds"] == {"guide": 0.30, "warn": 0.55, "block": 0.80}

    def test_empty_config(self):
        result = migrate_config({})
        assert "thresholds" not in result  # don't add what wasn't there
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -xvs`
Expected: ImportError — migrate_config not found

- [ ] **Step 3: Implement migrate_config and update config constants**

In `config_loader.py`, add migration function:

```python
_OLD_TO_NEW_THRESHOLDS = {
    "caution": "guide",
    "degrade": "warn",
    "quarantine": "block",
}

def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate old config keys to new names. Returns mutated config."""
    thresholds = config.get("thresholds")
    if thresholds is None:
        return config
    migrated = {}
    for key, val in thresholds.items():
        new_key = _OLD_TO_NEW_THRESHOLDS.get(key, key)
        if key == "restart":
            continue  # restart removed in 0.4.0
        migrated[new_key] = val
    config["thresholds"] = migrated
    return config
```

Update `DEFAULT_CONFIG["thresholds"]`:
```python
"thresholds": {
    "guide": 0.25,
    "warn": 0.50,
    "block": 0.75,
},
```

Update `CLAUDE_CODE_CONFIG["thresholds"]`:
```python
"thresholds": {
    "guide": 0.40,
    "warn": 0.60,
    "block": 0.80,
},
```

Update all 3 `MODE_PRESETS` — same rename pattern.

Remove `"version"` from `CLAUDE_CODE_CONFIG["soma"]`. Add to `DEFAULT_CONFIG["soma"]`:
```python
"soma": {
    "store": "~/.soma/state.json",
},
```

- [ ] **Step 4: Update load_config to auto-migrate**

```python
def load_config(path: str = "soma.toml") -> dict[str, Any]:
    if not os.path.exists(path):
        return DEFAULT_CONFIG.copy()
    with open(path, "rb") as fh:
        config = tomllib.load(fh)
    return migrate_config(config)
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_config.py -xvs`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/soma/cli/config_loader.py tests/test_config.py
git commit -m "feat: rename threshold keys guide/warn/block, add config migration"
```

### Task 2: guidance.py reads thresholds from config

**Files:**
- Modify: `src/soma/guidance.py:61-69`
- Modify: `src/soma/hooks/pre_tool_use.py:33-51`
- Modify: `src/soma/hooks/common.py:120-155`
- Test: `tests/test_guidance.py`

- [ ] **Step 1: Write failing test for configurable thresholds**

```python
# In tests/test_guidance.py, add:
class TestConfigurableThresholds:
    def test_custom_thresholds(self):
        from soma.guidance import pressure_to_mode
        from soma.types import ResponseMode
        # With custom thresholds: GUIDE at 40%, WARN at 60%, BLOCK at 80%
        thresholds = {"guide": 0.40, "warn": 0.60, "block": 0.80}
        assert pressure_to_mode(0.35, thresholds) == ResponseMode.OBSERVE
        assert pressure_to_mode(0.45, thresholds) == ResponseMode.GUIDE
        assert pressure_to_mode(0.65, thresholds) == ResponseMode.WARN
        assert pressure_to_mode(0.85, thresholds) == ResponseMode.BLOCK

    def test_default_thresholds(self):
        from soma.guidance import pressure_to_mode
        from soma.types import ResponseMode
        # Without custom thresholds, use defaults
        assert pressure_to_mode(0.20) == ResponseMode.OBSERVE
        assert pressure_to_mode(0.30) == ResponseMode.GUIDE

    def test_evaluate_with_thresholds(self):
        from soma.guidance import evaluate
        from soma.types import ResponseMode
        thresholds = {"guide": 0.40, "warn": 0.60, "block": 0.80}
        r = evaluate(0.35, "Write", {}, [], thresholds=thresholds)
        assert r.mode == ResponseMode.OBSERVE  # 35% is below custom guide=40%
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_guidance.py::TestConfigurableThresholds -xvs`
Expected: TypeError — pressure_to_mode() got unexpected keyword argument

- [ ] **Step 3: Update pressure_to_mode signature**

```python
# Default thresholds — used when no config provided
DEFAULT_THRESHOLDS = {"guide": 0.25, "warn": 0.50, "block": 0.75}

def pressure_to_mode(
    pressure: float,
    thresholds: dict[str, float] | None = None,
) -> ResponseMode:
    """Map pressure to response mode using configurable thresholds."""
    t = thresholds or DEFAULT_THRESHOLDS
    if pressure >= t.get("block", 0.75):
        return ResponseMode.BLOCK
    if pressure >= t.get("warn", 0.50):
        return ResponseMode.WARN
    if pressure >= t.get("guide", 0.25):
        return ResponseMode.GUIDE
    return ResponseMode.OBSERVE
```

- [ ] **Step 4: Update evaluate() to accept thresholds**

```python
def evaluate(
    pressure: float,
    tool_name: str,
    tool_input: dict,
    action_log: list[dict],
    gsd_active: bool = False,
    thresholds: dict[str, float] | None = None,
) -> GuidanceResponse:
    mode = pressure_to_mode(pressure, thresholds)
    # ... rest unchanged
```

- [ ] **Step 5: Update pre_tool_use.py to pass thresholds from config**

```python
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
    from soma.hooks.common import read_action_log, get_guidance_thresholds

    action_log = read_action_log()
    thresholds = get_guidance_thresholds()

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
        thresholds=thresholds,
    )

    if response.message:
        print(response.message, file=sys.stderr)

    if not response.allow:
        sys.exit(2)
```

- [ ] **Step 6: Add get_guidance_thresholds() to common.py**

```python
def get_guidance_thresholds() -> dict[str, float] | None:
    """Load guidance thresholds from soma.toml config."""
    try:
        from soma.cli.config_loader import load_config
        config = load_config()
        thresholds = config.get("thresholds")
        if thresholds and any(k in thresholds for k in ("guide", "warn", "block")):
            return thresholds
    except Exception:
        pass
    return None
```

- [ ] **Step 7: Update engine.py — pass thresholds to pressure_to_mode**

In `engine.py` `record_action()`, the call to `pressure_to_mode(effective)` needs thresholds:

```python
from soma.guidance import pressure_to_mode
# ... in record_action:
new_mode = pressure_to_mode(effective, self._guidance_thresholds)
```

Add `_guidance_thresholds` to engine init from `custom_thresholds`:
```python
# In __init__:
self._guidance_thresholds = custom_thresholds
```

- [ ] **Step 8: Run full tests**

Run: `.venv/bin/python -m pytest -x --tb=short`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add src/soma/guidance.py src/soma/hooks/pre_tool_use.py src/soma/hooks/common.py src/soma/engine.py tests/test_guidance.py
git commit -m "feat: configurable mode thresholds from soma.toml"
```

### Task 3: Update soma.toml and stale timeout config

**Files:**
- Modify: `soma.toml`
- Modify: `src/soma/hooks/notification.py:285`
- Modify: `src/soma/hooks/common.py`

- [ ] **Step 1: Update soma.toml with new keys**

```toml
[thresholds]
guide = 0.40
warn = 0.60
block = 0.80

[hooks]
# ... existing keys ...
stale_timeout = 1800    # seconds before session data is considered stale
```

- [ ] **Step 2: Read stale_timeout from config in notification.py**

Replace hardcoded `1800`:
```python
stale_timeout = hook_config.get("stale_timeout", 1800)
if last_ts and (time.time() - last_ts) > stale_timeout:
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest -x --tb=short`

- [ ] **Step 4: Commit**

```bash
git add soma.toml src/soma/hooks/notification.py
git commit -m "feat: stale_timeout configurable, update soma.toml keys"
```

### Task 4: Version bump to 0.4.1

- [ ] **Step 1: Bump version**

`pyproject.toml`: `version = "0.4.1"`
`src/soma/__init__.py`: `__version__ = "0.4.1"`

- [ ] **Step 2: Update CHANGELOG.md**

Add 0.4.1 section.

- [ ] **Step 3: Reinstall globally**

```bash
uv tool install --force soma-ai --from /Users/timur/projectos/SOMA
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/soma/__init__.py CHANGELOG.md
git commit -m "chore: bump to 0.4.1 — configurable thresholds"
```

---

## Chunk 2: False Positives & Noise (0.4.2)

### Task 5: Scope drift uses cwd-relative paths

**Files:**
- Modify: `src/soma/task_tracker.py:53-59, 138-164, 186-191`
- Modify: `src/soma/hooks/post_tool_use.py:131`
- Test: `tests/test_claude_code_layer.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_claude_code_layer.py TestTaskTracker, add:
def test_scope_drift_cwd_relative(self):
    """Files in different subdirs of same project should NOT trigger drift."""
    from soma.task_tracker import TaskTracker
    tt = TaskTracker(cwd="/Users/tim/project")
    for i in range(6):
        tt.record("Read", f"/Users/tim/project/src/auth/file{i}.py")
    for i in range(20):
        tt.record("Edit", f"/Users/tim/project/tests/unit/test{i}.py")
    ctx = tt.get_context()
    # src/ and tests/ are both under project/ — low drift
    assert ctx.scope_drift < 0.5

def test_scope_drift_outside_cwd(self):
    """Files outside project cwd SHOULD trigger drift."""
    from soma.task_tracker import TaskTracker
    tt = TaskTracker(cwd="/Users/tim/project-a")
    for i in range(6):
        tt.record("Read", f"/Users/tim/project-a/src/file{i}.py")
    for i in range(20):
        tt.record("Edit", f"/Users/tim/project-b/src/file{i}.py")
    ctx = tt.get_context()
    assert ctx.scope_drift > 0.5
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_claude_code_layer.py::TestTaskTracker::test_scope_drift_cwd_relative -xvs`
Expected: TypeError — TaskTracker() got unexpected keyword argument 'cwd'

- [ ] **Step 3: Update TaskTracker to accept cwd**

```python
class TaskTracker:
    def __init__(self, drift_window: int = 10, cwd: str = "") -> None:
        self.drift_window = drift_window
        self.cwd = cwd
        # ... rest unchanged

    def _extract_relative_dir(self, file_path: str) -> str:
        """Extract directory relative to cwd. If outside cwd, prefix with '!'."""
        if self.cwd and file_path.startswith(self.cwd):
            rel = file_path[len(self.cwd):].lstrip("/")
            parts = rel.split("/")
            return parts[0] if len(parts) > 1 else ""
        elif self.cwd:
            # Outside project — mark as external
            return "!" + _extract_dir(file_path)
        return _extract_dir(file_path)
```

Replace all calls to `_extract_dir(f)` with `self._extract_relative_dir(f)` in `record()` and `_compute_scope_drift()`.

- [ ] **Step 4: Pass cwd to TaskTracker in post_tool_use.py**

```python
# In post_tool_use.py, where tracker is created:
import os
cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
tracker = get_task_tracker(cwd=cwd)
```

Update `get_task_tracker` in common.py to accept and pass cwd.

- [ ] **Step 5: Update serialization**

Add `cwd` to `to_dict()` and `from_dict()`.

- [ ] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest -x --tb=short`

- [ ] **Step 7: Commit**

```bash
git add src/soma/task_tracker.py src/soma/hooks/post_tool_use.py src/soma/hooks/common.py tests/test_claude_code_layer.py
git commit -m "feat: scope drift uses cwd-relative paths"
```

### Task 6: gsd_active reduces pressure signals

**Files:**
- Modify: `src/soma/guidance.py:125-133`

- [ ] **Step 1: Write failing test**

```python
# tests/test_guidance.py, add:
def test_gsd_active_no_warn_on_agents(self):
    """When GSD is active, agent spawns don't generate suggestions."""
    from soma.guidance import evaluate
    from soma.types import ResponseMode
    action_log = [{"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)]
    r = evaluate(0.30, "Agent", {}, action_log, gsd_active=True)
    assert r.mode == ResponseMode.GUIDE
    assert not any("agents spawned" in s for s in r.suggestions)
```

- [ ] **Step 2: Implement — skip agent suggestion when gsd_active**

In `_build_suggestions`, add gsd_active parameter:
```python
def _build_suggestions(tool_name: str, action_log: list[dict], gsd_active: bool = False) -> list[str]:
    # ... existing code ...

    # Many agents — skip if GSD active (agent spawning is normal)
    if not gsd_active:
        agent_calls = sum(1 for e in recent if e["tool"] == "Agent")
        if agent_calls >= 3:
            suggestions.append(f"{agent_calls} agents spawned recently — check for file conflicts")

    return suggestions
```

Pass `gsd_active` through `evaluate()` → `_build_suggestions()`.

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/test_guidance.py -xvs`

- [ ] **Step 4: Commit**

```bash
git add src/soma/guidance.py tests/test_guidance.py
git commit -m "feat: gsd_active suppresses agent spawn suggestions"
```

### Task 7: Skip pattern collection at very low pressure

**Files:**
- Modify: `src/soma/hooks/notification.py:292-301`

- [ ] **Step 1: Move pattern skip before collection**

```python
        # In OBSERVE mode with low pressure, skip expensive analysis
        if level_name in ("OBSERVE", "HEALTHY") and pressure < 0.10:
            # Only output status line, no patterns/findings
            u = vitals.get("uncertainty", 0)
            d = vitals.get("drift", 0)
            e = vitals.get("error_rate", 0)
            # Silent — don't even output status at very low pressure
            return

        # ── Collect all findings ──
        findings = _collect_findings(action_log, vitals, pressure, level_name, actions, hook_config)
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest -x --tb=short`

- [ ] **Step 3: Commit**

```bash
git add src/soma/hooks/notification.py
git commit -m "fix: skip pattern analysis at very low pressure (<10%)"
```

### Task 8: Version bump to 0.4.2

- [ ] **Step 1: Bump version, update CHANGELOG, reinstall**

Same pattern as Task 4.

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: bump to 0.4.2 — false positive fixes"
```

---

## Chunk 3: First 5 Minutes (0.4.3)

### Task 9: Idempotent setup-claude

**Files:**
- Modify: `src/soma/cli/setup_claude.py:46-94`

- [ ] **Step 1: Write test**

```python
# tests/test_setup.py (new file)
import json
import tempfile
from pathlib import Path
from soma.cli.setup_claude import _install_hooks

class TestIdempotentSetup:
    def test_no_duplicate_hooks(self):
        """Running _install_hooks twice should not create duplicate entries."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            path = Path(f.name)

        _install_hooks(path, "soma-hook")
        _install_hooks(path, "soma-hook")  # second time

        settings = json.loads(path.read_text())
        for hook_type in ["PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit"]:
            entries = settings["hooks"][hook_type]
            soma_count = sum(
                1 for e in entries
                for h in e.get("hooks", [])
                if "soma" in str(h.get("command", ""))
            )
            assert soma_count == 1, f"Duplicate SOMA hooks in {hook_type}"

        path.unlink()
```

- [ ] **Step 2: Run — should PASS already (existing code checks)**

Run: `.venv/bin/python -m pytest tests/test_setup.py -xvs`
Expected: PASS (existing `soma_installed` check in _install_hooks)

If it passes, good — we just need the test. If it fails, fix the duplicate detection.

- [ ] **Step 3: Commit**

```bash
git add tests/test_setup.py
git commit -m "test: verify setup-claude idempotency"
```

### Task 10: soma doctor command

**Files:**
- Modify: `src/soma/cli/main.py`

- [ ] **Step 1: Implement _cmd_doctor**

```python
def _cmd_doctor(_args: argparse.Namespace) -> None:
    """Check SOMA installation health."""
    import shutil
    from pathlib import Path

    issues = []
    ok = []

    # 1. Check soma-hook is available
    soma_hook = shutil.which("soma-hook")
    if soma_hook:
        # Check version
        import subprocess
        try:
            result = subprocess.run(
                [soma_hook, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            # soma-hook doesn't have --version, check by importing
        except Exception:
            pass
        ok.append(f"soma-hook found: {soma_hook}")
    else:
        issues.append("soma-hook not in PATH — run: pip install soma-ai")

    # 2. Check settings.json hooks
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})
        expected = ["PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit"]
        for hook_type in expected:
            hook_list = hooks.get(hook_type, [])
            has_soma = any(
                "soma" in str(h.get("command", ""))
                for entry in hook_list
                for h in entry.get("hooks", [])
            )
            if has_soma:
                ok.append(f"{hook_type} hook: installed")
            else:
                issues.append(f"{hook_type} hook: MISSING — run: soma setup-claude")

        # Check hook command matches installed binary
        if soma_hook:
            for hook_type in expected:
                for entry in hooks.get(hook_type, []):
                    for h in entry.get("hooks", []):
                        cmd = h.get("command", "")
                        if "soma" in cmd:
                            # Extract the binary name from command
                            # e.g. "CLAUDE_HOOK=PreToolUse soma-hook" -> "soma-hook"
                            parts = cmd.split()
                            binary = next((p for p in parts if "soma" in p and not p.startswith("CLAUDE_HOOK")), None)
                            if binary:
                                resolved = shutil.which(binary)
                                if resolved != soma_hook:
                                    issues.append(f"{hook_type}: command uses '{binary}' but PATH resolves to '{resolved}'")

        # Check statusLine
        sl = settings.get("statusLine", {})
        if isinstance(sl, dict) and "soma" in sl.get("command", ""):
            ok.append("Status line: installed")
        else:
            issues.append("Status line: MISSING — run: soma setup-claude")
    else:
        issues.append("~/.claude/settings.json not found")

    # 3. Check ~/.soma/ state
    soma_dir = Path.home() / ".soma"
    if soma_dir.exists():
        engine_state = soma_dir / "engine_state.json"
        if engine_state.exists():
            ok.append(f"Engine state: {engine_state}")
        else:
            issues.append("Engine state missing — run: soma reset")
    else:
        issues.append("~/.soma/ directory missing — run: soma setup-claude")

    # 4. Check version consistency
    try:
        from importlib.metadata import version as pkg_version
        installed = pkg_version("soma-ai")
        ok.append(f"Version: {installed}")
    except Exception:
        issues.append("soma-ai package not found")

    # Print results
    print()
    if ok:
        for item in ok:
            print(f"  ✓ {item}")
    if issues:
        print()
        for item in issues:
            print(f"  ✗ {item}")
        print()
        print(f"  {len(issues)} issue(s) found.")
    else:
        print()
        print("  All good. SOMA is healthy.")
    print()
```

- [ ] **Step 2: Add to parser and dispatch**

In `_build_parser()`:
```python
subparsers.add_parser("doctor", help="Check SOMA installation health")
```

In dispatch dict:
```python
"doctor": _cmd_doctor,
```

- [ ] **Step 3: Test manually**

```bash
.venv/bin/soma doctor
```

- [ ] **Step 4: Commit**

```bash
git add src/soma/cli/main.py
git commit -m "feat: soma doctor — check installation health"
```

### Task 11: soma.toml auto-migration on hook startup

**Files:**
- Modify: `src/soma/hooks/common.py`

- [ ] **Step 1: Add migration check to get_engine()**

After loading config, check if soma.toml has old keys and migrate:

```python
def _maybe_migrate_soma_toml() -> None:
    """If soma.toml exists with old threshold keys, migrate in place."""
    try:
        import tomllib
        soma_toml = Path("soma.toml")
        if not soma_toml.exists():
            return
        with open(soma_toml, "rb") as f:
            config = tomllib.load(f)
        thresholds = config.get("thresholds", {})
        if any(k in thresholds for k in ("caution", "degrade", "quarantine")):
            from soma.cli.config_loader import migrate_config, save_config
            migrated = migrate_config(config)
            save_config(migrated, str(soma_toml))
    except Exception:
        pass
```

Call this once from `get_engine()` (gated by a flag so it runs max once per process).

- [ ] **Step 2: Commit**

```bash
git add src/soma/hooks/common.py
git commit -m "feat: auto-migrate soma.toml old keys on first hook run"
```

### Task 12: Version bump to 0.4.3

Same pattern. Commit.

---

## Chunk 4: CI & Quality (0.4.4)

### Task 13: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint
        run: ruff check src/ tests/

      - name: Test
        run: pytest --tb=short -q
```

- [ ] **Step 2: Add dev dependencies to pyproject.toml**

```toml
[project.optional-dependencies]
dev = ["pytest", "ruff"]
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml pyproject.toml
git commit -m "ci: GitHub Actions — pytest + ruff on push/PR"
```

### Task 14: Version bump to 0.4.4, global reinstall

- [ ] **Step 1: Bump, changelog, commit**

- [ ] **Step 2: Reinstall globally**

```bash
uv tool install --force soma-ai --from /Users/timur/projectos/SOMA
```

- [ ] **Step 3: Verify with doctor**

```bash
soma doctor
```
