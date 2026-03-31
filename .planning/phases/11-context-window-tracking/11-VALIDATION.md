---
phase: 11
slug: context-window-tracking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | OTL-01 | unit | `pytest tests/test_otel_exporter.py -v` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | OTL-01 | unit | `pytest tests/test_otel_exporter.py -v` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 1 | RPT-01 | unit | `pytest tests/test_report.py -v` | ❌ W0 | ⬜ pending |
| 11-02-02 | 02 | 1 | RPT-01 | unit | `pytest tests/test_report.py -v` | ❌ W0 | ⬜ pending |
| 11-03-01 | 03 | 2 | ALT-01 | unit | `pytest tests/test_webhook.py -v` | ❌ W0 | ⬜ pending |
| 11-04-01 | 04 | 2 | HIST-01 | unit | `pytest tests/test_analytics.py -v` | ❌ W0 | ⬜ pending |
| 11-05-01 | 05 | 1 | CTX | unit | `pytest tests/test_context_usage.py -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_otel_exporter.py` — stubs for OTL-01
- [ ] `tests/test_report.py` — stubs for RPT-01
- [ ] `tests/test_webhook.py` — stubs for ALT-01
- [ ] `tests/test_analytics.py` — stubs for HIST-01
- [ ] `tests/test_models.py` — stubs for model context window detection

*Existing infrastructure covers context pressure (test_context_usage.py) and predictor (test_predictor.py) patterns.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OTel spans visible in Jaeger/Grafana | OTL-01 | Requires external collector | Start Jaeger, run SOMA with OTel enabled, verify spans in UI |
| Webhook delivery to Slack/Discord | ALT-01 | Requires external webhook URL | Configure test webhook, trigger WARN, verify delivery |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
