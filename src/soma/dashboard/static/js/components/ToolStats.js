/**
 * ToolStats — Horizontal bar chart showing tool usage and error rates.
 */

import { html } from 'htm/preact';

export function ToolStats({ tools = [] }) {
  if (!tools.length) {
    return html`
      <div class="empty-state" style="padding:20px">
        <div class="empty-state-title">No tool data</div>
        <div class="empty-state-text">Tool statistics appear after actions are recorded.</div>
      </div>
    `;
  }

  const maxCount = Math.max(...tools.map(t => t.count || 0), 1);

  return html`
    <div role="list" aria-label="Tool statistics">
      ${tools.map(t => {
        const pct = ((t.count || 0) / maxCount) * 100;
        const errRate = t.error_rate ?? 0;
        const barColor = errRate > 0.5 ? 'var(--error)' :
                         errRate > 0.2 ? 'var(--warning)' :
                         errRate > 0 ? 'var(--info)' : 'var(--accent)';

        return html`
          <div key=${t.tool_name} role="listitem"
               style="display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid var(--border-subtle)">
            <span class="mono" style="min-width:110px;font-size:0.75rem;color:var(--text)">${t.tool_name}</span>
            <div style="flex:1;position:relative">
              <div style="height:6px;background:var(--border-subtle);border-radius:3px;overflow:hidden">
                <div style="width:${pct}%;height:100%;background:${barColor};border-radius:3px;transition:width var(--transition-slow)"></div>
              </div>
            </div>
            <span class="mono" style="min-width:40px;text-align:right;font-size:0.75rem;color:var(--text-secondary)">${t.count}</span>
            ${t.error_count > 0 && html`
              <span class="mono" style="font-size:0.6875rem;color:var(--error)">${t.error_count} err</span>
            `}
          </div>
        `;
      })}
    </div>
  `;
}

export default ToolStats;
