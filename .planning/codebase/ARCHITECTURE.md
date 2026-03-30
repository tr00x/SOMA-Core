# Architecture

**Analysis Date:** 2026-03-30

## Pattern Overview

**Overall:** Pipeline + Multi-layer Engine Architecture

SOMA is a behavioral monitoring and control system for AI agents. The architecture follows a **layered pipeline model** where actions flow through: **capture → vitals computation → pressure aggregation → guidance decision → optional blocking**.

**Key Characteristics:**
- **Actionable pipeline**: Actions enter the engine via `record_action()`, flow through vitals computation, pressure modeling, and guidance evaluation
- **Multi-agent support**: Agents are registered with distinct configurations and maintained in isolated state containers
- **Pressure graph**: Trust-weighted directed graph that propagates pressure across interconnected agents
- **Persistent state**: Engine state, predictors, quality trackers, and fingerprints saved to `~/.soma/` for session recovery
- **Hook-based integration**: Pre/Post tool-use hooks for Claude Code; extensible hook dispatch system
- **Composable guidance**: Pressure maps to response modes (OBSERVE → GUIDE → WARN → BLOCK) with configurable thresholds


## Layers

**Core Engine:**
- Purpose: Main monitoring and control pipeline
- Location: `src/soma/engine.py`
- Contains: `SOMAEngine` class, `ActionResult` dataclass, `_AgentState` internal class
- Depends on: vitals, pressure, baseline, graph, guidance, budget, learning
- Used by: Client wrapper (`wrap.py`), CLI, hooks

**Vitals Computation:**
- Purpose: Compute behavioral signals (uncertainty, drift, error rate, token usage, cost) from action history
- Location: `src/soma/vitals.py`
- Contains: `compute_uncertainty()`, `compute_drift()`, `compute_error_rate()`, `compute_resource_vitals()`, `compute_behavior_vector()`, `determine_drift_mode()`
- Depends on: types, baseline (for comparisons)
- Used by: engine (via `compute_all_vitals()`)

**Pressure Computation:**
- Purpose: Aggregate individual signal pressures into a single 0-1 scalar representing agent state severity
- Location: `src/soma/pressure.py`
- Contains: `compute_signal_pressure()` (z-score via sigmoid), `compute_aggregate_pressure()` (blended mean+max)
- Depends on: types
- Used by: engine

**Baseline & Statistics:**
- Purpose: Track exponential moving average (EMA) baselines for signals with cold-start blending to prevent false positives in early sessions
- Location: `src/soma/baseline.py`
- Contains: `Baseline` class with EMA update/query, cold-start blending
- Depends on: None (core math)
- Used by: engine, vitals (indirectly for z-score calculation)

**Guidance Engine:**
- Purpose: Map pressure to response mode; evaluate tool calls for destructiveness; suggest actions
- Location: `src/soma/guidance.py`
- Contains: `pressure_to_mode()`, `evaluate()`, `GuidanceResponse`, destructive pattern detection
- Depends on: types, guidance thresholds
- Used by: engine, hooks

**Pressure Graph:**
- Purpose: Model agent dependencies and propagate pressure across trust-weighted edges
- Location: `src/soma/graph.py`
- Contains: `PressureGraph` class with agent nodes, directed edges, damping-based propagation
- Depends on: types
- Used by: engine, persistence

**Budget System:**
- Purpose: Track spending across named resource dimensions (tokens, cost_usd)
- Location: `src/soma/budget.py`
- Contains: `MultiBudget` class with spend/replenish/health/burn_rate operations
- Depends on: None (core tracking)
- Used by: engine, wrap (for blocking exhausted budgets)

**Learning Engine:**
- Purpose: Adapt thresholds and signal weights based on intervention outcomes; track pending/resolved interventions
- Location: `src/soma/learning.py`
- Contains: `LearningEngine` class, intervention tracking, adaptive adjustment logic
- Depends on: types
- Used by: engine, persistence

**Recording & Persistence:**
- Purpose: Capture action sequences; persist/restore engine state across sessions
- Location: `src/soma/recorder.py`, `src/soma/persistence.py`
- Contains: `SessionRecorder`, `RecordedAction`, `save_engine_state()`, `load_engine_state()` with atomic writes
- Depends on: types
- Used by: engine, wrap, CLI

**Session Context:**
- Purpose: Detect workflow environment (GSD mode, action count, pressure); inform context-aware guidance
- Location: `src/soma/context.py`
- Contains: `SessionContext`, `detect_workflow_mode()`, `get_session_context()`
- Depends on: types
- Used by: hooks, guidance

**Findings Collector:**
- Purpose: Aggregate monitoring insights (quality, patterns, predictions, scope drift, RCA) into structured findings list
- Location: `src/soma/findings.py`
- Contains: `Finding` dataclass, `collect()` function that sources findings from multiple subsystems
- Depends on: state loaders (quality tracker, predictor, fingerprint engine)
- Used by: hooks (for output formatting)

**Client Wrapper:**
- Purpose: Proxy around API clients to intercept all LLM calls; apply SOMA controls transparently
- Location: `src/soma/wrap.py`
- Contains: `WrappedClient`, `SomaBlocked`, `SomaBudgetExhausted` exceptions
- Depends on: engine, recorder, guidance
- Used by: Direct API integration (e.g., `soma.wrap(anthropic.Anthropic())`)

**Hook Layer:**
- Purpose: Integration points for Claude Code environment; dispatch to context-aware handlers
- Location: `src/soma/hooks/`
- Contains: `claude_code.py` (dispatcher), `pre_tool_use.py`, `post_tool_use.py`, `stop.py`, `notification.py`, `statusline.py`, `common.py` (shared utilities)
- Depends on: engine, state, guidance, findings, context
- Used by: Claude Code environment via `CLAUDE_HOOK` mechanism

**State Management:**
- Purpose: Load/save transient subsystem state (quality tracker, predictor, fingerprint engine, task tracker) from `~/.soma/`
- Location: `src/soma/state.py`
- Contains: State path constants, getter/setter functions for each subsystem
- Depends on: subsystem classes
- Used by: hooks, findings, core modules for state recovery

**CLI Layer:**
- Purpose: User-facing command interface; dashboard, replay, config management, setup
- Location: `src/soma/cli/`
- Contains: `main.py` (argparse router), `config_loader.py`, tabs, wizard, status printer
- Depends on: engine, recorder, persistence
- Used by: `soma` CLI command

**Type System:**
- Purpose: Centralized type definitions for Actions, VitalsSnapshot, AgentConfig, ResponseMode enums
- Location: `src/soma/types.py`
- Contains: ResponseMode (OBSERVE/GUIDE/WARN/BLOCK), AutonomyMode, DriftMode, Action, VitalsSnapshot, AgentConfig
- Depends on: None
- Used by: All layers

## Data Flow

**Standard Action Recording Flow:**

1. **Action Entry** (`wrap.py`, hooks, or direct `engine.record_action()`)
   - Tool name, output text, tokens, cost, error flag, retry flag, duration

2. **Vitals Computation** (engine calls `_compute_vitals_for_agent()`)
   - Pull last 10 actions from ring buffer
   - Compute uncertainty (entropy-based), drift (tool deviation), error rate, resource stats
   - Return VitalsSnapshot with uncertainty, drift, token_usage, cost, error_rate

3. **Baseline Update** (engine calls `baseline.update()` for each signal)
   - EMA with cold-start blending prevents early false positives
   - Baseline captures long-term "normal" behavior; variance tracks volatility

4. **Pressure Computation** (engine calls `_compute_pressure_for_agent()`)
   - For each signal (uncertainty, drift, error_rate, cost, token_usage):
     - Compute z-score: `(current - baseline) / std`, clamped via sigmoid
   - Aggregate: `0.7 * weighted_mean + 0.3 * max_pressure`
   - If drift_mode is INFORMATIONAL, drift signal weight set to 0
   - Result: single scalar 0-1 representing agent pressure

5. **Graph Propagation** (engine calls `_graph.propagate()`)
   - Propagate agent's internal pressure along trust-weighted edges to dependents
   - Multi-pass until stable (max 3 iterations)
   - Effective pressure = max(internal_pressure, damping_factor * incoming_weighted_avg)

6. **Guidance Evaluation** (engine calls `guidance.evaluate()`)
   - Map pressure to ResponseMode via thresholds (OBSERVE < GUIDE < WARN < BLOCK)
   - Check if tool is destructive (in BLOCK mode only, non-destructive allowed)
   - Build context-aware suggestions based on action log patterns

7. **Mode Update** (engine updates `_agents[agent_id].mode`)
   - Store ResponseMode on agent state
   - Emit event via EventBus if level changed

8. **Optional Blocking** (WrappedClient enforces block_at threshold)
   - If mode >= block_at and call is destructive: raise SomaBlocked
   - If budget exhausted: raise SomaBudgetExhausted
   - Otherwise: allow call

9. **State Export** (optional, if auto_export=True)
   - Write agent snapshot and budget to `~/.soma/state.json`
   - Save full engine state to `~/.soma/engine_state.json`

**State Management Flow:**

- Engine state persisted atomically (temp file → fsync → rename) with file locking
- Subsystem state (quality tracker, predictor, fingerprint) loaded lazily via `state.py` getters
- Session recovery: `load_engine_state()` reconstructs engine from `engine_state.json`

## Key Abstractions

**Action:**
- Purpose: Immutable record of a single agent action
- Examples: `Action(tool_name="Bash", output_text="...", token_count=100)`
- Pattern: Frozen dataclass with optional metadata dict

**ResponseMode (Enum):**
- Purpose: Guidance response severity level
- Examples: `ResponseMode.OBSERVE` (silent), `ResponseMode.GUIDE` (suggest), `ResponseMode.WARN` (alert), `ResponseMode.BLOCK` (restrict destructive ops)
- Pattern: Ordered enum with comparison operators; legacy aliases for backward compatibility

**AgentConfig:**
- Purpose: Configuration for a monitored agent
- Examples: autonomy mode, system prompt, allowed tools, expensive/minimal tool lists
- Pattern: Mutable dataclass populated during `register_agent()`

**VitalsSnapshot:**
- Purpose: Point-in-time behavioral health metrics
- Examples: uncertainty, drift, error_rate, token_usage, cost, drift_mode
- Pattern: Frozen dataclass, immutable for event emitting

**Baseline:**
- Purpose: Per-signal EMA with variance tracking and cold-start blending
- Examples: baseline for uncertainty starts at default 0.05, updates via EMA with blend toward default during cold start
- Pattern: Stateful class, updated incrementally as actions arrive

**PressureGraph:**
- Purpose: Directed graph modeling inter-agent dependencies
- Examples: Agent A's pressure propagates to dependent Agent B via trust-weighted edge
- Pattern: Adjacency list with damping-based convergent propagation

## Entry Points

**Python Library Entry:**
- Location: `src/soma/__init__.py`
- Triggers: Direct import `import soma` or `from soma import SOMAEngine`
- Responsibilities: Export main classes (`SOMAEngine`, `ActionResult`, types), convenience function `quickstart()`

**CLI Entry:**
- Location: `src/soma/cli/main.py`
- Triggers: User runs `soma` command
- Responsibilities: Argparse router to subcommands (status, replay, wizard, setup, config)

**Wrapper Entry:**
- Location: `src/soma/wrap.py` (`wrap()` function, `WrappedClient` class)
- Triggers: `soma.wrap(client, ...)`
- Responsibilities: Proxy API client, intercept calls, apply engine rules, emit events

**Hook Entry (Claude Code):**
- Location: `src/soma/hooks/claude_code.py` (`main()` function)
- Triggers: `CLAUDE_HOOK=PreToolUse soma-hook` (or env var set by Claude Code)
- Responsibilities: Dispatch to handler, run pre/post tool-use logic, emit guidance/findings

**Configuration Entry:**
- Location: `src/soma/cli/config_loader.py`
- Triggers: `load_config()` called during engine creation or hook setup
- Responsibilities: Parse `soma.toml`, load budget/thresholds/agent config, with fallback to defaults

## Error Handling

**Strategy:** Explicit exceptions with helpful context + graceful fallbacks

**Patterns:**
- `AgentNotFound`: Raised when accessing unknown agent; message includes registration hint
- `SomaBlocked`: Raised by WrappedClient when pressure or budget prevents call; includes agent_id, level, pressure
- `SomaBudgetExhausted`: Raised when dimension budget spent; includes dimension name
- `SOMAError`: Base class for custom exceptions

**Defensive practices:**
- State save/load wrapped in try/except with fallback to in-memory state
- Config loading fails gracefully to defaults
- Hooks catch exceptions and log rather than crash (never disrupt Claude Code)
- Baseline/graph operations guard against edge cases (division by zero, empty collections)

## Cross-Cutting Concerns

**Logging:**
- Via `print()` to stdout (hooks redirect to JSON), rich console formatting in CLI
- Patterns: Debug info logged in verbose mode, warnings/errors always visible

**Validation:**
- Budget limits validated in constructor
- Agent IDs checked for existence before operations
- Tool names validated against allowed list (if configured)
- File paths checked for sensitivity patterns (guidance layer)

**Authentication:**
- No built-in auth; assumes API client already authenticated
- Env vars for config paths (`.soma/` directory) via Path.home()
- File locking in persistence prevents concurrent state corruption

**Session Lifecycle:**
- Engine created via `SOMAEngine()` constructor or `from_config()`
- Agents registered via `register_agent()`
- Actions recorded via `record_action()` (or via wrapped client)
- State exported via `export_state()` (auto or manual)
- Session recovered via `load_engine_state()` on restart

---

*Architecture analysis: 2026-03-30*
