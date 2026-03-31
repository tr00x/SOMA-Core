# Phase 1: Vitals Accuracy - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Add two new vitals to `VitalsSnapshot`: `goal_coherence` (float) and `baseline_integrity` (bool). Goal coherence detects "agent solving wrong problem" (separate from behavioral drift). Baseline integrity detects when the EMA baseline has been corrupted by adapting to bad behavior. No other changes — not uncertainty classification, not pressure vectors.

**Scope constraint:** Core engine only — `types.py`, `vitals.py`, `engine.py`, `fingerprint.py`, `baseline.py`. Hook output, statusline, and CLI display changes are deferred to a later integration pass. All thresholds must be configurable (no hardcoded values) — exposed via `AgentConfig` or `soma.toml` `[vitals]` section with sensible defaults.

</domain>

<decisions>
## Implementation Decisions

### Task signature capture (VIT-01)
- **D-01:** Freeze the initial task signature after the first **5 actions** of a session (warmup window). Before 5 actions, `goal_coherence` is `None` / not computed.
- **D-02:** Signature is captured once per session and never updated — it's the anchor for "what the agent was supposed to be doing."
- **D-03:** Signature is stored in `_AgentState` (in-memory per session, not persisted cross-session).

### Goal coherence scoring (VIT-01)
- **D-04:** Score = `cosine_similarity(current_behavior_vector, initial_task_vector)` — higher is better, range [0, 1].
- **D-05:** `goal_coherence` field in `VitalsSnapshot` is `float | None` — `None` during warmup (< 5 actions), float after.
- **D-06:** Default threshold for "wrong problem": **0.35** (coherence below this triggers concern). Configurable in `soma.toml` under `[vitals]` as `goal_coherence_threshold`.
- **D-07:** Uses existing `compute_behavior_vector()` and `cosine_similarity()` from `vitals.py` — no new math needed.

### Baseline integrity check (VIT-03)
- **D-08:** Flag fires when ALL of: (1) baseline `error_rate` EMA has drifted >2× the fingerprint's `avg_error_rate` norm, AND (2) current session error_rate remains elevated (>20%), AND (3) fingerprint has `sample_count >= 10` (enough history to judge).
- **D-09:** This distinguishes corruption ("baseline adapted down to absorb high errors") from legitimate change ("behavior and baseline shifted together for valid reasons").
- **D-10:** `baseline_integrity` is `bool` — `True` means baseline IS intact, `False` means potential corruption detected. Default `True` when insufficient fingerprint data.
- **D-11:** Computed inside the engine using the existing `FingerprintEngine` (already loaded via `state.py`).

### Output visibility
- **D-12:** DEFERRED — hook JSON output, `soma status`, and CLI display changes are out of scope for this phase.
- **D-13:** `goal_coherence` and `baseline_integrity` land in `VitalsSnapshot` — the engine computes them. Consumers (hooks, CLI) pick them up in a later integration pass.
- **D-14:** Goal coherence contributes to aggregate pressure via the same signal → pressure pipeline (no special-casing). Guidance messages from these signals: deferred.

### No hardcoding rule
- **D-15:** Every numeric threshold (signature warmup count, goal coherence threshold, baseline integrity ratio, min fingerprint samples) must have a named constant or be read from config — no magic numbers inline.
- **D-16:** Defaults live in one place: `config_loader.py` defaults dict or a `DEFAULTS` constant block (consistent with `baseline.py` pattern).

### Claude's Discretion
- Exact pressure weighting for goal_coherence signal
- Whether goal_coherence uses a rolling window or all actions after signature
- Where to declare threshold constants (alongside `DEFAULTS` in `baseline.py` or new `vitals_config.py`)
- Test scenario design for the 4 success criteria

</decisions>

<specifics>
## Specific Ideas

- VIT-01 requirement: "agent solving wrong problem" must be distinct from behavioral drift. Drift = HOW the agent works changed. Goal coherence = WHAT problem it's working on changed.
- VIT-03 requirement: scenario is agent running 20+ high-error actions and baseline adapting (absorbing the failures as "normal") — this is the corruption case.

</specifics>

<canonical_refs>
## Canonical References

### Requirements
- `.planning/REQUIREMENTS.md` §VIT-01, §VIT-03 — Exact requirement definitions
- `.planning/ROADMAP.md` §Phase 1 — Success criteria (4 specific conditions that must be TRUE)

### Existing code to extend
- `src/soma/types.py` — `VitalsSnapshot` dataclass to extend with new fields
- `src/soma/vitals.py` — `compute_behavior_vector()`, `cosine_similarity()` already implemented; add new compute functions here
- `src/soma/fingerprint.py` — `FingerprintEngine`, `Fingerprint.divergence()` — baseline integrity reads fingerprint data
- `src/soma/engine.py` — `_AgentState` (stores per-session state, add `initial_task_vector` here), `VitalsSnapshot` construction (line 401-407)
- `src/soma/baseline.py` — `Baseline.get()` returns EMA value for `error_rate` signal — used in integrity check

### Tests reference
- `tests/` — existing vitals tests show pattern for unit testing compute functions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_behavior_vector(actions, known_tools)` in `vitals.py:163` — produces the feature vector for cosine comparison
- `cosine_similarity(a, b)` in `vitals.py:205` — already implemented, no new math
- `FingerprintEngine.get(agent_id)` in `fingerprint.py:106` — returns `Fingerprint | None` with `avg_error_rate` and `sample_count`
- `Baseline.get("error_rate")` in `baseline.py:61` — returns current EMA value for error_rate signal

### Established Patterns
- `VitalsSnapshot` is a frozen dataclass with `slots=True` — adding fields follows the same pattern
- Engine builds `VitalsSnapshot` at `engine.py:404` — new fields computed just before construction
- `_AgentState` holds per-agent session state — add `initial_task_vector: list[float] | None = None` here, set after action #5

### Integration Points
- `_AgentState` → store `initial_task_vector` after 5th action
- `compute_all_vitals()` (or equivalent in engine) → add goal coherence computation
- Baseline integrity: read `Baseline._value["error_rate"]` vs `Fingerprint.avg_error_rate`
- `VitalsSnapshot` construction in `record_action()` → pass new fields

</code_context>

<deferred>
## Deferred Ideas

- Persisting task signature across sessions (mentioned as possible enhancement) — Phase 5 scope or later
- Using goal coherence as input to temporal task sharding — Phase 5
- Goal coherence threshold auto-tuning via learning engine — Phase 2+

</deferred>

---

*Phase: 01-vitals-accuracy*
*Context gathered: 2026-03-30*
