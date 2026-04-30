# Changelog

All notable changes to SOMA. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions from `2026.4.0` onward use [CalVer](https://calver.org/) (`YYYY.M.PATCH`); pre-CalVer versions used SemVer.

## [Unreleased]

Post-`2026.6.2` work-in-progress, not yet released:

### Added
- `tools/hook_bench.py` — hook-latency benchmark scaffold.

### Fixed
- `analytics`: SQLite trigger rejects `NULL firing_id` inserts into `ab_outcomes` (defense in depth for the firing-id contract).
- `analytics`: hot-path indexes on `guidance_outcomes(pattern_key, ts)` and partial `ab_outcomes(pattern, arm)`.
- `ab`: purge orphaned `ab_counters.json.tmp.*` files on `reset_counters` (left behind by hook subprocesses that crashed between `fsync` and `os.replace`).
- `cli`: friendly error on invalid `mode` argument; restore wheel build path.
- `errors`: `log_silent_failure` helper wired into 8 swallow sites in data-integrity / write paths. Gated on `SOMA_DEBUG=1`, silent by default.
- `config`: moved `config_loader` from `cli/` to top-level `soma.config` (no public API change).

### Removed
- Deprecated `packages/soma-ai/` TypeScript stub.
- All in-repo markdown docs (re-authored from scratch).

---

## [2026.6.2] — 2026-04-29

Reliability + performance hotfix on top of 6.1.

### Performance
- `hooks`: in-process `compile()` instead of `py_compile` subprocess; tighten lint timeouts to 500 ms. Cuts hook-tool RTT in the common path.

### Fixed
- `analytics`: set `busy_timeout=5000` + `synchronous=NORMAL` on SQLite connections. WAL mode already on.
- `ab`: atomic write for `ab_counters.json` (`tmp + fsync + os.replace` under `flock`). Prior non-atomic write could corrupt counters under concurrent hook subprocesses.
- `guidance`: short-circuit retired patterns in `check_followthrough` (no-op for `_stats`, `drift`, `entropy_drop`, `context`).
- `errors`: `SomaBlocked` and `SomaBudgetExhausted` now correctly inherit from `SOMAError`.
- `tools`: `phantom_smoke.py` resolves paths relative to script + reads env-overridable database location.

---

## [2026.6.1] — 2026-04-29

Stop-ship hotfix: four security + correctness fixes immediately after 6.0.

### Security
- `hooks`: reject flag-shaped `file_path` (rejects `--evil` masquerading as a file path) and add `--` separator before the path argument in the hook subprocess invocation.
- `cli`: function-level allowlist for the `--definition` SQL identifier in `validate-patterns` (no SQL identifier injection through CLI args).

### Fixed
- `release-gate`: exclude `NULL firing_id` rows from `_arm_counts` so the count matches the t-test filter — gates were previously letting through under-powered comparisons.
- `ab`: drop `h=2` INSERT when `pressure_after_h1` is `NULL` (closes the `B1`-class bias at horizon 1).

---

## [2026.6.0] — 2026-04-27

The "proof pipeline" release: multi-horizon A/B recording, multi-definition guidance outcomes, dropguard, and pattern retirement after audit.

### Added
- `ab`: **multi-horizon recording** — `INSERT` at `h=2` (or `h=1`), `UPDATE-by-firing_id` at `h=5` and `h=10`. Outcomes can be analysed at any horizon without rerunning sessions.
- `analytics`: `firing_id` column added to `ab_outcomes` + per-horizon pressure columns (`pressure_after_h1`, `pressure_after_h5`, `pressure_after_h10`).
- `guidance`: `compute_multi_helped` — three orthogonal "helped" definitions persisted side-by-side (`helped_pressure_drop`, `helped_tool_switch`, `helped_error_resolved`).
- `analytics`: `guidance_outcomes` columns for the three helped definitions.
- `cli`: `validate-patterns` gains `--horizon` and `--definition` flags.
- `dashboard`: pattern cards surface multi-helped breakdown.
- `feat: P2.1` — `bash_error_streak` predictor in `OBSERVE` mode.
- `feat: P2.2` — A/B coverage release gate blocks under-sized ships.
- `analytics`: migration archives pre-`firing_id` legacy `ab_outcomes` rows into a quarantine table; `validate-patterns` excludes them.
- `tools`: `phantom_smoke` runner — end-to-end pipeline verification without an LLM.

### Changed
- `wrap` + `hooks`: double-wrap guard + cross-IDE `agent_id` family routing.
- `setup`: refuse to overwrite a corrupt `settings.json`; atomic write with `.bak`.

### Fixed
- `ab`: idempotency token on `should_inject` — kills A/B counter rebias on retried hook invocations.
- `budget`: removed silent spend clamp that was suppressing the `cost_spiral` signal.
- `state`: atomic writes for predictor / quality / fingerprint / task_tracker persistence.
- `hooks`: `flock` around `circuit_<aid>.json` read-modify-write; wrap followthrough RMW block in `circuit_transaction`.
- `hooks`: surface `PostToolUse` exceptions on `stderr` instead of silent `pass`.
- `baseline`: `from_dict` defaults match the constructor.
- Multiple corrections from independent code-review (pre-firing slice, firing_id collision window, RMW rollback, timeout pressure).

### Performance
- `statusline`: mtime-keyed cache with 1-second TTL; cuts repeated reads when the user holds the prompt open.

### Removed
- **Patterns retired after audit:**
  - `entropy_drop` — hardcoded `avg_gap < 3.0` panic threshold fired during fast `Read`/`Glob` exploration loops; historical precision <20%. Underlying entropy signal stays.
  - `context` — `helped` was structurally biased toward 0% because it required the agent to literally write `next.md` or run `git compact`. Underlying context-usage signal stays.

---

## [2026.5.5] — 2026-04-23

Block-randomized A/B + data hygiene.

### Added
- `ab`: block-randomized A/B harness — per-firing assignment to `treatment` / `control`, randomization keyed on `firing_id` (not `session_id`) to prevent intra-session bleed.

### Fixed
- Silence-cache reset that was blocking the A/B data pipeline.
- Silence refresh now filters pre-reset `guidance_outcomes` so resets actually clear pattern-silence state.
- Test-agent write guard prevents `test_*` agents from polluting analytics; purge migration in analytics removes prior pollution.

---

## [2026.5.4] — 2026-04-19

A/B measurement bias + control-arm contamination fix.

### Fixed
- A/B measurement bias caused by control arm receiving the same context-injection as treatment under a specific code path.
- Control-arm cleanup migration to remove contaminated rows.

---

## [2026.5.3] — 2026-04-19

A/B proof pipeline + stricter followthrough.

### Added
- A/B proof pipeline: `ab_outcomes` table, control-arm sham firings, paired-difference reporting, and the validation CLI to surface gate status per pattern.

### Changed
- Followthrough scoring now requires stricter behavioural evidence to count as "helped".

---

## [2026.5.2] — 2026-04-19

Round-2 audit fixes — second-pass corrections after independent review of `2026.5.1`.

### Fixed
- A series of correctness fixes from the round-2 audit (specific issue ids in commit messages).

---

## [2026.5.1] — 2026-04-19

Audit-fix release — first-pass corrections after self-review of `2026.5.0`.

### Fixed
- Correctness regressions surfaced by the post-release audit.

---

## [2026.5.0] — 2026-04-19

**Self-Calibration + Strict Mode.** Per-agent warmup, adaptive thresholds, and a hard-block tier for destructive ops.

### Added
- `calibration`: `CalibrationProfile` + persistence — per-agent baselines persist across sessions.
- `calibration`: warmup gate — guidance disabled until enough actions have been observed for the per-agent baseline to be meaningful.
- `calibration`: personal thresholds in pattern checks — pattern triggers consult the per-agent profile, not a global constant.
- `calibration`: adaptive auto-silence refresh loop — patterns that consistently fail to help are silenced automatically; silence is re-evaluated on a refresh interval.
- `blocks`: `BLOCK` mode state + `soma unblock` CLI.
- `strict-mode`: `PreToolUse` enforcement + block lifecycle (issue, expire, clear).
- `signal-pruning`: dropped `_stats` user-facing emission. Highest fatigue source in 5.x; underlying signal collection unchanged.
- `visibility`: surfaced SOMA's work to the user explicitly via the status line and dashboard.

---

## [2026.4.3] — 2026-04-18

Clean replacement for the yanked `2026.4.2`.

### Fixed
- Drift pattern precision: removed false-positive triggers on intentional context shifts.

---

## [2026.4.2] — *yanked*

Pulled from PyPI immediately after release; replaced by `2026.4.3`.

---

## [2026.4.0] — 2026-04-17

**Switch to CalVer.** Same wire format as `0.7.x`; new versioning scheme.

### Changed
- Version scheme: SemVer → CalVer (`YYYY.M.PATCH`). Reset patch numbering.

---

## [0.7.0] — 2026-04-15

Dashboard rebuild + Smart Guidance v2.

### Added
- Dashboard: full rebuild on FastAPI + SSE with new pattern-card surface, ROI panel, replay tab.
- Smart Guidance v2: pattern engine refactor — priority dict, persistent cooldowns, per-pattern severity, healing-suggestion dictionary.
- Audit logging: every guidance firing recorded with evidence + outcome.
- Cost-template guidance.

---

## [0.6.3] — 2026-04-14

### Changed
- Pressure system recalibrated: tighter thresholds, less false-positive guidance.

---

## [0.6.2] — 2026-04-12

### Changed
- Repo cleanup; docs overhaul.

---

## [0.6.1] — 2026-04-12

### Added
- Dashboard v2 (predecessor to the 0.7.0 rebuild).

### Changed
- Repo cleanup pass.

---

## [0.6.0] — 2026-04-02

**Mirror: proprioceptive behavioural feedback.** First version where the agent reads its own state and changes course mid-session — the closed-loop primitive that everything since has built on.

### Added
- Mirror loop: state read → guidance → context injection → next action.

---

## [0.5.0] — 2026-03 (mid)

### Added
- Documentation overhaul.
- Async/streaming hardening.

---

## [0.4.0] – [0.4.12]

### Added
- `0.4.0` — initial guidance system release.
- `0.4.6` — workflow-aware severity.
- `0.4.7` — positive feedback (reinforce when the agent does the right thing).
- `0.4.9` — directive injections + audit fixes + coverage.
- `0.4.11` – `0.4.12` — core polish, multi-agent ready.

---

## [0.3.x] and earlier

- `0.3.1` — auto-install slash commands via `setup-claude`.
- `0.3.0` — Claude Code plugin: slash commands and auto-registered hooks; PyPI publish workflow with trusted publishing.
- `0.2.x` — 9 new CLI commands + autonomy modes fully connected.
- `0.1.x` — project skeleton: types, ring buffer, first 11 tests.

---

<sub>Versioning policy: CalVer minor (`YYYY.M.X`) bumps for any user-visible change, patch for hotfixes, retroactive yanks for shipped regressions (see `2026.4.2`).</sub>
