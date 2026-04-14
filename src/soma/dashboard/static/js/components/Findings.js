/**
 * Findings — Cards showing agent findings with priority color coding.
 */

import { html } from 'htm/preact';

function priorityClass(p) {
  if (!p) return '';
  const pl = String(p).toLowerCase();
  if (pl === 'high' || pl === 'critical') return 'priority-high';
  if (pl === 'medium' || pl === 'warning') return 'priority-medium';
  return 'priority-low';
}

function priorityTag(p) {
  if (!p) return 'tag-info';
  const pl = String(p).toLowerCase();
  if (pl === 'high' || pl === 'critical') return 'tag-high';
  if (pl === 'medium' || pl === 'warning') return 'tag-medium';
  return 'tag-low';
}

export function Findings({ findings = [] }) {
  if (!findings.length) {
    return html`
      <div class="empty-state" style="padding:20px">
        <div class="empty-state-title">No findings</div>
        <div class="empty-state-text">
          Findings are generated when the engine detects patterns, anomalies, or quality issues.
        </div>
      </div>
    `;
  }

  return html`
    <div role="list" aria-label="Findings">
      ${findings.map((f, i) => html`
        <div class="finding-card ${priorityClass(f.priority)}" key=${i} role="listitem">
          <div class="finding-title">${f.title || 'Untitled finding'}</div>
          ${f.detail && html`
            <div class="finding-detail">${f.detail}</div>
          `}
          <div class="finding-meta">
            ${f.priority && html`
              <span class="tag ${priorityTag(f.priority)}">${String(f.priority).toUpperCase()}</span>
            `}
            ${f.category && html`
              <span class="tag tag-info">${f.category}</span>
            `}
          </div>
        </div>
      `)}
    </div>
  `;
}

export default Findings;
