# Changelog

## [0.6.0] — 2026-04-02

Mirror: Proprioceptive Feedback — the agent sees itself.

### Added
- **Mirror module** (`soma.mirror`) — proprioceptive session context injected into tool responses via stdout
- **Three generation modes**: PATTERN (cached, 0 cost), STATS (computed, 0 cost), SEMANTIC (LLM-powered)
- **Self-learning**: Mirror tracks which contexts helped (pressure dropped ≥10%) and caches effective patterns in `~/.soma/patterns.json`
- **Multi-provider LLM** for semantic mode: Gemini (free), Anthropic, OpenAI via raw httpx — no SDK dependencies
- **VBD detection**: identifies verbal-behavioral divergence (edit without recent read of that file)
- **Full pipeline integration test** (`test_full_pipeline.py`) — engine → vitals → pressure → mirror → persistence → fingerprint
- **State loader tests** (`test_state_loaders.py`) — coverage for `state.py` lazy getters
- **Planner tests** (`test_planner.py`) — coverage for session capacity computation

### Changed
- Session context delivered via **stdout** (environment augmentation) instead of stderr (system messages)
- Agent sees behavioral data as part of tool response, not as external warnings
- "Show don't tell" — facts about behavior, not instructions to change it

### Removed
- Dead code: `daemon.py`, `inbox.py`, `benchmark/loop_verification.py`

### Architecture
- Mirror replaces directive guidance with factual self-reflection
- Three-tier escalation: silence (healthy) -> pattern/stats (elevated) -> semantic LLM (critical)
- `[mirror]` config section in `soma.toml` for semantic_enabled, semantic_provider, semantic_threshold

### Stats
- 86 modules, 1208 tests, 0 dead code

## [0.5.x] — Nervous System (March-April 2026, 124 commits unreleased)

Phases 11-16: reflex blocking, cross-session intelligence, advanced behavioral analysis.

### Added
- **Context window tracking** (CTX-01) — cumulative token tracking, context exhaustion pressure signal, proactive warnings at 70%/90%
- **OTel + webhook exporters** — `soma.exporters.otel`, `soma.exporters.webhook`, wired to EventBus
- **Session reports** — `soma.report` generates per-agent session summaries on shutdown
- **Core reflexes** (Phase 14) — pattern-based blocking in 3 modes: observe/guide/reflex. 80.2% error reduction proven in benchmark
- **Signal reflexes** (Phase 15) — commit gate (blocks git commit at grade D/F), drift checkpoint, RCA-triggered pauses
- **Advanced reflexes** (Phase 16) — circuit breaker, session memory with cosine similarity, smart throttle, fingerprint anomaly detection, context overflow evaluator
- **CLI tools** — `soma replay --last/--worst`, `soma stats`, `soma install`, `soma update`
- **Cross-session predictor** — blends local predictions with historical session trajectories
- **Threshold tuner** — phase-aware drift computation, adaptive thresholds from benchmark results
- **Session store** — append-only JSONL with automatic rotation at 10MB
- **Enhanced stop hook** — session summary with duration, peak pressure, quality grade, pattern detection
- **Subagent awareness** — SOMA monitoring block injected into Agent tool prompts

### Fixed
- **Bimodal pressure** — continuous ramp during grace period instead of step function (0 -> high cliff)
- **Session state leaking** — recycled PID detection via PPID start time comparison
- **Universal proxy layer** — SOMAProxy for any agent framework (LangChain, CrewAI, AutoGen)
- **Hybrid tone** — data-first format with brief context, not instruction-first directives

## [0.5.0] — 2026-03-31

Production Ready: 10 phases of behavioral analysis + full production API support.

### Added (Phase 9: Async + Streaming)
- **Async client wrapper** (ASYNC-01) — `soma.wrap(AsyncAnthropic())` detects async clients via `inspect.iscoroutinefunction` and wraps all methods with async interceptors; full 22-step engine pipeline runs identically to sync
- **Streaming interception** (ASYNC-02) — `client.messages.stream()` (Anthropic) and `stream=True` (OpenAI) are intercepted; chunks accumulated into single Action with token count from `get_final_message()`
- **SomaStreamContext** / **AsyncSomaStreamContext** — context managers that wrap streaming responses, accumulate text, and record one Action on exit

### Added (Phase 10: Production Hardening)
- **Context window tracking** (CTX-01) — `VitalsSnapshot.context_usage` tracks cumulative tokens as fraction of model context window; half-life degradation factor reduces predicted success rate as context fills
- **Structured audit logging** (LOG-01) — `AuditLogger` writes JSON Lines to `~/.soma/audit.jsonl` with timestamp, agent_id, tool_name, error, pressure, mode; zero-config, auto-rotating at 10MB
- **Real API integration tests** (TEST-01) — 5 tests covering Anthropic (sync/stream/async) + OpenAI (sync/stream) with real API keys; skipif guards for CI safety
- **CONTRIBUTING.md** (DOC-01) — dev setup, test instructions, project structure, code style, contribution workflow

### Fixed (Phase 10)
- Streaming context manager bug: `MessageStreamManager.__enter__()` returns `MessageStream` — was calling `text_stream` on manager instead of inner stream
- pytest-asyncio version constraint lowered to `>=0.23` for broader compatibility

### Added
- **Uncertainty classification** (VIT-02) — classifies uncertainty as epistemic (knowledge gap) or aleatoric (inherent ambiguity) via output entropy; epistemic gets 1.3x pressure, aleatoric gets 0.7x dampening
- **Goal coherence scoring** (VIT-01) — estimates goal coherence from system prompt; low coherence increases pressure
- **Baseline integrity checking** (VIT-03) — detects corrupted baseline state via checksums
- **Vector pressure propagation** (PRS-01) — per-signal PressureVector (uncertainty, drift, error_rate, cost) flows through trust graph; downstream agents know WHY upstream struggles
- **Coordination SNR** (PRS-02) — signal-to-noise isolation zeroes out influence from upstream agents with no meaningful pressure
- **Task complexity estimation** (PRS-03) — estimates task complexity from system prompt content (ambiguity markers, interdependencies)
- **Half-life temporal modeling** (HLF-01/02) — models agent degradation with exponential decay; predicts P(success) at future action counts
- **Calibration score** (REL-01) — measures how well agent confidence matches actual performance
- **Verbal-behavioral divergence** (REL-02) — detects agents that report success while performing poorly
- **Policy engine** (POL-01/02) — declarative YAML/TOML rules with when/do conditions; `PolicyEngine.from_file()`, `from_dict()`, `from_url()`
- **Guardrail decorator** (POL-03) — `@soma.guardrail(engine, agent_id, threshold)` blocks sync/async calls when pressure exceeds threshold
- **TypeScript SDK scaffold** (SDK-01-04) — `packages/soma-ai/` with SOMAEngine, track(), wrapVercelAI(), SomaLangChainCallback
- **Framework adapters** — LangChain callback, CrewAI middleware, AutoGen observer (Python SDK); importable without requiring the frameworks
- **Error-rate aggregate floor** — prevents weighted-mean dilution of high error signals; maps error_rate >=0.50 to guaranteed GUIDE/WARN/BLOCK floors

### Changed
- Default signal weights updated: uncertainty=2.0, drift=1.8, error_rate=1.5, cost=1.0, token_usage=0.8, goal_coherence=1.5
- VitalsSnapshot extended with: uncertainty_type, goal_coherence, calibration_score, task_complexity, predicted_success_rate
- PressureGraph extended with per-node PressureVector storage and vector-based propagation
- Engine pipeline expanded: 10 steps → includes uncertainty classification, complexity estimation, half-life modeling, reliability metrics, vector propagation

### Fixed
- Pressure sensitivity: 35% error rate was stuck in OBSERVE due to weighted-mean dilution — now correctly escalates via aggregate floor
- Epistemic multiplier test: uncertainty at exactly min_uncertainty threshold (0.30) returned None classification
- Grace period pressure_vector consistency during warmup
- Unused imports removed across graph, pressure, and SDK modules

## [0.4.12] — 2026-03-30

Multi-agent core hardening: concurrent safety, agent lifecycle, learning validation.

### Added
- Atomic persistence with file locking (`fcntl` + temp file + `os.rename`) — safe for concurrent multi-agent writes
- Agent TTL eviction — `engine.evict_stale_agents(ttl_seconds=3600)` removes dead agents from state
- Shared engine support in `wrap()` — `soma.wrap(client, engine=shared_engine)` for multi-agent pipelines
- Multi-agent stress tests: 5 concurrent agents, trust propagation, pipeline scenarios
- Learning convergence validation: thresholds proven bounded, non-oscillating

### Fixed
- Persistence race condition: concurrent saves no longer corrupt state file
- Lock held across full write cycle (mkstemp → fsync → rename)
- Windows compatibility: `fcntl` import guarded, graceful fallback
- `evict_stale_agents` now cleans graph edges (was leaking `_edges`/`_out_edges`)
- `ResponseMode.RESTART`/`SAFE_MODE` mapped to `BLOCK` (was 4/5, caused comparison bugs)
- Stale level names in wizard presets, config tab, testing.py, rca.py
- `wrap.py` docstring referenced `Level.HEALTHY` → `ResponseMode.OBSERVE`

## [0.4.11] — 2026-03-30

Core polish sprint: false positive reduction, actionable feedback, layer-agnostic architecture, and visibility fixes across 11 micro-releases.

### Architecture
- **Layer-agnostic intelligence** — pattern analysis, findings collection, workflow context extracted from Claude Code hooks into core modules (`soma/patterns.py`, `soma/findings.py`, `soma/context.py`)
- `notification.py` reduced from 420 to 154 lines — now a thin Claude Code formatter
- New layers (Cursor, Windsurf, etc) get full intelligence by importing core modules

### Added
- `soma doctor` — check installation health (hooks, binary, state, version)
- Auto-migrate soma.toml old keys on first hook run
- Ruff lint in CI pipeline (GitHub Actions), ruff config in pyproject.toml
- `detect_workflow_mode()` reads .planning/STATE.md for GSD context
- Workflow-aware severity: patterns suppressed when they'd be noise during plan/discuss/execute
- Positive feedback: `[✓] read-before-edit maintained` and `[✓] clean streak` when doing well
- `TaskTracker.get_efficiency()` — context_efficiency, success_rate, focus metrics
- Phase-aware header: `SOMA: #42 [implement] ctx=73% focused`
- Directive prompt injections: `[do] Read before editing` replaces `[pattern] 3 blind edits`
- WARN/BLOCK messages include specific recovery guidance
- Tests for `_collect_findings`, engine threshold propagation, config migration

### Changed
- Threshold config keys renamed: `caution`/`degrade`/`quarantine` -> `guide`/`warn`/`block`
- `restart` threshold removed — SOMA no longer has a restart concept
- `pressure_to_mode()` and `evaluate()` accept optional `thresholds` dict
- Engine uses `custom_thresholds` for mode transitions
- `stale_timeout` configurable via `[hooks]` section in soma.toml
- Grace period reduced to 3 actions (was: full silence below 10% pressure)
- Findings always collected and shown when present, regardless of pressure
- Periodic header every 15 actions when no findings
- Positive feedback thresholds lowered: 3 read-edit pairs (was 5), 10 clean actions (was 15)
- Agent spawn suggestions suppressed when GSD active
- Status line shows `ctx:high focus:focused` when healthy instead of raw vitals

### Fixed
- Scope drift uses cwd-relative paths — moving between `src/` and `tests/` no longer triggers false drift
- "Edit without Read" no longer fires when file was recently read via Read/Grep/Glob (checks last 30 actions)
- Pattern analysis skipped at very low pressure (<10%) — reduces noise in healthy sessions
- `_collect_findings` used stale level names (DEGRADE/QUARANTINE) — now uses WARN/BLOCK
- RCA priority checked "HEALTHY" instead of "OBSERVE"
- `soma mode` command uses new threshold key names
- Notification `ctx=0%` on cold start — now requires 10+ actions
- `detect_workflow_mode` fallback to `os.getcwd()` when env var missing
- All lint errors across core modules (unused imports, f-strings)
- SOMA visibility: silent mode at p<10% and suppression at p<25% meant agent never saw SOMA output

## [0.4.0] — 2026-03-30

Redesigned from a blocking system to a guidance system. SOMA no longer blocks normal tools at any pressure level — it guides the agent with increasingly urgent feedback, and only blocks truly destructive operations.

### Changed
- **Guidance over blocking**: replaced 6-level escalation ladder (HEALTHY -> CAUTION -> DEGRADE -> QUARANTINE -> RESTART -> SAFE_MODE) with 4-mode guidance system (OBSERVE -> GUIDE -> WARN -> BLOCK)
- **OBSERVE (0-24%)**: silent monitoring, metrics only (replaces HEALTHY)
- **GUIDE (25-49%)**: soft suggestions injected into context, never blocks (replaces CAUTION)
- **WARN (50-74%)**: insistent warnings, still never blocks normal tools (replaces DEGRADE)
- **BLOCK (75-100%)**: blocks ONLY destructive operations — `rm -rf`, `git push --force`, `.env` file writes (replaces QUARANTINE/RESTART)
- Write, Edit, Bash, and Agent tools are **never blocked** at any pressure level
- Central decision engine moved to new `guidance.py` module
- `ladder.py` and `Ladder` class deleted
- Threshold config keys renamed: `caution`/`degrade`/`quarantine` -> `guide`/`warn`/`block`
- Dead command queue IPC (`commands.py`) deleted

### Added
- `soma stop` — stop SOMA monitoring
- `soma start` — start SOMA monitoring
- `soma uninstall-claude` — remove SOMA hooks from Claude Code

### Removed
- `soma quarantine` — manual quarantine no longer exists
- `soma release` — no quarantine means no release
- `soma approve` — approval queue removed
- `soma daemon` — daemon mode removed
- `soma export` — export command removed
- Slash command `/soma:control quarantine` removed
- Slash command `/soma:control release` removed

### Fixed
- `soma reset` now works directly (was broken due to IPC indirection)

### Upgrading from 0.3.x

1. **Config**: rename threshold keys in `soma.toml`:
   ```toml
   # Old
   [thresholds]
   caution = 0.25
   degrade = 0.50
   quarantine = 0.75

   # New
   [thresholds]
   guide = 0.25
   warn = 0.50
   block = 0.75
   ```

2. **Code**: if you imported `Ladder` or `Level`, switch to `Guidance` and `Mode` from `soma.guidance`

3. **CLI scripts**: remove any references to `soma quarantine`, `soma release`, `soma approve`, `soma daemon`, `soma export`

4. **Slash commands**: `/soma:control quarantine` and `/soma:control release` no longer exist. Use `/soma:control reset` to reset baselines.
