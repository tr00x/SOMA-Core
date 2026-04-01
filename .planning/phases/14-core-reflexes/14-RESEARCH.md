# Phase 14: Core Reflexes - Research

**Researched:** 2026-04-01
**Domain:** Behavioral pattern enforcement (mechanical blocking via hook exit codes)
**Confidence:** HIGH

## Summary

Phase 14 transforms SOMA from an advisory system into one that mechanically blocks harmful agent behavior. The existing codebase has all the building blocks: `patterns.py` detects 7 behavioral patterns, `guidance.py` evaluates pressure-to-mode, `pre_tool_use.py` already supports `exit(2)` blocking, and `notification.py` injects text into agent context. The work is integration and orchestration, not greenfield.

The core architectural challenge is adding a new `reflexes.py` module that sits between pattern detection and hook execution, evaluating whether a detected pattern warrants a hard block (exit 2) vs. a soft injection (stdout text). This module must read the operating mode from config, check per-reflex toggles, and return a structured decision. The existing `evaluate()` in guidance.py handles pressure-based blocking of destructive commands; reflexes.py handles pattern-based blocking of harmful behavioral sequences.

**Primary recommendation:** Build `reflexes.py` as a pure function module (no state, no imports from hooks) that takes action_log + tool_name + tool_input + config and returns a `ReflexResult` frozen dataclass. Hook code calls it; it never calls hooks.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Three modes: observe (monitoring only), guide (suggestions, current behavior), reflex (hard blocks)
- **D-02:** Configured in soma.toml under `[soma] mode = "reflex"`
- **D-03:** Each mode inherits from previous -- reflex includes guide includes observe
- **D-04:** Default mode for new installs: "guide" (backward compatible)
- **D-05:** New module `src/soma/reflexes.py` -- checks patterns + signals, returns allow/block + message
- **D-06:** Called by PreToolUse hook when mode is "reflex"
- **D-07:** Each reflex is independently toggleable in `[reflexes]` config section
- **D-08:** Reflex decisions logged to audit log with type "reflex"
- **D-09:** blind_edits: 3+ Edit/Write without Read on target -> block Edit, require Read
- **D-10:** retry_dedup: exact same Bash command repeated -> block, require change
- **D-11:** bash_failures: 3+ consecutive Bash errors -> block identical command
- **D-12:** thrashing: 3+ edits to same file in 10 actions -> lock file, force Read
- **D-13:** error_rate: >50% errors in last 10 -> require plan before next action (soft block via injection, not hard block)
- **D-14:** research_stall and agent_spam: injection only, not block (too aggressive to block)
- **D-15:** Every block includes: what was blocked, why (pattern name + detail), how to proceed, current pressure
- **D-16:** Format: `[SOMA BLOCKED] {tool} on {target}\nReason: {detail}\nFix: {suggestion}\nPressure: {p}%`
- **D-17:** Block message goes to stderr (PreToolUse), notification goes to stdout (Notification hook)
- **D-18:** On first action of session, inject system prompt explaining SOMA via Notification hook
- **D-19:** Prompt tells agent: SOMA exists, may block, follow guidance, don't bypass
- **D-20:** Only injected once per session (track via state)
- **D-21:** Add block count and active reflex mode to statusline: `SOMA: #42 p=34% GUIDE | 2 blocked | ctx=73%`
- **D-22:** Re-run all 5 simulated benchmark scenarios with reflex mode enabled
- **D-23:** Expect >80% error reduction on retry_storm (mechanical blocks prevent retries)
- **D-24:** Expect 0 reflex activations on healthy_session (zero false positives)
- **D-25:** Update docs/BENCHMARK.md with reflex results alongside current results
- **D-26:** All reflexes configurable with thresholds in soma.toml `[reflexes]` section
- **D-27:** Override allowed: configurable flag `override_allowed = true` -- agent can say "SOMA override" to bypass (off by default)

### Claude's Discretion
- Exact implementation of retry dedup matching (whitespace handling, argument normalization)
- Reflex priority when multiple fire simultaneously
- Grace period behavior in reflex mode (keep or reduce)

### Deferred Ideas (OUT OF SCOPE)
- Signal reflexes (predictor, drift, half-life, RCA, quality) -- Phase 15
- Circuit breaker, session memory, smart throttle -- Phase 16
- Web dashboard -- Phase 17
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RFX-01 | Three operating modes (observe/guide/reflex) with config and mode inheritance | Config loader already supports presets; add `mode` key to `[soma]` section; mode read in hooks to gate reflex logic |
| RFX-02 | Pattern-based reflexes that mechanically block harmful actions | `patterns.analyze()` already detects all 7 patterns; new `reflexes.py` maps pattern kinds to block/inject decisions based on mode and per-reflex toggles |
| RFX-03 | Agent awareness prompt injection on session start | Notification hook already injects stdout text; add first-action detection via action_log length check or session state file |
| RFX-04 | Benchmark proof showing >80% error reduction on retry_storm and 0 false positives on healthy_session | Benchmark harness already runs 5 scenarios; add reflex mode parameter to `run_scenario()` and `run_benchmark()` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.11+ | All reflex logic, dataclasses, enum | Zero dependencies for core module |
| soma.patterns | existing | Pattern detection (7 detectors) | Already returns PatternResult with kind/severity/action/detail |
| soma.guidance | existing | Pressure-to-mode, destructive checks | Reflex mode adds pattern-based blocking alongside existing pressure-based blocking |
| soma.audit | existing | Audit logging (JSON Lines) | D-08 requires reflex decisions logged with type "reflex" |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tomli-w | >=1.0 | Config writing | When saving updated soma.toml with `[reflexes]` section |
| tomllib | stdlib | Config reading | Reading `[soma] mode` and `[reflexes]` section |

### Alternatives Considered
None -- this phase uses only existing stack. No new dependencies.

## Architecture Patterns

### Recommended Project Structure
```
src/soma/
  reflexes.py          # NEW: core reflex logic (pure functions)
  patterns.py          # EXISTING: no changes needed
  guidance.py          # EXISTING: no changes needed
  audit.py             # EXISTING: used for reflex audit logging
  hooks/
    pre_tool_use.py    # MODIFIED: call reflexes.evaluate() when mode=reflex
    notification.py    # MODIFIED: agent awareness prompt + block notifications
    statusline.py      # MODIFIED: block count + mode display
    common.py          # MODIFIED: add get_reflex_config(), get_soma_mode()
  cli/
    config_loader.py   # MODIFIED: add mode to DEFAULT_CONFIG, CLAUDE_CODE_CONFIG
  benchmark/
    harness.py         # MODIFIED: add reflex_mode parameter
    scenarios.py       # EXISTING: no changes (scenarios are mode-agnostic)
```

### Pattern 1: ReflexResult Frozen Dataclass
**What:** Every reflex evaluation returns a `ReflexResult` with `allow: bool`, `block_message: str | None`, `inject_message: str | None`, `reflex_kind: str`, `detail: str`
**When to use:** Always -- consistent return type for all reflex decisions
**Example:**
```python
@dataclass(frozen=True, slots=True)
class ReflexResult:
    """Result of a reflex evaluation."""
    allow: bool
    reflex_kind: str          # "blind_edits", "retry_dedup", etc. or "" if no reflex fired
    block_message: str | None = None   # stderr message on block
    inject_message: str | None = None  # stdout injection (soft guidance)
    detail: str = ""          # for audit logging
```

### Pattern 2: Reflex Registry (Dict Dispatch)
**What:** Map pattern kinds to reflex handler functions. Each handler receives the PatternResult + tool context and returns whether to block.
**When to use:** For extensibility and per-reflex toggling
**Example:**
```python
# Each reflex is a function: (PatternResult, tool_name, tool_input, action_log) -> ReflexResult | None
REFLEX_HANDLERS: dict[str, Callable] = {
    "blind_edits": _reflex_blind_edits,
    "bash_failures": _reflex_bash_failures,
    "thrashing": _reflex_thrashing,
    "retry_dedup": _reflex_retry_dedup,     # NEW pattern not in patterns.py
    "error_rate": _reflex_error_rate,       # soft block (injection only)
    "research_stall": _reflex_inject_only,  # injection only
    "agent_spam": _reflex_inject_only,      # injection only
}
```

### Pattern 3: Mode Gating in Hooks
**What:** PreToolUse reads `[soma] mode` from config. In "observe" mode, no reflexes or guidance. In "guide" mode, existing behavior (suggestions). In "reflex" mode, call `reflexes.evaluate()` before `guidance.evaluate()`.
**When to use:** Every PreToolUse hook invocation
**Example:**
```python
# In pre_tool_use.py:
soma_mode = get_soma_mode()  # "observe", "guide", "reflex"

if soma_mode == "observe":
    return  # no guidance, no reflexes

if soma_mode == "reflex":
    from soma.reflexes import evaluate as reflex_evaluate
    reflex_result = reflex_evaluate(
        tool_name=tool_name,
        tool_input=tool_input,
        action_log=action_log,
        config=reflex_config,
    )
    if not reflex_result.allow:
        # Log to audit
        audit_reflex(reflex_result)
        print(reflex_result.block_message, file=sys.stderr)
        sys.exit(2)

# Existing guidance logic (for both "guide" and "reflex" modes)
response = evaluate(pressure=pressure, ...)
```

### Pattern 4: Retry Dedup Detection
**What:** New pattern not currently in `patterns.py`. Detect when the exact same Bash command is repeated.
**When to use:** In reflexes.py, NOT in patterns.py (this is a reflex-specific check that needs tool_input context)
**Example:**
```python
def _detect_retry_dedup(tool_name: str, tool_input: dict, action_log: list[dict]) -> bool:
    """Detect if current Bash command is identical to the previous one."""
    if tool_name != "Bash":
        return False
    current_cmd = tool_input.get("command", "").strip()
    if not current_cmd:
        return False
    # Look at last Bash command in action_log
    for entry in reversed(action_log):
        if entry["tool"] == "Bash":
            # Action log doesn't store commands -- need to extend or check differently
            # IMPORTANT: action_log only stores tool/error/file/ts, not command text
            break
    return False  # placeholder
```

**CRITICAL FINDING:** The action_log (common.py `append_action_log`) only stores `tool`, `error`, `file`, `ts`. It does NOT store the command text. For retry_dedup (D-10), we need the Bash command from `tool_input`. Two options:
1. **Extend action_log** to optionally store command hash or command text for Bash actions
2. **Check in PreToolUse** which has access to current `tool_input` and compare against a separate "last_bash_command" state file

**Recommendation:** Option 2 -- store last N Bash commands in a small state file (`~/.soma/sessions/{agent_id}/bash_history.json`). This avoids bloating the action_log format. The reflex checks current `tool_input.command` against this history.

### Pattern 5: Agent Awareness Prompt
**What:** On first action of session, inject a system-level prompt into agent context via Notification hook stdout
**When to use:** D-18/D-19/D-20 -- once per session
**Example:**
```python
AGENT_AWARENESS_PROMPT = """[SOMA Active] This session is monitored by SOMA, a behavioral safety system.
- SOMA may BLOCK actions that match harmful patterns (blind edits, retry loops, file thrashing)
- When blocked, read the reason and follow the suggested fix
- Do NOT retry blocked actions without changing approach
- SOMA guidance appears in [SOMA] prefixed messages
- Current mode: {mode}"""
```

**Session tracking:** Check if awareness prompt was already injected by looking for a flag file `~/.soma/sessions/{agent_id}/awareness_sent`. Alternatively, check `action_log` length -- if length is 0 or 1, it's the first action.

**Recommendation:** Use action_log length check (simpler, no extra file). If `len(action_log) == 0`, inject awareness prompt. The Notification hook runs on `UserPromptSubmit`, which fires before the first tool call, making this natural.

### Anti-Patterns to Avoid
- **Reflex logic in hooks:** Keep `reflexes.py` as a pure core module. Hooks only call it and handle I/O.
- **Modifying patterns.py:** Don't add reflex logic to the pattern detector. Patterns detect, reflexes decide.
- **Global mutable state for block count:** Use the audit log to count blocks, or a simple counter in session state. Don't use module-level globals.
- **Blocking on soft patterns:** D-13/D-14 explicitly say error_rate, research_stall, agent_spam are injection-only. Never block on these.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pattern detection | Custom pattern checks in reflexes.py | `patterns.analyze()` | Already has 7 battle-tested detectors with proper windowing |
| Audit logging | Custom file writing | `soma.audit.AuditLogger.append()` | Handles rotation, JSON Lines format, error handling |
| Config loading | Custom TOML parsing | `config_loader.load_config()` | Already handles migration, defaults, profiles |
| Pressure-based blocking | Duplicate pressure logic | `guidance.evaluate()` | Already handles destructive command detection at BLOCK mode |

## Common Pitfalls

### Pitfall 1: Action Log Lacks Command Text
**What goes wrong:** Trying to implement retry_dedup by comparing commands in action_log, but action_log only stores `{tool, error, file, ts}`.
**Why it happens:** The action_log was designed for pattern analysis (tool sequences), not command dedup.
**How to avoid:** Store Bash command hashes in a separate session-scoped state file. PreToolUse has access to `tool_input` which contains the current command.
**Warning signs:** Tests pass with mock data but fail in real hooks because action_log entries don't have command field.

### Pitfall 2: Blind Edit Reflex Needs Current Tool Context
**What goes wrong:** `patterns.analyze()` looks at the action_log history to detect blind edits. But for PreToolUse blocking, we need to know if the CURRENT action (not yet in the log) is a blind edit.
**Why it happens:** PreToolUse fires BEFORE the action is recorded.
**How to avoid:** The reflex must check: (1) does `patterns.analyze(action_log)` show blind_edits pattern active? AND (2) is the current tool_name Edit/Write? If both true, block.
**Warning signs:** Reflex blocks on the 4th edit (after pattern fires) instead of preventing the 3rd.

### Pitfall 3: Mode Inheritance Confusion
**What goes wrong:** In "reflex" mode, forgetting to also run guide-level suggestions.
**Why it happens:** D-03 says "each mode inherits from previous."
**How to avoid:** Reflex mode = reflex checks + guide suggestions + observe metrics. The PreToolUse flow should be: reflex check first (can block), then guidance check (can suggest/block destructive).
**Warning signs:** In reflex mode, agent stops getting suggestions.

### Pitfall 4: Benchmark Harness Doesn't Support Blocking
**What goes wrong:** The benchmark harness feeds actions through `engine.record_action()` which doesn't block. It uses `guidance_responsive` flag to simulate skipping.
**Why it happens:** The harness is engine-level, not hook-level. There's no PreToolUse exit(2) in the harness.
**How to avoid:** For reflex benchmarking, add a reflex check in `_collect_metrics()`. If reflex says block, skip the action (similar to `guidance_responsive` behavior). Add a `reflex_blocked: bool` field to ActionMetric.
**Warning signs:** Benchmark results show no difference between guide and reflex modes.

### Pitfall 5: Notification Hook Timing for Awareness Prompt
**What goes wrong:** The awareness prompt fires on every `UserPromptSubmit`, flooding the agent context.
**Why it happens:** Notification hook has no memory of whether awareness was already sent.
**How to avoid:** Check `len(action_log) == 0` (no actions yet = first prompt of session). The action log persists within a session but is bounded at 20 entries, so checking for 0 is the reliable "first time" signal.
**Warning signs:** Agent sees "[SOMA Active]" message on every prompt.

### Pitfall 6: Override Mechanism Security
**What goes wrong:** Agent says "SOMA override" in a tool argument and bypasses all reflexes.
**Why it happens:** D-27 allows override but it's off by default. If implemented poorly, any text match in tool_input could trigger override.
**How to avoid:** Override should only work if (1) `override_allowed = true` in config AND (2) the override text appears in a specific location (e.g., the tool_input.command starts with "# SOMA override"). Keep it off by default per D-27.
**Warning signs:** Agent discovers it can bypass SOMA by including override text in any command.

## Code Examples

### reflexes.py Core Structure
```python
"""SOMA Reflexes -- mechanical behavioral enforcement.

Core module: layer-agnostic. Returns ReflexResult objects.
Called by hooks when mode is 'reflex'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from soma.patterns import analyze as analyze_patterns, PatternResult


@dataclass(frozen=True, slots=True)
class ReflexResult:
    """Result of a reflex evaluation."""
    allow: bool
    reflex_kind: str = ""
    block_message: str | None = None
    inject_message: str | None = None
    detail: str = ""


# Pattern kinds that trigger hard blocks
BLOCKING_REFLEXES = {"blind_edits", "bash_failures", "thrashing", "retry_dedup"}

# Pattern kinds that trigger soft injection only
INJECTION_REFLEXES = {"error_rate", "research_stall", "agent_spam"}


def evaluate(
    tool_name: str,
    tool_input: dict,
    action_log: list[dict],
    pressure: float = 0.0,
    config: dict | None = None,
    bash_history: list[str] | None = None,
    workflow_mode: str = "",
) -> ReflexResult:
    """Evaluate whether current action should be blocked by a reflex.

    Args:
        tool_name: Current tool being called
        tool_input: Tool arguments (e.g., command for Bash)
        action_log: Recent action history
        pressure: Current aggregate pressure
        config: [reflexes] config section from soma.toml
        bash_history: Recent Bash commands for dedup detection
        workflow_mode: GSD workflow mode

    Returns:
        ReflexResult with allow=False if action should be blocked.
    """
    cfg = config or {}

    # Check retry dedup first (needs tool_input, not in patterns.py)
    if cfg.get("retry_dedup", True) and tool_name == "Bash":
        cmd = tool_input.get("command", "").strip()
        if cmd and bash_history:
            # Normalize: strip whitespace, collapse spaces
            normalized = " ".join(cmd.split())
            if normalized in bash_history:
                return ReflexResult(
                    allow=False,
                    reflex_kind="retry_dedup",
                    block_message=_format_block("Bash", cmd[:60], "retry_dedup",
                                                "exact same command repeated", "Change the command", pressure),
                    detail=f"duplicate command: {cmd[:80]}",
                )

    # Run pattern analysis on action log
    patterns = analyze_patterns(action_log, workflow_mode)

    for pattern in patterns:
        if pattern.kind in BLOCKING_REFLEXES and cfg.get(pattern.kind, True):
            # Check if current tool matches the pattern's target
            if _should_block(pattern, tool_name, tool_input):
                return ReflexResult(
                    allow=False,
                    reflex_kind=pattern.kind,
                    block_message=_format_block(
                        tool_name, _target_name(tool_input), pattern.kind,
                        pattern.detail, pattern.action, pressure,
                    ),
                    detail=pattern.detail,
                )

        if pattern.kind in INJECTION_REFLEXES and cfg.get(pattern.kind, True):
            return ReflexResult(
                allow=True,
                reflex_kind=pattern.kind,
                inject_message=f"[SOMA] {pattern.action}",
                detail=pattern.detail,
            )

    return ReflexResult(allow=True)
```

### soma.toml Config Extension
```toml
[soma]
mode = "guide"  # "observe", "guide", "reflex"

[reflexes]
blind_edits = true
retry_dedup = true
bash_failures = true
thrashing = true
error_rate = true       # injection only, never blocks
research_stall = true   # injection only, never blocks
agent_spam = true       # injection only, never blocks
override_allowed = false

[reflexes.thresholds]
blind_edits_count = 3
bash_failures_count = 3
thrashing_count = 3
thrashing_window = 10
error_rate_threshold = 0.50
```

### PreToolUse Integration
```python
# In pre_tool_use.py main():
soma_mode = get_soma_mode()  # reads [soma] mode from config

if soma_mode == "observe":
    return

if soma_mode == "reflex":
    from soma.reflexes import evaluate as reflex_evaluate
    reflex_config = get_reflex_config()
    bash_history = read_bash_history(agent_id)

    reflex_result = reflex_evaluate(
        tool_name=tool_name,
        tool_input=tool_input,
        action_log=action_log,
        pressure=pressure,
        config=reflex_config,
        bash_history=bash_history,
    )

    if not reflex_result.allow:
        _audit_reflex(reflex_result)
        _increment_block_count(agent_id)
        print(reflex_result.block_message, file=sys.stderr)
        sys.exit(2)

# Existing guidance logic runs for both "guide" and "reflex" modes
response = evaluate(pressure=pressure, ...)
```

### Statusline Extension
```python
# Add to statusline.py main():
# After existing parts:
block_count = _get_block_count(agent_id)
if block_count > 0:
    parts.append(f"{block_count} blocked")

soma_mode = _get_soma_mode()
if soma_mode and soma_mode != "guide":  # only show non-default
    parts[-1] = parts[-1]  # mode shown in existing label
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Advisory only (guide.py evaluate) | Pattern-based mechanical blocking (reflexes.py) | Phase 14 | Agents physically cannot repeat harmful patterns |
| Single response mode (pressure-based) | Three operating modes (observe/guide/reflex) | Phase 14 | Users choose enforcement level |
| No agent awareness | System prompt injection | Phase 14 | Agent cooperates with SOMA instead of fighting it |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | pyproject.toml (pytest section) |
| Quick run command | `uv run python -m pytest tests/test_reflexes.py -x -q` |
| Full suite command | `uv run python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RFX-01 | Mode config loading and inheritance | unit | `uv run python -m pytest tests/test_reflexes.py::TestModeConfig -x` | Wave 0 |
| RFX-01 | Mode gating in PreToolUse | unit | `uv run python -m pytest tests/test_reflexes.py::TestModeGating -x` | Wave 0 |
| RFX-02 | blind_edits reflex blocks Edit without Read | unit | `uv run python -m pytest tests/test_reflexes.py::TestBlindEditsReflex -x` | Wave 0 |
| RFX-02 | retry_dedup blocks repeated Bash | unit | `uv run python -m pytest tests/test_reflexes.py::TestRetryDedup -x` | Wave 0 |
| RFX-02 | bash_failures blocks after 3 consecutive | unit | `uv run python -m pytest tests/test_reflexes.py::TestBashFailuresReflex -x` | Wave 0 |
| RFX-02 | thrashing blocks after 3 edits to same file | unit | `uv run python -m pytest tests/test_reflexes.py::TestThrashingReflex -x` | Wave 0 |
| RFX-02 | error_rate injects but does not block | unit | `uv run python -m pytest tests/test_reflexes.py::TestErrorRateReflex -x` | Wave 0 |
| RFX-02 | per-reflex toggle config | unit | `uv run python -m pytest tests/test_reflexes.py::TestReflexConfig -x` | Wave 0 |
| RFX-02 | block message format matches D-16 | unit | `uv run python -m pytest tests/test_reflexes.py::TestBlockFormat -x` | Wave 0 |
| RFX-03 | awareness prompt injected on first action | unit | `uv run python -m pytest tests/test_reflexes.py::TestAwarenessPrompt -x` | Wave 0 |
| RFX-03 | awareness prompt NOT injected after first action | unit | `uv run python -m pytest tests/test_reflexes.py::TestAwarenessPrompt -x` | Wave 0 |
| RFX-04 | benchmark retry_storm >80% error reduction with reflex | unit | `uv run python -m pytest tests/test_benchmark.py::TestReflexBenchmark -x` | Wave 0 |
| RFX-04 | benchmark healthy_session 0 reflex activations | unit | `uv run python -m pytest tests/test_benchmark.py::TestReflexBenchmark -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_reflexes.py -x -q`
- **Per wave merge:** `uv run python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_reflexes.py` -- covers RFX-01, RFX-02, RFX-03
- [ ] Extend `tests/test_benchmark.py` with `TestReflexBenchmark` class -- covers RFX-04

## Open Questions

1. **Retry dedup: how to access command text?**
   - What we know: Action log stores `{tool, error, file, ts}` only. PreToolUse has `tool_input` with command.
   - What's unclear: Best storage mechanism for bash command history.
   - Recommendation: Store last 5 normalized Bash commands in `~/.soma/sessions/{agent_id}/bash_history.json`. PreToolUse writes after each Bash, reflexes read before next Bash. Simple JSON list, append + truncate.

2. **Block count persistence for statusline**
   - What we know: Statusline reads engine snapshot. Block count is not in engine state.
   - What's unclear: Where to store cumulative block count.
   - Recommendation: Add `block_count` to session state (same pattern as action_log -- a simple integer in a file or in the session state dict). OR count "reflex" entries in audit log (but slower).

3. **Grace period in reflex mode**
   - What we know: Currently, first 3 actions are grace period (notification.py line 55). Patterns use recent 10 actions.
   - What's unclear: Should reflex mode reduce or eliminate grace period?
   - Recommendation: Keep the existing 3-action grace period for notifications. Reflexes should still fire based on pattern detection thresholds (which already require 3+ actions of the relevant type), providing natural warm-up.

## Sources

### Primary (HIGH confidence)
- `src/soma/patterns.py` -- full source reviewed, all 7 pattern detectors understood
- `src/soma/guidance.py` -- evaluate() function, GuidanceResponse type, destructive patterns
- `src/soma/hooks/pre_tool_use.py` -- exit(2) blocking mechanism confirmed
- `src/soma/hooks/notification.py` -- stdout injection mechanism confirmed
- `src/soma/hooks/common.py` -- action_log format `{tool, error, file, ts}` confirmed
- `src/soma/benchmark/harness.py` -- `guidance_responsive` skip mechanism understood
- `src/soma/cli/config_loader.py` -- DEFAULT_CONFIG, CLAUDE_CODE_CONFIG, MODE_PRESETS structures
- `soma.toml` -- current config structure, no `[reflexes]` section yet

### Secondary (MEDIUM confidence)
- `src/soma/hooks/post_tool_use.py` -- action recording flow, quality tracking
- `src/soma/audit.py` -- AuditLogger.append() interface for reflex logging

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all components exist, no new dependencies
- Architecture: HIGH -- integration of existing modules, clear data flow
- Pitfalls: HIGH -- identified from actual source code analysis (action_log format, PreToolUse timing)

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable codebase, internal architecture)
