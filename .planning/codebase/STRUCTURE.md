# Codebase Structure

**Analysis Date:** 2026-03-30

## Directory Layout

```
SOMA/
├── src/soma/                      # Main package
│   ├── __init__.py                # Public API exports + quickstart()
│   ├── engine.py                  # SOMAEngine, ActionResult, _AgentState
│   ├── types.py                   # Shared enums + dataclasses
│   ├── vitals.py                  # Behavioral signal computation
│   ├── pressure.py                # Pressure aggregation (z-score → sigmoid)
│   ├── baseline.py                # EMA with cold-start blending
│   ├── graph.py                   # PressureGraph with trust-weighted propagation
│   ├── guidance.py                # Mode mapping, destructiveness checking, suggestions
│   ├── budget.py                  # MultiBudget spend tracking across dimensions
│   ├── learning.py                # LearningEngine for adaptive threshold adjustment
│   ├── recorder.py                # SessionRecorder for action capture
│   ├── replay.py                  # replay_session() for playback analysis
│   ├── persistence.py             # save/load_engine_state with atomic writes
│   ├── events.py                  # EventBus for pub/sub event emission
│   ├── state.py                   # State loaders for quality/predictor/fingerprint/task
│   ├── context.py                 # SessionContext, workflow mode detection
│   ├── context_control.py         # Context isolation for concurrent requests
│   ├── findings.py                # Finding dataclass, collect() aggregator
│   ├── patterns.py                # Pattern detection and analysis
│   ├── quality.py                 # QualityTracker for write/bash grade
│   ├── predictor.py               # PressurePredictor for next-action forecast
│   ├── fingerprint.py             # FingerprintEngine for behavior divergence
│   ├── task_tracker.py            # TaskTracker for task/phase awareness
│   ├── rca.py                     # Root cause analysis for findings
│   ├── ring_buffer.py             # RingBuffer[T] FIFO for action history
│   ├── wrap.py                    # WrappedClient for transparent API interception
│   ├── testing.py                 # Test utilities (mock client, assertion helpers)
│   ├── errors.py                  # Custom exceptions (AgentNotFound, SomaBlocked)
│   ├── daemon.py                  # Background daemon process support
│   ├── inbox.py                   # Message inbox for async communication
│   ├── py.typed                   # PEP 561 marker for type checking
│   │
│   ├── cli/                       # Command-line interface
│   │   ├── __init__.py
│   │   ├── main.py                # Argparse router: status, replay, wizard, setup, config
│   │   ├── config_loader.py       # soma.toml parsing, config resolution
│   │   ├── hub.py                 # Hub management
│   │   ├── setup_claude.py        # Claude environment setup
│   │   ├── replay_cli.py          # Interactive TUI replay (uses textual)
│   │   ├── wizard.py              # Interactive setup wizard (uses rich)
│   │   ├── status.py              # Status printer
│   │   └── tabs/                  # Dashboard tabs (textual TUI)
│   │       ├── __init__.py
│   │       ├── dashboard.py       # Main dashboard container
│   │       ├── agents.py          # Agents tab
│   │       ├── config_tab.py      # Configuration tab
│   │       └── replay_tab.py      # Replay session tab
│   │
│   └── hooks/                     # Claude Code integration hooks
│       ├── __init__.py
│       ├── claude_code.py         # Hook dispatcher (CLAUDE_HOOK env var)
│       ├── common.py              # Shared utilities, hook config, state paths
│       ├── pre_tool_use.py        # PreToolUse hook: validation, prediction
│       ├── post_tool_use.py       # PostToolUse hook: recording, findings
│       ├── stop.py                # Stop hook: final state export
│       ├── notification.py        # Notification hook: user communication
│       └── statusline.py          # Statusline hook: real-time feedback
│
├── tests/                         # Test suite
│   ├── conftest.py                # Pytest fixtures (engine, config, etc)
│   ├── test_*.py                  # Module-level tests (30+ test files)
│   └── examples/                  # Example integrations
│
├── docs/                          # Documentation
│   ├── SPEC.md                    # Full SOMA specification
│   ├── API.md                     # Python API reference
│   └── ...
│
├── examples/                      # Example projects
│   ├── basic_claude.py            # Basic Claude integration
│   └── ...
│
├── skills/                        # Skill definitions for extensibility
│
├── .github/                       # GitHub workflows
│   ├── workflows/
│   │   └── ci.yml                 # Test + coverage CI
│   └── ...
│
├── .planning/                     # GSD planning (created during phase planning)
│   └── codebase/                  # Codebase analysis docs
│       ├── ARCHITECTURE.md
│       ├── STRUCTURE.md
│       ├── CONVENTIONS.md         # (if quality focus)
│       ├── TESTING.md             # (if quality focus)
│       ├── STACK.md               # (if tech focus)
│       ├── INTEGRATIONS.md        # (if tech focus)
│       └── CONCERNS.md            # (if concerns focus)
│
├── pyproject.toml                 # Package metadata, pytest config, ruff config
├── soma.toml                      # SOMA configuration (budget, thresholds, agents)
├── .env (not committed)           # Local dev overrides
├── README.md                      # User-facing overview
├── CHANGELOG.md                   # Version history
├── ROADMAP.md                     # Future plans
└── LICENSE                        # MIT
```

## Directory Purposes

**`src/soma/`:**
- Purpose: Main package — all production code
- Contains: Core engine, types, computation layers, budget, graph, learning, persistence
- Key files: `engine.py` (entry point), `types.py` (type definitions), `vitals.py`/`pressure.py` (computation)

**`src/soma/cli/`:**
- Purpose: User-facing command-line interface
- Contains: Argparse CLI router, config loader, wizard, replay TUI, dashboard tabs
- Key files: `main.py` (entry point), `config_loader.py` (config resolution)
- Entry point: `soma` CLI command (from `pyproject.toml` scripts)

**`src/soma/hooks/`:**
- Purpose: Claude Code environment integration
- Contains: Hook dispatcher, pre/post tool-use handlers, findings aggregation, statusline
- Key files: `claude_code.py` (dispatcher), `pre_tool_use.py` (validation), `post_tool_use.py` (recording)
- Entry point: `soma-hook` CLI command (invoked by Claude Code via `CLAUDE_HOOK` env var)

**`tests/`:**
- Purpose: Pytest-based test suite
- Contains: Unit tests for each module, integration tests, conftest fixtures
- Key files: `conftest.py` (fixtures), `test_engine.py`, `test_vitals.py`, `test_guidance.py`
- Run: `pytest` or `pytest tests/test_engine.py -v`

**`docs/`:**
- Purpose: Technical documentation
- Contains: SPEC.md (full specification), API.md (reference), architecture diagrams
- Generated: API docs via `pdoc3` (CI)

**`examples/`:**
- Purpose: Reference implementations
- Contains: Basic Claude integration, multi-agent setup, custom wrapper usage
- Purpose: Show common patterns and integration approaches

**`skills/`:**
- Purpose: Extensible skill definitions
- Contains: JSON/YAML skill metadata (not code)
- Usage: Referenced by task tracker and pattern engine

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents (created by `/gsd:map-codebase`)
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md
- Consumed by: `/gsd:plan-phase` and `/gsd:execute-phase` to guide implementation

## Key File Locations

**Entry Points:**

- **Library**: `src/soma/__init__.py` — Exports `SOMAEngine`, types, `wrap()`, `quickstart()`, etc.
- **CLI**: `src/soma/cli/main.py` — Argparse router for `soma` command
- **Hook**: `src/soma/hooks/claude_code.py` — Dispatcher for Claude Code hooks
- **Wrapper**: `src/soma/wrap.py` — `wrap()` function and `WrappedClient` class
- **Config**: `src/soma/cli/config_loader.py` — Loads `soma.toml`

**Configuration:**

- `soma.toml` — User-facing config (budget, thresholds, agent settings, hooks)
- `pyproject.toml` — Package metadata, dependencies, build config
- `.env` — Local dev overrides (not committed, ignored by git)
- `.coveragerc` — Coverage thresholds

**Core Logic:**

- `src/soma/engine.py` — Main monitoring pipeline
- `src/soma/vitals.py` — Behavioral signal computation
- `src/soma/pressure.py` — Pressure aggregation
- `src/soma/guidance.py` — Mode mapping and tool evaluation
- `src/soma/baseline.py` — EMA baseline tracking
- `src/soma/graph.py` — Multi-agent pressure propagation

**Testing:**

- `tests/conftest.py` — Pytest fixtures
- `tests/test_engine.py` — Core engine tests
- `tests/test_vitals.py` — Signal computation tests
- `tests/test_guidance.py` — Guidance evaluation tests
- `tests/test_*.py` — Module-specific tests (30+ files)

## Naming Conventions

**Files:**

- Lowercase with underscores: `session_recorder.py`, `pressure_graph.py`, `config_loader.py`
- Test files: `test_<module>.py` (collocated with tests/ directory)
- Hooks: `<hook_type>.py` (pre_tool_use.py, post_tool_use.py, notification.py)
- CLI subcommands: As methods in main.py (`_cmd_status()`, `_cmd_replay()`)

**Directories:**

- Lowercase: `cli/`, `hooks/`, `tests/`, `docs/`, `examples/`, `skills/`
- Package hierarchy: `soma/`, `soma/cli/`, `soma/hooks/`
- Planning docs: `.planning/codebase/` (created by orchestrator)

**Functions:**

- Lowercase with underscores: `compute_uncertainty()`, `record_action()`, `get_level()`
- Underscore prefix for private: `_compute_vitals_for_agent()`, `_AgentState`
- Command handlers: `_cmd_<name>()` (e.g., `_cmd_status()`)
- State getters: `get_<resource>()` (e.g., `get_quality_tracker()`)

**Classes:**

- PascalCase: `SOMAEngine`, `SessionRecorder`, `PressureGraph`, `Baseline`, `ResponseMode`
- Internal state: `_AgentState`, `_Node`, `_Edge`
- Dataclasses: `Action`, `VitalsSnapshot`, `AgentConfig`, `GuidanceResponse`, `Finding`

**Constants:**

- UPPERCASE: `DEFAULT_WEIGHTS`, `DEFAULT_THRESHOLDS`, `SOMA_DIR`, `ACTION_LOG_MAX`
- Enums: `ResponseMode.OBSERVE`, `AutonomyMode.HUMAN_ON_THE_LOOP`, `DriftMode.INFORMATIONAL`

**Variables:**

- Lowercase with underscores: `agent_id`, `pressure`, `token_count`, `baseline_vector`
- Single-letter for loops: `for p in pressures:`, `for e in edges:`

## Where to Add New Code

**New Feature (e.g., new signal type):**

1. **Add signal computation** in `src/soma/vitals.py`:
   - New `compute_<signal>()` function
   - Return float in [0, 1]
   - Called from `compute_all_vitals()`

2. **Add to VitalsSnapshot** in `src/soma/types.py`:
   - Add new field to `VitalsSnapshot` dataclass
   - Default value (e.g., 0.0)

3. **Add pressure weight** in `src/soma/pressure.py`:
   - Add to `DEFAULT_WEIGHTS` dict
   - Include in `compute_aggregate_pressure()` logic

4. **Add tests** in `tests/test_<module>.py`:
   - New test function `test_compute_<signal>()`
   - Test edge cases (empty input, extreme values)
   - Test integration with engine

5. **Update docs** in `docs/SPEC.md`:
   - Document new signal in the vitals section
   - Include computation method and thresholds

**New Component/Module:**

1. **Create in `src/soma/<name>.py`**:
   - Follow existing patterns (class definition, type hints, docstrings)
   - Avoid circular imports

2. **Add to `__init__.py`** if public:
   - Export in `__all__`
   - Add to docstring

3. **Create tests** in `tests/test_<name>.py`:
   - Use fixtures from `conftest.py`
   - Follow existing test structure

4. **Add to pipeline** in `engine.py` if needed:
   - Import in engine
   - Call from appropriate method
   - Handle errors gracefully

**New CLI Command:**

1. **Add handler function** in `src/soma/cli/main.py`:
   - Name: `_cmd_<command>()`
   - Parameter: `argparse.Namespace`
   - Return: None (prints to stdout)

2. **Add subparser** in `main()`:
   - `subparsers.add_parser('<command>', help='...')`
   - Set defaults to handler function

3. **Add tests** in `tests/test_cli.py`:
   - Mock config loader if needed
   - Check output format
   - Test error cases

**New Hook:**

1. **Create handler** in `src/soma/hooks/<hook_name>.py`:
   - `main()` function as entry point
   - Handle exceptions (never crash)
   - Return JSON or print formatted text

2. **Register in dispatcher** in `src/soma/hooks/claude_code.py`:
   - Add to `DISPATCH` dict
   - Map hook type name to handler function

3. **Add tests** in `tests/test_claude_code_layer.py`:
   - Mock environment variables
   - Test JSON output format
   - Test error handling

**Utilities:**

- **Shared math**: `src/soma/baseline.py`, `src/soma/pressure.py`
- **Shared state loaders**: `src/soma/state.py`
- **Hook utilities**: `src/soma/hooks/common.py`
- **Testing utilities**: `src/soma/testing.py`

## Special Directories

**`.planning/`:**
- Purpose: GSD workflow planning documents
- Generated: By `/gsd:map-codebase`, `/gsd:plan-phase`
- Committed: Yes (part of workflow)
- Contains: STATE.md (workflow state), codebase/ (analysis docs), phases/ (phase plans)

**`dist/`:**
- Purpose: Build output
- Generated: By `hatchling` during `pip install -e .`
- Committed: No (in .gitignore)
- Contains: Wheel/sdist files

**`.pytest_cache/`:**
- Purpose: Pytest internal cache
- Generated: By pytest during test runs
- Committed: No (in .gitignore)

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: By Python interpreter
- Committed: No (in .gitignore)

**`.ruff_cache/`:**
- Purpose: Ruff linter cache
- Generated: By ruff during linting
- Committed: No (in .gitignore)

**`.soma/`:**
- Purpose: User state directory in home folder
- Created: Dynamically at runtime
- Committed: No (outside repo)
- Contains: `engine_state.json`, `state.json`, `action_log.json`, `predictor.json`, `fingerprint.json`, `quality.json`, `task_tracker.json`

## State & Persistence Paths

**In-memory state:**
- Engine maintains `_agents`, `_budget`, `_graph`, `_learning`, `_events`
- Session recorder maintains action list
- All lost on process exit unless persisted

**Persisted state (in `~/.soma/`):**
- `engine_state.json` — Full engine state for recovery (agents, budget, graph, learning)
- `state.json` — Summary snapshot (agents, budget health) for dashboard
- `action_log.json` — Recent actions for pattern analysis
- `predictor.json` — Pressure predictor state
- `fingerprint.json` — Behavior fingerprint state
- `quality.json` — Write/bash quality tracker
- `task_tracker.json` — Task/phase awareness state

**File locking:**
- Uses `fcntl.flock()` on Unix (atomic writes + concurrent reads)
- Fallback to direct write on systems without fcntl

---

*Structure analysis: 2026-03-30*
