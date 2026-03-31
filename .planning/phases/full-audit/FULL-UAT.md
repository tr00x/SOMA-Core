---
status: complete
phase: full-audit
source: phases 01-08 (automated verification)
started: 2026-03-31T00:00:00Z
updated: 2026-03-31T00:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Full test suite passes
expected: uv run pytest -q returns 728 passed, 0 failed
result: pass

### 2. Public API imports clean
expected: PolicyEngine, guardrail, track, PressureVector all importable from soma
result: pass

### 3. soma.quickstart() works
expected: engine.get_snapshot returns pressure=0.0, level=OBSERVE
result: pass

### 4. soma.track() records an action
expected: t.result.mode in ResponseMode, t.result.pressure in [0, 1]
result: pass

### 5. soma.track() marks errors on exception
expected: exception propagates AND t.result.vitals.error_rate > 0
result: pass
note: error_rate=1.0 on first action after exception

### 6. PressureVector propagates through graph
expected: upstream error_rate=0.8 propagates to downstream node (requires both nodes to have internal_pressure_vector set, as engine always does)
result: pass
note: downstream error_rate = 0.48 (0.8 * damping 0.6)

### 7. Coordination SNR isolates noisy nodes
expected: upstream with error_rate=0 → SNR=0.0, node isolated (effective=0)
result: pass

### 8. Task complexity estimated from system prompt
expected: system_prompt with ambiguity markers yields score > 0
result: pass
note: score=0.59 for prompt with "ambiguous", "unclear", "interdependent"

### 9. Half-life prediction returns sane values
expected: 0 < pred <= 1.0, hl > 10.0
result: pass
note: hl=45.0, P(success@10)=0.86

### 10. Calibration score computed correctly
expected: compute_calibration_score(0.5, 0.0) == 0.75
result: pass

### 11. Verbal-behavioral divergence detected
expected: (0.8 - 0.1) > 0.4 → True; (0.5 - 0.8) > 0.4 → False
result: pass

### 12. PolicyEngine evaluates dict rules
expected: warn fires at error_rate=0.5, silent at 0.1
result: pass

### 13. @soma.guardrail blocks at threshold
expected: allows call at low pressure; raises SomaBlocked at effective_pressure=0.9
result: pass

### 14. PolicyEngine.from_file() loads TOML
expected: 1 rule loaded, name and action correct
result: pass

### 15. Framework adapters importable without frameworks
expected: LangChain, CrewAI, AutoGen adapters importable without deps
result: pass

### 16. TypeScript SDK files exist and export correctly
expected: all 5 src/*.ts files exist, all 5 symbols exported from index.ts
result: pass

### 17. Ruff linting passes
expected: "All checks passed!"
result: pass

### 18. VitalsSnapshot includes all new fields
expected: goal_coherence, calibration_score, task_complexity, predicted_success_rate all present, default None
result: pass

## Summary

total: 18
passed: 18
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
