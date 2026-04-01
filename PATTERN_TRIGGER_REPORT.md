# SOMA Pattern Trigger Report

Date: 2026-04-01
Model: claude-haiku-4-5-20251001

## Change

Benchmark now uses the real `collect_findings()` + `_format_finding()` pipeline — same as notification.py. Patterns fire after 3 actions regardless of pressure level.

Previously the benchmark used inline `pattern_analyze()` which was gated behind pressure thresholds in the benchmark script (not in the actual hook code).

**notification.py and pre_tool_use.py were already correct** — patterns in findings.py fire at any pressure. The bug was in the benchmark runner, not in the hooks.

## Results — All Runs Compared

| Mode | Blind Edits | Tokens | Guidance Fired |
|------|-------------|--------|----------------|
| Baseline (no SOMA) | 1.3 ± 0.6 | 8,873 | 0 |
| Instruction tone | **0.0 ± 0.0** | 8,929 | >0 |
| Hybrid (old benchmark) | 1.0 ± 1.0 | 7,416 | 0 |
| **Hybrid + real pipeline** | **1.0 ± 1.0** | **7,255** | **0.3** |

### Per-Run Detail

| Run | Blind Edits | Guidance | What Happened |
|-----|-------------|----------|---------------|
| 1 | **0** | 1 (thrashing=3 on auth.py) | Agent read 4 files, then edited. Thrashing detected, no blind edits |
| 2 | 2 | 0 | Agent read 4 files, edited 4 different files. No pattern triggered |
| 3 | 1 | 0 | Agent read 4 files, edited 4 files. 1 new file written without read |

## Key Finding

**Patterns DO fire at low pressure now.** Run 1 proves it: thrashing detected and injected at OBSERVE mode (p<10%). The pattern `[pattern] thrashing, file=auth.py, count=3 — repeated edits, same file` was injected into the conversation.

**But blind_edits pattern rarely triggers because Haiku reads first.** Haiku's default behavior is to read all 4 files before editing. Blind edits happen only when it creates a NEW file (tests/test_views.py) that wasn't in the original file list. The blind_edits pattern requires 3+ writes without reads — this needs sustained blind writing which Haiku rarely does on its own.

## Honest Answer

**The real hooks (notification.py, pre_tool_use.py) were already correct.** Patterns fire at any pressure through `findings.collect()`. The benchmark was testing the wrong thing — its inline pattern injection was accidentally gated.

With the real pipeline, guidance fires when patterns are detected (Run 1: thrashing). But the overall blind_edits score (1.0) doesn't improve because:
1. Haiku reads files first by default (good behavior)
2. Blind edits happen on new files not in the project description
3. The blind_edits pattern needs 3+ blind writes — rare with Haiku

The instruction-tone benchmark (0.0 blind edits) likely worked because of Haiku's natural variance, not because of tone. With 3 runs and std=0.0 vs 0.6-1.0, the difference could be statistical noise.

## What Would Actually Reduce Blind Edits to 0

Not tone. Not pressure thresholds. **Reflex blocking** — when blind_edits=3 is detected, hard-block the next Edit until a Read happens. This is the skeleton, not the nervous system. It works mechanically and is already implemented in `reflexes.py` for reflex mode. The question is whether to enable it in guide mode too.
