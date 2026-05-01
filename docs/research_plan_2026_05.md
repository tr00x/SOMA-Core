# SOMA Research Plan — Pivot from Product Iteration to Hypothesis Testing

**Status**: 2026-05-01. Current production code at commit `4dcc85f`. Tests `1853 passed / 8 skipped`. PyPI `soma-ai==2026.4.30` shipped.

This document is the recovery point for the SOMA project after the conclusion that **the current text-injection guidance hypothesis is not supported by empirical data**, but **the methodology that produced that conclusion was naive and may have led us to wrong null result**. Pick this up cold.

---

## What we already know (don't re-litigate)

### Empirically tested + disproved (in this configuration)

- **Live A/B on `~/.soma/analytics.db`** (16 days, 532 sessions, 41 paired observations on `bash_retry`):
  - p=0.43, Cohen's d=-0.25
  - Treatment Δp=+0.486, Control Δp=+0.532
  - File: `validation_snapshot.json`
  - Conclusion: no statistically significant treatment effect for any pattern.

- **Public-trace replay** (1,000 traces, 13,510 actions from GPT-4o + Claude-3.5-Sonnet):
  - `bash_retry`: 95.4% natural recovery within 3 actions (no headroom)
  - `entropy_drop`: 35% natural recovery (real headroom — only candidate)
  - All detectors lift ≈ 1.0 against base rate (not preferentially predictive)
  - Files: `tools/replay_traces.py`, `public_traces_report.json`, `docs/external_validation_2026_04_30.md`
  - Conclusion: confirms live finding — **bash_retry's "92.1% helped" is regression to mean**.

### What's known to work (don't break)

- **Hard blocks** (`_STRICT_BLOCK_PATTERNS`): blind_edit + bash_retry as PreToolUse blocks. Deterministic prevention, no statistical claim needed.
- **Observability stack**: pressure model, dashboard, fingerprinting, pattern firings recorded with `firing_id`. Real production-grade infra.
- **A/B harness mechanically correct**: block-randomized arms, atomic counters, `firing_id` integrity guaranteed by SQLite trigger. The harness itself is sound — it's the *intervention* that didn't show effect.

---

## What we have NOT tested (the methodological gaps)

These are the things that could explain a false null result. Each is a separate hypothesis to test before declaring guidance dead.

| # | Gap | Status |
|---|---|---|
| 1 | **Injection channel** — only tested tool_response stdout. Never tested: system prompt, synthetic user message, pre-tool prompt, structured error format. | not started |
| 2 | **Timing** — only PostToolUse. Never tested PreToolUse intervention. | not started |
| 3 | **Format** — only prose `[SOMA] ...`. Never tested JSON / XML / function-call-result / structured. | not started |
| 4 | **Pattern derivation** — patterns invented from intuition. Never derived from manual analysis of failed traces. | not started |
| 5 | **Pressure as a unified scalar** — assumed but not validated. May need per-domain interventions, not global "agent stressed". | not started |
| 6 | **Measurement horizon** — fixed at h=2 because dashboard. Effect could be at h=5/10/20. | not started |
| 7 | **Outcome metric** — measure pressure-delta (our own signal). Real metric should be **task completion rate**. Public traces have `resolved` flag — barely used. | not started |
| 8 | **Single agent + scaffold** — only Claude in Claude Code. Untested on weaker models (Llama, GPT-3.5, Qwen) where intervention might matter more. | not started |
| 9 | **No ablation studies** — never A/B'd 3 different wordings, 3 different thresholds, 3 different formats of the same pattern. | not started |

**Key insight**: we tested ONE point in a ~5-dimensional design space (channel × timing × format × pattern × horizon). A null result on one point doesn't disprove the concept.

---

## The research pivot — Phase plan

This is **research mode, not product mode**. Estimated effort: 2-3 months focused work. Each phase has a kill-criterion to prevent endless drift.

### Phase A: Data-driven failure-mode catalogue (week 1-2)

**Goal**: replace 9 invented patterns with N patterns derived from real failure observation.

**Deliverable**: `docs/failure_modes_catalog.md` — a hand-curated taxonomy of how AI agents actually fail on SWE tasks.

**Concrete steps**:
1. Pull 50 failed traces from `nebius/SWE-rebench-openhands-trajectories` (67K available, CC-BY-4.0). Filter `resolved=False`.
2. For each, manually read the trajectory and write a 1-sentence "what went wrong" diagnosis.
3. Cluster the 50 diagnoses into ≤10 distinct failure modes. Note the action signature that precedes failure.
4. For each cluster, sketch ONE proposed intervention (not the message text — the *trigger* + *action* structure).
5. Compare against current 9 patterns. Note overlap, additions, removals.

**Kill criterion**: If 5+ failure modes match existing patterns *exactly*, the issue isn't pattern design — skip ahead to Phase B (different bottleneck).

**Tooling reusable from current state**: `tools/replay_traces.py` — already pulls traces and converts to Action streams. Extend to dump failed traces in human-readable form.

---

### Phase B: Single-pattern multi-channel ablation (week 2-4)

**Goal**: prove or disprove that *any* injection channel can produce measurable behavioral change.

**Deliverable**: `docs/channel_ablation.md` — table of effect sizes for the same intervention across 5 channels.

**Concrete steps**:
1. Pick **`entropy_drop`** as the test pattern (only one with real measurement headroom — 65% non-recovery).
2. Implement 5 channels in `src/soma/hooks/post_tool_use.py`:
   - **C1**: tool_response stdout (current — baseline)
   - **C2**: synthetic user message (`additionalContext` field if Claude Code accepts it; otherwise add via PreToolUse)
   - **C3**: PreToolUse rejection with reason text (block + explain — agent must respond)
   - **C4**: structured JSON error in tool response
   - **C5**: system prompt augmentation at session start (requires session-start hook)
3. For each channel, run a 50-pair A/B against control. That's 250 firings minimum across all channels — needs ~3-4 weeks of normal Claude Code usage.
4. Compute Welch's t on each channel. Report p, d, mean Δp.

**Kill criterion**: If all 5 channels show p>0.10, guidance hypothesis is **strongly disconfirmed** — pivot to observability + hard blocks. Stop Phase C.

**Required new code**: ~600 LOC. Mostly hook-layer plumbing for new channels. A/B harness already supports per-channel tagging via `arm` field — just expand to {control, channel_1, ..., channel_5}.

---

### Phase C: Format ablation (week 4-6)

**Goal**: if a channel works in Phase B, find the optimal message format.

**Deliverable**: `docs/format_ablation.md` — table of effect sizes across formats for the winning channel.

**Concrete steps**:
1. Take the best-channel from Phase B.
2. Generate 4 message format variants for `entropy_drop`:
   - **F1**: terse imperative (`Try Read.`)
   - **F2**: prose with evidence (current)
   - **F3**: structured JSON (`{"warning": "tunnel", "suggest": "Read"}`)
   - **F4**: question form (`Are you stuck? Read the file?`)
3. 50-pair A/B per variant. Compare effect sizes.

**Kill criterion**: If all 4 formats are within 0.05 in effect size, format doesn't matter — proceed to Phase D with the cheapest one.

---

### Phase D: Outcome-metric validation (week 6-8)

**Goal**: confirm that pressure-delta (current proxy metric) tracks **task completion** (real metric).

**Deliverable**: `docs/metric_validation.md` — correlation between pressure-delta at h=2 and task completion at session end.

**Concrete steps**:
1. On public traces (have `resolved` outcome), compute pressure-delta at every action and the eventual outcome.
2. Compute correlation: does pressure dropping in middle of trace predict resolved=True?
3. If r < 0.3, pressure-delta is a poor proxy. Switch all evaluation to task-completion.

**Kill criterion**: If pressure-delta and task completion are uncorrelated (r<0.3), our entire 16 days of A/B data is measuring the wrong thing. **All previous null results become uninterpretable** — start over with completion as primary metric.

---

### Phase E: Multi-model generalization (week 8-12, optional)

**Goal**: test if guidance helps weaker agents even if Claude doesn't need it.

**Deliverable**: `docs/multi_model.md` — same intervention tested on Claude, GPT-4o, Qwen3-Coder.

**Concrete steps**:
1. Use OpenHands scaffolding (matches public traces).
2. Run a small task suite (~20 SWE-bench problems) with 3 models × 2 conditions (with/without SOMA intervention).
3. Compare task completion rates.

**Kill criterion**: If even a weak model (Llama, GPT-3.5) shows no benefit from guidance, the concept doesn't generalize. Pivot to hard blocks + observability for the strong-model market.

---

## Decision tree at end of Phase B

This is the most important branch point. Three outcomes:

| Phase B outcome | Interpretation | Next move |
|---|---|---|
| Some channel shows p<0.05, d>0.2 | Guidance works in non-default channels | Phase C, optimize that channel |
| All channels p<0.10 but trending positive | Underpowered, more data needed | Run Phase B for additional 4 weeks |
| All channels show null or negative | Guidance hypothesis dead | Skip C-E, pivot to observability + hard blocks; publish negative result |

---

## Concrete first actions (when session resumes)

1. **Create branch**: `git checkout -b research/failure-mode-catalog`
2. **Write Phase A scaffold**:
   - `tools/dump_failed_traces.py` — extend `replay_traces.py` to write 50 failed traces to `failed_traces/{idx}.md` in human-readable form.
3. **Manual analysis**: open each `failed_traces/{idx}.md` and write `failed_traces/{idx}_diagnosis.md` with 1-sentence what went wrong.
4. **Synthesize**: cluster diagnoses into `docs/failure_modes_catalog.md`.
5. **Compare against current 9 patterns**: explicit table of overlap.

If user wants to skip Phase A and go straight to Phase B (less rigorous but faster):
1. Take entropy_drop as the test pattern (only one with measurement headroom).
2. Implement C1 (current) + C3 (PreToolUse block) — easiest pair to ship first.
3. Run for 2 weeks of normal usage.
4. If C3 shows effect that C1 doesn't → channel matters → expand to C2/C4/C5.

---

## Reusable infrastructure already in repo

Don't rebuild — these exist and work:

| Asset | Path | What it does |
|---|---|---|
| Replay engine | `tools/replay_traces.py` | Streams HF dataset, converts to Actions, replays through SOMAEngine |
| Phantom (5 patterns end-to-end) | `tools/phantom_full.py` | Real subprocess test, deterministic |
| A/B harness | `src/soma/ab_control.py` | Block-randomized, atomic counters, validated |
| Welch's t-test runner | `soma validate-patterns` | CLI computes p/d/status against live or supplied DB |
| Coverage gate | `.github/scripts/ab_coverage_gate.py` | CI gate; honest no-asymmetric-bias rule |
| Pressure model | `src/soma/vitals.py`, `src/soma/pressure.py` | 5-signal → scalar; not validated as proxy but operationally sound |
| Calibration framework | `src/soma/calibration.py` | Per-user threshold adaptation; v1→v2 schema migration in place |

---

## What to stop doing

- **Stop iterating on the 9 current patterns**. They're a sunk cost from the wrong methodology. Phase A may keep some, drop others, add new — but *don't refactor them in place*.
- **Stop adding "helped %" metrics anywhere user-facing**. Until Phase D validates pressure-delta as a proxy for task completion, this number is misleading.
- **Stop adding new contextual_guidance patterns**. Phase A is the only legitimate pattern source going forward.
- **Stop releasing PyPI versions** until at least Phase B finishes. Current artifact (2026.4.30) is fine as-is.

## What to keep doing

- **Hard blocks** — they work deterministically. blind_edit, bash_retry, error_cascade. Independent of the guidance question.
- **Observability** — pressure dashboard, vitals snapshots, A/B harness. These are valuable infrastructure regardless of intervention outcome.
- **Honest CHANGELOG / README**. Current README correctly says "all collecting". Don't oversell.
- **Public dataset replays** — `tools/replay_traces.py` is a reusable artifact. Use it for Phase A failure-mode analysis.

---

## Files to create when resuming

- `docs/failure_modes_catalog.md` (Phase A)
- `tools/dump_failed_traces.py` (Phase A)
- `failed_traces/` (Phase A working dir; gitignored)
- `docs/channel_ablation.md` (Phase B)
- `src/soma/hooks/channels/` (Phase B — new injection channel implementations)
- `docs/format_ablation.md` (Phase C)
- `docs/metric_validation.md` (Phase D)

---

## Honest framing for any new conversations

If someone asks "does SOMA work?" — the answer until Phase B completes is:

> "SOMA's hard blocks and observability work. The hypothesis that text-injection guidance changes agent behavior was tested in one configuration (PostToolUse, prose, tool_response channel, h=2 measurement, Claude only) on 41 production pairs and 13,510 public-trace actions. Result: no measurable effect, with one caveat — entropy_drop wasn't sufficiently tested. We're running a multi-channel ablation to determine whether the null is a real null or a methodology artifact."

That's accurate. That's defensible. Don't overpromise; don't underclaim.

---

## Resume command for next session

```
Read docs/research_plan_2026_05.md, decide Phase A or skip-to-B,
then start with the corresponding "Concrete first actions" block.
```
