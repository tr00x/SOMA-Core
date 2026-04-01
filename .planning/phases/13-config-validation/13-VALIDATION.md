---
phase: 13
slug: config-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/test_benchmark.py tests/test_session_store.py tests/test_cross_session_predictor.py tests/test_threshold_tuner.py tests/test_task_phase_drift.py -q --tb=short` |
| **Full suite command** | `uv run python -m pytest tests/ -q --tb=short` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick command
- **After every plan wave:** Run full suite
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 3 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | PRED-01 | unit | `uv run python -m pytest tests/test_benchmark.py -q` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | PRED-01 | integration | `uv run python -m pytest tests/test_benchmark.py -q` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | TUNE-01, ANOM-01 | unit | `uv run python -m pytest tests/test_session_history.py tests/test_cross_session.py -q` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 1 | TASK-01 | unit | `uv run python -m pytest tests/test_cross_session.py -q` | ❌ W0 | ⬜ pending |
| 13-03-01 | 03 | 2 | PRED-01 | integration | `uv run python -m soma benchmark --dry-run` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_benchmark.py` — stubs for benchmark harness and scenario tests
- [ ] `tests/test_session_history.py` — stubs for session history storage
- [ ] `tests/test_cross_session.py` — stubs for cross-session predictor and task phase detection

*Existing test infrastructure (pytest, conftest) already covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Benchmark rich terminal output | PRED-01 | Visual formatting | Run `soma benchmark` and verify rich tables display correctly |
| BENCHMARK.md readability | PRED-01 | Content quality | Read docs/BENCHMARK.md and verify results are clear and compelling |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 3s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
