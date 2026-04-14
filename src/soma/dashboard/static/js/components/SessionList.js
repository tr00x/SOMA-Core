/**
 * SessionList — Compact list of recent sessions.
 */

import { html } from 'htm/preact';
import { route } from 'preact-router';

function modeClass(mode) {
  if (!mode) return 'mode-observe';
  const m = String(mode).toLowerCase();
  if (m === 'block') return 'mode-block';
  if (m === 'warn') return 'mode-warn';
  if (m === 'guide') return 'mode-guide';
  return 'mode-observe';
}

function relativeTime(ts) {
  if (!ts) return '';
  const diff = Date.now() - ts * 1000;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatCost(c) {
  if (c == null || c === 0) return '--';
  if (c < 0.01) return `$${c.toFixed(4)}`;
  return `$${c.toFixed(2)}`;
}

export function SessionList({ sessions = [], limit = 5, showAll = false }) {
  const items = showAll ? sessions : sessions.slice(0, limit);

  if (!items.length) {
    return html`
      <div class="empty-state" style="padding:24px">
        <div class="empty-state-title">No sessions recorded</div>
        <div class="empty-state-text">Sessions appear when agents process actions.</div>
      </div>
    `;
  }

  return html`
    <div class="scroll-panel" role="list" aria-label="Sessions list">
      ${items.map(s => html`
        <div class="timeline-item"
             key=${s.session_id}
             onClick=${() => route(`/sessions/${s.session_id}`)}
             onKeyDown=${(e) => (e.key === 'Enter' || e.key === ' ') && route(`/sessions/${s.session_id}`)}
             role="listitem"
             tabindex="0"
             style="cursor:pointer">
          <span class="time">${relativeTime(s.start_time || s.end_time)}</span>
          <span class="tool-name truncate" style="flex:1">${s.display_name || s.agent_id || s.session_id}</span>
          <span class="mono" style="color:var(--text-secondary);min-width:48px;text-align:right">
            ${s.action_count ?? 0} acts
          </span>
          <span class="pressure-val" style="color:${pressureColor(s.avg_pressure)}">
            ${s.avg_pressure != null ? `${Math.round(s.avg_pressure * 100)}%` : '--'}
          </span>
          ${s.mode && html`
            <span class="mode-badge ${modeClass(s.mode)}" style="font-size:0.625rem;padding:2px 6px">
              <span class="badge-dot" style="width:4px;height:4px"></span>
              ${String(s.mode).toUpperCase()}
            </span>
          `}
        </div>
      `)}

      ${!showAll && sessions.length > limit && html`
        <div style="padding:8px 12px;text-align:center">
          <a href="/sessions"
             onClick=${(e) => { e.preventDefault(); route('/sessions'); }}
             style="font-size:0.75rem;color:var(--text-secondary)">
            View all ${sessions.length} sessions
          </a>
        </div>
      `}
    </div>
  `;
}

function pressureColor(p) {
  if (p == null) return 'var(--text-tertiary)';
  if (p >= 0.75) return 'var(--mode-block)';
  if (p >= 0.5) return 'var(--mode-warn)';
  if (p >= 0.25) return 'var(--mode-guide)';
  return 'var(--mode-observe)';
}

export default SessionList;
