# Testing Patterns

**Analysis Date:** 2026-03-30

## Test Framework

**Runner:**
- pytest 8.0+ (configured in `pyproject.toml` lines 42-43)
- Config: `pyproject.toml`
  ```
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  ```

**Assertion Library:**
- Standard `assert` statements
- pytest built-in features: `pytest.approx()` for float comparisons, `pytest.raises()` for exceptions

**Run Commands:**
```bash
pytest                    # Run all tests in tests/ directory
pytest -v                 # Verbose output with test names
pytest tests/test_*.py    # Run specific test file
pytest -k "test_baseline" # Run tests matching pattern
pytest --cov              # Run with coverage (requires pytest-cov)
```

## Test File Organization

**Location:**
- All tests in `/Users/timur/projectos/SOMA/tests/` directory (separate from source)
- 26+ test files covering core modules, CLI, hooks, integration

**Naming:**
- Test files: `test_*.py` pattern (e.g., `test_engine.py`, `test_baseline.py`, `test_replay.py`)
- Test functions: `test_*()` pattern (e.g., `test_create_and_register()`)
- Test classes: `Test*` pattern (e.g., `TestSOMAEngine`, `TestConfigMigration`)

**Structure:**
```
tests/
├── conftest.py                 # Shared fixtures (normal_actions, error_actions)
├── test_api.py                 # Public API exports
├── test_baseline.py            # Baseline EMA behavior
├── test_budget.py              # Budget tracking
├── test_cli.py                 # CLI command tests
├── test_config.py              # Config loading and migration
├── test_engine.py              # Core SOMAEngine behavior
├── test_events.py              # EventBus pub/sub
├── test_findings.py            # Finding collection
├── test_graph.py               # Pressure graph
├── test_patterns.py            # Pattern analysis
├── test_pressure.py            # Pressure computation
├── test_recorder.py            # Session recording
├── test_replay.py              # Session replay
├── test_stress.py              # Behavioral stress tests
└── ...more test files
```

## Test Structure

**Suite Organization:**
```python
# From test_engine.py
class TestSOMAEngine:
    def test_create_and_register(self):
        e = SOMAEngine(budget={"tokens": 10000})
        e.register_agent("a")
        assert e.get_level("a") == ResponseMode.OBSERVE
```

Or standalone functions:
```python
# From test_baseline.py
def test_cold_start_uses_defaults():
    """Before any observations the baseline returns the signal default."""
    b = make_baseline()
    for signal, default in DEFAULTS.items():
        assert b.get(signal) == pytest.approx(default)
```

**Patterns:**
- Setup: Create fixtures (engine, recorder, actions) at start of test
- Action: Execute the behavior being tested
- Assert: Verify expected state/output
- Docstrings explain test intent before code

## Mocking

**Framework:** unittest.mock

**Patterns:**
```python
# From test_claude_code_layer.py
from unittest.mock import patch

@patch("soma.cli.main.get_engine")
def test_cli_calls_get_engine(mock_get_engine):
    # Configure mock
    mock_get_engine.return_value = engine
    # Call code under test
    result = main()
    # Verify mock was called
    mock_get_engine.assert_called_once()
```

**What to Mock:**
- External dependencies: file I/O, CLI main entry points, hooks integration
- Runtime behavior that varies: `get_engine()` in CLI tests
- Side effects: `@patch()` decorator for functions with external dependencies

**What NOT to Mock:**
- Core domain objects (Action, VitalsSnapshot, Baseline, etc.)
- Internal orchestration (SOMAEngine interactions)
- Computation functions (pressure, vitals, patterns)

## Fixtures and Factories

**Test Data (conftest.py):**
```python
# Shared fixtures across all tests
@pytest.fixture
def normal_actions():
    """10 normal, non-error actions with varied tools."""
    tools = ["search", "edit", "bash", "read", "search", "edit", "bash", "read", "search", "edit"]
    return [
        Action(
            tool_name=tools[i],
            output_text=f"Normal output from step {i}: " + "abcdefghij " * 5,
            token_count=100 + i * 10,
            cost=0.005,
            duration_sec=1.0 + i * 0.1,
        )
        for i in range(10)
    ]


@pytest.fixture
def error_actions():
    """10 error actions — all retries, same tool, repetitive output."""
    return [
        Action(
            tool_name="bash",
            output_text="error error error " * 10,
            token_count=200,
            cost=0.01,
            error=True,
            retried=True,
            duration_sec=0.5,
        )
        for _ in range(10)
    ]
```

**Test-specific Fixtures (e.g., test_replay.py):**
```python
@pytest.fixture
def normal_recording(normal_actions) -> SessionRecorder:
    """SessionRecorder with 10 normal actions under a single agent."""
    rec = SessionRecorder()
    for action in normal_actions:
        rec.record("agent-1", action)
    return rec
```

**Location:**
- Global fixtures: `/Users/timur/projectos/SOMA/tests/conftest.py`
- Local fixtures: In test file requiring them (e.g., `test_replay.py` defines `normal_recording`)

**Factory Functions in Tests:**
```python
# From test_baseline.py
def make_baseline(**kwargs) -> Baseline:
    return Baseline(**kwargs)
```

## Coverage

**Requirements:** No enforced minimum (as of pyproject.toml)

**View Coverage:**
```bash
pytest --cov=soma --cov-report=html    # Generate HTML report
pytest --cov=soma --cov-report=term    # Terminal summary
```

## Test Types

**Unit Tests:**
- Scope: Single module/class in isolation
- Approach: Test individual functions with direct inputs
- Examples: `test_baseline.py`, `test_pressure.py`, `test_budget.py`
- Use fixtures for test data, not mocks for internal dependencies

**Integration Tests:**
- Scope: Multiple components working together
- Approach: Create engine, register agents, record actions, verify results
- Examples: `test_engine.py` class tests orchestration of pressure graph, budget, baseline
- Stress tests in `test_stress.py`: extreme scenarios testing multi-agent contagion, recovery

**E2E Tests:**
- Scope: Full end-to-end workflows
- Framework: Not formalized; some behavior tests in `test_stress.py` simulate real workflows
- Examples: `test_api.py` smoke test for quickstart(), `test_config.py` full config load roundtrip

## Common Patterns

**Assertion Pattern - Float Tolerance:**
```python
# From test_baseline.py
assert b.get("uncertainty") > 0.30

# With pytest.approx for strict tolerance
assert result == pytest.approx(0.119, abs=0.001)
```

**Assertion Pattern - Enum Comparison:**
```python
# From test_engine.py
assert r.mode == ResponseMode.OBSERVE
assert r.mode >= ResponseMode.GUIDE  # Enums have comparison operators
```

**Assertion Pattern - Collections:**
```python
# From test_events.py
assert received == [{"value": 1}]
assert log == ["a", "b"]
assert captured == {"key": "value", "num": 7}
```

**Assertion Pattern - Existence:**
```python
# From test_api.py
for name in soma.__all__:
    assert hasattr(soma, name)
```

**Async Testing:**
Not used; all tests are synchronous.

**Error Testing:**
```python
# From test_engine.py
def test_escalation_on_errors(self, error_actions):
    e = SOMAEngine(budget={"tokens": 100000})
    e.register_agent("a")
    for action in error_actions:
        r = e.record_action("a", action)
    r = e.record_action("a", error_actions[0])
    assert r.mode.value >= ResponseMode.GUIDE.value

# With pytest.raises
with pytest.raises(AgentNotFound) as exc_info:
    engine.get_level("nonexistent-agent")
```

**Parametrized Tests:**
No `@pytest.mark.parametrize` used; similar behavior achieved with loops or multiple test functions

**Setup/Teardown:**
- setUp: Create engine, register agents at test start
- Teardown: None needed (tests are stateless, no cleanup required)
- Fixtures handle test data creation (conftest.py)

## Test Organization by Domain

**Core Logic Tests:**
- `test_baseline.py`: EMA computation, cold-start blending
- `test_pressure.py`: Signal pressure, aggregate pressure
- `test_budget.py`: Budget tracking, overspend
- `test_graph.py`: Pressure graph state, effective pressure
- `test_patterns.py`: Behavioral pattern detection
- `test_findings.py`: Finding collection and reporting

**Engine Tests:**
- `test_engine.py`: Main engine class, agent registration, action recording
- `test_stress.py`: Behavioral stress tests under extreme conditions

**Integration Tests:**
- `test_replay.py`: Session replay functionality
- `test_recorder.py`: Session recording and export
- `test_api.py`: Public API surface
- `test_config.py`: Config loading, migration, engine creation

**CLI/Hook Tests:**
- `test_cli.py`: CLI command execution
- `test_replay_cli.py`: Replay command specifics
- `test_claude_code_layer.py`: Claude Code hook integration
- `test_wizard.py`: Sensitivity wizard config presets

**Edge Case Tests:**
- `test_edge_cases.py`: Boundary conditions
- `test_context_control.py`: Context layer behavior
- `test_vitals.py`: Vitals computation edge cases

## Testing Best Practices in This Codebase

**Arrange-Act-Assert:**
```python
def test_record_normal(self):
    # Arrange
    e = SOMAEngine(budget={"tokens": 100000})
    e.register_agent("a")

    # Act
    for i in range(10):
        r = e.record_action("a", Action(...))

    # Assert
    assert r.mode == ResponseMode.OBSERVE
```

**Descriptive Test Names:**
- `test_cold_start_uses_defaults()` clearly states what is tested
- `test_escalation_on_errors()` describes the scenario
- `test_multi_agent_pressure()` indicates domain

**Focused Tests:**
- One assertion concept per test (may have multiple asserts for same concept)
- Clear docstring explaining intent
- Use fixtures to avoid setup duplication

**Use Fixtures Over Repetition:**
- `normal_actions` and `error_actions` reused across many tests
- Test-specific fixtures in local files when needed
- Factory functions for builder patterns (rare)

**No Brittle Tests:**
- Avoid testing implementation details (e.g., internal `_count` variable)
- Test behavior and outcomes
- Use approximate assertions for floats

---

*Testing analysis: 2026-03-30*
