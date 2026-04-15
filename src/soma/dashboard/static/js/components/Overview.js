/**
 * Overview — SOMA metrics dashboard with actionable insights.
 */

import { html } from 'htm/preact';
import { useMemo } from 'preact/hooks';
import AgentCard from './AgentCard.js';
import BudgetGauge from './BudgetGauge.js';
import SessionList from './SessionList.js';

function pressureColor(p) {
  if (p == null) return 'var(--text)';
  if (p >= 0.75) return 'var(--mode-block)';
  if (p >= 0.5) return 'var(--mode-warn)';
  if (p >= 0.25) return 'var(--mode-guide)';
  return 'var(--mode-observe)';
}

const MODE_COLORS = {
  OBSERVE: 'var(--mode-observe)',
  GUIDE: 'var(--mode-guide)',
  WARN: 'var(--mode-warn)',
  BLOCK: 'var(--mode-block)',
};

export function Overview({ overview, agents, sessions, budget, loading }) {
  if (loading) {
    return html`
      <div>
        <div class="stats-grid">
          ${[1, 2, 3, 4].map(i => html`<div class="card skeleton skeleton-stat" key=${i}></div>`)}
        </div>
      </div>
    `;
  }

  const ov = overview || {};
  const agentList = agents || [];
  const sessionList = sessions || [];

  // Compute real SOMA metrics from session data
  const metrics = useMemo(() => {
    const totalActions = ov.total_actions || sessionList.reduce((s, x) => s + x.action_count, 0);
    const totalErrors = sessionList.reduce((s, x) => s + (x.error_count || 0), 0);
    const errorRate = totalActions > 0 ? totalErrors / totalActions : 0;

    // Mode distribution
    const modes = { OBSERVE: 0, GUIDE: 0, WARN: 0, BLOCK: 0 };
    sessionList.forEach(s => {
      const m = (s.mode || 'OBSERVE').toUpperCase();
      modes[m] = (modes[m] || 0) + 1;
    });
    const guidedSessions = modes.GUIDE + modes.WARN + modes.BLOCK;
    const guidanceRate = sessionList.length > 0 ? guidedSessions / sessionList.length : 0;

    // Avg session pressure (from sessions, more meaningful than live)
    const avgPressure = sessionList.length > 0
      ? sessionList.reduce((s, x) => s + (x.avg_pressure || 0), 0) / sessionList.length
      : 0;

    // Max pressure ever seen
    const maxPressure = sessionList.length > 0
      ? Math.max(...sessionList.map(s => s.max_pressure || 0))
      : 0;

    // Token total
    const totalTokens = sessionList.reduce((s, x) => s + (x.total_tokens || 0), 0);
    const totalCost = sessionList.reduce((s, x) => s + (x.total_cost || 0), 0);

    return { totalActions, totalErrors, errorRate, modes, guidedSessions, guidanceRate, avgPressure, maxPressure, totalTokens, totalCost };
  }, [sessionList, ov]);

  return html`
    <div class="animate-in">
      <!-- Primary Metrics -->
      <div class="stats-grid">
        <div class="card stat-card">
          <div class="stat-label">Sessions Monitored</div>
          <div class="stat-value">${sessionList.length}</div>
          <div class="stat-sub">${(ov.total_actions || metrics.totalActions).toLocaleString()} total actions</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Guidance Rate</div>
          <div class="stat-value" style="color:${metrics.guidanceRate > 0.15 ? 'var(--warning)' : 'var(--success)'}">
            ${(metrics.guidanceRate * 100).toFixed(1)}%
          </div>
          <div class="stat-sub">${metrics.guidedSessions} of ${sessionList.length} sessions guided</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Error Rate</div>
          <div class="stat-value" style="color:${metrics.errorRate > 0.1 ? 'var(--error)' : metrics.errorRate > 0.05 ? 'var(--warning)' : 'var(--success)'}">
            ${(metrics.errorRate * 100).toFixed(1)}%
          </div>
          <div class="stat-sub">${metrics.totalErrors.toLocaleString()} errors in ${metrics.totalActions.toLocaleString()} actions</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Avg Pressure</div>
          <div class="stat-value" style="color:${pressureColor(metrics.avgPressure)}">
            ${(metrics.avgPressure * 100).toFixed(1)}%
          </div>
          <div class="stat-sub">Peak: ${(metrics.maxPressure * 100).toFixed(0)}%</div>
        </div>
      </div>

      <!-- Active Agents -->
      <div style="margin-bottom:20px">
        <h3 class="section-heading">Active Agents</h3>
        ${agentList.length === 0
          ? html`
            <div class="card empty-state">
              <div class="empty-state-title">No agents registered</div>
              <div class="empty-state-text">Agents appear here once SOMA starts monitoring.</div>
            </div>
          `
          : agentList.length <= 6
            ? html`
              <div class="agents-grid">
                ${agentList.map(a => html`<${AgentCard} key=${a.agent_id} agent=${a} />`)}
              </div>
            `
            : html`
              <div class="card">
                <div class="scroll-panel" style="max-height:400px">
                  <table style="width:100%;border-collapse:collapse">
                    <thead>
                      <tr style="border-bottom:1px solid var(--border);font-size:0.6875rem;color:var(--text-tertiary);text-align:left">
                        <th style="padding:6px 8px">Agent</th>
                        <th style="padding:6px 8px">Mode</th>
                        <th style="padding:6px 8px;text-align:right">Pressure</th>
                        <th style="padding:6px 8px;text-align:right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${agentList.map(a => html`
                        <tr key=${a.agent_id} style="border-bottom:1px solid var(--border-subtle);cursor:pointer"
                            onClick=${() => { import('preact-router').then(m => m.route('/agents/' + a.agent_id)); }}>
                          <td style="padding:6px 8px;font-size:0.8125rem">${a.display_name || a.agent_id}</td>
                          <td style="padding:6px 8px"><span class="mode-badge mode-${(a.level||'observe').toLowerCase()}" style="font-size:0.5625rem;padding:1px 5px">${(a.level||'OBSERVE').toUpperCase()}</span></td>
                          <td style="padding:6px 8px;text-align:right" class="mono" style="color:${pressureColor(a.pressure)}">${Math.round((a.pressure||0)*100)}%</td>
                          <td style="padding:6px 8px;text-align:right" class="mono">${a.action_count||0}</td>
                        </tr>
                      `)}
                    </tbody>
                  </table>
                </div>
              </div>
            `
        }
      </div>

      <!-- Middle row: Mode Distribution + Budget + Signals -->
      <div class="detail-grid" style="grid-template-columns:1fr 1fr 1fr">
        <!-- Mode Distribution -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Mode Distribution</span>
          </div>
          <div style="padding:4px 0">
            ${Object.entries(metrics.modes).map(([mode, count]) => {
              const pct = sessionList.length > 0 ? (count / sessionList.length * 100) : 0;
              return html`
                <div key=${mode} style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                  <span class="mode-badge mode-${mode.toLowerCase()}" style="width:70px;text-align:center;font-size:0.625rem">${mode}</span>
                  <div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                    <div style="width:${pct}%;height:100%;background:${MODE_COLORS[mode] || 'var(--text-tertiary)'};border-radius:3px;transition:width 0.3s"></div>
                  </div>
                  <span class="mono" style="font-size:0.75rem;color:var(--text-secondary);min-width:45px;text-align:right">${count} (${pct.toFixed(0)}%)</span>
                </div>
              `;
            })}
          </div>
        </div>

        <!-- Budget -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Token Budget</span>
          </div>
          <${BudgetGauge} budget=${budget} />
        </div>

        <!-- Signal Levels -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Signal Averages</span>
          </div>
          ${ov.top_signals && Object.keys(ov.top_signals).length > 0 ? html`
            <div style="padding:4px 0">
              ${Object.entries(ov.top_signals).map(([sig, val]) => {
                const pct = Math.min(val * 100, 100);
                const label = { uncertainty: 'Uncertainty', drift: 'Drift', error_rate: 'Error Rate', cost: 'Cost', token_usage: 'Token Usage' }[sig] || sig;
                return html`
                  <div key=${sig} style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                    <span style="font-size:0.75rem;color:var(--text-secondary);min-width:80px">${label}</span>
                    <div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                      <div style="width:${pct}%;height:100%;background:${pressureColor(val)};border-radius:3px"></div>
                    </div>
                    <span class="mono" style="font-size:0.75rem;color:var(--text);min-width:40px;text-align:right">${(val * 100).toFixed(1)}%</span>
                  </div>
                `;
              })}
            </div>
          ` : html`<div class="empty-state-text">No signal data</div>`}
        </div>
      </div>

      <!-- Bottom: Token/Cost Stats + Recent Sessions -->
      <div class="detail-grid" style="margin-top:12px">
        <div class="card">
          <div class="card-header">
            <span class="card-title">Resource Usage</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:4px 0">
            <div>
              <div style="font-size:0.6875rem;color:var(--text-tertiary);margin-bottom:4px">Total Tokens</div>
              <div class="mono" style="font-size:1.25rem;font-weight:600">${metrics.totalTokens >= 1000000 ? (metrics.totalTokens / 1000000).toFixed(1) + 'M' : metrics.totalTokens >= 1000 ? (metrics.totalTokens / 1000).toFixed(1) + 'K' : metrics.totalTokens}</div>
            </div>
            <div>
              <div style="font-size:0.6875rem;color:var(--text-tertiary);margin-bottom:4px">Total Cost</div>
              <div class="mono" style="font-size:1.25rem;font-weight:600">$${metrics.totalCost.toFixed(2)}</div>
            </div>
            <div>
              <div style="font-size:0.6875rem;color:var(--text-tertiary);margin-bottom:4px">Avg Tokens/Session</div>
              <div class="mono" style="font-size:1.25rem;font-weight:600">${sessionList.length > 0 ? Math.round(metrics.totalTokens / sessionList.length).toLocaleString() : '--'}</div>
            </div>
            <div>
              <div style="font-size:0.6875rem;color:var(--text-tertiary);margin-bottom:4px">Active Agents</div>
              <div class="mono" style="font-size:1.25rem;font-weight:600">${agentList.length}</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <span class="card-title">Recent Sessions</span>
          </div>
          <${SessionList} sessions=${sessionList} limit=${5} />
        </div>
      </div>
    </div>
  `;
}

export default Overview;
