---
phase: 12
slug: contributing-guide
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -q --tb=short` |
| **Full suite command** | `uv run pytest -q --tb=short` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -q --tb=short`
- **After every plan wave:** Run `uv run pytest -q --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | LAYER-01 | unit | `uv run pytest tests/test_hook_adapter.py -q` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | HOOK-01 | unit | `uv run pytest tests/test_cursor_hooks.py tests/test_windsurf_hooks.py -q` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 2 | NPM-01 | build | `cd packages/soma-ai && npm run build` | ✅ | ⬜ pending |
| 12-02-02 | 02 | 2 | POL-03 | unit | `uv run pytest tests/test_policy_packs.py -q` | ❌ W0 | ⬜ pending |
| 12-03-01 | 03 | 2 | DEMO-01 | manual | Visual inspection of demo output | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_hook_adapter.py` — stubs for LAYER-01 hook adapter protocol
- [ ] `tests/test_cursor_hooks.py` — stubs for Cursor hook adapter
- [ ] `tests/test_windsurf_hooks.py` — stubs for Windsurf hook adapter
- [ ] `tests/test_policy_packs.py` — stubs for POL-03 community policy packs

*Existing infrastructure covers test framework and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Demo GIF renders correctly | DEMO-01 | Visual content verification | Review generated demo output for accuracy and clarity |
| NPM package installs cleanly | NPM-01 | Requires npm registry interaction | `npm pack` and inspect tarball contents |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
