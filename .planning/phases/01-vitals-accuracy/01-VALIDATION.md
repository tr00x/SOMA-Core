---
phase: 1
slug: vitals-accuracy
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/test_vitals.py tests/test_types.py tests/test_engine.py -x` |
| **Full suite command** | `uv run pytest tests/ --cov=soma --cov-report=term-missing` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_vitals.py tests/test_types.py tests/test_engine.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | VIT-01, VIT-03 | unit | `uv run pytest tests/test_types.py -x -k "goal_coherence or baseline_integrity"` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | VIT-01 | unit | `uv run pytest tests/test_vitals.py -x -k goal_coherence` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 0 | VIT-03 | unit | `uv run pytest tests/test_engine.py -x -k baseline_integrity` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | VIT-01 SC1,SC2 | unit | `uv run pytest tests/test_vitals.py -x -k goal_coherence` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | VIT-01 SC1 | unit | `uv run pytest tests/test_types.py -x -k goal_coherence` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 2 | VIT-03 SC3 | unit | `uv run pytest tests/test_vitals.py -x -k baseline_integrity` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | VIT-03 SC3,SC4 | unit+integration | `uv run pytest tests/test_engine.py -x -k baseline_integrity` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_vitals.py` — add `TestGoalCoherence` class with stubs for compute_goal_coherence tests
- [ ] `tests/test_types.py` — add field presence checks for `goal_coherence` and `baseline_integrity` in VitalsSnapshot
- [ ] `tests/test_engine.py` — add `TestGoalCoherenceIntegration` and `TestBaselineIntegrityIntegration` stubs

*No new conftest.py fixtures needed — existing `normal_actions` and `error_actions` fixtures are sufficient.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
