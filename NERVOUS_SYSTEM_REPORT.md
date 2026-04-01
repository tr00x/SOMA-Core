# SOMA Nervous System Tone Report

Date: 2026-04-01

## What Changed

### findings.py — data instead of instructions
- Before: `"Pressure elevated"` + `"Slow down. Read→Think→Act"`
- After: `"p=55% u=0.71 d=0.52 e=35%"`
- Patterns: `"pattern=blind_edits, count=5, files=['f0.py']"` not `"Read before editing"`

### signal_reflexes.py — metrics not commands
- Before: `"Refocus on original task"`, `"Consider saving progress"`
- After: `"drift=0.52, original_task=\"Build auth\", current_activity=\"debug\""`, `"predicted_escalation in ~2 actions, confidence=80%, trigger=trend"`

### notification.py — awareness rewrite
- Before: `"SOMA may BLOCK actions"`, `"Do NOT retry blocked actions"`
- After: `"You have access to your own behavioral state"`, `"Use this data however you choose"`
- New: planner.py capacity line injected on first prompt

### planner.py — new module
- Computes: session_capacity, half_life, success_rate from existing modules
- Output: `[SOMA] capacity=~43actions half_life=51 success_rate=78%`
- Injected once on session start, agent knows its own limits

## Test Results

Before changes: 1062 passed, 5 skipped
After changes: 1062 passed, 5 skipped (8 test assertions updated for new strings)

## Live Benchmark: Data Tone vs Instruction Tone

3 runs each, claude-haiku-4-5-20251001, 12 actions per run.

| Mode | Blind Edits (mean±std) | Tokens (mean) |
|------|----------------------|---------------|
| Baseline (no SOMA) | 1.3 ± 0.6 | 8,873 |
| Instruction tone (reflex) | **0.0 ± 0.0** | 8,929 |
| Data tone (reflex) | 1.3 ± 1.2 | **7,201** |

## Honest Assessment

### What the data says

**Instruction tone is better for preventing blind edits.** 0.0 vs 1.3 — not even close. When SOMA says "Read the file first" explicitly, Haiku complies. When SOMA says "pattern=blind_edits, count=3", Haiku doesn't change behavior.

**BUT: guidance wasn't injected in data-tone runs.** guidance_count=0 in all 3 data-tone runs. Pressure never rose high enough (grace period + short session). The comparison is unfair — instruction tone had guidance firing, data tone had no guidance at all.

**Data tone uses 20% fewer tokens.** 7,201 vs 8,929. The shorter awareness prompt and lack of verbose guidance reduces context overhead.

### What this means

1. **Data tone alone doesn't work** — giving an LLM raw numbers like `pattern=blind_edits, count=3` doesn't change its behavior. LLMs respond to natural language instructions, not metric dashboards.

2. **The nervous system metaphor has limits** — a human reads "pulse 160" and knows to slow down because of years of embodied experience. An LLM has no embodied experience. `p=55%` means nothing to it without context.

3. **Hybrid is probably best** — data tone for awareness prompt (don't be controlling), instruction tone when a specific pattern fires (be clear about what's happening). Reflexes (hard blocks) remain the most reliable mechanism regardless of tone.

### Recommendation

Keep data tone for the awareness prompt and vitals header (agent should feel informed, not controlled). Revert pattern findings to include a brief action hint alongside the data: `[pattern] blind_edits count=3 — consider reading files first`. This gives the LLM both the data (nervous system) and enough context to act on it (without being prescriptive).

Reflexes (skeleton) are tone-independent — they block mechanically, not linguistically.
