# Phase 15: Signal Reflexes - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Every existing pipeline signal triggers a real action, not just a number. Convert predictor, drift, half-life, RCA, and quality modules from passive computation into active interventions.

</domain>

<decisions>
## Implementation Decisions

### Predictor → Auto-checkpoint
- **D-01:** When predictor confidence > 70% and escalation within 3 actions → auto `git stash push -m "soma-checkpoint-{N}"`
- **D-02:** In GUIDE mode: inject warning only. In REFLEX mode: auto-checkpoint
- **D-03:** Checkpoint logic in new module `src/soma/signal_reflexes.py` (separate from pattern reflexes)

### Drift → Scope Guardian
- **D-04:** When drift > 0.4 → inject original task into agent context
- **D-05:** Original task extracted from session context (first system prompt or task description)
- **D-06:** Format: "Your task: {X}. You're now doing: {Y}. Refocus."

### Half-life → Handoff Suggestion
- **D-07:** When predicted success rate < 40% → inject handoff summary
- **D-08:** Summary includes: what was done, what's left, key files touched
- **D-09:** In multi-agent graph: reduce trust weight for degraded agent

### RCA → Diagnosis Injection
- **D-10:** When error_rate > 30% → run RCA, inject root cause into context
- **D-11:** Format: "[SOMA DIAGNOSIS] Root cause: {cause}. Fix: {suggestion}"
- **D-12:** Not a block — injection only, agent decides what to do with diagnosis

### Quality → Commit Gate
- **D-13:** Grade D/F → block git commit in PreToolUse
- **D-14:** Grade C → inject warning but allow commit
- **D-15:** Uses existing quality.py grader, evaluated on recent actions

### Session Report Extension
- **D-16:** `soma report` includes reflex stats: blocks count, top reflex, estimated errors prevented
- **D-17:** Notification channel logs signal reflex events same as pattern reflexes

### Claude's Discretion
- How to detect "original task" from session context
- How to compute handoff summary (what files, what progress)
- Quality grade computation timing (per-commit vs continuous)
- Git stash cleanup strategy for old checkpoints

</decisions>

<specifics>
## Specific Ideas

- User wants every module to DO something, not just compute — "Ferrari engine, no wheels"
- RCA injection is the difference between "error rate high" (useless) and "pip install PyJWT" (actionable)
- Auto-checkpoint before predicted escalation = insurance policy, zero cost when things go well
- Quality commit gate is like a linter but for behavioral quality

</specifics>

<canonical_refs>
## Canonical References

### Design spec
- `docs/superpowers/specs/2026-04-01-soma-nervous-system-design.md` §3.2-3.6 — Signal reflex specifications

### Existing modules to activate
- `src/soma/predictor.py` — PressurePredictor (linear trend + pattern boost)
- `src/soma/halflife.py` — compute_half_life, predict_success_rate, generate_handoff_suggestion
- `src/soma/rca.py` — Root cause analysis
- `src/soma/quality.py` — A-F code quality grading
- `src/soma/vitals.py` — compute_drift, drift detection

### Reflex infrastructure (Phase 14)
- `src/soma/reflexes.py` — ReflexResult, evaluate(), pattern reflexes
- `src/soma/hooks/pre_tool_use.py` — Mode-gated hook with reflex support
- `src/soma/hooks/notification.py` — Agent awareness + injection
- `src/soma/hooks/common.py` — Helper functions for reflex state

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `reflexes.py` evaluate() pattern — extend with signal_evaluate() or compose
- `predictor.py` already returns Prediction with actions_until and confidence
- `halflife.py` already has generate_handoff_suggestion()
- `rca.py` already produces structured findings
- `quality.py` already grades A-F

### Integration Points
- signal_reflexes.py called from notification hook (for injection) and pre_tool_use (for commit gate)
- Auto-checkpoint needs subprocess.run("git stash") — careful with error handling
- Drift detection needs access to session's original task — stored where?

</code_context>

<deferred>
## Deferred Ideas

- Circuit breaker for multi-agent graph — Phase 16
- Session memory injection — Phase 16
- Smart throttle — Phase 16
- Context overflow management — Phase 16

</deferred>

---

*Phase: 15-signal-reflexes*
*Context gathered: 2026-04-01*
