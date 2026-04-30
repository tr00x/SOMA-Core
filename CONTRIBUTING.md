# Contributing to SOMA

Thanks for considering it. This document is short and direct — the bar is real but the rules are knowable.

---

## Scope

SOMA is a **runtime monitoring and guidance system** for autonomous LLM agents. Contributions that fit:

- Bug fixes against current behaviour.
- New vital signs (with prior, baseline, normalization, and tests).
- New guidance patterns (with the A/B contract — see below).
- Platform integrations beyond Claude Code / Cursor / Windsurf.
- Performance work on the hot path (`pre_tool_use` / `post_tool_use`).
- Documentation that explains *why* a decision was made, not what the code does.

Contributions that I will probably close:

- Features outside the closed-loop vitals → pressure → guidance pipeline.
- Refactors that move code without measurable benefit.
- Marketing-tone copy in any user-visible surface (README, dashboard, CLI).
- New external service dependencies in core.
- Anything that requires a daemon to run alongside the host agent.

If you're unsure, open a small **issue** first describing what you want to change and why. Two paragraphs is usually enough.

---

## Before you open a PR

- [ ] An issue exists, or the change is small enough not to need one (typo, doc fix, isolated bugfix with a regression test).
- [ ] You've read the relevant section of [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- [ ] `pytest` passes locally.
- [ ] `ruff check` is clean.
- [ ] If you added a new claim about behaviour ("pattern X helps Y%"), the claim is backed by data in the PR description, not just by argument.

---

## Dev setup

```bash
# Clone
git clone https://github.com/tr00x/SOMA-Core.git
cd SOMA-Core

# Install with uv (fast) or pip (works)
uv sync
# or:  pip install -e ".[dev]"

# Run the suite
pytest

# Lint
ruff check src tests

# Format
ruff format src tests
```

Python 3.11, 3.12, and 3.13 are all supported and tested in CI. Use whichever you have.

---

## Code conventions

- **Type hints on every function signature.** No exceptions for "obvious" return types.
- **Frozen dataclasses for value objects** (`Action`, `VitalsSnapshot`); mutable for mutable state (`AgentConfig`, `Baseline`).
- **No bare `except Exception: pass`.** Use `soma.errors.log_silent_failure(component, exc)` if you must swallow — it stays silent in production but surfaces under `SOMA_DEBUG=1`.
- **No mocks for SQLite or filesystem in integration tests.** Use a temp dir and a real `analytics.db`. Mocked persistence has shipped real bugs in this project before.
- **Atomic writes for any persistent state.** `tempfile.mkstemp` → `fsync` → `os.replace` under `flock`. See `persistence.py` and `ab_control.py` for the pattern.
- **No platform imports in `src/soma/` (top level).** Anything Claude Code / Cursor / Windsurf-specific lives under `src/soma/hooks/`.

---

## Commit messages

This repo uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body — what changed and why, in plain English>
```

`<type>` is one of:

| Type        | When                                                   |
|-------------|--------------------------------------------------------|
| `feat`      | New user-visible capability                            |
| `fix`       | Bug fix against current behaviour                      |
| `perf`      | Performance work on existing behaviour                 |
| `refactor`  | Internal restructuring with no behaviour change        |
| `test`      | Tests only                                             |
| `docs`      | Documentation only                                     |
| `chore`     | Dependency, build, release plumbing                    |
| `security`  | Security fix or hardening                              |

Keep the subject ≤ 72 characters. Use the body to explain *why*; a future maintainer will thank you.

---

## The architecture rules

These are non-negotiable because the layered design is the project's main design asset:

1. **Core is platform-agnostic.** `src/soma/` (top level) has zero imports from Claude Code, Cursor, Windsurf, Anthropic, or any specific provider.
2. **Hooks are the platform boundary.** Each platform gets a subdirectory in `src/soma/hooks/`. The CLI dispatcher (`hooks/claude_code.py`, etc.) routes to a shared core.
3. **State lives in `~/.soma/`.** No daemon, no network round-trip, no shared memory beyond the kernel's filesystem locks.
4. **Concurrency is file-based.** Multi-process hooks mean every state mutation must be `flock`-guarded and atomically written. This is not optional.
5. **The core path is synchronous.** No async, no queues, no background tasks in the action → vitals → pressure → guidance path. If a thing can't finish in one short subprocess lifetime, it doesn't belong on the hot path.

---

## The empirical rules

This is where SOMA differs from most monitoring projects.

### 1. No claim without data

If you add or modify a guidance pattern, you do **not** ship "this should help" copy in the README, the dashboard, or the message itself. The system has an A/B harness. Use it.

### 2. New guidance patterns must run the A/B contract

Any new entry in `_PATTERN_PRIORITY` (in `contextual_guidance.py`) must:

- Register with the A/B harness (`ab_control.py`).
- Have both a `treatment` and a `control` arm.
- Persist outcomes to `ab_outcomes` with a per-firing `firing_id`.
- Reach **n ≥ 30 paired observations** before being mentioned in the README's "what works" surface.

Until the gate is met, the pattern lives under the **"In active iteration"** label, with no quantitative claim attached.

### 3. Retiring a pattern is a respectable PR

If a pattern is shipping but the data says it's not helping (or is making things worse), opening a PR to retire it is welcome. Include the firing count, the helped %, and the reason in the commit body. See the `entropy_drop` and `context` retirements in `2026.6.0` for the template.

### 4. No marketing copy

The patterns talk to an LLM agent. The README talks to humans. Neither is the place for hype words ("revolutionary", "next-generation", "AI-powered safety platform"). Concrete sentences only.

---

## What's easy to land

- Bug fixes with regression tests.
- Documentation that explains a non-obvious decision.
- Performance improvements on the hot path with before/after numbers.
- New platform integrations (e.g. a hook adapter for a new IDE) that follow `hooks/claude_code.py` structurally.

## What's hard to land

- Changes to the **pressure aggregator** (`pressure.py`) or the **sigmoid clamp** in `vitals.py`. These are cross-cutting; touch them only with empirical justification.
- New core dependencies. Each one ships in every install. Justify it.
- Anything that breaks the synchronous, single-pass action path.
- Changes to the `~/.soma/` on-disk format without a migration in `analytics.py` and a regression test that loads pre-change state.

---

## Reporting issues

For bugs, the more reproducible the better. Useful things to include:

- SOMA version (`soma version`).
- Python version, OS.
- Which integration path (Claude Code hooks, SDK wrap).
- A minimal session: what the agent did, what SOMA showed, what you expected.
- Output of `soma status` and `soma doctor` if the project will not start.

For feature requests, lead with the *problem*. "I observed agents doing X" is more actionable than "SOMA should do Y".

---

## Security

Found a vulnerability? Don't open a public issue. See [`SECURITY.md`](SECURITY.md) for the disclosure process.

---

## License and attribution

SOMA is MIT-licensed. By submitting a PR you agree your contribution is licensed under the same terms. There is **no CLA** and there will not be one. Your name in the git log is your attribution.

---

<sub>Questions about contributing that aren't covered here? Open a discussion. Saying "this section was unclear" is itself a useful PR.</sub>
