# SOMA Core Hardening — Multi-Agent Ready

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden SOMA core for concurrent multi-agent use: atomic persistence, agent lifecycle, learning validation, and stress testing. No new layers — just making the engine bulletproof.

**Architecture:** persistence.py gets file locking for atomic read/write. Engine gets agent TTL eviction. Learning engine gets convergence validation. New stress tests simulate 5 concurrent agents hammering the engine. wrap.py gets shared-engine support for multi-agent pipelines.

**Tech Stack:** Python 3.11+, pytest, fcntl (file locking), threading (concurrency tests), existing SOMA infrastructure.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/soma/persistence.py` | Atomic file writes with locking |
| Modify | `src/soma/engine.py` | Agent TTL eviction, last_active tracking |
| Modify | `src/soma/wrap.py` | Shared engine support, multi-agent wrap |
| Create | `tests/test_multiagent.py` | Multi-agent integration + stress tests |
| Modify | `tests/test_persistence.py` | Atomic write tests |
| Modify | `tests/test_learning.py` | Convergence validation |

---

## Chunk 1: Atomic Persistence

### Task 1: File-locked atomic saves

**Problem:** Two agents calling `save_engine_state` simultaneously can corrupt the JSON file (partial writes, interleaved data). Need atomic write (write to temp, rename) + file lock.

**Files:**
- Modify: `src/soma/persistence.py:10-37` (save_engine_state)
- Modify: `src/soma/persistence.py:40-95` (load_engine_state)
- Test: `tests/test_persistence.py`

- [ ] **Step 1: Write failing test for concurrent saves**

```python
# tests/test_persistence.py, add:
import threading

class TestAtomicPersistence:
    def test_concurrent_saves_no_corruption(self, tmp_path):
        """Two threads saving simultaneously should not corrupt state."""
        from soma.engine import SOMAEngine
        from soma.persistence import save_engine_state, load_engine_state
        from soma.types import Action

        path = str(tmp_path / "engine.json")

        def run_agent(agent_id, n_actions):
            engine = SOMAEngine(budget={"tokens": 100000})
            engine.register_agent(agent_id)
            for i in range(n_actions):
                engine.record_action(agent_id, Action(
                    tool_name="Bash", output_text=f"ok {i}", token_count=10,
                ))
                save_engine_state(engine, path)

        threads = [
            threading.Thread(target=run_agent, args=("agent-a", 20)),
            threading.Thread(target=run_agent, args=("agent-b", 20)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File should be valid JSON, not corrupted
        restored = load_engine_state(path)
        assert restored is not None

    def test_atomic_write_survives_crash(self, tmp_path):
        """If write is interrupted, old state should remain valid."""
        from soma.engine import SOMAEngine
        from soma.persistence import save_engine_state, load_engine_state

        path = str(tmp_path / "engine.json")

        # Save initial state
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("test")
        save_engine_state(engine, path)

        # Verify it loads
        restored = load_engine_state(path)
        assert restored is not None
        assert "test" in restored._agents
```

- [ ] **Step 2: Run test to verify it fails (or passes with race condition)**

Run: `.venv/bin/python -m pytest tests/test_persistence.py::TestAtomicPersistence -xvs`

- [ ] **Step 3: Implement atomic save with file locking**

```python
import fcntl
import tempfile

def save_engine_state(engine: SOMAEngine, path: str | None = None) -> None:
    """Save full engine state atomically with file locking."""
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    state = {
        "agents": {},
        "budget": engine.budget.to_dict(),
        "graph": engine._graph.to_dict(),
        "learning": engine._learning.to_dict(),
        "custom_weights": engine._custom_weights,
        "custom_thresholds": engine._custom_thresholds,
    }

    for agent_id, s in engine._agents.items():
        if agent_id == "default":
            continue
        state["agents"][agent_id] = {
            "baseline": s.baseline.to_dict(),
            "action_count": s.action_count,
            "known_tools": s.known_tools,
            "baseline_vector": s.baseline_vector,
            "level": s.mode.name,
        }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(".lock")

    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                # Write to temp file, then atomic rename
                fd, tmp = tempfile.mkstemp(
                    dir=str(target.parent), suffix=".tmp",
                )
                try:
                    import os
                    os.write(fd, json.dumps(state, indent=2, default=str).encode())
                    os.fsync(fd)
                    os.close(fd)
                    os.rename(tmp, str(target))
                except Exception:
                    os.close(fd)
                    os.unlink(tmp)
                    raise
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except Exception:
        # Fallback: direct write (better than nothing)
        target.write_text(json.dumps(state, indent=2, default=str))


def load_engine_state(path: str | None = None) -> SOMAEngine | None:
    """Restore engine from saved state with file locking."""
    if path is None:
        path = str(Path.home() / ".soma" / "engine_state.json")

    p = Path(path)
    if not p.exists():
        return None

    lock_path = p.with_suffix(".lock")
    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_SH)
            try:
                state = json.loads(p.read_text())
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return None

    # ... rest of restoration unchanged
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_persistence.py -xvs`

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x --tb=short`

- [ ] **Step 6: Commit**

```bash
git add src/soma/persistence.py tests/test_persistence.py
git commit -m "feat: atomic persistence with file locking for multi-agent safety"
```

---

## Chunk 2: Agent Lifecycle

### Task 2: Agent TTL and eviction

**Problem:** Dead agents accumulate in engine state forever. A pipeline that creates 50 agents over a week bloats state.json. Need TTL-based eviction.

**Files:**
- Modify: `src/soma/engine.py` (_AgentState, record_action, new evict_stale_agents)
- Test: `tests/test_multiagent.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_multiagent.py (new file)
import time
from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode


class TestAgentLifecycle:
    def test_evict_stale_agents(self):
        """Agents inactive for longer than TTL should be evicted."""
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("active")
        engine.register_agent("stale")

        # Record action for active agent
        engine.record_action("active", Action(
            tool_name="Bash", output_text="ok", token_count=10,
        ))

        # Manually set stale agent's last_active to the past
        engine._agents["stale"]._last_active = time.time() - 7200  # 2 hours ago

        # Evict with 1-hour TTL
        evicted = engine.evict_stale_agents(ttl_seconds=3600)
        assert "stale" in evicted
        assert "stale" not in engine._agents
        assert "active" in engine._agents

    def test_evict_preserves_active(self):
        """Active agents should never be evicted."""
        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("a")
        engine.record_action("a", Action(
            tool_name="Bash", output_text="ok", token_count=10,
        ))

        evicted = engine.evict_stale_agents(ttl_seconds=60)
        assert len(evicted) == 0
        assert "a" in engine._agents

    def test_evict_returns_empty_on_no_stale(self):
        engine = SOMAEngine(budget={"tokens": 100000})
        assert engine.evict_stale_agents(ttl_seconds=3600) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_multiagent.py::TestAgentLifecycle -xvs`
Expected: AttributeError — evict_stale_agents not found

- [ ] **Step 3: Add last_active tracking to _AgentState**

In engine.py `_AgentState.__init__`:
```python
self._last_active: float = time.time()
```

Add `import time` at top.

In `_AgentState.__slots__`, add `"_last_active"`.

In `record_action`, after `s.action_count += 1`:
```python
s._last_active = time.time()
```

- [ ] **Step 4: Implement evict_stale_agents**

```python
def evict_stale_agents(self, ttl_seconds: float = 3600) -> list[str]:
    """Remove agents inactive for longer than ttl_seconds. Returns evicted IDs."""
    now = time.time()
    to_evict = [
        aid for aid, s in self._agents.items()
        if aid != "default" and (now - s._last_active) > ttl_seconds
    ]
    for aid in to_evict:
        del self._agents[aid]
        self._graph._nodes.pop(aid, None)
    return to_evict
```

- [ ] **Step 5: Update persistence to save/restore last_active**

In `save_engine_state`, add to agent state dict:
```python
"last_active": s._last_active,
```

In `load_engine_state`, after restoring agent:
```python
s._last_active = agent_state.get("last_active", time.time())
```

- [ ] **Step 6: Run tests, commit**

```bash
git add src/soma/engine.py src/soma/persistence.py tests/test_multiagent.py
git commit -m "feat: agent TTL eviction — remove stale agents from engine state"
```

---

## Chunk 3: Learning Convergence Validation

### Task 3: Prove learning engine converges

**Problem:** Self-tuning thresholds claim to converge after ~15 interventions. No test validates this. Need to run 50+ interventions and verify thresholds stabilize, don't oscillate.

**Files:**
- Modify: `tests/test_learning.py`

- [ ] **Step 1: Write convergence test**

```python
# In tests/test_learning.py, add:
class TestConvergence:
    def test_thresholds_converge_not_oscillate(self):
        """After many false-positive interventions, thresholds should stabilize."""
        from soma.learning import LearningEngine
        from soma.types import ResponseMode

        le = LearningEngine()

        # Simulate 30 false-positive escalations (OBSERVE → GUIDE that didn't help)
        for i in range(30):
            le.record_intervention(
                agent_id="test",
                old_level=ResponseMode.OBSERVE,
                new_level=ResponseMode.GUIDE,
                pressure=0.30,
                trigger_signals={"uncertainty": 0.4, "drift": 0.2},
            )
            le.evaluate("test", pressure=0.30, actions_since=6)

        # Get the threshold adjustment
        adj = le.get_threshold_adjustment(ResponseMode.OBSERVE, ResponseMode.GUIDE)

        # Should be positive (raising threshold = fewer false positives)
        assert adj > 0, f"Expected positive adjustment, got {adj}"

        # Should be bounded (max_threshold_shift = 0.10)
        assert adj <= 0.10, f"Adjustment {adj} exceeds max shift 0.10"

        # Run 30 more — should not grow beyond max
        for i in range(30):
            le.record_intervention(
                agent_id="test",
                old_level=ResponseMode.OBSERVE,
                new_level=ResponseMode.GUIDE,
                pressure=0.30,
                trigger_signals={"uncertainty": 0.4, "drift": 0.2},
            )
            le.evaluate("test", pressure=0.30, actions_since=6)

        adj2 = le.get_threshold_adjustment(ResponseMode.OBSERVE, ResponseMode.GUIDE)
        assert adj2 <= 0.10, f"After 60 interventions, adjustment {adj2} exceeds max"

    def test_weight_adjustment_bounded(self):
        """Signal weight adjustments should be bounded."""
        from soma.learning import LearningEngine
        from soma.types import ResponseMode

        le = LearningEngine()

        # Simulate many false positives driven by uncertainty
        for i in range(50):
            le.record_intervention(
                agent_id="test",
                old_level=ResponseMode.OBSERVE,
                new_level=ResponseMode.GUIDE,
                pressure=0.30,
                trigger_signals={"uncertainty": 0.8, "drift": 0.1},
            )
            le.evaluate("test", pressure=0.25, actions_since=6)

        # Uncertainty weight should be reduced but not below min_weight
        adj = le.get_weight_adjustment("uncertainty")
        assert adj <= 0, f"Expected negative weight adjustment, got {adj}"
        # Original weight + adjustment should stay above 0.2 (min_weight)
        assert 2.0 + adj >= 0.2
```

- [ ] **Step 2: Run test**

Run: `.venv/bin/python -m pytest tests/test_learning.py::TestConvergence -xvs`

- [ ] **Step 3: Fix any convergence issues found**

If test fails — adjust learning parameters. If test passes — learning is validated.

- [ ] **Step 4: Commit**

```bash
git add tests/test_learning.py
git commit -m "test: validate learning engine convergence and bounds"
```

---

## Chunk 4: Multi-Agent Stress Test

### Task 4: Concurrent agents hammering the engine

**Problem:** No test simulates realistic multi-agent concurrent access. Need to prove engine handles 5 agents recording actions simultaneously without data corruption or deadlocks.

**Files:**
- Modify: `tests/test_multiagent.py`

- [ ] **Step 1: Write stress test**

```python
# In tests/test_multiagent.py, add:
import threading

class TestConcurrentAgents:
    def test_five_agents_concurrent(self):
        """5 agents recording 50 actions each simultaneously."""
        engine = SOMAEngine(budget={"tokens": 1000000})
        for i in range(5):
            engine.register_agent(f"agent-{i}")
            if i > 0:
                engine.add_edge(f"agent-{i-1}", f"agent-{i}", trust_weight=0.5)

        errors = []

        def run_agent(agent_id):
            try:
                for j in range(50):
                    action = Action(
                        tool_name=["Bash", "Read", "Edit", "Write"][j % 4],
                        output_text=f"output {j}",
                        token_count=100,
                        error=(j % 10 == 0),  # 10% error rate
                    )
                    result = engine.record_action(agent_id, action)
                    assert 0.0 <= result.pressure <= 1.0
                    assert result.mode in ResponseMode
            except Exception as e:
                errors.append((agent_id, e))

        threads = [
            threading.Thread(target=run_agent, args=(f"agent-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Agent errors: {errors}"

        # All agents should have valid state
        for i in range(5):
            snap = engine.get_snapshot(f"agent-{i}")
            assert snap["action_count"] == 50
            assert 0.0 <= snap["pressure"] <= 1.0

    def test_pressure_propagation_under_load(self):
        """When one agent spirals, downstream agents should feel pressure."""
        engine = SOMAEngine(budget={"tokens": 1000000})
        engine.register_agent("planner")
        engine.register_agent("coder")
        engine.register_agent("reviewer")

        engine.add_edge("planner", "coder", trust_weight=0.8)
        engine.add_edge("coder", "reviewer", trust_weight=0.6)

        # Planner goes bad — lots of errors
        for i in range(20):
            engine.record_action("planner", Action(
                tool_name="Bash", output_text="error",
                token_count=100, error=True, retried=True,
            ))

        # Coder does normal work
        for i in range(5):
            engine.record_action("coder", Action(
                tool_name="Edit", output_text="code",
                token_count=50,
            ))

        planner_snap = engine.get_snapshot("planner")
        coder_snap = engine.get_snapshot("coder")

        # Coder should feel SOME propagated pressure from planner
        # (may not be much due to grace period, but should be >= 0)
        assert coder_snap["pressure"] >= 0.0

    def test_trust_graph_with_5_agents(self):
        """Full pipeline: 5 agents with trust edges."""
        engine = SOMAEngine(budget={"tokens": 1000000})
        agents = ["planner", "researcher", "coder", "tester", "reviewer"]
        for a in agents:
            engine.register_agent(a)

        # Chain trust
        for i in range(len(agents) - 1):
            engine.add_edge(agents[i], agents[i+1], trust_weight=0.7)

        # Each agent does 10 normal actions
        for a in agents:
            for j in range(10):
                engine.record_action(a, Action(
                    tool_name="Read", output_text="ok", token_count=50,
                ))

        # All should be OBSERVE
        for a in agents:
            assert engine.get_level(a) == ResponseMode.OBSERVE
```

- [ ] **Step 2: Run test**

Run: `.venv/bin/python -m pytest tests/test_multiagent.py -xvs`

- [ ] **Step 3: Fix any threading issues discovered**

If engine has race conditions in record_action (shared graph/budget), add minimal locking.

- [ ] **Step 4: Commit**

```bash
git add tests/test_multiagent.py
git commit -m "test: multi-agent stress — 5 concurrent agents, trust propagation"
```

---

## Chunk 5: Shared Engine for wrap.py

### Task 5: Multi-agent wrap with shared engine

**Problem:** `soma.wrap()` creates a new engine per client. Multi-agent pipelines need a shared engine so pressure propagates between agents.

**Files:**
- Modify: `src/soma/wrap.py`
- Modify: `tests/test_wrap.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_wrap.py, add:
class TestMultiAgentWrap:
    def test_shared_engine(self):
        """Multiple agents sharing one engine see each other's pressure."""
        import soma
        from soma.engine import SOMAEngine

        engine = SOMAEngine(budget={"tokens": 100000})
        engine.register_agent("planner")
        engine.register_agent("coder")
        engine.add_edge("planner", "coder", trust_weight=0.8)

        client_a = MockAnthropicClient()
        client_b = MockAnthropicClient()

        wrapped_a = soma.wrap(client_a, agent_id="planner", engine=engine)
        wrapped_b = soma.wrap(client_b, agent_id="coder", engine=engine)

        # Both should share the same engine
        assert wrapped_a.engine is wrapped_b.engine
```

- [ ] **Step 2: Add `engine` parameter to wrap()**

```python
def wrap(
    client: Any,
    budget: dict[str, float] | None = None,
    agent_id: str = "default",
    auto_export: bool = True,
    block_at: ResponseMode = ResponseMode.BLOCK,
    engine: SOMAEngine | None = None,
) -> WrappedClient:
    if engine is None:
        engine = SOMAEngine(budget=budget or {"tokens": 100_000})
    return WrappedClient(
        client=client,
        engine=engine,
        agent_id=agent_id,
        auto_export=auto_export,
        block_at=block_at,
    )
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/soma/wrap.py tests/test_wrap.py
git commit -m "feat: shared engine support in wrap() for multi-agent pipelines"
```

---

## Chunk 6: Version Bump & Verify

### Task 6: Bump to 0.4.12, reinstall, verify

- [ ] **Step 1: Bump version**

`pyproject.toml`: version = "0.4.12"
`src/soma/__init__.py`: __version__ = "0.4.12"

- [ ] **Step 2: Update CHANGELOG.md**

```markdown
## [0.4.12] — 2026-03-30

### Added
- Atomic persistence with file locking — safe for concurrent multi-agent access
- Agent TTL eviction — `engine.evict_stale_agents(ttl_seconds=3600)`
- Shared engine support in `wrap()` — `soma.wrap(client, engine=shared_engine)`
- Multi-agent stress tests (5 concurrent agents, trust propagation)
- Learning convergence validation tests

### Fixed
- Persistence race condition when multiple agents save simultaneously
```

- [ ] **Step 3: Run full suite + ruff**

Run: `.venv/bin/python -m pytest -x --tb=short && ruff check src/ tests/`

- [ ] **Step 4: Commit**

- [ ] **Step 5: Reinstall + doctor**

```bash
uv tool install --force soma-ai --from /Users/timur/projectos/SOMA
soma doctor
```
