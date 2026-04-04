# SOMA Dashboard v2 — Visual Design System

**Date:** 2026-04-03
**Companion to:** `2026-04-03-dashboard-v2-design.md`

---

## 1. Design Tokens

### Primitive Tokens (raw values)

```css
/* Colors */
--color-black-950: #0a0a0a;
--color-black-900: #111111;
--color-black-800: #1a1a1a;
--color-black-700: #1e1e1e;
--color-black-600: #2a2a2a;
--color-black-500: #333333;
--color-black-400: #444444;
--color-black-300: #555555;
--color-black-200: #666666;
--color-black-100: #999999;

--color-pink-500: #ff2d78;
--color-pink-400: #ff4d90;
--color-pink-300: #ff6ba6;
--color-pink-200: #ff8dbb;
--color-pink-100: #ffb3d4;
--color-pink-glow: rgba(255, 45, 120, 0.12);
--color-pink-glow-strong: rgba(255, 45, 120, 0.3);

--color-green-500: #00ff88;
--color-green-400: #33ff9f;
--color-green-glow: rgba(0, 255, 136, 0.5);

--color-yellow-500: #ffaa00;
--color-orange-500: #ff8c00;
--color-red-500: #ff4444;
--color-red-glow: rgba(255, 68, 68, 0.5);

--color-white: #ffffff;
--color-white-05: rgba(255, 255, 255, 0.05);
--color-white-10: rgba(255, 255, 255, 0.1);

/* Spacing (4px grid) */
--space-0: 0;
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;

/* Typography */
--font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

--text-2xs: 9px;
--text-xs: 11px;
--text-sm: 12px;
--text-base: 14px;
--text-lg: 16px;
--text-xl: 20px;
--text-2xl: 24px;
--text-3xl: 32px;
--text-4xl: 40px;

--leading-tight: 1.2;
--leading-normal: 1.5;
--leading-relaxed: 1.75;

--weight-normal: 400;
--weight-medium: 500;
--weight-semibold: 600;
--weight-bold: 700;

/* Borders */
--radius-sm: 4px;
--radius-md: 6px;
--radius-lg: 8px;
--radius-xl: 12px;
--radius-full: 9999px;

/* Shadows */
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 8px rgba(0, 0, 0, 0.3);
--shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.4);
--shadow-glow-pink: 0 0 12px var(--color-pink-glow);
--shadow-glow-green: 0 0 4px var(--color-green-glow);
--shadow-glow-red: 0 0 4px var(--color-red-glow);

/* Animation */
--duration-fast: 150ms;
--duration-normal: 200ms;
--duration-slow: 300ms;
--easing-out: cubic-bezier(0.16, 1, 0.3, 1);
--easing-in: cubic-bezier(0.7, 0, 0.84, 0);
--easing-in-out: cubic-bezier(0.4, 0, 0.2, 1);

/* Z-index scale */
--z-base: 0;
--z-dropdown: 10;
--z-sticky: 20;
--z-fixed: 30;
--z-overlay: 40;
--z-modal: 50;
--z-toast: 60;
```

### Semantic Tokens (purpose aliases)

```css
/* Surfaces */
--surface-base: var(--color-black-950);       /* Page background */
--surface-card: var(--color-black-900);        /* Cards, panels */
--surface-elevated: var(--color-black-800);    /* Hover states, active cards */
--surface-overlay: rgba(0, 0, 0, 0.6);        /* Modal backdrop */

/* Borders */
--border-default: var(--color-black-700);
--border-hover: var(--color-black-400);
--border-active: var(--color-pink-500);
--border-error: var(--color-red-500);

/* Text */
--text-primary: var(--color-white);
--text-secondary: #bbb;
--text-tertiary: var(--color-black-200);       /* #666 */
--text-disabled: var(--color-black-300);       /* #555 */
--text-accent: var(--color-pink-500);
--text-success: var(--color-green-500);
--text-warning: var(--color-yellow-500);
--text-error: var(--color-red-500);

/* Interactive */
--interactive-default: var(--color-pink-500);
--interactive-hover: var(--color-pink-400);
--interactive-active: var(--color-pink-300);
--interactive-focus-ring: var(--color-pink-glow-strong);

/* Status / Mode colors */
--mode-observe: var(--color-green-500);
--mode-guide: var(--color-yellow-500);
--mode-warn: var(--color-orange-500);
--mode-block: var(--color-red-500);

/* Pressure gradient stops */
--pressure-0: var(--color-green-500);     /* 0% */
--pressure-40: var(--color-yellow-500);   /* 40% */
--pressure-65: var(--color-orange-500);   /* 65% */
--pressure-100: var(--color-red-500);     /* 100% */
```

### Component Tokens

```css
/* Card */
--card-bg: var(--surface-card);
--card-border: var(--border-default);
--card-border-hover: var(--color-pink-500) / 30%;
--card-border-selected: var(--color-pink-500);
--card-shadow-selected: var(--shadow-glow-pink);
--card-radius: var(--radius-lg);
--card-padding: var(--space-4);

/* Button - primary */
--btn-primary-bg: var(--color-pink-500);
--btn-primary-bg-hover: var(--color-pink-400);
--btn-primary-text: var(--color-white);
--btn-primary-radius: var(--radius-md);
--btn-primary-padding: var(--space-2) var(--space-4);
--btn-primary-height: 36px;

/* Button - ghost */
--btn-ghost-bg: transparent;
--btn-ghost-bg-hover: var(--color-white-05);
--btn-ghost-text: var(--text-tertiary);
--btn-ghost-text-hover: var(--text-secondary);
--btn-ghost-border: var(--border-default);

/* Input */
--input-bg: var(--surface-base);
--input-border: var(--border-default);
--input-border-focus: var(--color-pink-500);
--input-text: var(--text-primary);
--input-placeholder: var(--text-disabled);
--input-radius: var(--radius-md);
--input-height: 44px;    /* Touch-friendly minimum */

/* Badge (mode badges) */
--badge-radius: var(--radius-full);
--badge-padding: var(--space-1) var(--space-2);
--badge-font-size: var(--text-2xs);
--badge-font-weight: var(--weight-bold);

/* Toast */
--toast-bg: var(--surface-card);
--toast-border: var(--border-default);
--toast-radius: var(--radius-lg);
--toast-shadow: var(--shadow-lg);

/* Tab */
--tab-height: 40px;
--tab-indicator-color: var(--color-pink-500);
--tab-indicator-height: 2px;
--tab-text-active: var(--color-pink-500);
--tab-text-inactive: var(--text-tertiary);
--tab-text-hover: var(--text-secondary);

/* Sidebar */
--sidebar-width: 280px;
--sidebar-bg: var(--surface-card);
--sidebar-border: var(--border-default);

/* Gauge */
--gauge-track-bg: var(--color-white-05);
--gauge-track-height: 4px;
--gauge-track-radius: var(--radius-full);

/* Scrollbar */
--scrollbar-width: 5px;
--scrollbar-track: transparent;
--scrollbar-thumb: var(--color-black-600);
--scrollbar-thumb-hover: var(--color-black-400);
```

---

## 2. Typography System

### Type Scale

| Role | Font | Size | Weight | Line Height | Use |
|------|------|------|--------|-------------|-----|
| Display | mono | 40px | 700 | 1.2 | Pressure big number on Deep Dive |
| Heading 1 | mono | 24px | 700 | 1.2 | Section titles |
| Heading 2 | mono | 20px | 600 | 1.3 | Card titles, sub-sections |
| Heading 3 | mono | 16px | 600 | 1.4 | Panel headers |
| Body | mono | 14px | 400 | 1.5 | Default text |
| Body small | mono | 12px | 400 | 1.5 | Secondary info, table cells |
| Caption | mono | 11px | 400 | 1.4 | Timestamps, hints, labels |
| Micro | mono | 9px | 400 | 1.3 | Keyboard shortcuts, badges, sparkline labels |

### Rules
- ALL text is monospace (this is a terminal-aesthetic monitoring tool)
- Numbers use `font-variant-numeric: tabular-nums` for alignment in tables/counters
- Minimum body text: 12px (11px only for captions, 9px only for micro elements)
- Line length: max 75ch for readable text blocks
- Heading hierarchy: use size + weight, never skip levels
- Truncation: ellipsis + title attribute for full text on hover

---

## 3. Layout System

### Grid
- **Desktop (>=1024px):** Main content area + optional sidebar (280px). Content uses CSS Grid with auto-fit columns.
- **Tablet (768-1023px):** Full width, sidebar collapses to bottom section. 2-column grid for cards.
- **Mobile (<768px):** Single column stack. Tab bar scrollable horizontally.

### Breakpoints
| Name | Min width | Columns | Container padding |
|------|-----------|---------|-------------------|
| Mobile | 0 | 1 | 16px |
| Tablet | 768px | 2 | 24px |
| Desktop | 1024px | 3+ sidebar | 24px |
| Wide | 1440px | 4+ sidebar | 32px |

### Spacing Rules
- **Between cards:** 12px (gap-3)
- **Card internal padding:** 16px (p-4)
- **Between sections:** 24px (gap-6)
- **Header height:** 48px (sticky)
- **Tab bar height:** 40px (sticky below header)
- **Content top padding:** 12px below tab bar

### Z-index Layers
| Layer | Z-index | Elements |
|-------|---------|----------|
| Base | 0 | Page content, cards |
| Dropdown | 10 | Agent selector dropdown |
| Sticky | 20 | Header, tab navigation |
| Fixed | 30 | Sidebar on desktop |
| Overlay | 40 | Search overlay, agent overlay |
| Modal | 50 | Help modal, confirm dialogs |
| Toast | 60 | Toast notifications |

---

## 4. Component Specs

### Agent Card

```
┌─────────────────────────────────────────┐
│ cc-main-abc123          [OBSERVE] badge  │  -- header: agent name (mono, 12px, bold, white) + mode badge
│                                          │
│  23%                                     │  -- pressure: 24px bold, color from pressure gradient
│  ▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  -- pressure bar: 4px height, gradient fill
│                                          │
│  U: 0.12  D: 0.08  E: 0.03              │  -- vitals: 3-col, 11px, tertiary color
│  Q: A     P: impl   HL: ●               │  -- quality + phase + half-life dot (green/yellow/red)
│  ▁▂▃▃▄▅▄▃▂▃▄▅▆▅▄▃▂▃                    │  -- sparkline: 30 points, 24px height, pink line
└─────────────────────────────────────────┘

States:
- Default: border-default, bg card
- Hover: border pink/30%, transition 200ms
- Selected: border pink, glow shadow
- Click → navigates to Deep Dive

Size: min-width 260px, flex-1, max-width 400px
```

### Mode Badge

| Mode | Background | Text | Example |
|------|-----------|------|---------|
| OBSERVE | green-500/15% | green-500 | subtle green tint |
| GUIDE | yellow-500/15% | yellow-500 | subtle yellow tint |
| WARN | orange-500/15% | orange-500 | subtle orange tint |
| BLOCK | red-500/15% | red-500 | subtle red tint |

Font: 9px, bold, uppercase, letter-spacing 0.05em
Padding: 4px 8px, border-radius full

### Pressure Gauge (big number)

```
 23%
```
- Font: mono, 24px (card) or 40px (deep dive), bold
- Color: interpolated from pressure gradient (0%=green → 40%=yellow → 65%=orange → 100%=red)
- Below: 4px height bar with gradient fill, width = pressure %
- Transition: color and width animate over 500ms

### Chart Components

**Pressure Timeline (Chart.js line)**
- Background: transparent
- Grid: #1e1e1e, 1px
- Axis labels: #666, 11px
- Line: pink-500, 2px width, no fill
- Threshold lines: dashed, 1px — green (guide), yellow (warn), red (block)
- Prediction cone: pink-200/20% fill, pink-300 dashed border
- Point: no visible points (too many), hover shows tooltip
- Tooltip: dark card bg, white text, shows pressure %, timestamp, mode
- Animation: DISABLED (prevents canvas context errors)

**Vitals Radar (Chart.js radar)**
- 6 axes: uncertainty, drift, error_rate, cost, goal_coherence, context_usage
- Current values: pink-500 fill with 20% opacity, pink border
- Baseline overlay: white/10% fill, white/30% border (dashed)
- Labels: 11px, #666
- Grid: concentric circles, #1e1e1e
- Scale: 0-1 for most, custom for cost/tokens

**Sparkline (inline mini chart)**
- Width: fill parent container
- Height: 24px
- Line: pink-500, 1.5px
- No axes, no labels, no grid
- Hover: no interaction (display only)
- Points: last 30 trajectory readings

**Bar Charts (horizontal)**
- Bar height: 20px
- Bar gap: 4px
- Bar color: pink-500 (or signal-specific colors)
- Background track: white/5%
- Label: left-aligned, 12px, #999
- Value: right-aligned, 12px, white
- Border radius: 3px

**Heatmap (24h activity)**
- Grid: 24 cells (one per hour)
- Cell size: 28x28px with 2px gap
- Color: scale from black-800 (0) → pink-500 (max)
- Hover: tooltip with hour, count, errors, avg_pressure
- Border radius: 3px per cell

### Status Bar

```
┌──────────────────────────────────────────────────────────────────────────┐
│  P: 23%  │  OBSERVE  │  Budget: 87%  │  Agents: 3  │  Cap: ~43 actions │
└──────────────────────────────────────────────────────────────────────────┘
```
- Background: card color
- Height: 36px
- Items separated by subtle vertical dividers (#1e1e1e)
- Text: 12px mono
- Values: white, labels: #666
- Pressure value colored by gradient
- Mode badge inline (same as card badge)

### Table (Logs, Actions)

- Header: #666 text, 11px, uppercase, border-bottom #1e1e1e
- Rows: alternating bg (transparent / white-05), 36px height
- Text: 12px mono
- Hover: row bg → white/5%
- Error rows: left 3px red border
- Selected row: left 3px pink border
- Columns: left-aligned by default, numbers right-aligned

### Toast Notification

```
┌───────────────────────────────┐
│  ● Mode Change                │  -- dot colored by severity
│  cc-main: OBSERVE → GUIDE     │  -- 12px, secondary text
└───────────────────────────────┘
```
- Position: bottom-left, 16px from edges
- Stack: max 3 visible, newest at bottom
- Enter: slide from left, 300ms ease-out
- Exit: slide to left, 200ms ease-in (exit faster than enter)
- Auto-dismiss: 4 seconds
- Background: card color, border-default, shadow-lg
- Width: 280px max

### Search Overlay

- Full screen overlay: black/60% backdrop with blur(4px)
- Search box: centered, 600px max width, top 20%
- Input: 48px height, 16px font, white text, pink focus border
- Results: below input, card bg, max 5 items
- Each result: icon + title + description, 44px height (touch-friendly)
- Navigate: arrow keys, Enter to select, Esc to close

### Settings Controls

**Slider (range input)**
- Track: 6px height, #2a2a2a bg, 3px radius
- Thumb: 16px circle, pink-500, 2px dark border
- Thumb hover: pink-400
- Progress fill (Firefox): pink-500
- Label: left (name), right (value), both 12px

**Toggle switch**
- Size: 36x20px
- Off: #333 track, white circle
- On: pink-500 track, white circle translated right
- Transition: 200ms ease

**Select dropdown**
- Height: 44px (touch-friendly)
- Background: surface-base
- Border: border-default, pink on focus
- Arrow: chevron icon, #666
- Options: card bg, hover = white/5%

---

## 5. Interaction States

Every interactive element MUST have these states defined:

| State | Visual Change |
|-------|--------------|
| Default | Base styling |
| Hover | Background lightens (white/5%), border lightens, transition 200ms |
| Active/Pressed | Scale 0.98, background darkens slightly, transition 100ms |
| Focus | 2px pink glow ring (box-shadow), visible on keyboard navigation |
| Disabled | Opacity 0.4, cursor not-allowed, no hover/active states |
| Selected | Pink border, pink glow shadow |
| Loading | Pulse animation on skeleton, or spinner replacing content |

### Focus management
- Tab order matches visual order (left→right, top→bottom)
- Focus ring: `box-shadow: 0 0 0 2px rgba(255, 45, 120, 0.3)`
- Focus visible only on keyboard navigation (`:focus-visible`)
- Escape closes any overlay/modal and returns focus to trigger

---

## 6. Animation Rules

| Type | Duration | Easing | Use |
|------|----------|--------|-----|
| Micro (hover, focus) | 150ms | ease-out | State changes |
| Normal (expand, toast) | 200ms | ease-out | Content reveal |
| Complex (overlay, tab) | 300ms | ease-out (enter), ease-in (exit) | Large transitions |
| Data update | 500ms | ease-in-out | Chart value changes, pressure bar |

### Rules
- Exit animations are 60-70% of enter duration
- Transform + opacity only (never animate width/height/top/left)
- Chart.js animations DISABLED globally (prevents requestAnimationFrame race conditions)
- Pressure color transitions use CSS transition on color property
- Respect `prefers-reduced-motion`: disable all non-essential animations
- Max 2 simultaneous animations per view
- Stagger list items by 30ms each on tab switch

---

## 7. Accessibility

### Contrast
- All text meets WCAG AA (4.5:1 minimum)
- Large text (>=18px bold or >=24px): 3:1 minimum
- Status colors (green/yellow/orange/red) always paired with text label or icon — never color-only

### Keyboard
- All interactive elements reachable via Tab
- 1-6 for tab switching
- Ctrl+K for search
- ? for help
- Esc closes overlays
- Arrow keys navigate within lists/dropdowns
- Enter activates focused element

### Screen readers
- `aria-label` on icon-only buttons
- `aria-live="polite"` on toast container
- `role="tablist"` / `role="tab"` / `role="tabpanel"` for tab navigation
- Charts have `aria-label` with text summary of data
- Mode badges include full text (not just color)

### Touch targets
- All clickable elements: minimum 44x44px hit area
- Minimum 8px gap between touch targets
- No hover-only functionality (everything accessible via click/tap)

---

## 8. Empty States

Every section must handle "no data" gracefully:

| Section | Empty state text |
|---------|-----------------|
| Agent cards | "No agents connected. Run `soma setup` to start monitoring." |
| Pressure chart | "Waiting for trajectory data..." (gray dashed line placeholder) |
| Findings | "No findings — all clear." (with green checkmark) |
| Actions feed | "No actions recorded yet." |
| Logs | "No log entries. Actions will appear here as agents work." |
| Sessions | "No past sessions. Session data is saved after each agent run." |
| Analytics | "Not enough session data for trends. Complete 2+ sessions to unlock." |
| Subagents | "No subagent activity detected." |
| RCA | (hidden entirely when no diagnosis) |
| Predictions | (hidden entirely when no escalation predicted) |

Style: centered, #555 text, 14px, optional icon above text.

---

## 9. Data Density Guide

SOMA is a monitoring tool — density matters. Follow Grafana/htop density, not Linear/Notion spacing.

| Area | Density |
|------|---------|
| Overview status bar | HIGH — compact single row, minimal padding |
| Agent cards | MEDIUM — enough to scan quickly, not cluttered |
| Deep Dive charts | LOW — charts need breathing room for readability |
| Deep Dive panels | HIGH — dense info panels, 12px body text, tight spacing |
| Settings | MEDIUM — forms need comfortable spacing for interaction |
| Logs table | HIGH — compact rows (36px), maximize visible rows |
| Sessions list | MEDIUM — scannable but not cramped |

---

## 10. Responsive Behavior

### Mobile (<768px)
- Header: single row, subtitle hidden
- Tabs: horizontal scroll, no keyboard hints
- Agent cards: single column, full width
- Deep Dive: single column stack, charts full width
- Sidebar: collapsed, shown as section below main content
- Settings sub-tabs: horizontal scroll instead of vertical sidebar
- Tables: horizontal scroll with sticky first column

### Tablet (768-1023px)
- Agent cards: 2-column grid
- Deep Dive: 2-column where specified, 1-column for charts
- Sidebar: shown below main content

### Desktop (>=1024px)
- Full layout as designed
- Sidebar visible on right
- Agent cards: 3+ columns auto-fit
