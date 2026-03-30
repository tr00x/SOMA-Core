# Coding Conventions

**Analysis Date:** 2026-03-30

## Naming Patterns

**Files:**
- Lowercase with underscores for modules: `engine.py`, `baseline.py`, `pressure.py`
- Plurals for groupings: `types.py` (enums and dataclasses), `errors.py` (exceptions)
- CLI files in `cli/` subdirectory: `main.py`, `replay_cli.py`, `config_loader.py`
- Tab modules in `cli/tabs/`: `dashboard.py`, `config_tab.py`, `replay_tab.py`

**Classes:**
- PascalCase: `SOMAEngine`, `Baseline`, `EventBus`, `SessionRecorder`, `PressureGraph`
- Exception classes inherit from `SOMAError`: `AgentNotFound`, `NoBudget`
- Private classes prefixed with underscore: `_AgentState` in `engine.py`
- Dataclass names include domain: `Action`, `VitalsSnapshot`, `AgentConfig`

**Functions:**
- snake_case: `record_action()`, `compute_uncertainty()`, `collect()`, `analyze()`
- Private functions prefixed with underscore: `_linear_trend()`, `_pattern_boost()` in `predictor.py`
- Factory/builder prefixes: `make_baseline()` in test files

**Variables:**
- snake_case for all variables: `signal_pressure`, `baseline_vector`, `action_count`, `budget_health`
- Private instance attributes use leading underscore: `self._agents`, `self._budget`, `self._graph`
- Dictionary keys use snake_case: `token_usage`, `error_rate`, `agent_id`, `tool_name`
- Loop counters as single letters: `i`, `n` when clear from context
- Enum members in UPPERCASE: `OBSERVE`, `GUIDE`, `WARN`, `BLOCK`

**Types/Enums:**
- Enum class names PascalCase: `ResponseMode`, `AutonomyMode`, `DriftMode`, `InterventionOutcome`
- Enum members UPPERCASE: `ResponseMode.OBSERVE`, `AutonomyMode.HUMAN_IN_THE_LOOP`
- Type aliases as constants: `Level = ResponseMode` for backward compatibility

## Code Style

**Formatting:**
- Ruff formatter configured in `pyproject.toml`
- Line length: 88 characters is default (E501 ignored by linter, relying on formatter)
- Indentation: 4 spaces

**Linting:**
- Tool: Ruff (`pyproject.toml` lines 45-56)
- Selected rules: `["F", "E"]` (pycodestyle + Pyflakes)
- Line length rule E501 ignored
- Per-file exceptions for tests and CLI tabs allow unused imports (F401, F811, F841)

**Type Hints:**
- Full type hints on function signatures: `def record_action(self, agent_id: str, action: Action) -> ActionResult`
- Union types use `|` syntax (Python 3.10+): `str | None`, `dict[str, float]`
- Generic containers: `list[str]`, `dict[str, int]`
- Forward references: `from __future__ import annotations` at top of files (46 files use this)
- Return type annotations required: `-> None`, `-> ActionResult`, `-> dict[str, Any]`

## Import Organization

**Order:**
1. `from __future__ import annotations` (almost universal across codebase)
2. Standard library imports: `import time`, `import json`, `from pathlib import Path`
3. Third-party imports: `import pytest`, `import tomli_w`, `from rich import ...`
4. Local imports: `from soma.types import ...`, `from soma.engine import ...`

**Path Aliases:**
- No path aliases configured; all imports use full relative paths from `soma` package
- Example: `from soma.engine import SOMAEngine`, not imports with `@` or custom paths

**Module Structure:**
- Barrel files: `__init__.py` exports public API with explicit `__all__` list
- See `/Users/timur/projectos/SOMA/src/soma/__init__.py` for main package exports
- Subpackages (cli, hooks) have their own `__init__.py`

## Error Handling

**Strategy:** Custom exception hierarchy with helpful error messages

**Patterns:**
- All custom exceptions inherit from `SOMAError` base class in `errors.py`
- Exceptions include context: `AgentNotFound.__init__()` suggests agent registration
- Guard clauses check preconditions: `if agent_id not in self._agents: raise AgentNotFound(agent_id)`
- Silent catches for optional features: `try...except Exception: pass` when importing state modules (findings.py)
- Guard clauses prevent null/undefined access before operations

## Logging

**Framework:** No external logging framework used

**Patterns:**
- Use `print()` or `rich.print()` for CLI output
- No structured logging; mainly print for debugging
- Error messages go to `stdout` via exceptions

## Comments

**When to Comment:**
- Document algorithm intent before complex math: see `baseline.py` EMA calculation
- Explain non-obvious domain logic: "Cold-start blending ensures early readings don't over-react"
- Section headers as visual separators: `# ------------------------------------------------------------------`
- Inline comments for config magic numbers: `# p=0-25%: silent, metrics only` in ResponseMode enum

**Code Block Organization:**
- Logically group related methods with separator comments
- Headers like `# Mutation`, `# Queries` organize class methods by responsibility
- Headers like `# Helpers` separate utility functions from main tests

**JSDoc/TSDoc:**
- Standard docstrings on classes: `"""Exponential moving average baseline with cold-start blending."""`
- Function docstrings explain purpose, not implementation: `"""Return the blended baseline for *signal*."""`
- Docstrings include usage examples: see `quickstart()` function with usage comment
- Type information in docstrings is minimal (prefer type hints on signature)

## Function Design

**Size:**
- Target small, focused functions: most core functions 10-30 lines
- Largest functions: `record_action()` in engine.py (~50 lines including docstring)
- Tests keep concerns isolated: single test per scenario

**Parameters:**
- Required params first, defaults last
- Type hints on all parameters
- Max 5-6 parameters; use dataclasses for complex structures (Action, AgentConfig)
- Keyword-only arguments where clarity helps: rarely used; mostly positional

**Return Values:**
- Single return type per function (no Union returns except Optional)
- Return dataclasses for structured results: `ActionResult`, `VitalsSnapshot`, `Prediction`
- Void functions explicitly return `None` type

## Module Design

**Exports:**
- Explicit `__all__` lists in public modules (see `__init__.py` lines 37-45)
- Private modules (e.g., `_AgentState`) use leading underscore convention
- Public API documented with exports

**Barrel Files:**
- `/Users/timur/projectos/SOMA/src/soma/__init__.py` re-exports all public types and factories
- Subpackages have their own minimal `__init__.py` (e.g., cli, hooks)

**Single Responsibility:**
- Each module focuses on one concern: `baseline.py` only handles EMA, `budget.py` only handles budgets
- Aggregator modules like `engine.py` orchestrate but keep orchestration clear
- Clear dependency direction: core modules (types.py, errors.py) have no dependencies

## Dataclass Patterns

**Usage:**
- Frozen dataclasses for immutable value objects: `@dataclass(frozen=True)` for Action, VitalsSnapshot
- Mutable dataclasses for config: `@dataclass` for AgentConfig, Baseline state
- Slots enabled for memory efficiency: `@dataclass(frozen=True, slots=True)`
- Factory methods on classes: `@classmethod def from_dict()` for serialization roundtrips

**Example from types.py:**
```python
@dataclass(frozen=True, slots=True)
class Action:
    """A single agent action recorded by SOMA."""
    tool_name: str
    output_text: str
    token_count: int = 0
    cost: float = 0.0
    error: bool = False
    retried: bool = False
    duration_sec: float = 0.0
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

*Convention analysis: 2026-03-30*
