# SOMA Integration Audit & Repair Report

Date: 2026-03-31
Auditor: Claude Opus 4.6 (1M context)
Baseline: 1056 tests passing, 5 skipped

---

## Phase 1 — Gaps Found

### GAP 1: phase_drift.py — Dead module (0 imports)

- **File**: `src/soma/phase_drift.py` (73 LOC)
- **What it does**: Reduces drift score by up to 50% when tool usage matches expected phase pattern (research: Read/Grep, implement: Edit/Write, test: Bash, debug: Bash/Read)
- **Where it should run**: engine.py, after raw drift computation, before pressure aggregation
- **Why it was dead**: engine.py called `compute_drift()` directly from vitals.py; phase_drift was never imported
- **Impact**: Read-heavy research sessions falsely registered as high drift, causing unnecessary GUIDE/WARN escalations

### GAP 2: context_control.py — Dead module (0 imports)

- **File**: `src/soma/context_control.py` (~50 LOC)
- **What it does**: Reduces message injection by ResponseMode — GUIDE retains 80%, WARN 50%, BLOCK 0%
- **Where it should run**: notification.py, before outputting finding_lines
- **Why it was dead**: notification.py never imported or called apply_context_control()
- **Impact**: Agent received same volume of findings regardless of pressure level; under BLOCK mode, still got messages

### GAP 3: cross_session.py — Dead module (0 runtime imports)

- **File**: `src/soma/cross_session.py` (~120 LOC)
- **What it does**: Extends PressurePredictor with historical trajectory matching (cosine > 0.8 similarity, 0.6 local + 0.4 historical blending)
- **Where it should run**: state.py:get_predictor(), returning CrossSessionPredictor instead of base PressurePredictor
- **Why it was dead**: get_predictor() always created PressurePredictor; cross_session was never imported at runtime
- **Impact**: Predictor had no historical context; predictions in early sessions had no reference trajectories
- **Secondary gap**: stop.py never called session_store.append_session(), so even if wired, there would be no historical data

### GAP 4: Orphan injection reflexes (error_rate, research_stall, agent_spam)

- **File**: `src/soma/reflexes.py` INJECTION_REFLEXES set + `src/soma/patterns.py` detection
- **What they do**: Inject guidance when error rate > 30%, research stalls (7+ reads, 0 writes), or agent spam (3+ Agent calls)
- **Where they should run**: pre_tool_use.py, in both guide and reflex modes
- **Why they were dead**: reflex_evaluate() was only called in "reflex" mode; the default "guide" mode skipped it entirely
- **Impact**: In the default operating mode, agents got no guidance about high error rates, research stalls, or agent spam

### GAP 5: stop.py — No session store persistence

- **File**: `src/soma/hooks/stop.py`
- **What was missing**: SessionRecord creation and append_session() call
- **Why**: stop.py saved engine state and fingerprint but never wrote to session_store.history.jsonl
- **Impact**: cross_session.py had no data source; session_memory.py had no completed session records to match against

---

## Phase 2 — Changes Made

### Change 1: Wire phase_drift.py into engine.py

- **File**: `src/soma/engine.py`
- **Added**: import of `compute_phase_aware_drift` from `phase_drift`
- **Added**: `_detect_phase()` helper function that infers development phase from ring buffer tool names (mirrors task_tracker logic without dependency)
- **Changed**: drift computation now calls `compute_phase_aware_drift(actions, baseline_vector, known_tools, current_phase)` instead of raw `compute_drift()`
- **Commit**: `715b53f`

### Change 2: Wire context_control.py into notification.py

- **File**: `src/soma/hooks/notification.py`
- **Added**: After collecting finding_lines and before output, apply `apply_context_control()` to filter findings by current ResponseMode
- **Effect**: GUIDE mode retains 80% of findings, WARN retains 50%, BLOCK retains 0%
- **Commit**: `e84cf83`

### Change 3: Wire cross_session.py into predictor pipeline

- **File**: `src/soma/state.py`
- **Changed**: `get_predictor()` now returns `CrossSessionPredictor` instead of base `PressurePredictor`
- **Added**: Automatic `load_history()` call to populate session patterns from session_store
- **Added**: Fallback to base PressurePredictor if cross_session module fails
- **Commit**: `b5a1a81`

### Change 4: Wire orphan injection reflexes into guide mode

- **File**: `src/soma/hooks/pre_tool_use.py`
- **Added**: In "guide" mode, call `reflex_evaluate()` and surface inject_messages (never blocks in guide mode)
- **Effect**: error_rate, research_stall, and agent_spam guidance now fires in the default operating mode
- **Commit**: `aa92c7d`

### Change 5: Wire stop.py to session_store

- **File**: `src/soma/hooks/stop.py`
- **Added**: SessionRecord creation from action log data and `append_session()` call
- **Effect**: Sessions with 3+ actions are persisted to history.jsonl for cross-session intelligence
- **Commit**: `1b19bfa`

---

## Phase 3 — Test Results

### Before changes
- 1056 passed, 5 skipped

### After changes
- 1062 passed, 5 skipped (6 new tests added, 0 broken)

### New tests (`tests/test_integration_wiring.py`)

1. `test_phase_drift_reduces_read_heavy_drift` — Proves phase_drift suppresses drift during research sessions
2. `test_phase_detection_returns_correct_phases` — Validates the phase detection helper
3. `test_context_control_limits_by_mode` — Proves OBSERVE/GUIDE/WARN/BLOCK retain 100%/80%/50%/0% of messages
4. `test_context_control_preserves_newest` — Verifies newest messages are kept, oldest dropped
5. `test_cross_session_blending_activates` — Proves historical trajectory blending with synthetic data
6. `test_cross_session_fallback_without_history` — Proves CrossSessionPredictor matches base predictor when no history

---

## Modules That Still Have Issues

### threshold_tuner.py — CLI-only, not wired to runtime

Collects FP rate data and computes optimal thresholds. Only accessible via CLI commands. Could be wired to auto-tune thresholds at session end, but this is a feature enhancement, not a dead code fix.

### analytics.py — CLI-only

SQLite session analytics. CLI-only by design; no runtime pipeline gap.

### daemon.py + inbox.py — Dead, not connected

Background daemon architecture. Not connected to anything. These are future features, not currently useful modules.

### policy.py — Export only

Declarative YAML rules + @guardrail decorator. Exported from __init__.py but not used in any runtime path. Needs a policy evaluation step in the engine or hooks to be useful.

### stop.py session record quality

The SessionRecord created in stop.py has incomplete data:
- `pressure_trajectory` only contains the final pressure value (not per-action trajectory)
- `max_pressure` and `avg_pressure` are set to final pressure (not tracked)
- `retry_count` and `total_tokens` are 0 (not tracked in action_log)

To get full trajectory data, the post_tool_use hook would need to append pressure values to a session file on each action. This is a meaningful improvement but requires adding a new per-action persistence path.

### _detect_phase duplication

The `_detect_phase()` function in engine.py mirrors logic from `task_tracker._detect_phase()`. This is intentional — the engine should not depend on the task_tracker (which is a hook-level concern). However, if the phase detection logic changes in one place, it must change in both.

---

## Honest Assessment

### What works

- **phase_drift**: Correctly reduces drift during research/implement/test phases. Math unchanged. Integration is clean — one import + one call replaces the raw drift call.
- **context_control**: Correctly truncates finding injections by mode. Uses the module exactly as designed.
- **cross_session**: CrossSessionPredictor is now the default predictor. Loads history automatically. Falls back gracefully.
- **Injection reflexes**: Now fire in guide mode. The inject_message mechanism was already working in reflex mode; this just extends it.
- **Session persistence**: stop.py now creates session records, giving cross_session data to work with.

### What is untested in production

- **cross_session in real sessions**: The blending logic requires 3+ historical sessions with 5+ pressure readings each. First few sessions will still use base predictor only. Test uses synthetic data.
- **context_control with real finding volumes**: In production, finding_lines might be 2-3 items (not 10). With 2 items at GUIDE mode (80%), ceil(2 * 0.8) = 2 — no reduction. The effect only matters when there are 4+ findings.
- **Phase detection accuracy**: The _detect_phase helper uses simple tool counting. A session that mixes Read and Edit equally will be classified as whichever has more — this is a rough heuristic, not a precise classifier.

### What is uncertain

- **Performance of session_store.load_sessions() in get_predictor()**: On first call per hook invocation, this reads history.jsonl. After hundreds of sessions, this file could be large. The max_sessions=100 cap limits memory, but disk I/O per hook call is a concern. Should be profiled.
- **phase_drift interaction with learning.py**: Learning adjusts drift weight based on intervention outcomes. Phase_drift reduces the drift value itself. These two mechanisms could interact unexpectedly — learning might learn to compensate for phase_drift's reduction, effectively negating it. Not tested.
