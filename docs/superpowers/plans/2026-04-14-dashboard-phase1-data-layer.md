# Dashboard Phase 1: Core Fixes + Data Layer

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and test the complete data layer for the SOMA dashboard rebuild, plus fix 3 core bugs that make session data disappear.

**Architecture:** Single `src/soma/dashboard/data.py` module that reads from state.json (live), analytics.db (history), and circuit files (guidance state). All functions return typed dataclasses. Existing code in `analytics.py`, `state.py`, `findings.py`, `persistence.py` is wrapped, not rewritten.

**Tech Stack:** Python 3.11+, SQLite (analytics.db), JSON (state/circuit files), pytest + fixtures

**Spec:** `docs/superpowers/specs/2026-04-14-dashboard-rebuild-design.md`

---

## Chunk 1: Core Fixes

These 3 fixes are prerequisites — without them, the dashboard has no data to show.

### Task 1: Archive sessions instead of deleting them

**Context:** `_cleanup_old_agents()` in `hooks/common.py:378` deletes all agents except the `keep=2` most recent. This destroys session data. Fix: move files to `~/.soma/archive/{agent_id}/` instead.

**Files:**
- Modify: `src/soma/hooks/common.py:355-397` (`_clear_session_files`, `_cleanup_old_agents`)
- Test: `tests/test_claude_code_layer.py` (existing tests + new ones)

- [ ] **Step 1: Write test for archive behavior**

In `tests/test_claude_code_layer.py`, add:

```python
def test_cleanup_archives_instead_of_deleting(tmp_path, monkeypatch):
    """Cleaned-up agents should be archived, not deleted."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    monkeypatch.setattr("soma.hooks.common.SOMA_DIR", soma_dir)

    # Create fake session files for 4 agents
    for i in range(4):
        aid = f"cc-{1000 + i}"
        for fname in ["trajectory.json", "action_log.jsonl", "quality.json"]:
            p = soma_dir / f"{fname.split('.')[0]}_{aid}.json"
            p.write_text("{}")

    # Mock engine with 4 agents, current = cc-1003
    engine = MagicMock()
    engine._agents = {
        f"cc-{1000 + i}": MagicMock(last_active=float(i))
        for i in range(4)
    }

    _cleanup_old_agents(engine, "cc-1003", keep=2)

    # Oldest agents (cc-1000, cc-1001) should be archived
    archive_dir = soma_dir / "archive"
    assert archive_dir.exists()
    assert (archive_dir / "cc-1000").exists()
    assert (archive_dir / "cc-1001").exists()

    # Archived files should exist in archive dir
    assert (archive_dir / "cc-1000" / "trajectory_cc-1000.json").exists()

    # Original files should be gone
    assert not (soma_dir / "trajectory_cc-1000.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_claude_code_layer.py::test_cleanup_archives_instead_of_deleting -v`
Expected: FAIL — current code deletes files, doesn't archive

- [ ] **Step 3: Modify `_clear_session_files` to archive**

In `src/soma/hooks/common.py`, modify `_clear_session_files()` at line 355:

```python
def _clear_session_files(agent_id: str, archive: bool = False) -> None:
    """Clear (or archive) all per-session files for an agent."""
    soma_dir = Path.home() / ".soma"
    suffixes = [
        f"trajectory_{agent_id}.json",
        f"action_log_{agent_id}.jsonl",
        f"quality_{agent_id}.json",
        f"predictor_{agent_id}.json",
        f"fingerprint_{agent_id}.json",
        f"circuit_{agent_id}.json",
    ]

    if archive:
        archive_dir = soma_dir / "archive" / agent_id
        archive_dir.mkdir(parents=True, exist_ok=True)
        for s in suffixes:
            src = soma_dir / s
            if src.exists():
                dst = archive_dir / s
                src.rename(dst)
    else:
        for s in suffixes:
            p = soma_dir / s
            if p.exists():
                p.unlink()
```

- [ ] **Step 4: Modify `_cleanup_old_agents` to use archive**

In `src/soma/hooks/common.py`, modify `_cleanup_old_agents()` at line 378. Change the call from `_clear_session_files(agent_id)` to `_clear_session_files(agent_id, archive=True)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_claude_code_layer.py::test_cleanup_archives_instead_of_deleting -v`
Expected: PASS

- [ ] **Step 6: Run existing cleanup tests to check for regressions**

Run: `pytest tests/test_claude_code_layer.py -k cleanup -v`
Expected: All existing cleanup tests still pass

- [ ] **Step 7: Commit**

```bash
git add src/soma/hooks/common.py tests/test_claude_code_layer.py
git commit -m "fix: archive session data instead of deleting on cleanup"
```

### Task 2: Human-readable agent names

**Context:** `_get_session_agent_id()` at `common.py:146` returns `cc-{ppid}` which is meaningless to users. Fix: add a display_name field that resolves to `{project_name} #{N}`.

**Files:**
- Modify: `src/soma/hooks/common.py:146-162` (`_get_session_agent_id`)
- Modify: `src/soma/engine.py` (`export_state` to include display_name)
- Test: `tests/test_claude_code_layer.py`

- [ ] **Step 1: Write test for display name generation**

```python
def test_get_display_name_from_cwd(tmp_path, monkeypatch):
    """Display name should be project folder name + sequence."""
    monkeypatch.setenv("CLAUDE_WORKING_DIRECTORY", str(tmp_path / "my-project"))
    monkeypatch.setattr("soma.hooks.common.SOMA_DIR", tmp_path / ".soma")
    (tmp_path / ".soma").mkdir()

    name = _get_display_name("cc-12345")
    assert name == "my-project #1"


def test_get_display_name_increments(tmp_path, monkeypatch):
    """Second session in same project gets #2."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    monkeypatch.setenv("CLAUDE_WORKING_DIRECTORY", str(tmp_path / "my-project"))
    monkeypatch.setattr("soma.hooks.common.SOMA_DIR", soma_dir)

    # Write a name registry with one existing entry
    registry = soma_dir / "agent_names.json"
    registry.write_text('{"cc-99999": "my-project #1"}')

    name = _get_display_name("cc-12345")
    assert name == "my-project #2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_claude_code_layer.py::test_get_display_name_from_cwd -v`
Expected: FAIL — `_get_display_name` doesn't exist

- [ ] **Step 3: Implement `_get_display_name` in common.py**

Add after `_get_session_agent_id()`:

```python
def _get_display_name(agent_id: str) -> str:
    """Generate human-readable display name for an agent session."""
    soma_dir = Path.home() / ".soma"
    registry_path = soma_dir / "agent_names.json"

    # Load existing registry
    registry: dict[str, str] = {}
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Already named?
    if agent_id in registry:
        return registry[agent_id]

    # Derive project name from working directory
    cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
    project_name = Path(cwd).name or "session"

    # Find next sequence number for this project
    existing_nums = []
    for name in registry.values():
        if name.startswith(f"{project_name} #"):
            try:
                existing_nums.append(int(name.split("#")[1]))
            except (ValueError, IndexError):
                pass
    seq = max(existing_nums, default=0) + 1

    display_name = f"{project_name} #{seq}"
    registry[agent_id] = display_name

    # Save atomically
    try:
        tmp = registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(registry))
        tmp.rename(registry_path)
    except OSError:
        pass

    return display_name
```

- [ ] **Step 4: Wire display_name into state.json**

In `src/soma/engine.py`, in `export_state()` method, add `display_name` field to each agent's dict. The engine doesn't know display names, so add an optional `display_names: dict[str, str]` parameter:

```python
def export_state(self, path: Path | None = None, display_names: dict[str, str] | None = None) -> dict:
```

In the agent loop, add:
```python
agent_data["display_name"] = (display_names or {}).get(agent_id, agent_id)
```

In `hooks/common.py` where `export_state()` is called, pass the display name:
```python
display_names = {agent_id: _get_display_name(agent_id)}
engine.export_state(display_names=display_names)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_claude_code_layer.py -k display_name -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/soma/hooks/common.py src/soma/engine.py tests/test_claude_code_layer.py
git commit -m "feat: human-readable agent display names (project #N format)"
```

### Task 3: Fix `_clear_session_files` called on subagent stale detection

**Context:** `_is_stale_session()` at line 278 marks subagents as stale because their parent process exits quickly. Then `_clear_session_files()` wipes their data. Fix: skip clearing if session has recorded actions.

**Files:**
- Modify: `src/soma/hooks/common.py:278-300` (stale detection logic)
- Test: `tests/test_claude_code_layer.py`

- [ ] **Step 1: Write test**

```python
def test_stale_detection_preserves_sessions_with_data(tmp_path, monkeypatch):
    """Sessions with action data should not be cleared even if stale."""
    soma_dir = tmp_path / ".soma"
    soma_dir.mkdir()
    monkeypatch.setattr("soma.hooks.common.SOMA_DIR", soma_dir)

    agent_id = "cc-99999"
    # Create action log with data
    action_log = soma_dir / f"action_log_{agent_id}.jsonl"
    action_log.write_text('{"tool": "Bash"}\n{"tool": "Read"}\n')

    # Session marker exists but process is dead (stale)
    marker = soma_dir / f"session_{agent_id}.marker"
    marker.write_text("99999")

    # Even though stale, should NOT clear because data exists
    result = _should_clear_stale_session(agent_id)
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_claude_code_layer.py::test_stale_detection_preserves_sessions_with_data -v`
Expected: FAIL — function doesn't exist

- [ ] **Step 3: Add `_should_clear_stale_session` helper**

In `common.py`, add:

```python
def _should_clear_stale_session(agent_id: str) -> bool:
    """Return True only if a stale session has no recorded action data."""
    soma_dir = Path.home() / ".soma"
    action_log = soma_dir / f"action_log_{agent_id}.jsonl"
    if action_log.exists() and action_log.stat().st_size > 0:
        return False
    trajectory = soma_dir / f"trajectory_{agent_id}.json"
    if trajectory.exists() and trajectory.stat().st_size > 2:  # > "{}" or "[]"
        return False
    return True
```

Then modify the stale session handling code to call `_should_clear_stale_session()` before clearing. If it returns False, archive instead of clearing.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_claude_code_layer.py -k stale -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/soma/hooks/common.py tests/test_claude_code_layer.py
git commit -m "fix: preserve subagent session data on stale detection"
```

---

## Chunk 2: Data Layer — Types and Live Agents

### Task 4: Define data layer types

**Files:**
- Create: `src/soma/dashboard/types.py`
- Test: none (pure types)

- [ ] **Step 1: Create types file**

```python
"""Typed data structures for the SOMA dashboard data layer."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    agent_id: str
    display_name: str
    level: str  # OBSERVE, GUIDE, WARN, BLOCK
    pressure: float
    action_count: int
    vitals: dict[str, float | None]
    # Guidance v2
    escalation_level: int = 0
    dominant_signal: str = ""
    throttled_tool: str = ""
    # Circuit breaker
    consecutive_block: int = 0
    is_open: bool = False


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: str
    agent_id: str
    display_name: str
    action_count: int
    avg_pressure: float
    max_pressure: float
    total_tokens: int
    total_cost: float
    error_count: int
    start_time: float
    end_time: float
    mode: str = "OBSERVE"


@dataclass(frozen=True, slots=True)
class SessionDetail(SessionSummary):
    actions: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    tool_stats: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionEvent:
    timestamp: float
    tool_name: str
    pressure: float
    error: bool
    mode: str
    token_count: int = 0
    cost: float = 0.0


@dataclass(frozen=True, slots=True)
class OverviewStats:
    total_agents: int
    total_sessions: int
    total_actions: int
    avg_pressure: float
    top_signals: dict[str, float]  # signal_name -> avg value
    budget: BudgetSnapshot | None = None


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    health: float
    tokens_limit: int
    tokens_spent: int
    cost_limit: float
    cost_spent: float


@dataclass(frozen=True, slots=True)
class PressurePoint:
    timestamp: float
    pressure: float
    mode: str


@dataclass(frozen=True, slots=True)
class ToolStat:
    tool_name: str
    count: int
    error_count: int
    error_rate: float


@dataclass(frozen=True, slots=True)
class HeatmapCell:
    hour: int  # 0-23
    day: int  # 0-6 (Mon-Sun)
    count: int


@dataclass(frozen=True, slots=True)
class QualitySnapshot:
    total_writes: int
    total_bashes: int
    syntax_errors: int
    lint_issues: int
    bash_errors: int
    write_error_rate: float
    bash_error_rate: float


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    nodes: list[dict]  # [{id, pressure, level}]
    edges: list[dict]  # [{source, target, trust}]
```

- [ ] **Step 2: Commit**

```bash
git add src/soma/dashboard/types.py
git commit -m "feat(dashboard): add typed data structures for data layer"
```

### Task 5: Implement `get_live_agents()`

**Files:**
- Create: `src/soma/dashboard/data.py`
- Create: `tests/test_dashboard_data.py`
- Create: `tests/fixtures/` (test data files)

- [ ] **Step 1: Create test fixture — state.json**

Create `tests/fixtures/dashboard/state.json`:

```json
{
  "agents": {
    "cc-1001": {
      "display_name": "SOMA-Core #1",
      "level": "GUIDE",
      "pressure": 0.35,
      "vitals": {
        "uncertainty": 0.2,
        "drift": 0.1,
        "error_rate": 0.4,
        "cost": 0.05,
        "token_usage": 0.3
      },
      "action_count": 42
    },
    "cc-1002": {
      "display_name": "SOMA-Core #2",
      "level": "OBSERVE",
      "pressure": 0.12,
      "vitals": {
        "uncertainty": 0.05,
        "drift": 0.02,
        "error_rate": 0.0,
        "cost": 0.01,
        "token_usage": 0.1
      },
      "action_count": 8
    }
  },
  "budget": {
    "health": 0.85,
    "limits": {"tokens": 1000000, "cost_usd": 50.0},
    "spent": {"tokens": 150000, "cost_usd": 7.5}
  }
}
```

- [ ] **Step 2: Create test fixture — circuit file**

Create `tests/fixtures/dashboard/circuit_cc-1001.json`:

```json
{
  "agent_id": "cc-1001",
  "consecutive_block": 0,
  "consecutive_observe": 3,
  "is_open": false,
  "guidance_state": {
    "dominant_signal": "error_rate",
    "last_guidance_action_num": 38,
    "ignore_count": 2,
    "escalation_level": 1,
    "throttled_tool": "",
    "throttle_remaining": 0
  }
}
```

- [ ] **Step 3: Write failing test for get_live_agents**

In `tests/test_dashboard_data.py`:

```python
"""Tests for the dashboard data layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.dashboard.data import get_live_agents
from soma.dashboard.types import AgentSnapshot

FIXTURES = Path(__file__).parent / "fixtures" / "dashboard"


@pytest.fixture
def soma_dir(tmp_path, monkeypatch):
    """Set up a fake ~/.soma with fixture data."""
    import shutil
    # Copy state.json
    shutil.copy(FIXTURES / "state.json", tmp_path / "state.json")
    # Copy circuit file
    shutil.copy(FIXTURES / "circuit_cc-1001.json", tmp_path / "circuit_cc-1001.json")
    monkeypatch.setattr("soma.dashboard.data.SOMA_DIR", tmp_path)
    return tmp_path


def test_get_live_agents_returns_all_agents(soma_dir):
    agents = get_live_agents()
    assert len(agents) == 2
    assert all(isinstance(a, AgentSnapshot) for a in agents)


def test_get_live_agents_fields_correct(soma_dir):
    agents = {a.agent_id: a for a in get_live_agents()}

    a1 = agents["cc-1001"]
    assert a1.display_name == "SOMA-Core #1"
    assert a1.level == "GUIDE"
    assert a1.pressure == 0.35
    assert a1.action_count == 42
    assert a1.vitals["error_rate"] == 0.4
    # Guidance v2 from circuit file
    assert a1.escalation_level == 1
    assert a1.dominant_signal == "error_rate"
    assert a1.throttled_tool == ""


def test_get_live_agents_without_circuit_file(soma_dir):
    """Agent without circuit file should have default guidance values."""
    agents = {a.agent_id: a for a in get_live_agents()}

    a2 = agents["cc-1002"]
    assert a2.escalation_level == 0
    assert a2.dominant_signal == ""


def test_get_live_agents_empty_state(soma_dir):
    """Missing or empty state.json returns empty list."""
    (soma_dir / "state.json").unlink()
    assert get_live_agents() == []
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_dashboard_data.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 5: Implement get_live_agents**

Create `src/soma/dashboard/data.py`:

```python
"""SOMA Dashboard data layer — single source of truth for all dashboard data."""
from __future__ import annotations

import json
from pathlib import Path

from soma.dashboard.types import AgentSnapshot

SOMA_DIR = Path.home() / ".soma"


def get_live_agents() -> list[AgentSnapshot]:
    """Return all currently active agents from state.json + circuit files."""
    state_path = SOMA_DIR / "state.json"
    if not state_path.exists():
        return []

    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    agents_data = state.get("agents", {})
    result = []

    for agent_id, data in agents_data.items():
        # Read guidance state from circuit file
        esc_level = 0
        dominant = ""
        throttled = ""
        cb_block = 0
        cb_open = False

        circuit_path = SOMA_DIR / f"circuit_{agent_id}.json"
        if circuit_path.exists():
            try:
                circuit = json.loads(circuit_path.read_text())
                gs = circuit.get("guidance_state", {})
                esc_level = gs.get("escalation_level", 0)
                dominant = gs.get("dominant_signal", "")
                throttled = gs.get("throttled_tool", "")
                cb_block = circuit.get("consecutive_block", 0)
                cb_open = circuit.get("is_open", False)
            except (json.JSONDecodeError, OSError):
                pass

        result.append(AgentSnapshot(
            agent_id=agent_id,
            display_name=data.get("display_name", agent_id),
            level=data.get("level", "OBSERVE"),
            pressure=data.get("pressure", 0.0),
            action_count=data.get("action_count", 0),
            vitals=data.get("vitals", {}),
            escalation_level=esc_level,
            dominant_signal=dominant,
            throttled_tool=throttled,
            consecutive_block=cb_block,
            is_open=cb_open,
        ))

    return result
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_dashboard_data.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py tests/fixtures/dashboard/
git commit -m "feat(dashboard): implement get_live_agents data layer function"
```

---

## Chunk 3: Data Layer — Sessions and Overview

### Task 6: Implement `get_all_sessions()`

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`
- Create: `tests/fixtures/dashboard/analytics.db` (generated by test setup)

- [ ] **Step 1: Write test fixture helper for analytics.db**

In `tests/test_dashboard_data.py`, add:

```python
import sqlite3

@pytest.fixture
def analytics_db(soma_dir):
    """Create a test analytics.db with sample data."""
    db_path = soma_dir / "analytics.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            timestamp REAL,
            agent_id TEXT,
            session_id TEXT,
            tool_name TEXT,
            pressure REAL,
            uncertainty REAL,
            drift REAL,
            error_rate REAL,
            context_usage REAL,
            token_count INTEGER,
            cost REAL,
            mode TEXT DEFAULT 'OBSERVE',
            error INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_agent_session ON actions(agent_id, session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp)")

    # Session 1: 5 actions
    for i in range(5):
        conn.execute(
            "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1700000000.0 + i * 60, "cc-1001", "sess-001", "Bash",
             0.2 + i * 0.05, 0.1, 0.05, 0.0, 0.3, 500 + i * 100, 0.01, "OBSERVE", 0),
        )

    # Session 2: 3 actions, one error
    for i in range(3):
        conn.execute(
            "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1700001000.0 + i * 60, "cc-1001", "sess-002", "Read",
             0.4 + i * 0.1, 0.2, 0.1, 0.3, 0.5, 800, 0.02, "GUIDE", 1 if i == 2 else 0),
        )

    # Session 3: different agent
    for i in range(2):
        conn.execute(
            "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1700002000.0 + i * 60, "cc-1002", "sess-003", "Grep",
             0.1, 0.05, 0.02, 0.0, 0.2, 200, 0.005, "OBSERVE", 0),
        )

    conn.commit()
    conn.close()
    return db_path
```

- [ ] **Step 2: Write failing test**

```python
from soma.dashboard.data import get_all_sessions
from soma.dashboard.types import SessionSummary


def test_get_all_sessions_returns_all(soma_dir, analytics_db):
    sessions = get_all_sessions()
    assert len(sessions) == 3  # ALL sessions, not just 2
    assert all(isinstance(s, SessionSummary) for s in sessions)


def test_get_all_sessions_fields_correct(soma_dir, analytics_db):
    sessions = {s.session_id: s for s in get_all_sessions()}

    s1 = sessions["sess-001"]
    assert s1.agent_id == "cc-1001"
    assert s1.action_count == 5
    assert s1.error_count == 0
    assert s1.total_tokens == 500 + 600 + 700 + 800 + 900  # 3500
    assert s1.start_time == 1700000000.0
    assert s1.end_time == 1700000000.0 + 4 * 60

    s2 = sessions["sess-002"]
    assert s2.error_count == 1
    assert s2.action_count == 3


def test_get_all_sessions_no_db(soma_dir):
    """Missing analytics.db returns empty list."""
    assert get_all_sessions() == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_dashboard_data.py::test_get_all_sessions_returns_all -v`
Expected: FAIL

- [ ] **Step 4: Implement get_all_sessions**

In `src/soma/dashboard/data.py`, add:

```python
import sqlite3
from soma.dashboard.types import SessionSummary


def _get_db_connection() -> sqlite3.Connection | None:
    """Open analytics.db, return None if not available."""
    db_path = SOMA_DIR / "analytics.db"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _get_name_registry() -> dict[str, str]:
    """Load agent display name registry."""
    path = SOMA_DIR / "agent_names.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_all_sessions() -> list[SessionSummary]:
    """Return ALL sessions from analytics.db, newest first."""
    conn = _get_db_connection()
    if conn is None:
        return []

    try:
        rows = conn.execute("""
            SELECT
                session_id,
                agent_id,
                COUNT(*) as action_count,
                AVG(pressure) as avg_pressure,
                MAX(pressure) as max_pressure,
                SUM(token_count) as total_tokens,
                SUM(cost) as total_cost,
                SUM(error) as error_count,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                MAX(mode) as mode
            FROM actions
            GROUP BY session_id, agent_id
            ORDER BY start_time DESC
        """).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    names = _get_name_registry()
    return [
        SessionSummary(
            session_id=r["session_id"],
            agent_id=r["agent_id"],
            display_name=names.get(r["agent_id"], r["agent_id"]),
            action_count=r["action_count"],
            avg_pressure=round(r["avg_pressure"], 4),
            max_pressure=round(r["max_pressure"], 4),
            total_tokens=r["total_tokens"] or 0,
            total_cost=round(r["total_cost"] or 0.0, 4),
            error_count=r["error_count"] or 0,
            start_time=r["start_time"],
            end_time=r["end_time"],
            mode=r["mode"] or "OBSERVE",
        )
        for r in rows
    ]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_dashboard_data.py -k session -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): implement get_all_sessions from analytics.db"
```

### Task 7: Implement `get_session_detail()`

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`

- [ ] **Step 1: Write failing test**

```python
from soma.dashboard.data import get_session_detail
from soma.dashboard.types import SessionDetail


def test_get_session_detail(soma_dir, analytics_db):
    detail = get_session_detail("sess-001")
    assert detail is not None
    assert isinstance(detail, SessionDetail)
    assert detail.action_count == 5
    assert len(detail.actions) == 5
    assert detail.actions[0]["tool_name"] == "Bash"
    assert "Bash" in detail.tool_stats
    assert detail.tool_stats["Bash"] == 5


def test_get_session_detail_not_found(soma_dir, analytics_db):
    assert get_session_detail("nonexistent") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_data.py::test_get_session_detail -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
from soma.dashboard.types import SessionDetail


def get_session_detail(session_id: str) -> SessionDetail | None:
    """Return full detail for a single session."""
    conn = _get_db_connection()
    if conn is None:
        return None

    try:
        rows = conn.execute(
            "SELECT * FROM actions WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    if not rows:
        return None

    actions = [dict(r) for r in rows]
    agent_id = rows[0]["agent_id"]
    names = _get_name_registry()

    # Tool stats
    tool_counts: dict[str, int] = {}
    for a in actions:
        t = a["tool_name"]
        tool_counts[t] = tool_counts.get(t, 0) + 1

    pressures = [r["pressure"] for r in rows]
    return SessionDetail(
        session_id=session_id,
        agent_id=agent_id,
        display_name=names.get(agent_id, agent_id),
        action_count=len(rows),
        avg_pressure=round(sum(pressures) / len(pressures), 4),
        max_pressure=round(max(pressures), 4),
        total_tokens=sum(r["token_count"] or 0 for r in rows),
        total_cost=round(sum(r["cost"] or 0.0 for r in rows), 4),
        error_count=sum(1 for r in rows if r["error"]),
        start_time=rows[0]["timestamp"],
        end_time=rows[-1]["timestamp"],
        mode=rows[-1]["mode"] or "OBSERVE",
        actions=actions,
        tool_stats=tool_counts,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_dashboard_data.py -k session_detail -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): implement get_session_detail"
```

### Task 8: Implement `get_overview_stats()` and `get_budget_status()`

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`

- [ ] **Step 1: Write failing tests**

```python
from soma.dashboard.data import get_overview_stats, get_budget_status
from soma.dashboard.types import OverviewStats, BudgetSnapshot


def test_get_overview_stats(soma_dir, analytics_db):
    stats = get_overview_stats()
    assert isinstance(stats, OverviewStats)
    assert stats.total_agents == 2  # from state.json
    assert stats.total_sessions == 3  # from analytics.db
    assert stats.total_actions == 10  # 5 + 3 + 2
    assert stats.budget is not None
    assert stats.budget.health == 0.85


def test_get_budget_status(soma_dir):
    budget = get_budget_status()
    assert isinstance(budget, BudgetSnapshot)
    assert budget.health == 0.85
    assert budget.tokens_spent == 150000
    assert budget.cost_limit == 50.0


def test_get_budget_no_state(soma_dir):
    (soma_dir / "state.json").unlink()
    assert get_budget_status() is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_dashboard_data.py -k "overview or budget" -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
from soma.dashboard.types import OverviewStats, BudgetSnapshot


def get_budget_status() -> BudgetSnapshot | None:
    """Read budget from state.json."""
    state_path = SOMA_DIR / "state.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    b = state.get("budget")
    if not b:
        return None

    return BudgetSnapshot(
        health=b.get("health", 1.0),
        tokens_limit=b.get("limits", {}).get("tokens", 0),
        tokens_spent=b.get("spent", {}).get("tokens", 0),
        cost_limit=b.get("limits", {}).get("cost_usd", 0.0),
        cost_spent=b.get("spent", {}).get("cost_usd", 0.0),
    )


def get_overview_stats() -> OverviewStats:
    """Aggregate overview stats from all data sources."""
    agents = get_live_agents()
    sessions = get_all_sessions()

    total_actions = sum(s.action_count for s in sessions)

    # Average signal values across live agents
    signal_sums: dict[str, list[float]] = {}
    for a in agents:
        for sig, val in a.vitals.items():
            if val is not None:
                signal_sums.setdefault(sig, []).append(val)

    top_signals = {
        sig: round(sum(vals) / len(vals), 4)
        for sig, vals in signal_sums.items()
        if vals
    }

    return OverviewStats(
        total_agents=len(agents),
        total_sessions=len(sessions),
        total_actions=total_actions,
        avg_pressure=round(
            sum(a.pressure for a in agents) / len(agents), 4
        ) if agents else 0.0,
        top_signals=top_signals,
        budget=get_budget_status(),
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_dashboard_data.py -k "overview or budget" -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): implement get_overview_stats and get_budget_status"
```

---

## Chunk 4: Data Layer — Analytics, Guidance, System

### Task 9: Implement `get_pressure_history()` and `get_agent_timeline()`

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`

- [ ] **Step 1: Write failing tests**

```python
from soma.dashboard.data import get_pressure_history, get_agent_timeline
from soma.dashboard.types import PressurePoint, ActionEvent


def test_get_pressure_history(soma_dir, analytics_db):
    points = get_pressure_history("cc-1001")
    assert len(points) == 8  # 5 + 3 actions across 2 sessions
    assert all(isinstance(p, PressurePoint) for p in points)
    assert points[0].timestamp < points[-1].timestamp  # sorted


def test_get_pressure_history_empty(soma_dir, analytics_db):
    assert get_pressure_history("nonexistent") == []


def test_get_agent_timeline(soma_dir, analytics_db):
    events = get_agent_timeline("cc-1001")
    assert len(events) == 8
    assert all(isinstance(e, ActionEvent) for e in events)
    assert events[0].tool_name == "Bash"
```

- [ ] **Step 2: Implement**

```python
from soma.dashboard.types import PressurePoint, ActionEvent


def get_pressure_history(agent_id: str) -> list[PressurePoint]:
    """Return pressure values over time for an agent."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT timestamp, pressure, mode FROM actions WHERE agent_id = ? ORDER BY timestamp",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    return [
        PressurePoint(timestamp=r["timestamp"], pressure=r["pressure"], mode=r["mode"] or "OBSERVE")
        for r in rows
    ]


def get_agent_timeline(agent_id: str) -> list[ActionEvent]:
    """Return all actions for an agent as timeline events."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT timestamp, tool_name, pressure, error, mode, token_count, cost FROM actions WHERE agent_id = ? ORDER BY timestamp",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    return [
        ActionEvent(
            timestamp=r["timestamp"],
            tool_name=r["tool_name"],
            pressure=r["pressure"],
            error=bool(r["error"]),
            mode=r["mode"] or "OBSERVE",
            token_count=r["token_count"] or 0,
            cost=r["cost"] or 0.0,
        )
        for r in rows
    ]
```

- [ ] **Step 3: Run tests and commit**

Run: `pytest tests/test_dashboard_data.py -k "pressure_history or timeline" -v`

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): implement get_pressure_history and get_agent_timeline"
```

### Task 10: Implement `get_tool_stats()` and `get_activity_heatmap()`

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`

- [ ] **Step 1: Write failing tests**

```python
from soma.dashboard.data import get_tool_stats, get_activity_heatmap
from soma.dashboard.types import ToolStat, HeatmapCell


def test_get_tool_stats(soma_dir, analytics_db):
    stats = get_tool_stats("cc-1001")
    assert len(stats) == 2  # Bash + Read
    by_name = {s.tool_name: s for s in stats}
    assert by_name["Bash"].count == 5
    assert by_name["Read"].count == 3
    assert by_name["Read"].error_count == 1
    assert by_name["Read"].error_rate == pytest.approx(1 / 3, rel=0.01)


def test_get_activity_heatmap(soma_dir, analytics_db):
    cells = get_activity_heatmap("cc-1001")
    assert len(cells) > 0
    assert all(isinstance(c, HeatmapCell) for c in cells)
    total = sum(c.count for c in cells)
    assert total == 8  # all cc-1001 actions
```

- [ ] **Step 2: Implement**

```python
from datetime import datetime
from soma.dashboard.types import ToolStat, HeatmapCell


def get_tool_stats(agent_id: str) -> list[ToolStat]:
    """Return per-tool usage counts and error rates."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """SELECT tool_name, COUNT(*) as cnt, SUM(error) as errs
               FROM actions WHERE agent_id = ?
               GROUP BY tool_name ORDER BY cnt DESC""",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    return [
        ToolStat(
            tool_name=r["tool_name"],
            count=r["cnt"],
            error_count=r["errs"] or 0,
            error_rate=round((r["errs"] or 0) / r["cnt"], 4) if r["cnt"] else 0.0,
        )
        for r in rows
    ]


def get_activity_heatmap(agent_id: str) -> list[HeatmapCell]:
    """Return hour x day-of-week action counts."""
    conn = _get_db_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT timestamp FROM actions WHERE agent_id = ?",
            (agent_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    grid: dict[tuple[int, int], int] = {}
    for r in rows:
        dt = datetime.fromtimestamp(r["timestamp"])
        key = (dt.hour, dt.weekday())
        grid[key] = grid.get(key, 0) + 1

    return [HeatmapCell(hour=h, day=d, count=c) for (h, d), c in sorted(grid.items())]
```

- [ ] **Step 3: Run tests and commit**

Run: `pytest tests/test_dashboard_data.py -k "tool_stats or heatmap" -v`

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): implement get_tool_stats and get_activity_heatmap"
```

### Task 11: Implement `get_audit_log()` and `get_findings()`

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`

- [ ] **Step 1: Write fixture — audit log file**

The audit log is written by pre_tool_use.py as JSONL at `~/.soma/audit_{agent_id}.jsonl`. Create test fixture.

```python
@pytest.fixture
def audit_log(soma_dir):
    """Create test audit log."""
    log = soma_dir / "audit_cc-1001.jsonl"
    entries = [
        {"action_num": 10, "type": "guidance", "signal": "error_rate", "level": "GUIDE", "message": "High error rate", "timestamp": 1700000600.0},
        {"action_num": 15, "type": "throttle", "signal": "error_rate", "tool": "Bash", "timestamp": 1700000900.0},
        {"action_num": 20, "type": "guidance", "signal": "drift", "level": "WARN", "message": "Scope drift detected", "timestamp": 1700001200.0},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries))
    return log
```

- [ ] **Step 2: Write failing tests**

```python
from soma.dashboard.data import get_audit_log, get_findings


def test_get_audit_log(soma_dir, audit_log):
    entries = get_audit_log("cc-1001")
    assert len(entries) == 3
    assert entries[0]["type"] == "guidance"
    assert entries[1]["type"] == "throttle"


def test_get_audit_log_empty(soma_dir):
    assert get_audit_log("nonexistent") == []


def test_get_findings(soma_dir):
    # Findings depend on quality/predictor/fingerprint state files
    # With no state files, should return empty list gracefully
    findings = get_findings("cc-1001")
    assert isinstance(findings, list)
```

- [ ] **Step 3: Implement**

```python
def get_audit_log(agent_id: str) -> list[dict]:
    """Read guidance audit log entries for an agent."""
    path = SOMA_DIR / f"audit_{agent_id}.jsonl"
    if not path.exists():
        return []
    entries = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        pass
    return entries


def get_findings(agent_id: str) -> list[dict]:
    """Collect findings from quality/predictor/fingerprint subsystems."""
    try:
        from soma.findings import collect
        findings = collect()
        return [
            {"priority": f.priority, "category": f.category, "title": f.title, "detail": f.detail}
            for f in findings
        ]
    except Exception:
        return []
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_dashboard_data.py -k "audit or findings" -v`

```bash
git add src/soma/dashboard/data.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): implement get_audit_log and get_findings"
```

### Task 12: Implement remaining data functions

**Files:**
- Modify: `src/soma/dashboard/data.py`
- Modify: `tests/test_dashboard_data.py`

Implement the remaining 8 functions. These wrap existing SOMA subsystems:

- [ ] **Step 1: Implement `get_config()` and `update_config()`**

```python
def get_config() -> dict:
    """Read current soma.toml config."""
    try:
        from soma.cli.config_loader import load_config
        return load_config()
    except Exception:
        return {}


def update_config(patch: dict) -> dict:
    """Update soma.toml with partial config."""
    try:
        import tomllib
        import tomli_w

        config_path = Path("soma.toml")
        if config_path.exists():
            current = tomllib.loads(config_path.read_text())
        else:
            current = {}

        # Deep merge patch into current
        def _merge(base: dict, updates: dict) -> dict:
            for k, v in updates.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    _merge(base[k], v)
                else:
                    base[k] = v
            return base

        merged = _merge(current, patch)
        config_path.write_bytes(tomli_w.dumps(merged))
        return merged
    except Exception:
        return get_config()
```

- [ ] **Step 2: Implement `get_quality()`, `get_fingerprint()`, `get_baselines()`**

```python
def get_quality(agent_id: str) -> QualitySnapshot | None:
    """Read quality tracker state for an agent."""
    try:
        from soma.state import get_quality_tracker
        qt = get_quality_tracker()
        if qt is None:
            return None
        return QualitySnapshot(
            total_writes=qt.total_writes,
            total_bashes=qt.total_bashes,
            syntax_errors=qt.syntax_errors,
            lint_issues=qt.lint_issues,
            bash_errors=qt.bash_errors,
            write_error_rate=round(qt.syntax_errors / max(qt.total_writes, 1), 4),
            bash_error_rate=round(qt.bash_errors / max(qt.total_bashes, 1), 4),
        )
    except Exception:
        return None


def get_fingerprint(agent_id: str) -> dict | None:
    """Read behavioral fingerprint data."""
    try:
        from soma.state import get_fingerprint_engine
        fe = get_fingerprint_engine()
        if fe is None:
            return None
        return {"patterns": fe.patterns if hasattr(fe, "patterns") else {}}
    except Exception:
        return None


def get_baselines(agent_id: str) -> dict[str, float]:
    """Read EMA baselines from engine state."""
    path = SOMA_DIR / "engine_state.json"
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text())
        agent_state = state.get("agents", {}).get(agent_id, {})
        baseline = agent_state.get("baseline", {})
        return {k: round(v, 4) for k, v in baseline.items() if isinstance(v, (int, float))}
    except (json.JSONDecodeError, OSError):
        return {}
```

- [ ] **Step 3: Implement `get_prediction()`, `get_agent_graph()`, `get_learning_state()`**

```python
def get_prediction(agent_id: str) -> dict | None:
    """Read pressure prediction from predictor state."""
    try:
        from soma.state import get_predictor
        pred = get_predictor()
        if pred is None:
            return None
        prediction = pred.predict(agent_id) if hasattr(pred, "predict") else None
        if prediction is None:
            return None
        return {
            "predicted_pressure": prediction.predicted_pressure,
            "confidence": prediction.confidence,
            "horizon_actions": prediction.horizon_actions,
        }
    except Exception:
        return None


def get_agent_graph() -> GraphSnapshot | None:
    """Read the agent pressure graph."""
    path = SOMA_DIR / "engine_state.json"
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
        graph_data = state.get("graph", {})
        if not graph_data:
            return None
        nodes = [
            {"id": aid, "pressure": adata.get("level", "OBSERVE")}
            for aid, adata in state.get("agents", {}).items()
        ]
        edges = [
            {"source": e.get("source"), "target": e.get("target"), "trust": e.get("trust", 1.0)}
            for e in graph_data.get("edges", [])
        ]
        return GraphSnapshot(nodes=nodes, edges=edges)
    except (json.JSONDecodeError, OSError):
        return None


def get_learning_state(agent_id: str) -> dict | None:
    """Read learning engine state."""
    path = SOMA_DIR / "engine_state.json"
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
        learning = state.get("learning", {})
        if not learning:
            return None
        return learning
    except (json.JSONDecodeError, OSError):
        return None
```

- [ ] **Step 4: Implement `export_session()`**

```python
def export_session(session_id: str, fmt: str = "json") -> bytes:
    """Export session data as JSON or CSV bytes."""
    detail = get_session_detail(session_id)
    if detail is None:
        return b""

    if fmt == "csv":
        import csv
        import io
        output = io.StringIO()
        if detail.actions:
            writer = csv.DictWriter(output, fieldnames=detail.actions[0].keys())
            writer.writeheader()
            writer.writerows(detail.actions)
        return output.getvalue().encode("utf-8")
    else:
        import dataclasses
        return json.dumps(dataclasses.asdict(detail), indent=2).encode("utf-8")
```

- [ ] **Step 5: Write tests for all remaining functions**

```python
def test_get_config(soma_dir):
    config = get_config()
    assert isinstance(config, dict)


def test_get_quality_no_state(soma_dir):
    assert get_quality("cc-1001") is None


def test_get_baselines_from_engine_state(soma_dir):
    engine_state = {
        "agents": {"cc-1001": {"baseline": {"uncertainty": 0.05, "drift": 0.03}}}
    }
    (soma_dir / "engine_state.json").write_text(json.dumps(engine_state))
    baselines = get_baselines("cc-1001")
    assert baselines["uncertainty"] == 0.05
    assert baselines["drift"] == 0.03


def test_get_baselines_no_state(soma_dir):
    assert get_baselines("cc-1001") == {}


def test_export_session_json(soma_dir, analytics_db):
    data = export_session("sess-001", "json")
    assert len(data) > 0
    parsed = json.loads(data)
    assert parsed["action_count"] == 5


def test_export_session_csv(soma_dir, analytics_db):
    data = export_session("sess-001", "csv")
    assert b"tool_name" in data  # header row
    assert b"Bash" in data


def test_export_session_not_found(soma_dir, analytics_db):
    assert export_session("nonexistent") == b""
```

- [ ] **Step 6: Run full data layer test suite**

Run: `pytest tests/test_dashboard_data.py -v`
Expected: All PASS

- [ ] **Step 7: Run full SOMA test suite for regressions**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add src/soma/dashboard/data.py src/soma/dashboard/types.py tests/test_dashboard_data.py
git commit -m "feat(dashboard): complete data layer — all 19 functions implemented and tested"
```

---

## Phase 1 Completion Checklist

- [ ] All 3 core bugs fixed (archive, naming, stale protection)
- [ ] `src/soma/dashboard/types.py` — 11 typed dataclasses
- [ ] `src/soma/dashboard/data.py` — 19 functions, all tested
- [ ] `tests/test_dashboard_data.py` — comprehensive test suite with fixtures
- [ ] Full SOMA test suite passes
- [ ] All commits made with descriptive messages
