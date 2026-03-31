# Phase 1: Vitals Accuracy - Research

**Researched:** 2026-03-30
**Domain:** Python behavioral monitoring — VitalsSnapshot extension, cosine similarity, EMA baseline integrity
**Confidence:** HIGH

## Summary

Phase 1 adds two new fields to `VitalsSnapshot`: `goal_coherence` (float | None) and `baseline_integrity` (bool). All the math already exists in the codebase — `compute_behavior_vector()` and `cosine_similarity()` in `vitals.py`, `FingerprintEngine` in `fingerprint.py`, and `Baseline.get()` in `baseline.py`. The implementation is a wiring job, not a math job.

The primary risk is a vector length mismatch bug: `compute_behavior_vector()` returns a vector of length `4 + len(known_tools)`, and `known_tools` grows as the session progresses. The initial task vector captured at action 5 will have fewer dimensions than the current vector at action 50. `cosine_similarity()` uses `zip()` which silently truncates to the shorter length, inflating similarity scores. This must be handled by snapshotting `known_tools` at capture time and always recomputing the "current" vector against that frozen tool set.

A secondary structural concern: `FingerprintEngine` is not currently a member of `SOMAEngine`. It lives in `~/.soma/fingerprint.json` and is only loaded via `state.py` getters from hooks. For baseline integrity to work inside the engine, the engine needs access. The cleanest path is lazy-loading it inside `record_action()` via `state.get_fingerprint_engine()` — consistent with how hooks already use it.

**Primary recommendation:** Wire the two computations into `record_action()` after vitals step 1 and before VitalsSnapshot construction. Add `initial_task_vector: list[float] | None` and `initial_known_tools: list[str] | None` to `_AgentState.__slots__`. Add a `[vitals]` section to `DEFAULT_CONFIG` and `CLAUDE_CODE_CONFIG`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Freeze initial task signature after first 5 actions (warmup). Before 5 actions, `goal_coherence` is `None`.
- **D-02:** Signature is captured once per session and never updated.
- **D-03:** Signature stored in `_AgentState` (in-memory, not persisted cross-session).
- **D-04:** Score = `cosine_similarity(current_behavior_vector, initial_task_vector)` — higher is better, range [0, 1].
- **D-05:** `goal_coherence` field in `VitalsSnapshot` is `float | None`.
- **D-06:** Default threshold for "wrong problem": 0.35 (configurable as `[vitals] goal_coherence_threshold` in soma.toml).
- **D-07:** Uses existing `compute_behavior_vector()` and `cosine_similarity()` — no new math.
- **D-08:** Baseline integrity flag fires when ALL of: (1) baseline `error_rate` EMA drifted >2× fingerprint's `avg_error_rate` norm, AND (2) current session error_rate >20%, AND (3) fingerprint `sample_count >= 10`.
- **D-09:** Distinguishes corruption from legitimate behavioral change.
- **D-10:** `baseline_integrity` is `bool` — True = intact, False = corrupted. Default True when insufficient fingerprint data.
- **D-11:** Computed inside engine using existing `FingerprintEngine` (loaded via `state.py`).
- **D-12:** DEFERRED — hook JSON output, `soma status`, CLI display changes are out of scope.
- **D-13:** `goal_coherence` and `baseline_integrity` land in `VitalsSnapshot` — consumers pick them up in a later pass.
- **D-14:** Goal coherence contributes to aggregate pressure via the same signal → pressure pipeline.
- **D-15:** Every numeric threshold must have a named constant or be read from config — no magic numbers inline.
- **D-16:** Defaults live in one place: `config_loader.py` `DEFAULT_CONFIG` or a `DEFAULTS` constant block.

### Claude's Discretion
- Exact pressure weighting for goal_coherence signal
- Whether goal_coherence uses a rolling window or all actions after signature
- Where to declare threshold constants (alongside `DEFAULTS` in `baseline.py` or new `vitals_config.py`)
- Test scenario design for the 4 success criteria

### Deferred Ideas (OUT OF SCOPE)
- Persisting task signature across sessions
- Using goal coherence as input to temporal task sharding (Phase 5)
- Goal coherence threshold auto-tuning via learning engine (Phase 2+)
- Hook JSON output, `soma status`, and CLI display changes
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VIT-01 | Goal Coherence Score — save initial task signature (first N actions behavior vector), periodically compute cosine distance to detect "agent solving wrong problem" separate from behavioral drift | `compute_behavior_vector()` + `cosine_similarity()` already in vitals.py; vector length mismatch must be handled via frozen known_tools snapshot |
| VIT-03 | Baseline Integrity Check — detect baseline corruption (adapting to bad behavior) by comparing baseline trajectory against historical fingerprint; distinguish adaptation from corruption | `FingerprintEngine.get(agent_id).avg_error_rate` + `sample_count` from fingerprint.py; `Baseline.get("error_rate")` from baseline.py; FingerprintEngine must be made accessible inside engine |
</phase_requirements>

---

## Standard Stack

### Core (all already present in codebase)
| Module | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `compute_behavior_vector()` | `src/soma/vitals.py:163` | Produces feature vector `[4 + len(tools)]` | Already used for drift |
| `cosine_similarity()` | `src/soma/vitals.py:205` | Cosine similarity [0,1] | Already handles zero vectors |
| `FingerprintEngine` | `src/soma/fingerprint.py` | Per-agent historical norms | Load via `state.get_fingerprint_engine()` |
| `Baseline.get("error_rate")` | `src/soma/baseline.py:61` | Current EMA value for a signal | Already tracked in `_AgentState.baseline` |
| `_AgentState` | `src/soma/engine.py:39` | Per-session state — add new fields here | Uses `__slots__` |
| `VitalsSnapshot` | `src/soma/types.py:82` | Frozen dataclass — add new fields | `slots=True`, needs defaults |

### No New Dependencies Required
All required primitives exist. No new PyPI packages. No new modules unless threshold constants need a dedicated home.

---

## Architecture Patterns

### Recommended Project Structure (unchanged)
```
src/soma/
├── types.py        — add goal_coherence, baseline_integrity to VitalsSnapshot
├── vitals.py       — add compute_goal_coherence(), compute_baseline_integrity()
├── engine.py       — update _AgentState.__slots__, wire into record_action()
├── baseline.py     — DEFAULTS pattern for vitals thresholds (or config_loader.py)
└── cli/
    └── config_loader.py — add [vitals] section to DEFAULT_CONFIG
```

### Pattern 1: Extending VitalsSnapshot
**What:** Add new fields to the frozen dataclass. All fields must have defaults to preserve backward compatibility with existing tests that call `VitalsSnapshot()` with no arguments.
**When to use:** Any new vital metric.
**Example:**
```python
# Source: src/soma/types.py — follow existing field pattern
@dataclass(frozen=True, slots=True)
class VitalsSnapshot:
    # ... existing fields ...
    goal_coherence: float | None = None   # None during warmup (< 5 actions)
    baseline_integrity: bool = True       # True = baseline is healthy
```

### Pattern 2: Extending _AgentState.__slots__
**What:** `_AgentState` uses `__slots__` for memory efficiency. New per-session state must be declared in `__slots__` or an `AttributeError` is raised at runtime.
**When to use:** Any new per-agent session variable.
**Example:**
```python
# Source: src/soma/engine.py:40 — follow existing pattern
class _AgentState:
    __slots__ = ("config", "ring_buffer", "baseline", "mode", "known_tools",
                 "baseline_vector", "action_count", "_last_active",
                 "initial_task_vector", "initial_known_tools")  # NEW fields

    def __init__(self, config: AgentConfig) -> None:
        # ... existing init ...
        self.initial_task_vector: list[float] | None = None
        self.initial_known_tools: list[str] | None = None
```

### Pattern 3: Threshold Constants Placement
**What:** Threshold defaults live in `config_loader.py`'s `DEFAULT_CONFIG` under a `[vitals]` section (and in `CLAUDE_CODE_CONFIG`). No inline magic numbers in `vitals.py` or `engine.py`.
**When to use:** Any new configurable threshold.
**Example:**
```python
# Source: src/soma/cli/config_loader.py — follow DEFAULT_CONFIG pattern
DEFAULT_CONFIG: dict[str, Any] = {
    # ... existing sections ...
    "vitals": {
        "goal_coherence_threshold": 0.35,
        "goal_coherence_warmup_actions": 5,
        "baseline_integrity_error_ratio": 2.0,   # baseline drifted > 2x fingerprint norm
        "baseline_integrity_min_error_rate": 0.20,  # current session error_rate floor
        "baseline_integrity_min_samples": 10,    # min fingerprint samples to judge
    },
}
```

### Pattern 4: Signal → Pressure Pipeline for goal_coherence
**What:** D-14 says goal_coherence enters the same signal → pressure pipeline. `pressure.py`'s `DEFAULT_WEIGHTS` needs a `goal_coherence` entry. In `engine.py`, call `compute_signal_pressure()` for goal_coherence when it's not None, otherwise skip (zero contribution during warmup).
**When to use:** Any new VitalsSnapshot field that contributes to aggregate pressure.

Note on direction: `goal_coherence` is similarity (higher = better). Pressure should increase when coherence is LOW. Invert before computing z-score: use `1.0 - goal_coherence` as the "signal value" fed to `compute_signal_pressure`, or set a low baseline so divergence produces positive z-scores. The simplest approach: treat `1.0 - goal_coherence` as the drift-like signal.

### Pattern 5: FingerprintEngine Access in Engine
**What:** `FingerprintEngine` is not currently a member of `SOMAEngine`. For baseline integrity, the engine needs it at `record_action()` time.
**When to use:** Lazy-load via `state.get_fingerprint_engine()` inside the integrity check function — consistent with hooks. Don't pass it as a constructor parameter (would change the public API).
**Example:**
```python
# In vitals.py or engine.py (inside compute_baseline_integrity helper):
from soma.state import get_fingerprint_engine
fp_engine = get_fingerprint_engine()
fp = fp_engine.get(agent_id)
```
**Tradeoff:** Disk I/O on every action. Acceptable because `get_fingerprint_engine()` reads a JSON file once per call — and this can be cached in `_AgentState` if benchmarking shows it matters. Flag as future optimization.

### Anti-Patterns to Avoid
- **Magic numbers inline:** Never write `if score < 0.35` — always read from config/constants.
- **Forgetting `__slots__`:** Adding a new attribute to `_AgentState` without updating `__slots__` causes `AttributeError` silently at assignment.
- **Forgetting field defaults in VitalsSnapshot:** All existing test code calls `VitalsSnapshot()` with positional args. New fields without defaults break those tests.
- **Computing current vector against growing known_tools for goal_coherence:** Must use `initial_known_tools` snapshot (frozen at action 5), not the live `s.known_tools`, when comparing to the initial task vector.
- **Using cosine_similarity(a, b) where len(a) != len(b):** zip() silently truncates — result is wrong. Always ensure same-length vectors.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity | Custom dot product / normalization | `cosine_similarity()` in vitals.py | Already handles zero vectors, tested |
| Behavior vectorization | Custom feature extraction | `compute_behavior_vector()` in vitals.py | Already tested, consistent with drift computation |
| EMA baseline reads | Custom state access | `Baseline.get("error_rate")` | Already handles cold-start blending |
| Fingerprint loading | Direct file I/O | `state.get_fingerprint_engine()` | Handles missing file, JSON errors gracefully |
| Pressure from vitals | Custom pressure math | `compute_signal_pressure()` in pressure.py | Consistent sigmoid z-score with everyone else |

**Key insight:** This phase is almost entirely a wiring job. The hard math (cosine similarity, EMA, fingerprint divergence) is already tested and production-hardened. New code is: compute functions, field additions, threshold plumbing.

---

## Common Pitfalls

### Pitfall 1: Vector Length Mismatch (CRITICAL)
**What goes wrong:** `compute_behavior_vector(actions, s.known_tools)` returns a vector of length `4 + len(s.known_tools)`. `s.known_tools` grows as new tools appear during the session. The initial task vector (captured at action 5) has length `4 + len(known_tools_at_action_5)`. By action 20, `known_tools` is longer. `cosine_similarity(current, initial)` uses `zip()` which truncates — extra tool dimensions are silently ignored, artificially inflating coherence.

**Why it happens:** `compute_behavior_vector` pads tool_dist with per-tool fractions for known tools. More tools = longer vector.

**How to avoid:** When capturing the initial task vector, also capture `s.known_tools` as `s.initial_known_tools` (a copy, not a reference). When computing current vector for goal_coherence comparison, always call `compute_behavior_vector(current_actions, s.initial_known_tools)` — not `s.known_tools`. This freezes the feature space at capture time.

**Warning signs:** Goal coherence stuck at 1.0 or never dropping even when agent clearly switches tasks.

### Pitfall 2: Omitting __slots__ for New _AgentState Fields
**What goes wrong:** Adding `self.initial_task_vector = None` in `__init__` raises `AttributeError: 'initial_task_vector' attribute does not exist` because `__slots__` is defined and the slot isn't in the tuple.

**Why it happens:** Python `__slots__` prevents `__dict__` creation; all attributes must be declared.

**How to avoid:** Update `__slots__` tuple at the same time as adding `__init__` assignments. Both changes in the same edit.

**Warning signs:** `AttributeError` immediately on first `record_action()` call.

### Pitfall 3: VitalsSnapshot Fields Without Defaults Break Existing Tests
**What goes wrong:** Adding `goal_coherence: float | None` without `= None` breaks every test that constructs `VitalsSnapshot(uncertainty=0.1, drift=0.0, ...)` without passing goal_coherence.

**Why it happens:** Frozen dataclasses require all fields with no default to be positional. New field without default = required positional arg.

**How to avoid:** Always add new VitalsSnapshot fields with defaults. `goal_coherence: float | None = None` and `baseline_integrity: bool = True`.

**Warning signs:** Dozens of test failures immediately after adding fields.

### Pitfall 4: Pressure Direction Inversion for goal_coherence
**What goes wrong:** `compute_signal_pressure(goal_coherence, baseline, std)` treats higher values as worse (z-score: current > baseline = pressure). But goal_coherence is a similarity score where higher = better, lower = problem.

**Why it happens:** All other signals (uncertainty, drift, error_rate) are "more = worse." Goal coherence is inverted.

**How to avoid:** Feed `1.0 - goal_coherence` as the signal to `compute_signal_pressure()`. This converts it to a "divergence" metric consistent with other signals.

**Warning signs:** Pressure drops when agent drifts to wrong task, rises when it stays on track — backwards behavior.

### Pitfall 5: FingerprintEngine Disk I/O Per Action
**What goes wrong:** `get_fingerprint_engine()` reads `~/.soma/fingerprint.json` on every call. If called per `record_action()`, this is file I/O on every agent action.

**Why it happens:** `state.py` always reads from disk (no caching).

**How to avoid:** Cache the loaded engine at module level or in `_AgentState` for the session duration. Alternatively, accept the overhead in v1 and mark as a performance optimization. The integrity check is cheap once the engine is loaded.

**Warning signs:** `record_action()` suddenly much slower; `strace` shows repeated file reads.

### Pitfall 6: Baseline Integrity Check When Fingerprint Has No Data
**What goes wrong:** `FingerprintEngine.get(agent_id)` returns `None` for new agents. The integrity check tries to read `fp.avg_error_rate` on a None object.

**Why it happens:** New agents have no fingerprint until their first session completes.

**How to avoid:** D-10 already specifies: default `baseline_integrity = True` when fingerprint is absent or `sample_count < 10`. Guard: `if fp is None or fp.sample_count < MIN_SAMPLES: return True`.

---

## Code Examples

### Goal Coherence Computation (in vitals.py)
```python
# Suggested function signature for vitals.py
def compute_goal_coherence(
    current_actions: Sequence[Action],
    initial_task_vector: list[float],
    initial_known_tools: list[str],
) -> float:
    """Cosine similarity between current behavior and initial task signature.

    Returns float in [0, 1]. Higher = agent still working on original task.
    Uses initial_known_tools (frozen at signature capture time) to ensure
    consistent vector dimensionality.
    """
    current_vec = compute_behavior_vector(current_actions, initial_known_tools)
    return cosine_similarity(current_vec, initial_task_vector)
```

### Baseline Integrity Check (in vitals.py)
```python
def compute_baseline_integrity(
    baseline_error_rate: float,
    current_error_rate: float,
    fingerprint_avg_error_rate: float,
    fingerprint_sample_count: int,
    min_samples: int,
    error_ratio_threshold: float,
    min_current_error_rate: float,
) -> bool:
    """True = baseline is intact, False = potential baseline corruption.

    Fires False when ALL of:
    - fingerprint has enough history (sample_count >= min_samples)
    - baseline EMA error_rate has drifted > error_ratio_threshold * fingerprint norm
    - current session error_rate is still elevated (> min_current_error_rate)
    """
    if fingerprint_sample_count < min_samples:
        return True  # Not enough history to judge — assume intact
    if fingerprint_avg_error_rate <= 0:
        return True  # No historical error rate to compare against
    drift_ratio = baseline_error_rate / max(fingerprint_avg_error_rate, 0.001)
    if drift_ratio > error_ratio_threshold and current_error_rate > min_current_error_rate:
        return False
    return True
```

### Signal Capture in engine.py record_action()
```python
# After action 5: freeze task signature (add after action_count increment)
if s.action_count == VITALS_WARMUP_ACTIONS and s.initial_task_vector is None:
    s.initial_known_tools = list(s.known_tools)  # snapshot, not reference
    s.initial_task_vector = compute_behavior_vector(actions, s.initial_known_tools)

# Compute goal_coherence (None during warmup)
goal_coherence: float | None = None
if s.initial_task_vector is not None and s.initial_known_tools is not None:
    goal_coherence = compute_goal_coherence(actions, s.initial_task_vector, s.initial_known_tools)
```

### Pressure Integration for goal_coherence
```python
# In engine.py, after existing signal_pressures dict construction:
if goal_coherence is not None:
    # Invert: low coherence = high divergence = high pressure
    goal_coherence_divergence = 1.0 - goal_coherence
    signal_pressures["goal_coherence"] = compute_signal_pressure(
        goal_coherence_divergence,
        s.baseline.get("goal_coherence"),
        s.baseline.get_std("goal_coherence"),
    )
    s.baseline.update("goal_coherence", goal_coherence_divergence)
```

### Config [vitals] Section Addition
```python
# In config_loader.py DEFAULT_CONFIG:
"vitals": {
    "goal_coherence_threshold": 0.35,
    "goal_coherence_warmup_actions": 5,
    "baseline_integrity_error_ratio": 2.0,
    "baseline_integrity_min_error_rate": 0.20,
    "baseline_integrity_min_samples": 10,
},
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Scalar behavioral drift only | Goal coherence as separate metric | Phase 1 | Distinguishes "HOW changed" from "WHAT changed" |
| No baseline integrity check | EMA corruption detection via fingerprint | Phase 1 | Catches baselines that normalize bad behavior |
| Drift covers task changes | Goal coherence as VitalsSnapshot field | Phase 1 | Explicit signal for wrong-problem detection |

---

## Open Questions

1. **Where to declare vitals threshold constants**
   - What we know: D-16 says defaults in one place — `config_loader.py` `DEFAULT_CONFIG` or a `DEFAULTS` block in `baseline.py`
   - What's unclear: Whether a new `VITALS_DEFAULTS` dict in `vitals.py` is cleaner than adding to `config_loader.py`
   - Recommendation: Put in `config_loader.py`'s `DEFAULT_CONFIG` under `[vitals]` section — matches D-06's `soma.toml` specification and keeps all config defaults co-located. Add named constants at top of `engine.py` or `vitals.py` as fallbacks if config key missing.

2. **Pressure weight for goal_coherence**
   - What we know: D-14 says same pipeline, no special-casing. DEFAULT_WEIGHTS in pressure.py has `uncertainty=2.0, drift=1.8, error_rate=1.5`.
   - What's unclear: What weight? Goal coherence measures task deviation, similar in importance to behavioral drift.
   - Recommendation: Start with `goal_coherence: 1.5` (same as error_rate). This is moderate — enough to be detectable without over-dominating. Configurable via `[weights]` in soma.toml.

3. **Rolling window vs all-actions for current vector**
   - What we know: Ring buffer in `_AgentState` holds last 10 actions (engine.py line 45). `compute_behavior_vector` is called with `list(s.ring_buffer)` — always the last 10 actions.
   - What's unclear: Claude's discretion area — use rolling window (last 10) or all actions after signature.
   - Recommendation: Use the same ring buffer window (last N actions) already used for drift. Consistent behavior, no new state required. The planner can document this explicitly.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/ -x` |
| Full suite command | `uv run pytest tests/ --cov=soma --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VIT-01 SC1 | `VitalsSnapshot` has `goal_coherence` field | unit | `uv run pytest tests/test_types.py -x -k goal_coherence` | ❌ Wave 0 |
| VIT-01 SC2 | Agent drifting to unrelated task gets coherence < 0.35, behavioral drift stays normal | unit | `uv run pytest tests/test_vitals.py -x -k goal_coherence` | ❌ Wave 0 |
| VIT-03 SC3 | `VitalsSnapshot` has `baseline_integrity` field | unit | `uv run pytest tests/test_types.py -x -k baseline_integrity` | ❌ Wave 0 |
| VIT-03 SC4 | Agent with 20+ high-error actions adapting baseline triggers `baseline_integrity=False`, distinguishable from legitimate change | unit + integration | `uv run pytest tests/test_engine.py -x -k baseline_integrity` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_vitals.py tests/test_types.py tests/test_engine.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_vitals.py` — extend with `TestGoalCoherence` and `TestBaselineIntegrity` classes
- [ ] `tests/test_types.py` — extend with field presence checks for new VitalsSnapshot fields
- [ ] `tests/test_engine.py` — extend with integration tests: goal coherence after warmup, baseline corruption scenario
- [ ] No new conftest.py fixtures needed — existing `normal_actions` and `error_actions` fixtures are sufficient

---

## Sources

### Primary (HIGH confidence)
- `src/soma/vitals.py` — `compute_behavior_vector()` signature, `cosine_similarity()` implementation, vector dimensions
- `src/soma/engine.py` — `_AgentState.__slots__`, `record_action()` flow, VitalsSnapshot construction at lines 401-408
- `src/soma/fingerprint.py` — `Fingerprint.avg_error_rate`, `sample_count`, `FingerprintEngine.get()`
- `src/soma/baseline.py` — `Baseline.get()`, `DEFAULTS` pattern
- `src/soma/types.py` — `VitalsSnapshot` frozen dataclass with `slots=True`
- `src/soma/pressure.py` — `DEFAULT_WEIGHTS`, `compute_signal_pressure()` z-score formula
- `src/soma/state.py` — `get_fingerprint_engine()` lazy-load pattern
- `src/soma/cli/config_loader.py` — `DEFAULT_CONFIG` structure, `CLAUDE_CODE_CONFIG`
- `tests/test_vitals.py`, `tests/conftest.py` — test patterns and fixtures

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions D-01 through D-16 — verified against implementation patterns in codebase

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all code read directly from source
- Architecture patterns: HIGH — derived from direct code inspection, no inference
- Pitfalls: HIGH — vector length mismatch (zip truncation) verified by reading cosine_similarity() source; __slots__ constraint verified by reading _AgentState; VitalsSnapshot backward compat verified by reading test files
- Pressure direction: HIGH — verified by reading compute_signal_pressure() z-score formula (current > baseline = more pressure)

**Research date:** 2026-03-30
**Valid until:** Indefinite — this is brownfield research from live source code, not versioned library docs
