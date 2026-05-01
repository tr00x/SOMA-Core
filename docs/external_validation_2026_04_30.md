# External Validation — Public-Trace Replay (2026-04-30)

**Dataset**: `SWE-Gym/OpenHands-Sampled-Trajectories` (HuggingFace, CC-BY-4.0). 1,000 traces of GPT-4o and Claude-3.5-Sonnet running OpenHands scaffolding on real GitHub-issue resolution tasks.

**Method**: Convert each trace into a stream of `Action` events; replay through `SOMAEngine` and `ContextualGuidance.evaluate()`; aggregate firings against the dataset's per-trace `resolved` outcome label. **No injection** — observational only.

**Tooling**: [`tools/replay_traces.py`](../tools/replay_traces.py). Raw output: [`public_traces_report.json`](../public_traces_report.json).

---

## Corpus shape

| Field | Value |
|---|---:|
| Traces processed | 1,000 |
| Total actions | 13,510 |
| Total errors (heuristic) | 1,729 |
| Resolved (success) | 69 |
| Unresolved (failed) | 931 |
| Base failure rate | 0.931 |
| Tool distribution | Read 7,520 · Bash 2,780 · Edit 2,272 · Write 632 · Finish 306 |

The dataset is intentionally heavy on failed traces (it was sampled for fine-tuning failed-recovery behavior). The 0.931 base failure rate dominates per-trace precision; we use **lift** (`precision_failed / base_fail_rate`) to control for it. `lift > 1` means a firing is more likely on a failed trace than chance; `lift ≈ 1` means the detector fires proportionally to the base rate (no preference); `lift < 1` means a firing is more likely on a *succeeded* trace.

---

## Per-pattern findings

| Pattern | Fires | Lift | Natural recovery@3 | Verdict |
|---|---:|---:|---:|---|
| `entropy_drop` | 2,669 | **1.02** | **35.0%** | not preferentially predictive, **but** low natural recovery → real headroom for intervention |
| `bash_retry` | 1,271 | **0.97** | **95.4%** | not preferentially predictive, ceiling-bound recovery — **no treatment headroom** |
| `error_cascade` | 58 | **1.07** | 44.8% | rare; slightly above base; moderate headroom |
| `bash_error_streak` | 35 | 0.98 | 82.9% | rare; near-ceiling recovery |

**Did not fire on this corpus**: `cost_spiral`, `budget`, `context`, `drift`, `blind_edit`. The dataset's tool taxonomy (3 tools mapped to Read/Edit/Write/Bash/Finish) and the fact that token budgets weren't exceeded means several detectors had no input shape to match. Coverage gap, not a refutation.

---

## What this corroborates from production data

1. **`bash_retry` "92.1% helped" is regression to mean.** Live A/B (`validate-patterns`): treatment Δp=+0.486, control Δp=+0.532, p=0.43. Public traces: 95.4% natural recovery within 3 actions when the pattern fires. The two findings line up: the agent recovers from a Bash error on its own ~95% of the time. There is no measurable effect to *add* via guidance injection.

2. **No detector is preferentially predictive on independent data.** Lift across all four firing patterns is in [0.97, 1.07]. Detectors fire on failed and successful traces at the base rate. The detection layer is not differentiating outcomes on per-firing basis.

3. **`entropy_drop` is the single pattern with treatment headroom.** Natural recovery rate of 35% means 65% of tunnel-vision firings persist unresolved beyond a 3-action window. If guidance injection could break even 10% of those tunnels, that's a measurable effect. This is the one pattern where the live A/B harness — once it accumulates pairs post-resurrection — could plausibly show signal.

---

## What this means for SOMA

- The "guidance text injection changes agent behavior" hypothesis as currently formulated **is not supported by independent data**. Two complementary methods (live A/B with 41 pairs, public-trace replay with 13,510 actions) converge on the same null result for the most-tested pattern.
- The infrastructure (pressure model, A/B harness, phantom replay, observability dashboard) is **independently useful** — this report itself is evidence: replaying public corpora through the engine in a single afternoon produced honest verdicts on detector quality.
- The narrow product position is **observability + 1-3 hard safety blocks**. The "9 patterns helping agents" framing should be retired from the README until at least one pattern clears the A/B gate against control.

---

## Caveats

1. **Single dataset, single scaffold (OpenHands)**. Different scaffolds (e.g. Claude Code with native tools) may produce different distributions.
2. **Heuristic error detection** — public traces don't have a structured `is_error` field. We scan tool output for known error markers (Traceback, command-not-found, exit-code-1, etc.). Matches the live hook's strategy 2 but may under- or over-count.
3. **Tool taxonomy mapping** — `str_replace_editor` is split into Read/Write/Edit by command argument. `execute_bash` → Bash. `finish` → Finish. Detectors specific to other tool families (Grep, Glob, mcp-*) had no match surface.
4. **Recovery-window=3 is arbitrary**. Detectors might "help" at h=5 or h=10. Replicate at multiple windows in a follow-up.
5. **No causal claim**. Replay shows what *would have been observed* in the absence of injection. It cannot prove injection is ineffective; only that the natural recovery rate is high enough that any plausible intervention has limited measurable headroom.

---

## Reproducing this report

```bash
uv run --with 'datasets>=2.0' python tools/replay_traces.py \
    --limit 1000 --out public_traces_report.json
```

Roughly 8 minutes against a fresh HuggingFace cache; subsequent runs are faster.

To extend to the larger nebius corpus (67K traces, Qwen3-Coder runs):

```python
# In tools/replay_traces.py, change DATASET to:
#     "nebius/SWE-rebench-openhands-trajectories"
# (Same schema; just larger and single-model.)
```
