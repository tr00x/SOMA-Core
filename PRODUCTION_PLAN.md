# SOMA Production Plan

**Date:** 2026-04-18
**Baseline:** 361 real guidance_outcomes / 24h clean data / 40% overall precision

## Today's commit (9fdddb0)

Closed guidance→analytics pipeline:
1. `_record_outcome_if_resolved` bridges firings to analytics.db
2. Pressure-based resolver (15% drop = helped, flat 2 actions = ignored) for drift/cost_spiral/context/budget/error_cascade
3. fastapi/uvicorn moved from [dashboard] extra → core deps
4. ROI dashboard whitelist (excludes test_key/retry_loop/mixed/bad_pattern/maybe_bad)

1449 tests passing.

## Honest metrics snapshot

| Pattern | Fires | Helped | % |
|---|---|---|---|
| _stats | 240 | 75 | 31 |
| error_cascade | 33 | 30 | **91** |
| blind_edit | 30 | 30 | **100** |
| entropy_drop | 17 | 5 | 29 |
| retry_storm | 16 | 0 | **0 ❌** |
| drift | 16 | 0 | **0 ❌** |
| bash_retry | 9 | 5 | 56 |
| cost_spiral | 0 | — | — |
| context | 0 | — | — |
| budget | 0 | — | — |

## P0 — Blockers (do this session)

### 1. retry_storm precision = 0%
16 firings, zero helped. Hypothesis: fires after 3+ consecutive fails — agent already
gave up or switched tool anyway. Fix options:
- Lower threshold from 3 to 2 consecutive fails
- Verify `check_followthrough` retry_storm branch (line 168-177) matches reality
- Compare firing time vs. actual agent recovery time

### 2. drift precision = 0%
Pressure-based resolver uses 15% drop threshold. drift doesn't correlate with
pressure drops (it's a state signal, not an actionable nudge). Fix options:
- Lower drift-specific threshold to 8%
- Remove drift from actionable patterns (keep as vital only, stop firing guidance)
- Add `drift`-specific followthrough detection (e.g. tool diversity improvement)

### 3. Release v2026.4.2 → PyPI + GitHub
Without release, fixes never reach users. Steps:
- Bump version in pyproject.toml
- Update CHANGELOG.md
- `git tag v2026.4.2 && git push --tags`
- GitHub Actions publishes to PyPI
- Create GitHub release

## P1 — Next 3-5 days

### 4. Fire-rate audit: cost_spiral, context, budget
Zero firings in 24h. Either thresholds too high or trigger bugged. Read each
pattern's `_check_*` method in `contextual_guidance.py`, run against real logs.

### 5. Session cleanup
`~/.soma/sessions/` has 2400+ dirs. Add `soma prune --older-than 30d` CLI command.

### 6. entropy_drop 29% precision
12/17 ignored. Acceptable but not great. Collect 100+ firings before deciding
fate.

### 7. Dashboard whitelist source of truth
Whitelist hardcoded in `data.py:_REAL_PATTERN_KEYS`. Move to
`contextual_guidance._PATTERN_PRIORITY.keys()` (plus `_stats`) so there's one
place to update when adding patterns.

## P2 — Production polish

### 8. Real benchmark: 100 sessions
Precision/recall on actual dataset, not just firing counts. Compare
with-SOMA vs baseline on known-hard tasks.

### 9. Tier 2 healing validation
Bash→Read -7% now verifiable with clean data. Run query on guidance_outcomes
+ action sequences to confirm.

### 10. Setup UX
`soma setup` must work out-of-the-box after `pip install soma-ai` without
`uv tool install --force --editable .`.

## Recommended start

P0.1 (retry_storm) is easiest signal — 16 firings, 0 helped is clearly broken
behavior, not just bad luck. Fix it first, see if precision jumps.
