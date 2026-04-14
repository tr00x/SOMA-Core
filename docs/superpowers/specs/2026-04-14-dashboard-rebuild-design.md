# SOMA Dashboard Rebuild — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Approach:** Clean rebuild (not refactor), data-first strategy

## Problem

Current dashboard (v0.2, ~6700 LOC) has critical issues:
- `_cleanup_old_agents(keep=2)` deletes all sessions except 2 most recent
- `_get_session_agent_id()` generates opaque `cc-{ppid}` names
- `_clear_session_files()` destroys subagent data (35/45 sessions empty)
- Monolithic app.py (1823 lines), half of endpoints duplicate each other
- No WebSocket (polling only), no deep linking, no drill-down
- Previous rebuild failed because UI was built before understanding data model

## Strategy: Data-First

Build bottom-up: data layer (tested) → API (tested) → UI. Each layer verified before next.

## Tech Stack

- **Backend:** FastAPI (stays), modular routes, WebSocket
- **Frontend:** Preact + HTM (CDN, no build step, no Node.js dependency)
- **Charts:** Chart.js (stays)
- **Router:** preact-router (~1KB)
- **Theme:** Black and pink (`--bg: #0a0a0a`, `--accent: #ff2d7b`)

## Data Sources

| Source | What | Updated by |
|--------|------|-----------|
| `~/.soma/state.json` | Live agent state (pressure, vitals, action_count, level) | `save_state()` every tool call |
| `~/.soma/analytics.db` | Historical session data | `post_tool_use` hook |
| `~/.soma/circuit_{agent_id}.json` | Guidance v2 state (escalation, throttle, dominant_signal) | `pre_tool_use` hook |
| `~/.soma/archive/{agent_id}/` | Archived session data (NEW) | `_cleanup_old_agents()` |

## Core Fixes (Prerequisites)

### 1. `_cleanup_old_agents` → archive instead of delete
Move session files to `~/.soma/archive/{agent_id}/` instead of deleting. Data layer reads both active and archive.

### 2. `_get_session_agent_id` → human-readable names
Format: `{project_name} #{sequence}` (e.g. `SOMA-Core #3`). Project name from cwd. Sequence incremented in analytics.db.

### 3. `_clear_session_files` → archive instead of rm
Same data, `mv` instead of `rm`.

## Data Layer (`src/soma/dashboard/data.py`)

Single source of truth for all dashboard data. 19 typed functions:

### Live agents
- `get_live_agents() -> list[AgentSnapshot]` — active agents from state.json + guidance from circuit files
- `get_agent_timeline(agent_id) -> list[ActionEvent]` — action timeline

### Sessions
- `get_all_sessions() -> list[SessionSummary]` — ALL sessions from analytics.db (not just 2)
- `get_session_detail(session_id) -> SessionDetail` — full session for deep link

### Overview
- `get_overview_stats() -> OverviewStats` — total actions, avg pressure, top signals
- `get_activity_heatmap(agent_id) -> list[HeatmapCell]` — hour x day heatmap

### Guidance v2
- `get_audit_log(agent_id) -> list[AuditEntry]` — guidance audit entries
- `get_findings(agent_id) -> list[Finding]` — quality, patterns, predictions, RCA

### Analytics
- `get_pressure_history(agent_id) -> list[PressurePoint]` — pressure over time for charts
- `get_prediction(agent_id) -> Prediction` — PressurePredictor forecast
- `get_baselines(agent_id) -> dict[str, float]` — EMA baselines for chart overlay
- `get_tool_stats(agent_id) -> list[ToolStat]` — tool usage count + error rate per tool

### System
- `get_budget_status() -> BudgetSnapshot` — MultiBudget tokens/cost_usd
- `get_config() -> dict` — soma.toml current config
- `update_config(patch) -> dict` — write config changes
- `get_quality(agent_id) -> QualitySnapshot` — write ratio, test signals
- `get_fingerprint(agent_id) -> FingerprintSnapshot` — behavioral patterns/anomalies
- `get_agent_graph() -> GraphSnapshot` — PressureGraph agent dependencies
- `get_learning_state(agent_id) -> LearningSnapshot` — adaptive thresholds, intervention outcomes
- `export_session(session_id, format) -> bytes` — CSV/JSON export

### Agent naming
Data layer resolves `cc-{ppid}` → human-readable name. Logic: project name from cwd (last path segment) + sequence number.

## API Layer

### Structure (replaces monolithic app.py)

```
src/soma/dashboard/
  app.py          — FastAPI factory, middleware, static mount (~50 lines)
  data.py         — 19 functions (single source of truth)
  ws.py           — WebSocket manager (broadcast diffs)
  routes/
    agents.py     — GET /api/agents, GET /api/agents/{id}, GET /api/agents/{id}/timeline
    sessions.py   — GET /api/sessions, GET /api/sessions/{id}
    overview.py   — GET /api/overview, GET /api/heatmap
    guidance.py   — GET /api/agents/{id}/audit, GET /api/agents/{id}/guidance
    analytics.py  — GET /api/agents/{id}/pressure-history, GET /api/agents/{id}/predictions
    config.py     — GET /api/config, PATCH /api/config
    budget.py     — GET /api/budget
    export.py     — GET /api/sessions/{id}/export?format=csv|json
    quality.py    — GET /api/agents/{id}/quality, GET /api/agents/{id}/fingerprint
    graph.py      — GET /api/graph
    learning.py   — GET /api/agents/{id}/learning
    baselines.py  — GET /api/agents/{id}/baselines
    findings.py   — GET /api/agents/{id}/findings
    tools.py      — GET /api/agents/{id}/tools
```

Each route file: validate params → call data.py → return. No business logic in routes.

### WebSocket (`ws.py`)
- Client connects to `ws://host/ws`
- Server polls state.json every 1s, pushes diffs to subscribed clients
- Client subscribes to specific agent: `{"subscribe": "agent_id"}`
- Message format: `{"type": "agents_update", "data": {...}}`
- Fallback: if WS disconnects, frontend falls back to HTTP polling every 2s

### Cross-cutting
- CORS middleware (localhost access)
- Graceful shutdown (clean WS disconnect)
- All non-API paths serve index.html (SPA routing)

## Frontend

### Component Structure

```
static/
  index.html           — CDN imports, router mount
  css/
    theme.css          — black+pink theme, CSS variables
    components.css     — cards, charts, tables
  js/
    app.js             — router, WS init, global store
    store.js           — reactive state: agents, sessions, config, ws status
    ws.js              — WebSocket client + auto-reconnect + fallback polling
    components/
      AgentCard.js     — pressure bar, vitals, mode badge, escalation/throttle
      PressureChart.js — Chart.js line + baseline overlay
      SessionList.js   — all sessions, sort, filter
      SessionDetail.js — timeline, actions, findings
      Overview.js      — aggregates, heatmap, budget, agent graph
      AuditLog.js      — guidance audit, filter by type
      ToolStats.js     — bar chart usage + error rate
      Settings.js      — soma.toml editor (all 34 params)
      Findings.js      — quality, patterns, RCA, predictions
      AgentGraph.js    — PressureGraph visualization (SVG)
      BudgetGauge.js   — tokens/cost gauges
      ExportButton.js  — CSV/JSON download
    pages/
      OverviewPage.js  — / route
      AgentPage.js     — /agents/{id} — full agent detail
      SessionPage.js   — /sessions/{id}
      SettingsPage.js  — /settings
```

### UX Features
- **Ctrl+K** global search (agents, sessions, findings, audit)
- **Keyboard shortcuts** — tab navigation, R for refresh
- **Loading states** — skeleton loaders
- **Error boundary** — component-level error catch
- **Empty states** — onboarding message when SOMA not running
- **Mobile** — responsive 1/2/3 column grid
- **Reconnect banner** — shown when WebSocket disconnects

### Deep Linking
- `/` → overview
- `/agents/{id}` → agent detail
- `/sessions/{id}` → session detail
- `/settings` → config editor
- Backend serves index.html for all non-API paths

### Visual Design
- Black+pink theme: `--bg: #0a0a0a`, `--accent: #ff2d7b`, `--card-bg: #141414`
- Agent card border-left color by mode (green/yellow/orange/red)
- Guidance badge on cards when escalation > 0
- Favicon: existing `favicon.svg`

## Implementation Phases

### Phase 1: Core Fixes + Data Layer
- 3 core fixes (_cleanup_old_agents, _get_session_agent_id, _clear_session_files)
- `data.py` — all 19 functions
- Tests with real fixture files (state.json, analytics.db with test data)
- **Done when:** `pytest tests/test_dashboard_data.py` — 100% green, every field verified

### Phase 2: API + WebSocket
- `app.py` factory, all route modules, `ws.py`
- Tests via httpx TestClient + WebSocket test client
- **Done when:** every endpoint returns correct data from data layer, WS pushes updates

### Phase 3: Frontend — Skeleton
- index.html, router, store, WS client, theme CSS
- Overview page + AgentCard (most important component)
- **Done when:** open browser, see real agents with correct data, WS updates live

### Phase 4: Frontend — All Pages
- Agent detail, session detail, settings, all remaining components
- Search, keyboard shortcuts, empty states, mobile
- **Done when:** all routes work, all data correct, deep links work
