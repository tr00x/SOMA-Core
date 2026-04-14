/**
 * SessionDetail — Detailed view of a single session.
 *
 * Stats, tool breakdown, action timeline, export button.
 */

import { html } from 'htm/preact';
import { useEffect, useRef } from 'preact/hooks';
import ExportButton from './ExportButton.js';

let Chart = null;
let chartLoaded = false;

async function ensureChartJs() {
  if (chartLoaded) return;
  const mod = await import('chart.js/auto');
  Chart = mod.default || mod.Chart;
  chartLoaded = true;
}

function pressureColor(p) {
  if (p >= 0.75) return 'var(--mode-block)';
  if (p >= 0.5) return 'var(--mode-warn)';
  if (p >= 0.25) return 'var(--mode-guide)';
  return 'var(--mode-observe)';
}

function formatTime(ts) {
  if (!ts) return '--';
  return new Date(ts * 1000).toLocaleString();
}

function formatTokens(n) {
  if (n == null) return '--';
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function formatCost(c) {
  if (c == null || c === 0) return '--';
  if (c < 0.01) return `$${c.toFixed(4)}`;
  return `$${c.toFixed(2)}`;
}

export function SessionDetail({ session }) {
  const chartRef = useRef(null);
  const canvasRef = useRef(null);

  // Tool stats chart
  useEffect(() => {
    if (!session || !session.tool_stats) return;
    const entries = Object.entries(session.tool_stats).sort((a, b) => b[1] - a[1]);
    if (!entries.length) return;

    let cancelled = false;
    (async () => {
      await ensureChartJs();
      if (cancelled || !canvasRef.current) return;

      const colors = [
        '#f43f5e', '#3b82f6', '#22c55e', '#eab308', '#f97316',
        '#a855f7', '#06b6d4', '#ec4899', '#14b8a6', '#84cc16',
      ];

      if (chartRef.current) chartRef.current.destroy();
      chartRef.current = new Chart(canvasRef.current, {
        type: 'doughnut',
        data: {
          labels: entries.map(e => e[0]),
          datasets: [{
            data: entries.map(e => e[1]),
            backgroundColor: entries.map((_, i) => colors[i % colors.length]),
            borderWidth: 0,
            hoverBorderWidth: 2,
            hoverBorderColor: '#fafafa',
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '65%',
          plugins: {
            legend: {
              position: 'right',
              labels: {
                color: '#a1a1aa',
                font: { family: "'JetBrains Mono', monospace", size: 10 },
                padding: 8,
                boxWidth: 10,
                boxHeight: 10,
                borderRadius: 2,
              },
            },
            tooltip: {
              backgroundColor: '#18181b',
              titleColor: '#fafafa',
              bodyColor: '#a1a1aa',
              borderColor: '#27272a',
              borderWidth: 1,
              padding: 10,
              cornerRadius: 8,
            },
          },
          animation: { duration: 400, easing: 'easeOutQuart' },
        },
      });
    })();

    return () => {
      cancelled = true;
      if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }
    };
  }, [session]);

  if (!session) {
    return html`<div class="skeleton skeleton-chart"></div>`;
  }

  const actions = session.actions || [];

  return html`
    <div>
      <!-- Stats Row -->
      <div class="stats-grid" style="margin-bottom:16px">
        <div class="card stat-card">
          <div class="stat-label">Avg Pressure</div>
          <div class="stat-value" style="color:${pressureColor(session.avg_pressure)}">
            ${session.avg_pressure != null ? `${Math.round(session.avg_pressure * 100)}%` : '--'}
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Max Pressure</div>
          <div class="stat-value" style="color:${pressureColor(session.max_pressure)}">
            ${session.max_pressure != null ? `${Math.round(session.max_pressure * 100)}%` : '--'}
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Tokens</div>
          <div class="stat-value">${formatTokens(session.total_tokens)}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Cost</div>
          <div class="stat-value">${formatCost(session.total_cost)}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Errors</div>
          <div class="stat-value" style="color:${session.error_count > 0 ? 'var(--error)' : 'var(--text)'}">
            ${session.error_count ?? 0}
          </div>
        </div>
      </div>

      <div class="detail-grid">
        <!-- Tool Breakdown -->
        ${session.tool_stats && Object.keys(session.tool_stats).length > 0 && html`
          <div class="card">
            <div class="card-header">
              <span class="card-title">Tool Breakdown</span>
            </div>
            <div style="height:200px">
              <canvas ref=${canvasRef}></canvas>
            </div>
          </div>
        `}

        <!-- Metadata -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Session Info</span>
            <${ExportButton} sessionId=${session.session_id} />
          </div>
          <div>
            <div class="config-row">
              <span class="config-key">Session ID</span>
              <span class="config-value">${session.session_id}</span>
            </div>
            <div class="config-row">
              <span class="config-key">Agent</span>
              <span class="config-value">${session.display_name || session.agent_id}</span>
            </div>
            <div class="config-row">
              <span class="config-key">Started</span>
              <span class="config-value">${formatTime(session.start_time)}</span>
            </div>
            <div class="config-row">
              <span class="config-key">Ended</span>
              <span class="config-value">${formatTime(session.end_time)}</span>
            </div>
            <div class="config-row">
              <span class="config-key">Actions</span>
              <span class="config-value">${session.action_count ?? 0}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Action Timeline -->
      ${actions.length > 0 && html`
        <div class="card" style="margin-top:12px">
          <div class="card-header">
            <span class="card-title">Action Timeline (${actions.length})</span>
          </div>
          <div class="scroll-panel" style="max-height:500px" role="list" aria-label="Action timeline">
            ${actions.map((a, i) => html`
              <div class="timeline-item" key=${i} role="listitem">
                <span class="time">#${i + 1}</span>
                <span class="tool-name">${a.tool_name || '--'}</span>
                <span class="pressure-val" style="color:${pressureColor(a.pressure)}">
                  ${a.pressure != null ? `${Math.round(a.pressure * 100)}%` : '--'}
                </span>
                ${a.token_count && html`
                  <span class="mono" style="color:var(--text-tertiary);font-size:0.6875rem">
                    ${formatTokens(a.token_count)} tok
                  </span>
                `}
                ${a.error && html`
                  <span class="error-badge">ERR</span>
                `}
              </div>
            `)}
          </div>
        </div>
      `}
    </div>
  `;
}

export default SessionDetail;
