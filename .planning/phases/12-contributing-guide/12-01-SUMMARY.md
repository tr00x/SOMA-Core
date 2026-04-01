---
phase: 12-contributing-guide
plan: 01
subsystem: hooks
tags: [hook-adapter, protocol, cursor, windsurf, claude-code, platform-agnostic]

requires:
  - phase: 09-wrap-api
    provides: "Core engine and existing Claude Code hook dispatcher"
provides:
  - "HookAdapter Protocol (LAYER-01) for cross-platform hook integration"
  - "CursorAdapter and WindsurfAdapter (HOOK-01)"
  - "ClaudeCodeAdapter for protocol compliance"
  - "soma setup --cursor/--windsurf/--claude-code CLI commands"
  - "generate_cursor_config() and generate_windsurf_config() for config generation"
affects: [12-02, 12-03, future-platform-integrations]

tech-stack:
  added: []
  patterns: ["HookAdapter runtime_checkable Protocol", "Platform adapter pattern with thin translation layers"]

key-files:
  created:
    - src/soma/hooks/base.py
    - src/soma/hooks/cursor.py
    - src/soma/hooks/windsurf.py
    - tests/test_hook_adapters.py
  modified:
    - src/soma/hooks/claude_code.py
    - src/soma/hooks/__init__.py
    - src/soma/cli/setup_claude.py
    - src/soma/cli/main.py

key-decisions:
  - "HookAdapter uses runtime_checkable Protocol for duck-typing compatibility with existing patterns"
  - "Existing Claude Code main() and DISPATCH left untouched for backward compatibility"
  - "Windsurf tool names inferred from event names via mapping dict"

patterns-established:
  - "Platform adapter: implement HookAdapter Protocol with platform_name, parse_input, format_output, get_event_type"
  - "Config generator: each adapter module exports generate_*_config() returning dict for hooks.json"

requirements-completed: [LAYER-01, HOOK-01]

duration: 4min
completed: 2026-03-31
---

# Phase 12 Plan 01: Cross-Platform Hook Adapters Summary

**HookAdapter Protocol with Cursor/Windsurf adapters translating platform-specific events to SOMA canonical types**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-01T01:10:00Z
- **Completed:** 2026-04-01T01:14:38Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- HookAdapter runtime_checkable Protocol defining cross-platform hook contract (platform_name, parse_input, format_output, get_event_type)
- CursorAdapter translating camelCase events and Cursor-specific input fields to SOMA canonical types
- WindsurfAdapter mapping split events (pre_write_code, pre_run_command, etc.) to unified PreToolUse/PostToolUse
- ClaudeCodeAdapter providing Protocol compliance without changing existing behavior
- Setup commands: `soma setup --cursor` and `soma setup --windsurf` generating correct hooks.json configs
- 41 adapter tests + full suite 890 passed, 0 regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: HookAdapter protocol, HookInput/HookResult types, and base dispatcher** - `f93ae95` (feat)
2. **Task 2: Cursor, Windsurf, and Claude Code adapters + setup commands** - `99b3f8f` (feat)

## Files Created/Modified
- `src/soma/hooks/base.py` - HookAdapter Protocol, HookInput/HookResult dataclasses, dispatch_hook()
- `src/soma/hooks/cursor.py` - CursorAdapter with camelCase event translation, generate_cursor_config()
- `src/soma/hooks/windsurf.py` - WindsurfAdapter with split-event mapping, generate_windsurf_config()
- `src/soma/hooks/claude_code.py` - Added ClaudeCodeAdapter class (existing main() untouched)
- `src/soma/hooks/__init__.py` - Exports HookAdapter, HookInput, HookResult, all adapters
- `src/soma/cli/setup_claude.py` - Added run_setup_cursor() and run_setup_windsurf()
- `src/soma/cli/main.py` - Added `soma setup --cursor/--windsurf/--claude-code` subcommand
- `tests/test_hook_adapters.py` - 41 tests covering protocol, adapters, config gen, setup commands

## Decisions Made
- HookAdapter uses runtime_checkable Protocol (consistent with existing ExporterProtocol pattern from phase 11)
- Existing Claude Code main() and DISPATCH dict left completely untouched for backward compatibility
- Windsurf tool names inferred from event names via _WINDSURF_EVENT_TO_TOOL mapping
- Cursor format_output writes both JSON stdout and stderr for maximum compatibility

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- HookAdapter Protocol ready for additional platform integrations
- Cursor and Windsurf configs can be generated and installed
- All existing Claude Code behavior preserved

---
*Phase: 12-contributing-guide*
*Completed: 2026-03-31*
