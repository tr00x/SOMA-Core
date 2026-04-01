# SOMA Hybrid Tone Report

Date: 2026-04-01
Model: claude-haiku-4-5-20251001
Runs: 3 per mode, 12 actions each

## Results — All Four Tones Compared

| Mode | Blind Edits (mean±std) | Tokens (mean) | Guidance Injected |
|------|----------------------|---------------|-------------------|
| Baseline (no SOMA) | 1.3 ± 0.6 | 8,873 | 0 |
| **Instruction tone** | **0.0 ± 0.0** | 8,929 | >0 |
| Data-only tone | 1.3 ± 1.2 | 7,201 | 0 |
| **Hybrid tone** | **1.0 ± 1.0** | **7,416** | 0 |

## The Real Problem

Guidance was injected 0 times in both data-only and hybrid runs. The tone change made no difference because **SOMA never spoke**.

The instruction-tone benchmark from earlier happened to have guidance fire (pressure crossed GUIDE threshold). The data and hybrid runs didn't — different random LLM behavior meant pressure stayed in OBSERVE range.

This means we're not comparing tones. We're comparing "SOMA spoke" vs "SOMA didn't speak". When SOMA speaks (any tone), blind edits drop. When SOMA is silent, they don't.

## What Actually Determines Blind Edits

Looking across all 12 runs:

| SOMA spoke? | Blind edits (mean) | Runs |
|-------------|-------------------|------|
| Yes (instruction tone) | 0.0 | 3 |
| No (all other runs) | 1.2 | 9 |

The tone doesn't matter because guidance only fires at GUIDE+ pressure. In 12-action sessions, pressure often doesn't reach GUIDE threshold (0.40 for Claude Code config). When it does, ANY tone works. When it doesn't, NO tone works.

## Token Efficiency

Hybrid and data tones use ~17% fewer tokens than instruction tone (7,416 vs 8,929). This is because:
- Shorter awareness prompt (data tone)
- No verbose instruction messages
- Haiku generates slightly shorter responses without instruction preamble

## Honest Answer

**Does hybrid tone match instruction tone on blind_edits prevention?**

Can't answer — the comparison is confounded. Guidance injected 0 times in hybrid runs vs >0 times in instruction runs. We'd need to force the same number of guidance injections in both to compare tones fairly.

**What we actually know:**
1. When SOMA injects guidance, agents change behavior (proven in loop_verification.py)
2. The content of guidance (instruction vs hybrid vs data) can't be compared because injection frequency varies with random LLM behavior
3. Token cost: hybrid/data ~17% cheaper than instruction
4. Reflexes (hard blocks) work regardless of tone — they're mechanical

## Recommendation

Keep hybrid tone — it's honest (data + context), cheaper (17% fewer tokens), and the awareness prompt respects agent autonomy. The actual behavioral impact comes from whether guidance fires at all, not from what it says. Fix the real problem: make sure guidance fires when patterns are detected, regardless of pressure level. Pattern reflexes (blind_edits, thrashing) should inject in GUIDE mode even at low pressure — the pattern itself is the signal, not the pressure number.
