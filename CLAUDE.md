<!-- GSD:project-start source:PROJECT.md -->
## Project

**SOMA — Behavioral Monitoring for AI Agents**

SOMA is an open-source (MIT) behavioral monitoring and guidance system for AI agents. It observes agent actions in real-time, computes behavioral pressure from 5 vital signals, and injects corrective guidance into agent context before problems escalate. Think of it as a nervous system for AI agents — htop/Prometheus for the agent era.

Currently works as a Claude Code hook system (v0.4.12, published on PyPI as `soma-ai`). The goal is to become the industry standard for AI agent observability and safety — platform-agnostic, framework-agnostic, used by everyone from solo developers to enterprises.

**Core Value:** **Real-time behavioral guidance that makes AI agents safer and more effective without requiring human babysitting.**

If everything else fails, the closed-loop feedback system must work: actions → vitals → pressure → guidance → agent behavior change.

### Constraints

- **Language**: Python-first (core + CLI), TypeScript SDK later
- **License**: MIT — everything stays open
- **Compatibility**: Python 3.11+ (matching current CI matrix)
- **Dependencies**: Minimal core deps (rich, textual, tomli-w); everything else optional
- **Architecture**: Core must remain platform-agnostic — no Claude Code imports in core
- **Quality**: 90%+ test coverage for core, all CI green before release
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11+ - Core implementation language. Package requires `>=3.11` with explicit support for Python 3.11, 3.12, 3.13
- TOML - Configuration format for `soma.toml`
## Runtime
- Python 3.11, 3.12, 3.13 - All three versions tested in CI
- uv (UV package manager) - Used for dependency management
- pip - Fallback installation method
- Lockfile: `uv.lock` (present)
## Frameworks
- No external framework for core logic - Architecture is built on Python stdlib + carefully selected dependencies
- Textual 3.0+ - Terminal user interface for interactive dashboard (`src/soma/cli/hub.py`, `src/soma/cli/tabs/`)
- Hatchling - Build backend and package builder
- pytest 8.0+ - Testing framework with coverage support
- ruff - Linter for Python code quality (F and E error codes)
- pytest-cov - Coverage measurement plugin
## Key Dependencies
- `rich>=13.0` - Rich text and formatting for CLI output, progress bars, tables
- `textual>=3.0` - TUI framework for interactive monitoring dashboard
- `tomli-w>=1.0` - TOML serialization library for writing `soma.toml` config files
- Built-in `tomllib` - Standard library TOML parsing (Python 3.11+)
- `opentelemetry-api>=1.20` - OpenTelemetry API for observability integration (optional `otel` extra)
- `opentelemetry-sdk>=1.20` - OpenTelemetry SDK for exporting metrics (optional `otel` extra)
- `pytest>=8.0` - Test runner
- `pytest-cov` - Coverage plugin
- `ruff` - Linter
- `build` - Package building tool (used in CI)
- `colorama` - Cross-platform colored terminal output
- `iniconfig` - INI file parsing (pytest dependency)
- Various other support libraries
## Configuration
- Configuration stored in `soma.toml` (TOML format)
- Default config returned if `soma.toml` is missing: `src/soma/cli/config_loader.py`
- Session state stored in JSON: `~/.soma/state.json` and `~/.soma/engine_state.json`
- Environment variables: `CLAUDE_WORKING_DIRECTORY` (optional, for GSD workflow detection)
- Environment variables: `CLAUDE_HOOK` (for hook dispatcher routing)
- `pyproject.toml` - Standard Python project metadata and dependencies
- `soma.toml` - Main configuration file (in project root or current directory)
- `~/.soma/state.json` - User session state (default location)
- `~/.soma/engine_state.json` - Engine persistence (atomic write with file locking)
- `.coveragerc` - Coverage configuration for pytest-cov
## Platform Requirements
- Python 3.11+ (interpreter)
- pip or uv (package installation)
- Unix/POSIX systems for file locking in persistence (`fcntl` module with fallback)
- Optional: Node.js for JavaScript validation (if `validate_js` enabled in hooks)
- Python 3.11+ runtime
- No external service dependencies required
- Optional: OpenTelemetry collector for observability integration
- Deployment: PyPI package (`soma-ai`), installable via `pip install soma-ai`
## Entry Points
- `soma` - Main CLI tool (from `soma.cli.main:main`)
- `soma-hook` - Hook dispatcher for Claude Code (from `soma.hooks.claude_code:main`)
- `soma-statusline` - Status line formatter (from `soma.hooks.statusline:main`)
- `soma.quickstart()` - Fastest way to initialize engine
- `soma.wrap()` - Wrap any LLM client (e.g., `anthropic.Anthropic()`)
- `soma.SOMAEngine` - Core engine class
- `soma.replay_session()` - Replay recording for analysis
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Lowercase with underscores for modules: `engine.py`, `baseline.py`, `pressure.py`
- Plurals for groupings: `types.py` (enums and dataclasses), `errors.py` (exceptions)
- CLI files in `cli/` subdirectory: `main.py`, `replay_cli.py`, `config_loader.py`
- Tab modules in `cli/tabs/`: `dashboard.py`, `config_tab.py`, `replay_tab.py`
- PascalCase: `SOMAEngine`, `Baseline`, `EventBus`, `SessionRecorder`, `PressureGraph`
- Exception classes inherit from `SOMAError`: `AgentNotFound`, `NoBudget`
- Private classes prefixed with underscore: `_AgentState` in `engine.py`
- Dataclass names include domain: `Action`, `VitalsSnapshot`, `AgentConfig`
- snake_case: `record_action()`, `compute_uncertainty()`, `collect()`, `analyze()`
- Private functions prefixed with underscore: `_linear_trend()`, `_pattern_boost()` in `predictor.py`
- Factory/builder prefixes: `make_baseline()` in test files
- snake_case for all variables: `signal_pressure`, `baseline_vector`, `action_count`, `budget_health`
- Private instance attributes use leading underscore: `self._agents`, `self._budget`, `self._graph`
- Dictionary keys use snake_case: `token_usage`, `error_rate`, `agent_id`, `tool_name`
- Loop counters as single letters: `i`, `n` when clear from context
- Enum members in UPPERCASE: `OBSERVE`, `GUIDE`, `WARN`, `BLOCK`
- Enum class names PascalCase: `ResponseMode`, `AutonomyMode`, `DriftMode`, `InterventionOutcome`
- Enum members UPPERCASE: `ResponseMode.OBSERVE`, `AutonomyMode.HUMAN_IN_THE_LOOP`
- Type aliases as constants: `Level = ResponseMode` for backward compatibility
## Code Style
- Ruff formatter configured in `pyproject.toml`
- Line length: 88 characters is default (E501 ignored by linter, relying on formatter)
- Indentation: 4 spaces
- Tool: Ruff (`pyproject.toml` lines 45-56)
- Selected rules: `["F", "E"]` (pycodestyle + Pyflakes)
- Line length rule E501 ignored
- Per-file exceptions for tests and CLI tabs allow unused imports (F401, F811, F841)
- Full type hints on function signatures: `def record_action(self, agent_id: str, action: Action) -> ActionResult`
- Union types use `|` syntax (Python 3.10+): `str | None`, `dict[str, float]`
- Generic containers: `list[str]`, `dict[str, int]`
- Forward references: `from __future__ import annotations` at top of files (46 files use this)
- Return type annotations required: `-> None`, `-> ActionResult`, `-> dict[str, Any]`
## Import Organization
- No path aliases configured; all imports use full relative paths from `soma` package
- Example: `from soma.engine import SOMAEngine`, not imports with `@` or custom paths
- Barrel files: `__init__.py` exports public API with explicit `__all__` list
- See `/Users/timur/projectos/SOMA/src/soma/__init__.py` for main package exports
- Subpackages (cli, hooks) have their own `__init__.py`
## Error Handling
- All custom exceptions inherit from `SOMAError` base class in `errors.py`
- Exceptions include context: `AgentNotFound.__init__()` suggests agent registration
- Guard clauses check preconditions: `if agent_id not in self._agents: raise AgentNotFound(agent_id)`
- Silent catches for optional features: `try...except Exception: pass` when importing state modules (findings.py)
- Guard clauses prevent null/undefined access before operations
## Logging
- Use `print()` or `rich.print()` for CLI output
- No structured logging; mainly print for debugging
- Error messages go to `stdout` via exceptions
## Comments
- Document algorithm intent before complex math: see `baseline.py` EMA calculation
- Explain non-obvious domain logic: "Cold-start blending ensures early readings don't over-react"
- Section headers as visual separators: `# ------------------------------------------------------------------`
- Inline comments for config magic numbers: `# p=0-25%: silent, metrics only` in ResponseMode enum
- Logically group related methods with separator comments
- Headers like `# Mutation`, `# Queries` organize class methods by responsibility
- Headers like `# Helpers` separate utility functions from main tests
- Standard docstrings on classes: `"""Exponential moving average baseline with cold-start blending."""`
- Function docstrings explain purpose, not implementation: `"""Return the blended baseline for *signal*."""`
- Docstrings include usage examples: see `quickstart()` function with usage comment
- Type information in docstrings is minimal (prefer type hints on signature)
## Function Design
- Target small, focused functions: most core functions 10-30 lines
- Largest functions: `record_action()` in engine.py (~50 lines including docstring)
- Tests keep concerns isolated: single test per scenario
- Required params first, defaults last
- Type hints on all parameters
- Max 5-6 parameters; use dataclasses for complex structures (Action, AgentConfig)
- Keyword-only arguments where clarity helps: rarely used; mostly positional
- Single return type per function (no Union returns except Optional)
- Return dataclasses for structured results: `ActionResult`, `VitalsSnapshot`, `Prediction`
- Void functions explicitly return `None` type
## Module Design
- Explicit `__all__` lists in public modules (see `__init__.py` lines 37-45)
- Private modules (e.g., `_AgentState`) use leading underscore convention
- Public API documented with exports
- `/Users/timur/projectos/SOMA/src/soma/__init__.py` re-exports all public types and factories
- Subpackages have their own minimal `__init__.py` (e.g., cli, hooks)
- Each module focuses on one concern: `baseline.py` only handles EMA, `budget.py` only handles budgets
- Aggregator modules like `engine.py` orchestrate but keep orchestration clear
- Clear dependency direction: core modules (types.py, errors.py) have no dependencies
## Dataclass Patterns
- Frozen dataclasses for immutable value objects: `@dataclass(frozen=True)` for Action, VitalsSnapshot
- Mutable dataclasses for config: `@dataclass` for AgentConfig, Baseline state
- Slots enabled for memory efficiency: `@dataclass(frozen=True, slots=True)`
- Factory methods on classes: `@classmethod def from_dict()` for serialization roundtrips
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- **Actionable pipeline**: Actions enter the engine via `record_action()`, flow through vitals computation, pressure modeling, and guidance evaluation
- **Multi-agent support**: Agents are registered with distinct configurations and maintained in isolated state containers
- **Pressure graph**: Trust-weighted directed graph that propagates pressure across interconnected agents
- **Persistent state**: Engine state, predictors, quality trackers, and fingerprints saved to `~/.soma/` for session recovery
- **Hook-based integration**: Pre/Post tool-use hooks for Claude Code; extensible hook dispatch system
- **Composable guidance**: Pressure maps to response modes (OBSERVE → GUIDE → WARN → BLOCK) with configurable thresholds
## Layers
- Purpose: Main monitoring and control pipeline
- Location: `src/soma/engine.py`
- Contains: `SOMAEngine` class, `ActionResult` dataclass, `_AgentState` internal class
- Depends on: vitals, pressure, baseline, graph, guidance, budget, learning
- Used by: Client wrapper (`wrap.py`), CLI, hooks
- Purpose: Compute behavioral signals (uncertainty, drift, error rate, token usage, cost) from action history
- Location: `src/soma/vitals.py`
- Contains: `compute_uncertainty()`, `compute_drift()`, `compute_error_rate()`, `compute_resource_vitals()`, `compute_behavior_vector()`, `determine_drift_mode()`
- Depends on: types, baseline (for comparisons)
- Used by: engine (via `compute_all_vitals()`)
- Purpose: Aggregate individual signal pressures into a single 0-1 scalar representing agent state severity
- Location: `src/soma/pressure.py`
- Contains: `compute_signal_pressure()` (z-score via sigmoid), `compute_aggregate_pressure()` (blended mean+max)
- Depends on: types
- Used by: engine
- Purpose: Track exponential moving average (EMA) baselines for signals with cold-start blending to prevent false positives in early sessions
- Location: `src/soma/baseline.py`
- Contains: `Baseline` class with EMA update/query, cold-start blending
- Depends on: None (core math)
- Used by: engine, vitals (indirectly for z-score calculation)
- Purpose: Map pressure to response mode; evaluate tool calls for destructiveness; suggest actions
- Location: `src/soma/guidance.py`
- Contains: `pressure_to_mode()`, `evaluate()`, `GuidanceResponse`, destructive pattern detection
- Depends on: types, guidance thresholds
- Used by: engine, hooks
- Purpose: Model agent dependencies and propagate pressure across trust-weighted edges
- Location: `src/soma/graph.py`
- Contains: `PressureGraph` class with agent nodes, directed edges, damping-based propagation
- Depends on: types
- Used by: engine, persistence
- Purpose: Track spending across named resource dimensions (tokens, cost_usd)
- Location: `src/soma/budget.py`
- Contains: `MultiBudget` class with spend/replenish/health/burn_rate operations
- Depends on: None (core tracking)
- Used by: engine, wrap (for blocking exhausted budgets)
- Purpose: Adapt thresholds and signal weights based on intervention outcomes; track pending/resolved interventions
- Location: `src/soma/learning.py`
- Contains: `LearningEngine` class, intervention tracking, adaptive adjustment logic
- Depends on: types
- Used by: engine, persistence
- Purpose: Capture action sequences; persist/restore engine state across sessions
- Location: `src/soma/recorder.py`, `src/soma/persistence.py`
- Contains: `SessionRecorder`, `RecordedAction`, `save_engine_state()`, `load_engine_state()` with atomic writes
- Depends on: types
- Used by: engine, wrap, CLI
- Purpose: Detect workflow environment (GSD mode, action count, pressure); inform context-aware guidance
- Location: `src/soma/context.py`
- Contains: `SessionContext`, `detect_workflow_mode()`, `get_session_context()`
- Depends on: types
- Used by: hooks, guidance
- Purpose: Aggregate monitoring insights (quality, patterns, predictions, scope drift, RCA) into structured findings list
- Location: `src/soma/findings.py`
- Contains: `Finding` dataclass, `collect()` function that sources findings from multiple subsystems
- Depends on: state loaders (quality tracker, predictor, fingerprint engine)
- Used by: hooks (for output formatting)
- Purpose: Proxy around API clients to intercept all LLM calls; apply SOMA controls transparently
- Location: `src/soma/wrap.py`
- Contains: `WrappedClient`, `SomaBlocked`, `SomaBudgetExhausted` exceptions
- Depends on: engine, recorder, guidance
- Used by: Direct API integration (e.g., `soma.wrap(anthropic.Anthropic())`)
- Purpose: Integration points for Claude Code environment; dispatch to context-aware handlers
- Location: `src/soma/hooks/`
- Contains: `claude_code.py` (dispatcher), `pre_tool_use.py`, `post_tool_use.py`, `stop.py`, `notification.py`, `statusline.py`, `common.py` (shared utilities)
- Depends on: engine, state, guidance, findings, context
- Used by: Claude Code environment via `CLAUDE_HOOK` mechanism
- Purpose: Load/save transient subsystem state (quality tracker, predictor, fingerprint engine, task tracker) from `~/.soma/`
- Location: `src/soma/state.py`
- Contains: State path constants, getter/setter functions for each subsystem
- Depends on: subsystem classes
- Used by: hooks, findings, core modules for state recovery
- Purpose: User-facing command interface; dashboard, replay, config management, setup
- Location: `src/soma/cli/`
- Contains: `main.py` (argparse router), `config_loader.py`, tabs, wizard, status printer
- Depends on: engine, recorder, persistence
- Used by: `soma` CLI command
- Purpose: Centralized type definitions for Actions, VitalsSnapshot, AgentConfig, ResponseMode enums
- Location: `src/soma/types.py`
- Contains: ResponseMode (OBSERVE/GUIDE/WARN/BLOCK), AutonomyMode, DriftMode, Action, VitalsSnapshot, AgentConfig
- Depends on: None
- Used by: All layers
## Data Flow
- Engine state persisted atomically (temp file → fsync → rename) with file locking
- Subsystem state (quality tracker, predictor, fingerprint) loaded lazily via `state.py` getters
- Session recovery: `load_engine_state()` reconstructs engine from `engine_state.json`
## Key Abstractions
- Purpose: Immutable record of a single agent action
- Examples: `Action(tool_name="Bash", output_text="...", token_count=100)`
- Pattern: Frozen dataclass with optional metadata dict
- Purpose: Guidance response severity level
- Examples: `ResponseMode.OBSERVE` (silent), `ResponseMode.GUIDE` (suggest), `ResponseMode.WARN` (alert), `ResponseMode.BLOCK` (restrict destructive ops)
- Pattern: Ordered enum with comparison operators; legacy aliases for backward compatibility
- Purpose: Configuration for a monitored agent
- Examples: autonomy mode, system prompt, allowed tools, expensive/minimal tool lists
- Pattern: Mutable dataclass populated during `register_agent()`
- Purpose: Point-in-time behavioral health metrics
- Examples: uncertainty, drift, error_rate, token_usage, cost, drift_mode
- Pattern: Frozen dataclass, immutable for event emitting
- Purpose: Per-signal EMA with variance tracking and cold-start blending
- Examples: baseline for uncertainty starts at default 0.05, updates via EMA with blend toward default during cold start
- Pattern: Stateful class, updated incrementally as actions arrive
- Purpose: Directed graph modeling inter-agent dependencies
- Examples: Agent A's pressure propagates to dependent Agent B via trust-weighted edge
- Pattern: Adjacency list with damping-based convergent propagation
## Entry Points
- Location: `src/soma/__init__.py`
- Triggers: Direct import `import soma` or `from soma import SOMAEngine`
- Responsibilities: Export main classes (`SOMAEngine`, `ActionResult`, types), convenience function `quickstart()`
- Location: `src/soma/cli/main.py`
- Triggers: User runs `soma` command
- Responsibilities: Argparse router to subcommands (status, replay, wizard, setup, config)
- Location: `src/soma/wrap.py` (`wrap()` function, `WrappedClient` class)
- Triggers: `soma.wrap(client, ...)`
- Responsibilities: Proxy API client, intercept calls, apply engine rules, emit events
- Location: `src/soma/hooks/claude_code.py` (`main()` function)
- Triggers: `CLAUDE_HOOK=PreToolUse soma-hook` (or env var set by Claude Code)
- Responsibilities: Dispatch to handler, run pre/post tool-use logic, emit guidance/findings
- Location: `src/soma/cli/config_loader.py`
- Triggers: `load_config()` called during engine creation or hook setup
- Responsibilities: Parse `soma.toml`, load budget/thresholds/agent config, with fallback to defaults
## Error Handling
- `AgentNotFound`: Raised when accessing unknown agent; message includes registration hint
- `SomaBlocked`: Raised by WrappedClient when pressure or budget prevents call; includes agent_id, level, pressure
- `SomaBudgetExhausted`: Raised when dimension budget spent; includes dimension name
- `SOMAError`: Base class for custom exceptions
- State save/load wrapped in try/except with fallback to in-memory state
- Config loading fails gracefully to defaults
- Hooks catch exceptions and log rather than crash (never disrupt Claude Code)
- Baseline/graph operations guard against edge cases (division by zero, empty collections)
## Cross-Cutting Concerns
- Via `print()` to stdout (hooks redirect to JSON), rich console formatting in CLI
- Patterns: Debug info logged in verbose mode, warnings/errors always visible
- Budget limits validated in constructor
- Agent IDs checked for existence before operations
- Tool names validated against allowed list (if configured)
- File paths checked for sensitivity patterns (guidance layer)
- No built-in auth; assumes API client already authenticated
- Env vars for config paths (`.soma/` directory) via Path.home()
- File locking in persistence prevents concurrent state corruption
- Engine created via `SOMAEngine()` constructor or `from_config()`
- Agents registered via `register_agent()`
- Actions recorded via `record_action()` (or via wrapped client)
- State exported via `export_state()` (auto or manual)
- Session recovered via `load_engine_state()` on restart
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
