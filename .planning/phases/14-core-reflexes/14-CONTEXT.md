# Phase 14: Core Reflexes - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

SOMA blocks harmful patterns and forces correct behavior — mechanical (exit code 2), not advisory (text). Transform 7 existing pattern detectors into hard reflexes. Add 3 operating modes (observe/guide/reflex). Inject agent awareness prompt so agents cooperate with SOMA instead of fighting it. Prove with benchmark.

</domain>

<decisions>
## Implementation Decisions

### Operating modes
- **D-01:** Three modes: observe (monitoring only), guide (suggestions, current behavior), reflex (hard blocks)
- **D-02:** Configured in soma.toml under `[soma] mode = "reflex"`
- **D-03:** Each mode inherits from previous — reflex includes guide includes observe
- **D-04:** Default mode for new installs: "guide" (backward compatible)

### Reflex engine
- **D-05:** New module `src/soma/reflexes.py` — checks patterns + signals, returns allow/block + message
- **D-06:** Called by PreToolUse hook when mode is "reflex"
- **D-07:** Each reflex is independently toggleable in `[reflexes]` config section
- **D-08:** Reflex decisions logged to audit log with type "reflex"

### Pattern reflexes (from existing patterns.py detectors)
- **D-09:** blind_edits: 3+ Edit/Write without Read on target → block Edit, require Read
- **D-10:** retry_dedup: exact same Bash command repeated → block, require change
- **D-11:** bash_failures: 3+ consecutive Bash errors → block identical command
- **D-12:** thrashing: 3+ edits to same file in 10 actions → lock file, force Read
- **D-13:** error_rate: >50% errors in last 10 → require plan before next action (soft block via injection, not hard block)
- **D-14:** research_stall and agent_spam: injection only, not block (too aggressive to block)

### Agent notification on block
- **D-15:** Every block includes: what was blocked, why (pattern name + detail), how to proceed, current pressure
- **D-16:** Format: `[SOMA BLOCKED] {tool} on {target}\nReason: {detail}\nFix: {suggestion}\nPressure: {p}%`
- **D-17:** Block message goes to stderr (PreToolUse), notification goes to stdout (Notification hook)

### Agent awareness prompt injection
- **D-18:** On first action of session, inject system prompt explaining SOMA via Notification hook
- **D-19:** Prompt tells agent: SOMA exists, may block, follow guidance, don't bypass
- **D-20:** Only injected once per session (track via state)

### Statusline extension
- **D-21:** Add block count and active reflex mode to statusline: `SOMA: #42 p=34% GUIDE | 2 blocked | ctx=73%`

### Benchmark proof
- **D-22:** Re-run all 5 simulated benchmark scenarios with reflex mode enabled
- **D-23:** Expect >80% error reduction on retry_storm (mechanical blocks prevent retries)
- **D-24:** Expect 0 reflex activations on healthy_session (zero false positives)
- **D-25:** Update docs/BENCHMARK.md with reflex results alongside current results

### Configuration
- **D-26:** All reflexes configurable with thresholds in soma.toml `[reflexes]` section
- **D-27:** Override allowed: configurable flag `override_allowed = true` — agent can say "SOMA override" to bypass (off by default)

### Claude's Discretion
- Exact implementation of retry dedup matching (whitespace handling, argument normalization)
- Reflex priority when multiple fire simultaneously
- Grace period behavior in reflex mode (keep or reduce)

</decisions>

<specifics>
## Specific Ideas

- User wants all 3 mode variants available simultaneously as a config choice
- Agent MUST be notified why something was blocked — "не начнётся напика"
- User wants "жёсткую промпт инъекцию во благо" — agent awareness is mandatory
- Benchmark must show dramatic improvement to prove reflexes work
- User explicitly said "1 реальное действие 😬" about current state — this phase fixes that

</specifics>

<canonical_refs>
## Canonical References

### Design spec
- `docs/superpowers/specs/2026-04-01-soma-nervous-system-design.md` — Full nervous system design with all decisions

### Existing pattern detection
- `src/soma/patterns.py` — 7 pattern detectors (blind_edits, bash_failures, error_rate, thrashing, agent_spam, research_stall, no_checkin)
- `src/soma/guidance.py` — Current evaluate() function, destructive bash patterns, GuidanceResponse type

### Hook system
- `src/soma/hooks/pre_tool_use.py` — PreToolUse hook (exit 2 = block)
- `src/soma/hooks/notification.py` — Notification hook (stdout injection)
- `src/soma/hooks/statusline.py` — Statusline formatter
- `src/soma/hooks/common.py` — Shared utilities (get_engine, read_action_log)

### Benchmark
- `src/soma/benchmark/harness.py` — A/B benchmark harness
- `src/soma/benchmark/scenarios.py` — 5 scenario definitions
- `docs/BENCHMARK.md` — Current benchmark results

### Config
- `src/soma/cli/config_loader.py` — soma.toml loader

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `patterns.analyze()` — already detects all 7 patterns, returns PatternResult with kind/severity/action/detail
- `guidance.evaluate()` — already handles mode-based decisions, returns GuidanceResponse with allow/message
- PreToolUse hook — already supports exit(2) for blocking
- Notification hook — already injects text into agent context
- Benchmark harness — already runs A/B scenarios

### Established Patterns
- Frozen dataclasses for results (PatternResult, GuidanceResponse, ActionResult)
- Hook reads engine snapshot + action log, makes decision, outputs via stdout/stderr
- Config loaded from soma.toml with defaults

### Integration Points
- reflexes.py sits between patterns.py and pre_tool_use.py
- PreToolUse calls reflexes.evaluate() instead of (or in addition to) guidance.evaluate()
- Notification hook checks reflex state for block notifications
- Benchmark harness needs reflex mode parameter

</code_context>

<deferred>
## Deferred Ideas

- Signal reflexes (predictor, drift, half-life, RCA, quality) — Phase 15
- Circuit breaker, session memory, smart throttle — Phase 16
- Web dashboard — Phase 17

</deferred>

---

*Phase: 14-core-reflexes*
*Context gathered: 2026-04-01*
