---
phase: 12-contributing-guide
plan: 02
subsystem: ecosystem
tags: [npm, typescript, policy-packs, yaml, cli]

requires:
  - phase: 08-sdk-policy-guardrail
    provides: PolicyEngine with from_file/from_url/from_dict and @guardrail decorator
provides:
  - NPM-publish-ready TypeScript SDK package.json with metadata
  - Community policy pack loading from soma.toml config
  - soma policy list/add/remove CLI commands
  - Two example policy packs (strict.yaml, cost-guard.yaml)
affects: [npm-publishing, policy-ecosystem, cli]

tech-stack:
  added: [pyyaml]
  patterns: [policy-pack-yaml-format, config-driven-pack-loading]

key-files:
  created:
    - packages/soma-ai/README.md
    - policies/strict.yaml
    - policies/cost-guard.yaml
    - tests/test_policy_packs.py
  modified:
    - packages/soma-ai/package.json
    - src/soma/policy.py
    - src/soma/cli/main.py
    - .gitignore

key-decisions:
  - "Duck-type checks in tests to avoid module-reload isinstance failures"
  - "Exports condition ordering: types first for proper TypeScript resolution"

patterns-established:
  - "Policy pack YAML format: version 1 with policies array of when/do rules"
  - "CLI subcommand pattern: soma <noun> <verb> for resource management"

requirements-completed: [NPM-01, POL-03]

duration: 4min
completed: 2026-03-31
---

# Phase 12 Plan 02: NPM + Policy Packs Summary

**NPM-publish-ready TS SDK with repository metadata, and community policy pack loading from soma.toml config with CLI management**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-01T01:09:58Z
- **Completed:** 2026-04-01T01:14:27Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- TypeScript SDK package.json has full NPM metadata (repository, author, homepage, bugs, publishConfig, engines)
- Build produces CJS + ESM + DTS in dist/, typecheck passes, npm pack succeeds
- load_policy_packs() loads policy packs from soma.toml [policies] packs list
- soma policy list/add/remove CLI commands for pack management
- Two example policy packs ship in policies/ directory

## Task Commits

Each task was committed atomically:

1. **Task 1: NPM publish preparation** - `b8f86ad` (feat)
2. **Task 2 RED: Failing tests for policy packs** - `40b3b1f` (test)
3. **Task 2 GREEN: Policy pack loading + CLI + example packs** - `31a1587` (feat)
4. **Gitignore update** - `8521221` (chore)

## Files Created/Modified
- `packages/soma-ai/package.json` - Added repository, author, homepage, bugs, publishConfig, engines; fixed exports ordering
- `packages/soma-ai/README.md` - NPM listing README with install + quick start
- `src/soma/policy.py` - Added load_policy_packs() for config-driven pack loading
- `src/soma/cli/main.py` - Added soma policy list/add/remove subcommands
- `policies/strict.yaml` - Example strict policy pack (3 rules: error, cost, drift)
- `policies/cost-guard.yaml` - Example cost guard pack (2 rules: token budget, cost cap)
- `tests/test_policy_packs.py` - Tests for pack loading and example YAML validation
- `.gitignore` - Added node_modules/ and package-lock.json

## Decisions Made
- Fixed exports condition ordering in package.json (types first) to eliminate tsup build warnings
- Used duck-type checks (hasattr) instead of isinstance for PolicyEngine in tests, avoiding module-reload compatibility issues from test_policy.py's reload test

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed exports condition ordering in package.json**
- **Found during:** Task 1 (NPM publish preparation)
- **Issue:** tsup warned that "types" condition after "import"/"require" would never be used
- **Fix:** Moved "types" to first position in exports conditions
- **Files modified:** packages/soma-ai/package.json
- **Committed in:** b8f86ad

**2. [Rule 3 - Blocking] Added node_modules and package-lock.json to .gitignore**
- **Found during:** Task 1 (after npm install)
- **Issue:** npm install created node_modules/ and package-lock.json not in .gitignore
- **Fix:** Added both patterns to .gitignore
- **Files modified:** .gitignore
- **Committed in:** 8521221

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both necessary for correctness. No scope creep.

## Issues Encountered
- Pre-existing test failure in test_hook_adapters.py::TestSetupCommands::test_run_setup_cursor_exists (not caused by this plan, unrelated to policy packs)

## Known Stubs
None - all functionality is fully wired.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- TypeScript SDK ready for npm publish (user runs `cd packages/soma-ai && npm publish` manually)
- Policy pack ecosystem ready for community contributions
- soma policy CLI ready for user workflow

---
*Phase: 12-contributing-guide*
*Completed: 2026-03-31*
