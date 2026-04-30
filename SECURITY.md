# Security Policy

Thanks for taking the time to find this file. Security reports are read and answered.

---

## Reporting a vulnerability

**Do not open a public GitHub issue for vulnerabilities.**

Email **`tr00x@proton.me`** with:

- A description of the issue and the affected component (`hooks/`, `cli/`, `analytics`, etc.).
- A minimal reproducer — commands, file paths, or session traces that exhibit the behaviour.
- The SOMA version (`soma version`), Python version, and OS.
- Your name (or pseudonym) and a link if you'd like credit in the advisory.

If you prefer end-to-end encrypted mail, the same address works on Proton's bridge.

### What to expect

- **Acknowledgment** within 72 hours.
- **Triage decision** (in scope / out of scope / duplicate) within 7 days.
- **Fix or mitigation** within 30 days for confirmed vulnerabilities. If the work needs longer (architecture-level changes), I will say so explicitly with a target date.
- **Coordinated disclosure**: a public advisory + patched release shipped together, with credit to the reporter unless they opt out.

---

## Supported versions

| Version line       | Status                                |
|--------------------|---------------------------------------|
| `2026.6.x`         | **Supported** — fixes in latest patch |
| `2026.5.x`         | Critical fixes only                   |
| `2026.4.x`         | End of life                           |
| `0.7.x` and older  | Unsupported                           |

The CalVer scheme means a security release is `YYYY.M.PATCH+1` on the current line. There is no separate LTS.

---

## Threat model

SOMA runs **locally**, in the same trust domain as the host agent (Claude Code, Cursor, an SDK consumer). The threat model reflects that.

### What SOMA defends against

- **Hostile tool output.** The agent's tool invocations may produce arbitrary text. SOMA parses that text into vitals; it must never execute, evaluate, or shell-out anything derived from it.
- **CLI argument injection.** `soma`, `soma-hook`, and `soma-statusline` accept arguments that may originate from the host's settings file. Flag-shaped or shell-metacharacter inputs in path arguments are rejected; SQL identifier arguments (`validate-patterns --definition X`) pass through a function-level allowlist.
- **State file corruption.** Concurrent hook subprocesses share `~/.soma/`. All persistent state is written through `flock` + atomic `tempfile + fsync + os.replace`. A crashed or killed writer cannot leave a partial state file readable.
- **A/B counter biasing.** The block-randomized A/B harness is sensitive to any concurrent write that could rebias arms. `ab_counters.json` is double-protected (lock + atomic replace) and idempotent on retry.

### What SOMA does *not* defend against

These are architectural choices, listed so reports targeting them can be triaged correctly.

- **Malicious agent behaviour itself.** SOMA observes and guides; it does not sandbox the agent's tool execution. If the agent runs `rm -rf ~/`, the host's tool runtime (Claude Code, Cursor, etc.) is what allowed the call — SOMA can refuse a destructive op only when its pressure scalar already exceeds 0.75, which is a heuristic gate, not a guarantee.
- **Compromise of the user's local machine.** SOMA's state lives in `~/.soma/` with the user's file permissions. A local adversary with read access to that directory can see the user's behavioural history. Encrypt your home directory if that matters to you.
- **Provider-side compromise.** SOMA wraps an LLM client. If the LLM API endpoint is compromised, SOMA does not detect that.
- **Long-running daemon attacks.** SOMA does not run a daemon. There is no listening port, no IPC socket, no long-lived process to attack.

---

## Hardening practices

These are the standing rules in the codebase. PRs that violate them are rejected on review.

- **No `eval` / `exec` / `shell=True` of agent-derived strings.** Anywhere in `src/soma/`. Subprocess invocations use list-form `argv` with a `--` separator before any path argument.
- **Atomic writes for every persistent file.** `tempfile.mkstemp` → `os.fsync` → `os.replace`, under `fcntl.flock`. See `persistence.py` and `ab_control.py`.
- **SQLite hardening.** `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`. Schema includes triggers that reject inserts violating critical invariants (e.g. `NULL firing_id` into `ab_outcomes`).
- **Identifier allowlists for SQL.** Anywhere user input becomes a column or table name (`validate-patterns --definition`), the input must pass a function-level allowlist before reaching the query builder. No string formatting of identifiers from arbitrary input.
- **Path argument hardening for hook subprocesses.** Flag-shaped values (`--whatever`) are rejected as `file_path` arguments; the subprocess argv uses `--` to separate flags from positional paths.
- **No silent failures in write paths.** `log_silent_failure(component, exc)` is the only sanctioned swallow, and it stays silent in production but surfaces under `SOMA_DEBUG=1`.

---

## Past advisories

Tracked here so the security history is auditable. Commit references are stable across the rewritten history.

| Date        | Severity | Component        | Summary                                                                       |
|-------------|----------|------------------|-------------------------------------------------------------------------------|
| 2026-04-29  | Medium   | `cli`            | SQL identifier injection guard for `validate-patterns --definition` (function-level allowlist). |
| 2026-04-29  | Medium   | `hooks`          | Hook subprocess argument injection via dash-prefixed `file_path` (added rejection + `--` separator). |

These were both shipped in `2026.6.1`. There is no embargoed advisory at the time of writing.

---

## What's not a vulnerability

Sometimes useful to be explicit:

- **A guidance pattern that doesn't help.** That's a behavioural data finding, not a security issue. Open a regular issue with the data.
- **A pressure miscalculation.** Same — that's a correctness or calibration issue, not a vulnerability.
- **The fact that an agent ignored a `WARN`.** SOMA does not enforce non-`BLOCK` modes; the agent reading the message is the agent's prerogative.
- **Use of personal data in `~/.soma/analytics.db`.** That's *your* behavioural history on *your* machine. SOMA does not transmit it anywhere unless you wire up `[otel]` and point it at a collector.

---

## Disclosure

If a fix takes more than 90 days, I will publish a partial advisory anyway describing the issue at a level that helps users mitigate without disclosing the exploit path. This keeps me honest on the timeline.

---

<sub>This file is the canonical contact point. The GitHub Security tab also accepts private vulnerability reports if you prefer that flow.</sub>
