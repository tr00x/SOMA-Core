/**
 * BudgetGauge — Token budget usage with clear labels.
 */

import { html } from 'htm/preact';

function formatNumber(n) {
  if (n == null) return '--';
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(Math.round(n));
}

function usageColor(pct) {
  if (pct >= 90) return 'var(--error)';
  if (pct >= 70) return 'var(--warning)';
  return 'var(--success)';
}

export function BudgetGauge({ budget }) {
  if (!budget || !budget.tokens_limit) {
    return html`
      <div class="empty-state" style="padding:12px">
        <div class="empty-state-text">No token budget configured</div>
      </div>
    `;
  }

  const spent = budget.tokens_spent || 0;
  const limit = budget.tokens_limit;
  const remaining = limit - spent;
  const usedPct = Math.round((spent / limit) * 100);
  const remainPct = 100 - usedPct;

  return html`
    <div style="padding:4px 0">
      <!-- Usage bar -->
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="font-size:0.75rem;color:var(--text-secondary)">Token Usage</span>
        <span class="mono" style="font-size:0.75rem;color:${usageColor(usedPct)}">${usedPct}% used</span>
      </div>
      <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;margin-bottom:12px">
        <div style="width:${usedPct}%;height:100%;background:${usageColor(usedPct)};border-radius:4px;transition:width 0.3s"></div>
      </div>

      <!-- Numbers -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <div style="font-size:0.6875rem;color:var(--text-tertiary)">Spent</div>
          <div class="mono" style="font-size:1rem;font-weight:600">${formatNumber(spent)}</div>
        </div>
        <div>
          <div style="font-size:0.6875rem;color:var(--text-tertiary)">Remaining</div>
          <div class="mono" style="font-size:1rem;font-weight:600;color:${usageColor(usedPct)}">${formatNumber(remaining)}</div>
        </div>
        <div>
          <div style="font-size:0.6875rem;color:var(--text-tertiary)">Limit</div>
          <div class="mono" style="font-size:1rem;font-weight:600">${formatNumber(limit)}</div>
        </div>
        ${budget.cost_limit > 0 && html`
          <div>
            <div style="font-size:0.6875rem;color:var(--text-tertiary)">Cost</div>
            <div class="mono" style="font-size:1rem;font-weight:600">$${(budget.cost_spent || 0).toFixed(2)} / $${budget.cost_limit.toFixed(2)}</div>
          </div>
        `}
      </div>
    </div>
  `;
}

export default BudgetGauge;
