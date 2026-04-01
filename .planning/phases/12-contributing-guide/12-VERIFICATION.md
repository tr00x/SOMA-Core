---
phase: 12-contributing-guide
verified: 2026-04-01T01:44:35Z
status: human_needed
score: 11/12 must-haves verified
human_verification:
  - test: "Review demo.tape and confirm its scope is acceptable"
    expected: "Tape uses demo_session.py for monitoring demo; does NOT show pip install or soma setup CLI commands. Confirm this is an acceptable deviation from the plan spec or request CLI commands be added."
    why_human: "Plan 12-03 was autonomous:false with a checkpoint:human-verify gate. The summary documents a deliberate deviation (system Python 3.9, VHS quoting issues) that changed the approach from install+setup+monitor to monitor-only. Acceptability is a judgment call."
---

# Phase 12: Ecosystem — Hooks, NPM, Demo, Policy Packs Verification Report

**Phase Goal:** Ecosystem — Hooks, NPM, Demo, Policy Packs. Build cross-platform hook adapters, prepare NPM publishing, create terminal demo, and add community policy pack support.
**Verified:** 2026-04-01T01:44:35Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | HookAdapter protocol defines parse_input, format_output, get_event_type, platform_name | VERIFIED | `src/soma/hooks/base.py` contains all 4 protocol methods, runtime_checkable decorator present |
| 2 | Cursor adapter correctly translates camelCase events and Cursor-specific fields to HookInput | VERIFIED | `cursor.py` maps preToolUse/postToolUse/stop, extracts conversation_id as session_id, 41 adapter tests pass |
| 3 | Windsurf adapter correctly maps split events to SOMA canonical events | VERIFIED | `windsurf.py` has _WINDSURF_EVENT_MAP with pre_run_command, pre_write_code, post_* entries; isinstance check passes |
| 4 | Claude Code adapter implements HookAdapter protocol without breaking existing behavior | VERIFIED | ClaudeCodeAdapter class added in claude_code.py; existing main() and DISPATCH dict untouched; 890 tests pass |
| 5 | soma setup --cursor generates correct .cursor/hooks.json | VERIFIED | run_setup_cursor() in setup_claude.py; --cursor flag wired in main.py |
| 6 | soma setup --windsurf generates correct .windsurf/hooks.json | VERIFIED | run_setup_windsurf() in setup_claude.py; --windsurf flag wired in main.py |
| 7 | TypeScript SDK builds successfully producing CJS + ESM + DTS in dist/ | VERIFIED | dist/index.js, dist/index.mjs, dist/index.d.ts all exist |
| 8 | package.json has correct repository, author, homepage fields for NPM publishing | VERIFIED | grep confirms repository, author, homepage, publishConfig, engines all present |
| 9 | Policy packs can be loaded from soma.toml [policies] packs list | VERIFIED | load_policy_packs() in policy.py reads config.get("policies", {}).get("packs", []); 13 policy pack tests pass |
| 10 | soma policy list shows loaded policy packs | VERIFIED | _cmd_policy() in main.py calls load_policy_packs and prints results; add/remove subcommands also wired |
| 11 | Example policy pack YAML files exist in policies/ directory | VERIFIED | policies/strict.yaml (version "1", 3 rules) and policies/cost-guard.yaml (version "1", 2 rules) both exist |
| 12 | The tape demonstrates install, setup, and monitoring in action | UNCERTAIN | demo.tape exists and is valid VHS syntax; demo.gif generated (867KB); README references it. However the tape only runs `uv run python3 demo_session.py` — no pip install or soma CLI commands. Monitoring IS shown through real engine. Needs human sign-off. |

**Score:** 11/12 truths verified (1 needs human)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/soma/hooks/base.py` | HookAdapter Protocol + HookInput + HookResult + dispatch_hook() | VERIFIED | All 4 classes/functions present; frozen dataclasses with slots=True; runtime_checkable Protocol |
| `src/soma/hooks/cursor.py` | CursorAdapter implementing HookAdapter | VERIFIED | class CursorAdapter, camelCase event mapping, generate_cursor_config(), isinstance check passes |
| `src/soma/hooks/windsurf.py` | WindsurfAdapter implementing HookAdapter | VERIFIED | class WindsurfAdapter, split-event mapping dict, generate_windsurf_config(), isinstance check passes |
| `src/soma/hooks/claude_code.py` | ClaudeCodeAdapter added (existing main() untouched) | VERIFIED | ClaudeCodeAdapter present; imports HookInput/HookResult from base; DISPATCH dict unchanged |
| `src/soma/hooks/__init__.py` | Exports all adapters + base types | VERIFIED | Exports HookAdapter, HookInput, HookResult, CursorAdapter, WindsurfAdapter, ClaudeCodeAdapter |
| `src/soma/cli/setup_claude.py` | run_setup_cursor() and run_setup_windsurf() | VERIFIED | Both functions present |
| `tests/test_hook_adapters.py` | 41 adapter tests | VERIFIED | 41 passed, 0 failed |
| `packages/soma-ai/package.json` | NPM-publishable metadata | VERIFIED | repository, author, homepage, bugs, publishConfig, engines all present |
| `packages/soma-ai/README.md` | NPM listing README | VERIFIED | File exists with install instructions |
| `packages/soma-ai/dist/` | CJS + ESM + DTS output | VERIFIED | index.js, index.mjs, index.d.ts all present |
| `src/soma/policy.py` | load_policy_packs() function | VERIFIED | Function present, reads [policies].packs from config, graceful error handling |
| `src/soma/cli/main.py` | soma policy list/add/remove subcommands | VERIFIED | _cmd_policy() wired; soma policy subparser registered |
| `policies/strict.yaml` | Example strict policy pack | VERIFIED | version "1", 3 rules (high-error-guard, cost-limit, drift-alert) |
| `policies/cost-guard.yaml` | Example cost guard policy pack | VERIFIED | version "1", 2 rules (token-budget, hard-cost-cap) |
| `tests/test_policy_packs.py` | Policy pack tests | VERIFIED | 13 passed, 0 failed |
| `demo.tape` | VHS tape script | VERIFIED | Valid VHS syntax, Output demo.gif directive, theme set, demo_session.py invoked |
| `demo.gif` | Generated terminal recording | VERIFIED | 867KB file present |
| `README.md` | Demo section with image ref | VERIFIED | Contains Demo section, img src="demo.gif", vhs generation instructions |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/soma/hooks/cursor.py` | `src/soma/hooks/base.py` | implements HookAdapter protocol | WIRED | `from soma.hooks.base import HookAdapter, HookInput, HookResult`; CursorAdapter class present |
| `src/soma/hooks/windsurf.py` | `src/soma/hooks/base.py` | implements HookAdapter protocol | WIRED | same import pattern; WindsurfAdapter class present |
| `src/soma/hooks/claude_code.py` | `src/soma/hooks/base.py` | imports HookInput, uses dispatch or existing DISPATCH | WIRED | `from soma.hooks.base import HookInput, HookResult` confirmed |
| `src/soma/cli/config_loader.py` | `src/soma/policy.py` | loads [policies] packs from soma.toml | WIRED | load_policy_packs() reads config dict key "policies"."packs"; _cmd_policy calls load_policy_packs with loaded config |
| `src/soma/cli/main.py` | `src/soma/policy.py` | soma policy list CLI command | WIRED | `from soma.policy import load_policy_packs` inside _cmd_policy; subcommand registered in parser |
| `README.md` | `demo.tape` | references generated demo GIF | WIRED | `<img src="demo.gif">` and vhs generation note present |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LAYER-01 | 12-01 | Layer SDK — trivial creation of new platform integrations | SATISFIED | HookAdapter runtime_checkable Protocol in base.py provides the layer abstraction; dispatch_hook() routes events; CursorAdapter/WindsurfAdapter demonstrate the pattern |
| HOOK-01 | 12-01 | Cursor/Windsurf hooks — same 4-hook architecture for other AI coding tools | SATISFIED | cursor.py and windsurf.py both implement HookAdapter; isinstance checks pass; setup commands generate correct config files |
| NPM-01 | 12-02 | NPM publish TypeScript SDK | SATISFIED | package.json has all required metadata; dist/ CJS+ESM+DTS present; README exists; package is publish-ready |
| POL-03 | 12-02 | Community policy packs — shareable rule sets | SATISFIED | load_policy_packs() loads from URLs or local paths; soma policy CLI manages packs; two example YAMLs in policies/ |
| DEMO-01 | 12-03 | Demo GIF/video for README | SATISFIED (conditional) | demo.gif exists (867KB), README references it, demo.tape is valid VHS script. Demo shows real SOMA engine monitoring. Condition: human sign-off on scope (no install/setup CLI commands in tape) |

All 5 requirement IDs declared across plans are accounted for. No orphaned requirements found for Phase 12 in REQUIREMENTS.md (Milestone 5 section lists exactly these 5 IDs assigned to this phase).

### Anti-Patterns Found

No anti-patterns detected. Scanned all new phase files for TODO/FIXME/PLACEHOLDER/not-implemented patterns — all clear.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No issues found | — | — |

### Human Verification Required

#### 1. Demo Tape Scope Review

**Test:** Open `demo.tape` and read its 20 lines. Then view `demo.gif` (867KB, should play in browser or image viewer).
**Expected:** The tape runs `uv run python3 demo_session.py` which shows a real 20-action SOMA monitoring session with pressure escalating from OBSERVE through GUIDE to WARN. The tape does NOT show `pip install soma-ai` or `soma setup` commands.
**Why human:** Plan 12-03 truth states "The tape demonstrates install, setup, and monitoring in action." The implementation shows monitoring-in-action only (via demo_session.py). The summary documents a deliberate deviation: system Python 3.9 forced `uv run` instead of pip install, and VHS parser quoting issues forced moving inline Python to a separate script. This changed the demo from a CLI walkthrough to a monitoring showcase. Whether this satisfies DEMO-01 ("Demo GIF/video for README") is a judgment call — the GIF exists and is in the README, but it doesn't show the install+setup flow the plan specified.

**Options if gap matters:**
- Add `Type "soma setup --claude-code"` to demo.tape before the demo_session.py invocation
- Accept the current form — the monitoring showcase is compelling and DEMO-01 says "Demo GIF/video" not "install tutorial"

### Gaps Summary

No blocking gaps. One soft gap pending human sign-off:

The demo tape delivers the monitoring-in-action portion of DEMO-01 (real engine, real pressure escalation, rich terminal output, GIF in README) but omits the install and setup CLI walkthrough specified in the plan. This was a documented intentional deviation in the phase 12-03 summary due to environment constraints. The requirement DEMO-01 ("Demo GIF/video for README") is met; the plan's extended truth is partially met.

All other requirements (LAYER-01, HOOK-01, NPM-01, POL-03) are fully satisfied with substantive, wired implementations. Full test suite: 890 passed, 5 skipped, 0 failed.

---

_Verified: 2026-04-01T01:44:35Z_
_Verifier: Claude (gsd-verifier)_
