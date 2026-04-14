/**
 * BudgetGauge — Visual gauge for budget health (tokens + cost).
 */

import { html } from 'htm/preact';

function gaugeColor(health) {
  if (health == null) return 'var(--text-tertiary)';
  if (health >= 0.75) return 'var(--success)';
  if (health >= 0.5) return 'var(--warning)';
  if (health >= 0.25) return 'var(--mode-warn)';
  return 'var(--error)';
}

function formatNumber(n) {
  if (n == null) return '--';
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function formatCost(c) {
  if (c == null) return '--';
  return `$${c.toFixed(2)}`;
}

export function BudgetGauge({ budget }) {
  if (!budget) {
    return html`
      <div class="empty-state" style="padding:16px">
        <div class="empty-state-title">No budget configured</div>
      </div>
    `;
  }

  const health = budget.health ?? 1;
  const healthPct = Math.round(health * 100);

  return html`
    <div class="gauge-container">
      <!-- Overall Health -->
      <div style="margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px">
          <span style="font-size:0.75rem;color:var(--text-secondary)">Health</span>
          <span class="mono" style="font-size:0.875rem;font-weight:600;color:${gaugeColor(health)}">${healthPct}%</span>
        </div>
        <div class="gauge-bar">
          <div class="gauge-bar-fill"
               style="width:${healthPct}%;background:${gaugeColor(health)}"></div>
        </div>
      </div>

      <!-- Tokens -->
      ${budget.tokens_limit != null && html`
        <div style="margin-bottom:10px">
          <div class="gauge-label">
            <span>Tokens</span>
            <span class="mono">${formatNumber(budget.tokens_spent)} / ${formatNumber(budget.tokens_limit)}</span>
          </div>
          <div class="gauge-bar" style="margin-top:4px">
            <div class="gauge-bar-fill"
                 style="width:${Math.min(((budget.tokens_spent || 0) / budget.tokens_limit) * 100, 100)}%;background:var(--info)"></div>
          </div>
        </div>
      `}

      <!-- Cost -->
      ${budget.cost_limit != null && html`
        <div>
          <div class="gauge-label">
            <span>Cost</span>
            <span class="mono">${formatCost(budget.cost_spent)} / ${formatCost(budget.cost_limit)}</span>
          </div>
          <div class="gauge-bar" style="margin-top:4px">
            <div class="gauge-bar-fill"
                 style="width:${Math.min(((budget.cost_spent || 0) / budget.cost_limit) * 100, 100)}%;background:var(--accent)"></div>
          </div>
        </div>
      `}
    </div>
  `;
}

export default BudgetGauge;
