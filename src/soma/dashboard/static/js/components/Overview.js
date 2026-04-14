/**
 * Overview — Stats cards and agent grid for the main page.
 */

import { html } from 'htm/preact';
import AgentCard from './AgentCard.js';
import BudgetGauge from './BudgetGauge.js';
import SessionList from './SessionList.js';

function formatPressure(p) {
  if (p == null) return '--';
  return `${Math.round(p * 100)}%`;
}

function pressureColor(p) {
  if (p == null) return 'var(--text)';
  if (p >= 0.75) return 'var(--mode-block)';
  if (p >= 0.5) return 'var(--mode-warn)';
  if (p >= 0.25) return 'var(--mode-guide)';
  return 'var(--mode-observe)';
}

export function Overview({ overview, agents, sessions, budget, loading }) {
  if (loading) {
    return html`
      <div>
        <div class="stats-grid">
          ${[1, 2, 3, 4].map(i => html`<div class="card skeleton skeleton-stat" key=${i}></div>`)}
        </div>
        <div class="agents-grid">
          ${[1, 2, 3].map(i => html`<div class="card skeleton skeleton-card" key=${i}></div>`)}
        </div>
      </div>
    `;
  }

  const ov = overview || {};
  const agentList = agents || [];
  const sessionList = sessions || [];

  return html`
    <div class="animate-in">
      <!-- Stats Row -->
      <div class="stats-grid">
        <div class="card stat-card">
          <div class="stat-label">Total Agents</div>
          <div class="stat-value">${ov.total_agents ?? agentList.length}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Total Sessions</div>
          <div class="stat-value">${ov.total_sessions ?? sessionList.length}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Total Actions</div>
          <div class="stat-value">${ov.total_actions ?? 0}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Avg Pressure</div>
          <div class="stat-value" style="color:${pressureColor(ov.avg_pressure)}">
            ${formatPressure(ov.avg_pressure)}
          </div>
        </div>
      </div>

      <!-- Agent Grid -->
      <div style="margin-bottom:20px">
        <h3 class="section-heading">Active Agents</h3>
        ${agentList.length === 0
          ? html`
            <div class="card empty-state">
              <div class="empty-state-title">No agents registered</div>
              <div class="empty-state-text">
                Agents will appear here once SOMA starts monitoring. Run a SOMA-enabled agent to get started.
              </div>
            </div>
          `
          : html`
            <div class="agents-grid">
              ${agentList.map(a => html`<${AgentCard} key=${a.agent_id} agent=${a} />`)}
            </div>
          `
        }
      </div>

      <!-- Bottom row: Budget + Recent Sessions -->
      <div class="detail-grid">
        ${budget && html`
          <div class="card">
            <div class="card-header">
              <span class="card-title">Budget</span>
            </div>
            <${BudgetGauge} budget=${budget} />
          </div>
        `}

        <div class="card">
          <div class="card-header">
            <span class="card-title">Recent Sessions</span>
          </div>
          <${SessionList} sessions=${sessionList} limit=${5} />
        </div>
      </div>

      <!-- Top Signals -->
      ${ov.top_signals && Object.keys(ov.top_signals).length > 0 && html`
        <div class="card" style="margin-top:12px">
          <div class="card-header">
            <span class="card-title">Top Signals</span>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            ${Object.entries(ov.top_signals).map(([sig, val]) => html`
              <div class="vital-chip" key=${sig}>
                <span>${sig}</span>
                <span class="mono" style="color:var(--text)">${typeof val === 'number' ? val.toFixed(3) : val}</span>
              </div>
            `)}
          </div>
        </div>
      `}
    </div>
  `;
}

export default Overview;
