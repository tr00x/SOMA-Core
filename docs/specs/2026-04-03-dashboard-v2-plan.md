# SOMA Dashboard v2 — Implementation Plan

**Spec:** `2026-04-03-dashboard-v2-design.md`
**Approach:** Parallel subagents, wave-based execution

---

## Wave 1: Foundation (parallel)

### Agent A: Backend refactor + new endpoints
- Refactor app.py: clean up duplication, organize by domain
- Add new endpoints: reflexes, rca, mirror, context, session-memory, capacity, circuit-breaker, scope, subagents, analytics, policies, threshold-tuner, session record/report
- Add SSE endpoint (sse.py): event stream with configurable refresh
- Keep all existing endpoints working (backward compat during transition)

### Agent B: Frontend shell + module system
- Create index.html shell (~150 lines): header, nav with 6 tabs, tab containers
- Create style.css: extract all CSS from current index.html, add new animations
- Create app.js: Alpine init, tab routing, keyboard shortcuts, shared state, toast system
- Create api.js: all fetch functions + SSE EventSource connection + fallback polling
- Create charts.js: Chart.js lifecycle wrappers (create, update, destroy)

**Wave 1 gate:** Backend serves data, frontend shell loads and connects via SSE.

---

## Wave 2: Core tabs (parallel)

### Agent C: Overview tab
- overview.html + overview.js
- Status bar: max pressure, worst mode, budget health, capacity, cascade risk
- Agent cards: pressure + sparkline + mode + quality + phase + circuit breaker + half-life
- RCA strip, predictions alert strip
- Findings cards, patterns section
- Sidebar: budget gauges, burn rate, tool usage top-5, 24h heatmap

### Agent D: Agent Deep Dive tab
- deep-dive.html + deep-dive.js
- All 10 rows from spec: header, charts, signal breakdown, intelligence, reflexes/RCA, mirror/context, session memory/scope, graph, subagents, history
- Agent graph visualization (Canvas-based, interactive)
- Prediction cone on pressure chart

### Agent E: Settings tab
- settings.html + settings.js
- All 10 sub-tabs: mode, thresholds, weights, budget, graph, vitals, hooks, agents, policies, raw TOML
- Form controls, save/reset, toast feedback

**Wave 2 gate:** All three core tabs render with real data from API.

---

## Wave 3: Remaining tabs (parallel)

### Agent F: Logs tab
- logs.html + logs.js
- Filters: agent, text, mode, event type, date range
- Table with color coding, reflex_kind column, policy fires
- CSV export, SSE auto-refresh

### Agent G: Sessions tab
- sessions.html + sessions.js
- Enriched session list with mode_transitions, phase_sequence, fingerprint_divergence
- Session detail: trajectory chart, phase timeline, tool distribution, similar sessions, report
- Cross-session trends chart
- Session JSON export

### Agent H: Analytics tab
- analytics.html + analytics.js
- Agent trends (line charts over sessions)
- Tool stats histogram
- Session comparison picker
- Mirror effectiveness, threshold performance

**Wave 3 gate:** All 6 tabs functional with real data.

---

## Wave 4: Polish + Tests (parallel)

### Agent I: Integration tests
- pytest tests for all new backend endpoints
- Test SSE stream connection and events
- Test config save/load roundtrip
- Test edge cases: no agents, empty sessions, missing files

### Agent J: Visual polish + Playwright E2E
- Animations: pressure transitions, mode change morphs, toast system
- Empty states for all tabs
- Keyboard shortcuts verification
- Playwright tests: load each tab, verify data renders, click interactions
- Screenshot capture for README

**Wave 4 gate:** All tests pass, all tabs render correctly in Playwright.

---

## Execution Rules

1. Each agent gets the full spec + relevant section of this plan
2. Agents write to their assigned files only — no conflicts
3. Backend agent (A) must complete before tab agents (C-H) start fetching data
4. Frontend shell agent (B) must complete before tab agents plug in
5. Wave gates are hard — next wave starts only when previous passes
6. All agents follow existing code style (CLAUDE.md conventions)
7. No new npm/node dependencies — CDN only
8. Dark theme (black + pink) throughout
