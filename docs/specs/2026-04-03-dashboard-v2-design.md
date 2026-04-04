# SOMA Dashboard v2 — Full Design Spec

**Date:** 2026-04-03
**Status:** Approved
**Stack:** Alpine.js + Tailwind CDN + Chart.js + FastAPI (no build step)

---

## Architecture

### Principle
Modular SPA — index.html is a shell, each tab is a separate JS module.
Backend serves REST API + SSE stream. Frontend knows nothing about storage layer.

### File Structure

```
src/soma/dashboard/
├── app.py                    # FastAPI backend (refactored, clean)
├── sse.py                    # Server-Sent Events hub
├── server.py                 # uvicorn launcher
├── __init__.py
└── static/
    ├── index.html            # Shell: header, nav, tab containers (~150 lines)
    ├── favicon.svg
    ├── style.css             # All CSS (tailwind config, custom styles, animations)
    ├── app.js                # Alpine init, routing, shared state, keyboard shortcuts
    ├── api.js                # All fetch calls + SSE connection + fallback polling
    ├── charts.js             # Chart.js wrappers (create, update, destroy lifecycle)
    └── tabs/
        ├── overview.html     # Overview tab template
        ├── overview.js       # Overview tab logic
        ├── deep-dive.html    # Agent Deep Dive tab template
        ├── deep-dive.js      # Agent Deep Dive tab logic
        ├── settings.html     # Settings tab template
        ├── settings.js       # Settings tab logic
        ├── logs.html         # Logs tab template
        ├── logs.js           # Logs tab logic
        ├── sessions.html     # Sessions tab template
        ├── sessions.js       # Sessions tab logic
        ├── analytics.html    # Analytics tab template
        ├── analytics.js      # Analytics tab logic
```

### Backend: SSE instead of polling

Single endpoint `GET /api/stream` pushes events:
- `event: agents` — agent list with vitals (every N seconds)
- `event: budget` — budget health
- `event: alert` — escalation/mode change/circuit breaker events
- `event: reflex` — reflex trigger events

Fallback: if SSE disconnects, auto-switch to polling.

---

## Tab 1: Overview

**Status bar** (single row):
- Max pressure across agents, worst mode badge
- Budget health %, active agents count
- Session capacity (actions remaining from planner.py)
- Cascade risk indicator (if subagents exist)

**Agent cards** (horizontal row, scrollable):
- Pressure number + colored bar + sparkline (last 30 trajectory points)
- Mode badge (OBSERVE/GUIDE/WARN/BLOCK)
- Quality grade letter + phase badge (research/implement/test/debug)
- Circuit breaker state badge (OPEN/CLOSED) if applicable
- Half-life indicator (green/yellow/red)
- Click → navigate to Deep Dive tab for this agent

**RCA strip** (if any diagnosis exists):
- Red/orange banner with diagnosis text from rca.py
- e.g. "stuck in Edit→Bash→Edit loop on config.py (3 cycles)"

**Predictions alert strip**:
- If will_escalate=true: "Agent X predicted to escalate in ~N actions (reason)"

**Findings** — top 5 cards, priority-colored (critical=red, important=orange, positive=green)

**Patterns** — detected patterns across all agents

**Sidebar (desktop):**
- Budget gauges per dimension + burn rate (tokens/hr, $/hr, projected overshoot)
- Tool usage top-5 horizontal bars
- 24h activity heatmap

---

## Tab 2: Agent Deep Dive

Selected via click from Overview or dropdown at top.

**Row 1 — Header:**
- Agent ID, mode, pressure big number, phase, uptime
- Half-life gauge: P(success) decay curve, current position, handoff suggestion
- Session capacity: actions remaining estimate
- Circuit breaker: state + consecutive counters

**Row 2 — Charts (2 columns):**
- Left: **Pressure timeline** — trajectory + threshold lines (guide/warn/block) + prediction cone (dashed future points)
- Right: **Vitals radar** — 6 axes (uncertainty, drift, error_rate, cost, goal_coherence, context_usage) current vs baseline overlay

**Row 3 — Signal breakdown (3 columns):**
- **Pressure vector** — horizontal bars per signal with weights applied
- **Calibration panel** — score, verbal_behavioral_divergence flag, hedging rate vs error rate, uncertainty_type (epistemic/aleatoric)
- **Baseline health** — integrity flag, per-signal EMA vs current, warmup progress

**Row 4 — Intelligence (2 columns):**
- **Predictions** — will_escalate, confidence %, dominant_reason, actions_ahead countdown
- **Fingerprint** — divergence score, tool distribution current vs historical (side-by-side bars), read_write_ratio shift

**Row 5 — Reflexes & RCA (2 columns):**
- **Reflex timeline** — recent reflex triggers: kind (blind_edits, thrashing, commit_gate, retry_dedup), block vs inject, override usage
- **RCA** — current diagnosis text + history of past diagnoses

**Row 6 — Mirror & Context (2 columns):**
- **Mirror system** — injection effectiveness %, pattern DB summary (top patterns + success rates), semantic call count
- **Context control** — tool availability at current mode, message retention %, context reduction events

**Row 7 — Session Memory & Scope (2 columns):**
- **Session memory** — matched similar session (if any), similarity score, outcome of matched session
- **Scope drift** — drift score, drift_explanation, focus_files/focus_dirs, initial vs current focus

**Row 8 — Graph (full width):**
- **Agent relationship graph** — interactive visualization. Nodes = agents, edges = trust weights. Node size = pressure, color = mode. Inner/outer ring = internal vs effective pressure. Coordination SNR labels on edges.

**Row 9 — Subagents (full width, if parent agent):**
- **Cascade risk** gauge
- **Subagent matrix** — table: id, actions, errors, error_rate, top_tool, pressure

**Row 10 — History:**
- **Intervention history** — timeline: mode changes with outcomes (success/failure), learning adjustments (threshold/weight deltas)
- **Actions feed** — last 20 actions: tool, file, error, timestamp
- **Context burn** — burn_rate trend, remaining context estimate

---

## Tab 3: Settings

Vertical sub-tabs on left:

| Sub-tab | Content |
|---------|---------|
| **Mode** | soma.mode (reflex/advisory/strict), one-click switch |
| **Thresholds** | guide/warn/block sliders (0-1) with visual zone scale. Threshold tuner: run benchmark, see optimal vs current, false positive rate |
| **Weights** | Per-signal weight sliders with numbers |
| **Budget** | Token/cost limits, current spend, reset button |
| **Graph** | damping, trust_decay_rate, trust_recovery_rate sliders |
| **Vitals** | goal_coherence_threshold, warmup, error_ratio, min_samples |
| **Hooks** | Feature toggles: validate_python, validate_js, lint_python, predict, fingerprint, quality, task_tracking |
| **Agents** | Per-agent: autonomy mode, sensitivity, tools list |
| **Policies** | Rule catalog from policy.py. View conditions + actions. Add/edit/delete rules |
| **Raw TOML** | Textarea with raw soma.toml content, save button |

Each sub-tab: values loaded from API, save button, toast on success/error, defaults reset button.

---

## Tab 4: Logs

**Filters bar:**
- Agent dropdown, text search, mode filter (checkboxes), event type filter (action/reflex/policy/mode_change), date range

**Table columns:**
- Timestamp, agent, tool, file, pressure, mode, error, reflex_kind, policy_rule

**Features:**
- Color coding: rows tinted by mode
- Reflex events: show reflex_kind column (blind_edits, thrashing, commit_gate, retry_dedup)
- Override audit: when SOMA overrides were used
- Policy fires: which rules triggered
- Export CSV button
- Auto-refresh via SSE (new entries animate in at top)

---

## Tab 5: Sessions

**Session list** (enriched):
- Agent ID, action_count, duration, quality score 0-100
- Mode transitions count, phase_sequence visualization (colored blocks)
- Fingerprint divergence score, "has replay" indicator

**Session detail panel:**
- Pressure trajectory chart + mode transitions overlay (colored vertical bands)
- Phase timeline bar (colored segments: research→implement→test→debug)
- Tool distribution chart (horizontal bars)
- Similar sessions panel — cosine similarity matches from session_memory.py
- Session report — rendered markdown from report.py

**Cross-session trends:**
- Pressure/errors/cost over last N sessions (line chart from analytics.py)

**Export:** Session JSON download

---

## Tab 6: Analytics

Data from analytics.py (SQLite) + derived metrics:

**Agent trends** — line charts over last 10-50 sessions:
- avg_pressure, max_pressure, error_count, total_cost per session

**Tool stats** — usage histogram across all sessions

**Session comparison** — side-by-side metrics picker for any two sessions

**Mirror effectiveness:**
- Injection success rate over time
- Pattern learning curve (patterns created vs pruned)

**Threshold performance:**
- False positive rate actual vs target
- Threshold adjustment history

---

## Visual Design

- **Theme:** Black (#0a0a0a) + pink (#ff2d78) — existing SOMA brand
- **Font:** SF Mono / Cascadia Code / Fira Code / monospace
- **Animations:** Smooth Chart.js transitions, mode change color morphs, toast slide-in/out
- **Prediction cone:** Dashed area on pressure chart showing predicted future
- **Agent graph:** Interactive, draggable nodes, pulsing trust edges
- **Empty states:** Helpful text explaining what to do ("Run `soma setup` to start monitoring")
- **Keyboard shortcuts:** 1-6 for tabs, Ctrl+K search, ? help overlay, Esc close

## SSE Event Types

| Event | Payload | Frequency |
|-------|---------|-----------|
| `agents` | Full agent list with vitals | Every N seconds |
| `budget` | Budget health, spent, limits | Every N seconds |
| `alert` | Mode change, escalation, circuit breaker | On occurrence |
| `reflex` | Reflex trigger event | On occurrence |
| `finding` | New finding detected | On occurrence |
| `rca` | New RCA diagnosis | On occurrence |

---

## Backend API Endpoints

### Existing (keep, refactor)
- `GET /api/agents` — agent list
- `GET /api/agent/{id}` — agent detail
- `GET /api/agent/{id}/trajectory` — pressure trajectory
- `GET /api/agent/{id}/actions` — recent actions
- `GET /api/agent/{id}/quality` — quality report
- `GET /api/config` — parsed config
- `GET /api/budget` — budget health
- `GET /api/audit` — audit tail
- `GET /api/sessions` — session list
- `GET /api/overview` — combined overview data
- `PUT /api/config` — save config
- `PATCH /api/settings/*` — granular config updates

### New endpoints
- `GET /api/stream` — SSE event stream
- `GET /api/agent/{id}/reflexes` — reflex trigger history
- `GET /api/agent/{id}/rca` — current + past RCA diagnoses
- `GET /api/agent/{id}/mirror` — mirror pattern DB + effectiveness stats
- `GET /api/agent/{id}/context` — context control state (tools available, retention %)
- `GET /api/agent/{id}/session-memory` — similar session match
- `GET /api/agent/{id}/capacity` — session capacity from planner.py
- `GET /api/agent/{id}/circuit-breaker` — circuit breaker state
- `GET /api/agent/{id}/scope` — scope drift detail
- `GET /api/subagents/{parent_id}` — subagent matrix + cascade risk
- `GET /api/analytics/trends/{agent_id}` — cross-session trends
- `GET /api/analytics/tools/{agent_id}` — tool stats
- `GET /api/policies` — policy rule catalog
- `POST /api/policies` — add rule
- `DELETE /api/policies/{rule_name}` — delete rule
- `GET /api/sessions/{id}/report` — rendered session report
- `GET /api/sessions/{id}/record` — full SessionRecord
- `GET /api/threshold-tuner/status` — current vs optimal thresholds
