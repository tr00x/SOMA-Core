# SOMA Dashboard — Actionable Controls Spec

**Date:** 2026-04-14
**Status:** Ready for implementation
**Depends on:** Dashboard rebuild (complete)

## Problem

Dashboard is read-only. User can only observe. No ability to act on what they see. A monitoring tool without controls is a TV — you watch but can't change the channel.

## Principle

Every piece of data shown should have an action attached. If you show pressure is high — let me reset baseline. If mode is WARN — let me override to OBSERVE. If a tool is throttled — let me unthrottle it.

## Actions by Page

### Overview Page

| Where | Action | API | Effect |
|-------|--------|-----|--------|
| Agent card | "Reset Baseline" button | POST /api/agents/{id}/reset | Reset pressure baseline to current values |
| Agent card | "Switch Mode" dropdown | POST /api/agents/{id}/mode | OBSERVE/GUIDE/WARN/BLOCK override |
| Budget section | "Adjust Limit" | PATCH /api/config | Edit tokens/cost_usd limits inline |
| Session row | "Export" icon | GET /api/sessions/{id}/export | Download CSV/JSON |
| Header | "Pause SOMA" toggle | POST /api/control/pause | Disable hooks temporarily |

### Agent Detail Page

| Where | Action | API | Effect |
|-------|--------|-----|--------|
| Header | "Reset Baseline" button | POST /api/agents/{id}/reset | Clear learned baselines |
| Header | "Force Mode" dropdown | POST /api/agents/{id}/mode | Override auto mode |
| Guidance panel | "Clear Escalation" | POST /api/agents/{id}/clear-escalation | Reset escalation to 0 |
| Guidance panel | "Unthrottle" button | POST /api/agents/{id}/unthrottle | Remove tool throttle |
| Tool stats | "Block Tool" toggle | PATCH /api/config | Add tool to blocked list |
| Timeline | "Flag Action" | POST /api/agents/{id}/flag | Mark action for review |

### Session Detail Page

| Where | Action | API | Effect |
|-------|--------|-----|--------|
| Header | "Export JSON" / "Export CSV" | GET /api/sessions/{id}/export | Download |
| Header | "Delete Session" | DELETE /api/sessions/{id} | Remove from analytics.db |
| Actions list | "Replay" button | POST /api/sessions/{id}/replay | Re-run through engine (future) |

### Settings Page

Current settings page is a raw config dump. Redesign:

| Section | What to show | Controls |
|---------|-------------|----------|
| **Mode** | Current mode (observe/guide/reflex) | 3-button radio toggle, applies immediately |
| **Sensitivity** | Threshold sliders for GUIDE/WARN/BLOCK | Range inputs (0.0-1.0) with live preview |
| **Budget** | Token limit, cost limit | Number inputs, save button |
| **Hooks** | Enabled hooks list | Toggle switches per hook |
| **Agent Profile** | claude-code/strict/relaxed/autonomous | Dropdown selector |
| **Danger Zone** | Reset all baselines, Clear all sessions, Uninstall | Red buttons with confirmation dialog |

## New Backend Endpoints Needed

```
POST /api/agents/{id}/reset          — reset baseline for agent
POST /api/agents/{id}/mode           — override mode {mode: "OBSERVE"}
POST /api/agents/{id}/clear-escalation — reset guidance escalation
POST /api/agents/{id}/unthrottle     — remove tool throttle
POST /api/control/pause              — pause/resume SOMA hooks
POST /api/control/resume             — resume SOMA hooks
DELETE /api/sessions/{id}            — delete session from analytics.db
```

## Implementation Plan

### Phase 1: Quick Wins (same session)
- Settings page redesign with grouped sections + toggle/slider controls
- Export buttons on session cards
- Mode switcher on agent cards

### Phase 2: Agent Controls
- Reset baseline, clear escalation, unthrottle
- Backend POST endpoints in new `routes/control.py`

### Phase 3: System Controls
- Pause/resume SOMA
- Danger zone (reset all, clear sessions)

## Visual Design

- Action buttons: ghost style (transparent bg, border on hover), accent color on primary actions
- Confirmation dialogs: modal overlay for destructive actions (delete, reset all)
- Inline editing: click value → input field → Enter to save, Esc to cancel
- Toggle switches: iOS-style, accent color when active
- Sliders: thin track, large thumb, live value display
