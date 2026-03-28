# Changelog

All notable changes to SOMA Core are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [0.2.0-beta] — 2026-03-28

### Paperclip Plugin v3

- Full Paperclip integration: dashboard widget, monitoring page (`/soma`), sidebar, settings page, agent detail tab
- Real-time monitoring pipeline: Claude Code hook → `~/.soma/inbox/` → daemon → `state.json` → plugin UI (2–3s latency)
- File-based command queue: quarantine, release, reset baseline, replenish budget, set thresholds, set budget limits
- SOMA daemon (`soma.daemon`) — polls inbox + commands every 1s, auto-exports state
- 1-click install from Paperclip UI (Settings → Plugins → Examples)
- Editable escalation thresholds, budget limits, behavior toggles in Settings
- Control Panel: Quarantine All / Release All / Reset All Baselines / Export State
- Per-agent Quarantine/Release with real-time level indicators
- Toast notifications on level changes and user actions
- Tooltips on all vitals and level badges
- Onboarding flow: 3 states (offline, 0 agents, active) with step-by-step guidance
- Dynamic sidebar with company prefix detection

### Engine

- Command queue processor (`soma.commands`) — `force_level`, `replenish_budget`, `reset_baseline`, `set_trust`, `set_thresholds`, `set_budget_limits`, `get_snapshot`, `export_state`
- Inbox processor (`soma.inbox`) — reads Claude Code hook output, auto-registers agents, creates Action objects
- Daemon mode (`soma.daemon`) — long-running bridge between external tools and SOMA engine

### Integration

- Claude Code PostToolUse hook (async, non-blocking, 5s timeout)
- File-based IPC: `~/.soma/inbox/` (actions), `~/.soma/commands/` (control), `~/.soma/results/` (responses), `~/.soma/state.json` (state)

---

## [0.1.0-beta] — 2026-03-28

First public release.

### Core Engine

- **Behavioral vitals:** uncertainty (retry rate, output entropy, tool deviation, format deviation) and semantic drift (cosine distance on behavior vectors)
- **Dual drift mode:** informational (logged only) vs directive (influences pressure)
- **EMA baseline** with cold start blending and grace period (first 10 actions)
- **Pressure computation:** sigmoid-clamped z-score, 70/30 mean/max aggregate
- **Absolute pressure floors** for error_rate and retry_rate (errors never become "normal")
- **Time anomaly detection:** response time spikes boost uncertainty
- **Burn rate feedback** into pressure (early warning before budget exhaustion)
- **Pressure graph:** trust-weighted multi-pass inter-agent propagation
- **Asymmetric trust dynamics:** decay=0.05, recovery=0.02
- **6-level escalation ladder** with hysteresis (HEALTHY → SAFE_MODE)
- **Self-learning feedback loop** with safety bounds — adjusted weights and thresholds feed back into engine
- **Directive context control:** truncate, block tools, quarantine, restart
- **State persistence** across process restarts
- **Session recording** and replay

### CLI

- `soma` — TUI hub with 4 tabs (Dashboard, Agents, Replay, Config)
- `soma init` — interactive wizard (Claude Code / SDK / CI modes)
- `soma status` — quick text status with colored levels
- `soma replay FILE` — rich table replay with per-agent summary
- `soma setup-claude` — one-command Claude Code integration
- `soma version`

### Integration

- `soma.wrap(client)` — universal API client wrapper (Anthropic + OpenAI SDKs)
- `soma.quickstart()` — fastest way to create a configured engine
- `SomaBlocked` / `SomaBudgetExhausted` exceptions for agent control
- Claude Code hooks (PreToolUse, PostToolUse, PostMessage, Stop)
- Paperclip plugin (dashboard widget, state file protocol)

### Testing

- `soma.testing.Monitor` — pytest context manager with `assert_healthy` / `assert_below`
- 399 tests, 100% coverage on core modules
- Edge case tests (100 agents, graph cycles, 10K action roundtrip)
- Behavioral stress tests (degradation, recovery, contagion, budget depletion)

### Documentation

- Getting Started Guide (`docs/guide.md`)
- Technical Reference (`docs/reference.md`)
- API Reference (`docs/api.md`)
- Contributing Guide (`CONTRIBUTING.md`)
