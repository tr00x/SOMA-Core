/**
 * AuditLog — Scrollable list of guidance audit events.
 */

import { html } from 'htm/preact';

function typeColor(type) {
  switch (String(type).toLowerCase()) {
    case 'block': return 'tag-high';
    case 'warn': return 'tag-medium';
    case 'guide': return 'tag-low';
    case 'escalation': return 'tag-medium';
    case 'reset': return 'tag-info';
    default: return 'tag-info';
  }
}

export function AuditLog({ events = [] }) {
  if (!events.length) {
    return html`
      <div class="empty-state" style="padding:20px">
        <div class="empty-state-title">No audit events</div>
        <div class="empty-state-text">Guidance events appear when the engine takes action.</div>
      </div>
    `;
  }

  return html`
    <div class="scroll-panel" style="max-height:350px" role="list" aria-label="Audit log">
      ${events.map((ev, i) => html`
        <div class="timeline-item" key=${i} role="listitem">
          <span class="time mono">#${ev.action_num ?? i + 1}</span>
          <span class="tag ${typeColor(ev.type)}">${String(ev.type || '--').toUpperCase()}</span>
          ${ev.signal && html`
            <span class="mono" style="color:var(--text-secondary);font-size:0.6875rem">${ev.signal}</span>
          `}
          ${ev.old_mode && ev.new_mode && html`
            <span class="mono" style="font-size:0.6875rem;color:var(--text-tertiary)">
              ${ev.old_mode} \u2192 ${ev.new_mode}
            </span>
          `}
          ${ev.reason && html`
            <span style="color:var(--text-secondary);font-size:0.75rem;flex:1" class="truncate">
              ${ev.reason}
            </span>
          `}
        </div>
      `)}
    </div>
  `;
}

export default AuditLog;
