# Codebase Concerns

**Analysis Date:** 2026-03-30

## Tech Debt

**Deprecated Type Alias (Level = ResponseMode):**
- Issue: `soma.types.py` maintains backward-compatible alias `Level = ResponseMode` with plan to remove in 0.5.0
- Files: `src/soma/types.py` (line 47), `src/soma/engine.py` (lines 34-36), `src/soma/testing.py` (line 6), `src/soma/cli/status.py` (line 30)
- Impact: Codebase uses both `Level` and `ResponseMode` interchangeably, creating confusion. All internal code should migrate to `ResponseMode`
- Fix approach: Audit all imports and usages of `Level`; rename to `ResponseMode` consistently; remove alias in next minor version bump

**Legacy Enum Values (HEALTHY, CAUTION, DEGRADE, QUARANTINE, RESTART, SAFE_MODE):**
- Issue: Six deprecated enum aliases in `ResponseMode` mapping old names to new ones, scheduled removal in 0.5.0
- Files: `src/soma/types.py` (lines 18-23)
- Impact: Code outside SOMA that imports these enum values will break on upgrade
- Fix approach: Add migration guide to docs; add deprecation warnings on enum access; coordinate with external callers before 0.5.0 release

**Version String Fallback Mismatch:**
- Issue: `src/soma/cli/main.py` (line 17) and `src/soma/cli/status.py` hardcode fallback version "0.4.0" while actual version is "0.4.12" in `__init__.py`
- Files: `src/soma/cli/main.py:17`, `src/soma/cli/status.py`, `src/soma/__init__.py`
- Impact: If package metadata fails to load, users see outdated version number (0.4.0 instead of 0.4.12)
- Fix approach: Import `__version__` from `src/soma/__init__.py` instead of hardcoding, or update fallback automatically during release

**Backward Compatibility Shims in Hooks:**
- Issue: Multiple hook modules contain backward compatibility code that can be removed
- Files: `src/soma/hooks/notification.py` (lines 138-147), `src/soma/hooks/statusline.py` (line 23), `src/soma/hooks/claude_code.py` (line 38)
- Impact: Dead code paths slow debugging and increase maintenance burden
- Fix approach: Remove shims when dropping 0.4.x support; document upgrade path for existing installations

## Missing Error Handling

**Bare Exception Catches in State Persistence:**
- Issue: Multiple state loader functions use bare `except Exception:` without logging or propagating errors
- Files: `src/soma/state.py` (lines 22-28, 36-37, 43-49, 54-58, 67-70, 75-79, 87-93, 98-103)
- Impact: Silently ignores corrupted JSON, missing files, and I/O errors, making it hard to debug state issues. Users won't know if state failed to load
- Fix approach: Log errors with context; distinguish between "file not found" (OK) and "corrupted state" (warn); let critical errors bubble up in production

**Fallback Writes Without Error Reporting in Persistence:**
- Issue: `src/soma/persistence.py` (lines 83-85) falls back to direct write if atomic path fails, but doesn't log or notify about the fallback
- Files: `src/soma/persistence.py:83-85`
- Impact: If exclusive file locking fails, users don't know state might be partially written or corrupted across processes
- Fix approach: Log fallback attempts; consider making this a warning in status output or dashboard

**Subprocess Timeouts Swallowed in Post-Tool Hooks:**
- Issue: Python/JS validation and linting in `src/soma/hooks/post_tool_use.py` catches `subprocess.TimeoutExpired` without logging
- Files: `src/soma/hooks/post_tool_use.py` (lines 35-36, 50, 62, 72)
- Impact: If Ruff, Node, or Python validator hangs, users get no feedback — validation silently fails and doesn't block bad code
- Fix approach: Log timeout as warning; set reasonable timeouts (5s is OK) but surface them to user

## Fragile Areas

**Action Recording Pipeline (record_action in SOMAEngine):**
- Files: `src/soma/engine.py:227-412`
- Why fragile: Massive 185-line function with 11 sequential computation steps. If any step fails (e.g., graph propagation, learning evaluation), the entire action is lost. No transaction semantics.
  - Line 356: `self._graph.propagate()` could fail silently if graph is malformed
  - Line 389: Learning engine evaluation happens after mode change; if it throws, no rollback
  - Line 410: Auto-export happens last; if it fails, engine state is out of sync with persisted state
- Safe modification: Break into smaller methods (`_compute_vitals()`, `_compute_pressure()`, `_update_graph()`, etc.); wrap in try-catch at each step; log failures; consider state rollback on critical failures
- Test coverage gaps: No tests for graph propagation failures, learning engine exceptions, or export failures during record_action

**Multi-Process File Locking (fcntl in persistence and hooks):**
- Files: `src/soma/persistence.py:58-86`, `src/soma/hooks/common.py:95-128`
- Why fragile: Relies on fcntl locking which doesn't work on Windows or network filesystems (NFS). Two concurrent processes could corrupt `~/.soma/state.json` if locks fail
- Safe modification: Add platform detection; document Windows limitation; test multi-process scenarios on different filesystems
- Test coverage gaps: No concurrency tests; no Windows CI

**Baseline Vector Cold Start (engine.py lines 255-256):**
- Files: `src/soma/engine.py:255-256`
- Why fragile: Baseline vector is only updated every 10 actions OR when `None`. If an agent has exactly 9 actions and crashes, baseline_vector remains `None` forever, breaking drift calculation
- Safe modification: Initialize baseline_vector on first action, not on None check; ensure it's always defined
- Test coverage gaps: No tests for baseline_vector persistence across restarts

**Graph Trust Mutation During Propagation:**
- Files: `src/soma/graph.py:87-112`, `src/soma/engine.py:367-370`
- Why fragile: Trust weights are mutated after propagation but before effective pressure is read. If two agents communicate through a third, concurrent updates could race
- Safe modification: Separate read-only propagation from weight mutation; use epoch-based updates; lock graph during mutation
- Test coverage gaps: No multi-agent concurrent update tests

## Performance Bottlenecks

**Learning Engine Overhead in Hot Path:**
- Files: `src/soma/learning.py`, `src/soma/engine.py:331-338, 385-389`
- Problem: Every action triggers `_learning.evaluate()` and `_learning.record_intervention()`. Learning engine stores full history in memory with no trimming
- Cause: No maximum history size; memory grows unbounded across agent lifetime
- Improvement path: Add circular history buffer (keep last N interventions); lazy evaluation (batch 10 actions before evaluating); measure evaluation time

**Repetitive Pattern Matching in RCA:**
- Files: `src/soma/rca.py:66-102`
- Problem: Loop detection and error cascade detection iterate over last 12 actions repeatedly; called on every action
- Cause: Not cached; no short-circuit for low pressure
- Improvement path: Cache recent tool sequences; only evaluate RCA when pressure > threshold; use fast pattern algorithms (KMP instead of naive string matching)

**JSON Serialization for Every Auto-Export:**
- Files: `src/soma/engine.py:128-170`, `src/soma/persistence.py:20-86`
- Problem: Auto-export=True (default in Claude Code config) serializes entire engine state to JSON on every action. For a 1000-action session, this is 1000 JSON writes
- Cause: No batching; no dirty-flag tracking
- Improvement path: Batch exports every N actions (e.g., 10); only write if state changed; use compact binary format for large histories

**Action Log Locking on Every Hook:**
- Files: `src/soma/hooks/common.py:89-128`
- Problem: Post-tool hook appends to action log with exclusive file lock. In rapid tool sequences, this serializes all hooks
- Cause: Lock held for entire read-modify-write cycle
- Improvement path: Use append-only log; periodic compaction; read-write locks (not exclusive)

## Scaling Limits

**Single Agent Session Baseline Memory:**
- Current: Baseline stores per-signal value, variance, and count (3 dicts with ~10-15 entries each)
- Limit: With 10,000 actions, baseline is negligible. But if signals are added dynamically, dicts could grow to 100+ entries
- Scaling path: Monitor signal count; warn if >50 signals tracked; consider sparse representation

**Ring Buffer Size (capacity=10):**
- Current: `src/soma/engine.py:45` uses fixed `RingBuffer(capacity=10)` for action history
- Limit: Only last 10 actions retained. Vitals computation averages over 10 actions; this is tight for noisy signals
- Scaling path: Make configurable per agent; document effect on pressure stability

**Graph Effective Pressure Convergence (3 iterations):**
- Current: `src/soma/graph.py:87` propagates up to 3 iterations max
- Limit: In a linear chain of >3 agents, pressure doesn't fully propagate. In a highly connected mesh, 3 iterations may not converge
- Scaling path: Detect graph diameter; run `min(diameter, 10)` iterations; add max_iterations to config

**Learning Engine History per Agent:**
- Current: `_pending` and `_history` dicts grow unbounded as agents interact
- Limit: With 100 long-lived agents, learning engine could hold 10,000+ records in memory
- Scaling path: Add max history size; LRU eviction; periodic persistence to disk

## Dependencies at Risk

**fcntl Import on Non-Unix Systems:**
- Risk: `src/soma/persistence.py:10-14` conditionally imports fcntl; on Windows, file locking is silently disabled
- Impact: Multi-process state saves will fail silently on Windows; data corruption possible
- Migration plan: Implement Windows-compatible locking (msvcrt.locking); add platform-specific tests; document limitation

**subprocess Tool Validation Dependencies:**
- Risk: `src/soma/hooks/post_tool_use.py` requires Ruff (line 45), Node (line 62), Python interpreter (line 26)
- Impact: If Ruff not installed, Python validation silently fails; if Node not installed, JS validation fails. No warnings
- Migration plan: Add dependency check on hook initialization; cache results; offer optional validation mode

## Test Coverage Gaps

**Graph Propagation Edge Cases:**
- Files: `src/soma/graph.py:87-112`
- What's not tested: Cycles in graph (not possible but not checked), zero trust weights, divergence detection
- Risk: Malformed graphs could infinite-loop or produce NaN pressures
- Recommendation: Add graph validation tests; test cycles; test zero-trust scenarios

**Concurrent Engine State Access:**
- Files: `src/soma/engine.py`, `src/soma/persistence.py`
- What's not tested: Two processes writing state simultaneously; one reading while other writes
- Risk: Race conditions causing data corruption or lost updates
- Recommendation: Add multi-process test suite; mock concurrent saves; test with ProcessPoolExecutor

**Learning Engine Outcome Evaluation:**
- Files: `src/soma/learning.py:95-160` (record_intervention, evaluate methods)
- What's not tested: Edge cases like same old/new level (no-op intervention), zero-sample evaluation, threshold adjustment ceiling
- Risk: Learning could fail silently or produce NaN adjustments
- Recommendation: Add unit tests for intervention evaluation; test threshold saturation; test min_interventions threshold

**Baseline EMA Cold Start Blending:**
- Files: `src/soma/baseline.py:60-75` (get method with blending)
- What's not tested: Blending factor transitions (n=min_samples-1 vs n=min_samples); behavior with zero signal variance
- Risk: Pressure calculation could jump unexpectedly at n=min_samples boundary
- Recommendation: Add blending transition tests; verify no discontinuity at boundary

**Budget Multi-Dimensional Tracking:**
- Files: `src/soma/budget.py:80-94` (projected_overshoot)
- What's not tested: Division by zero when current_step=0 (line 91 guards this but no test), overshoot with zero spend_per_step, mixed dimensions with very different burn rates
- Risk: Spurious burn_rate alerts; incorrect projections
- Recommendation: Add dimension-specific budget tracking tests; test mixed token + cost scenarios

**Hook Command Path Validation:**
- Files: `src/soma/hooks/post_tool_use.py:26, 44, 62`
- What's not tested: subprocess calls with invalid paths, shell injection via tool_input fields
- Risk: Invalid subprocess.run calls could raise unhandled exceptions; tool_input is user-controlled
- Recommendation: Escape shell arguments; add fuzzing for tool_input; test with missing executables

## Security Considerations

**Sensitive File Detection Limited to Patterns:**
- Risk: `src/soma/guidance.py:44-50` uses regex to detect sensitive files (`.env`, `credentials`, `.pem`, `secret`, `.key`)
- Files: `src/soma/guidance.py:44-50`
- Current mitigation: Blocks blocking Write/Edit to matching files when pressure is BLOCK level
- Recommendations:
  - Add `.aws`, `.ssh`, `config/keys`, `private/` patterns
  - Support `.gitignore`-based detection for user-defined sensitive paths
  - Cross-check against git hooks (reject commits of sensitive files)
  - Consider integrating with git-secrets or similar tools

**Destructive Bash Pattern Detection Incomplete:**
- Risk: `src/soma/guidance.py:32-42` defines destructive patterns but can be bypassed with aliases, variables, or obfuscation
- Files: `src/soma/guidance.py:32-42`
- Current mitigation: Only blocks at BLOCK pressure; WARN and GUIDE modes allow destruction
- Recommendations:
  - Add more patterns: `dd`, `mkfs`, `format`, `shred`, `truncate`
  - Consider integrating with shell history to detect patterns dynamically
  - Test against real destructive commands to measure false-negative rate

**Action Log File Permissions:**
- Risk: Action logs written to `~/.soma/action_log.json` with default umask (likely world-readable)
- Files: `src/soma/hooks/common.py:89-128`, `src/soma/engine.py:128-170`
- Current mitigation: None
- Recommendations:
  - Set `chmod 0600` after writing `~/.soma/` files
  - Warn user if `~/.soma/` directory is world-readable
  - Document that state files may contain sensitive action paths

**Tool Input Not Validated Before Subprocess:**
- Risk: `src/soma/hooks/post_tool_use.py:76-80` extracts file_path from tool_input dict without path traversal checks
- Files: `src/soma/hooks/post_tool_use.py:76-80`
- Current mitigation: Python validation only runs on files ending in `.py`; JS validation only on `.js/.mjs/.cjs`
- Recommendations:
  - Validate file_path is within expected directories
  - Add checks for `..` and symlink traversal
  - Use `pathlib.Path.resolve()` to canonicalize paths

## Known Issues

**Backward Compatibility with Older State Files:**
- Issue: `src/soma/persistence.py:88-158` (load_engine_state) doesn't handle migration of old engine state formats
- Impact: If user upgrades from 0.3.x to 0.4.12, persisted state may fail to load
- Workaround: Users must delete `~/.soma/engine_state.json` and restart
- Fix: Add version field to state JSON; implement migration functions for old formats

**Version String Inconsistency Across CLI:**
- Issue: `src/soma/cli/main.py:15-17` tries to load package version dynamically but falls back to hardcoded "0.4.0" which doesn't match actual version
- Impact: `soma version` may show stale version number
- Workaround: Run `pip show soma-ai` to see real version
- Fix: Update fallback version during release; add CI check for version consistency

**Learning Engine Doesn't Handle No-Op Interventions:**
- Issue: `src/soma/learning.py` records interventions when mode changes, but if old_mode == new_mode due to baseline adaptation, it still records as intervention
- Impact: Learning engine may adapt thresholds based on non-events
- Workaround: Not applicable; silently produces noise
- Fix: Check if mode actually changed before recording intervention

**Graph Eviction Doesn't Clean Learning History:**
- Issue: `src/soma/engine.py:213-225` evicts stale agents from graph but `_learning._history` and `_learning._pending` still hold records
- Impact: Evicted agent's records stay in memory; over time, learning engine grows unbounded
- Workaround: Periodically reset learning engine or delete `~/.soma/engine_state.json`
- Fix: Add learning engine cleanup in `evict_stale_agents()`

---

*Concerns audit: 2026-03-30*
