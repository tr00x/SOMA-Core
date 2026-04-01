---
phase: 14
slug: core-reflexes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/test_reflexes.py tests/test_reflex_benchmark.py -q --tb=short` |
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
| 14-01-01 | 01 | 1 | RFX-01 | unit | `uv run python -m pytest tests/test_reflexes.py -q` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | RFX-02 | unit+integration | `uv run python -m pytest tests/test_reflexes.py -q` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | RFX-03 | integration | `uv run python -m pytest tests/test_reflex_hooks.py -q` | ❌ W0 | ⬜ pending |
| 14-02-02 | 02 | 1 | RFX-04 | integration | `uv run python -m pytest tests/test_reflex_benchmark.py -q` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_reflexes.py` — stubs for reflex engine unit tests
- [ ] `tests/test_reflex_hooks.py` — stubs for hook integration tests
- [ ] `tests/test_reflex_benchmark.py` — stubs for benchmark with reflexes

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Agent awareness prompt appears in Claude Code | RFX-03 | Requires live Claude Code session | Start Claude Code with SOMA, check first notification output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 3s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
