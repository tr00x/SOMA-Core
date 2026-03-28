# SOMA Core — What's Actually Broken

Honest audit. No bullshit. What exists but doesn't work.

## CRITICAL — Must fix before telling anyone "it works"

### 1. soma.wrap() never tested with real SDK
**Problem:** All wrap tests use mocks. Real Anthropic/OpenAI response objects have different structure. Response parsing will probably fail.
**Fix:** Write integration test with real `anthropic.Anthropic()` call. Fix `_extract_response_data()` for real response objects. Need API key.
**Effort:** 1 hour

### 2. Claude Code hooks never installed/tested
**Problem:** `src/soma/hooks/claude_code.py` written but never actually run in a Claude Code session. The stdin JSON format is guessed. `CLAUDE_HOOK` env var might not be set by Claude Code.
**Fix:** Run `soma setup-claude`, restart Claude Code, do a few tool calls, check `~/.soma/state.json`. Fix whatever breaks.
**Effort:** 30 min

### 3. ~~soma.toml weights/thresholds ignored by engine~~ ✓ FIXED
`SOMAEngine.__init__()` now accepts `custom_weights` and `custom_thresholds`. `from_config()` reads them from `soma.toml` and passes them in. `record_action()` uses `custom_weights` as the base weight dict; `evaluate_with_adjustments()` accepts `custom_thresholds`.

### 4. ~~No auto-export in engine~~ ✓ FIXED
`SOMAEngine.__init__()` now accepts `auto_export: bool = False`. When `True`, `record_action()` calls `export_state()` after every action. `from_config()` sets `auto_export=True` automatically.

## MEDIUM — Works partially, needs finishing

### 5. Autonomy mode: no approval UI
**Problem:** Engine emits `approval_needed` event but nothing listens. No CLI command, no dashboard button, no way for human to approve.
**Fix:** Add `soma approve <agent-id>` CLI command. Add approval button in dashboard Agents tab. Wire event to notification.
**Effort:** 2 hours

### 6. context_action ignored by soma.wrap()
**Problem:** ActionResult has `context_action` field ("truncate_20", "quarantine" etc.) but `soma.wrap()` doesn't use it. It only checks level for blocking, not for context modification.
**Fix:** In WrappedClient, after recording action, check context_action. For "truncate_20"/"truncate_50_block_tools" — trim message history in kwargs before next call. For "quarantine" — already blocked by SomaBlocked.
**Effort:** 2 hours

### 7-9. TUI tabs untested
**Problem:** Replay, Config, Agents tabs in hub.py were written by agents but never visually tested. Probably crash on real data.
**Fix:** Open `soma`, click through all tabs, fix what breaks.
**Effort:** 1-2 hours

### 10. projected_overshoot hardcoded
**Problem:** Engine passes `estimated_total_steps=100` always. Should be configurable or calculated from history.
**Fix:** Add to soma.toml `[budget] max_steps = 100`. Read in engine.
**Effort:** 15 min

### ~~11. store.py is dead~~ ✓ FIXED
`store.py` deleted. `persistence.py` handles all state persistence.

## LOW — Cleanup, can wait

### 12-16. Dead code and orphans
- ~~Delete or document stateless.py~~ ✓ FIXED — `wrappers/` deleted entirely
- ~~Remove old dashboard/app.py (hub.py replaced it)~~ ✓ FIXED — `dashboard/` deleted entirely
- Fix learning from_dict
- ~~Update examples to use real data~~ ✓ FIXED — no fake/demo data anywhere
- ~~Auto-export in the old Claude Code wrapper~~ ✓ FIXED — hooks/claude_code.py handles this directly

**Remaining effort:** 15 min (learning from_dict)

---

## Priority Order

1. ~~Fix #4 (auto-export)~~ ✓ Done
2. ~~Fix #3 (config weights)~~ ✓ Done
3. Fix #2 (test hooks) — 30 min. Needs manual testing.
4. Fix #1 (real SDK test) — 1 hour. Needs API key.
5. Fix #5-6 (autonomy + context in wrap) — 2-3 hours.
6. Fix #7-9 (TUI tabs) — 1-2 hours.
7. Fix #10 (projected_overshoot) + Fix learning from_dict — 30 min.

**Remaining: ~4-5 hours of real work.**
