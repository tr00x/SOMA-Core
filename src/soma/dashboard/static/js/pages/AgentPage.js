/**
 * AgentPage — Agent detail page with all sub-panels.
 *
 * Fetches: agent info, pressure history, tools, audit,
 * guidance, quality, findings, baselines, predictions.
 */

import { html } from 'htm/preact';
import { useEffect, useState } from 'preact/hooks';
import api from '../api.js';
import PressureChart from '../components/PressureChart.js';
import ToolStats from '../components/ToolStats.js';
import AuditLog from '../components/AuditLog.js';
import Findings from '../components/Findings.js';

function modeClass(level) {
  if (!level) return 'mode-observe';
  const l = String(level).toLowerCase();
  if (l === 'block') return 'mode-block';
  if (l === 'warn') return 'mode-warn';
  if (l === 'guide') return 'mode-guide';
  return 'mode-observe';
}

function pressureColor(p) {
  if (p >= 0.75) return 'var(--mode-block)';
  if (p >= 0.5) return 'var(--mode-warn)';
  if (p >= 0.25) return 'var(--mode-guide)';
  return 'var(--mode-observe)';
}

function formatPct(v) {
  if (v == null) return '--';
  return `${(v * 100).toFixed(1)}%`;
}

const VITAL_LABELS = {
  uncertainty: 'Uncertainty',
  drift: 'Drift',
  error_rate: 'Error Rate',
  token_usage: 'Token Usage',
  cost: 'Cost',
};

export function AgentPage({ id }) {
  const [loading, setLoading] = useState(true);
  const [agent, setAgent] = useState(null);
  const [pressureHistory, setPressureHistory] = useState([]);
  const [tools, setTools] = useState([]);
  const [audit, setAudit] = useState([]);
  const [guidance, setGuidance] = useState(null);
  const [quality, setQuality] = useState(null);
  const [findings, setFindings] = useState([]);
  const [baselines, setBaselines] = useState(null);
  const [predictions, setPredictions] = useState(null);
  const [timeline, setTimeline] = useState([]);

  useEffect(() => {
    if (!id) return;

    setLoading(true);

    Promise.all([
      api.agent(id).catch(() => null),
      api.agentPressureHistory(id).catch(() => []),
      api.agentTools(id).catch(() => []),
      api.agentAudit(id).catch(() => []),
      api.agentGuidance(id).catch(() => null),
      api.agentQuality(id).catch(() => null),
      api.agentFindings(id).catch(() => []),
      api.agentBaselines(id).catch(() => null),
      api.agentPredictions(id).catch(() => null),
      api.agentTimeline(id).catch(() => []),
    ]).then(([ag, ph, tl, au, gu, qu, fi, ba, pr, tm]) => {
      setAgent(ag);
      setPressureHistory(Array.isArray(ph) ? ph : []);
      setTools(Array.isArray(tl) ? tl : []);
      setAudit(Array.isArray(au) ? au : []);
      setGuidance(gu);
      setQuality(qu);
      setFindings(Array.isArray(fi) ? fi : []);
      setBaselines(ba);
      setPredictions(pr);
      setTimeline(Array.isArray(tm) ? tm : []);
      setLoading(false);
    });
  }, [id]);

  if (loading) {
    return html`
      <div class="page">
        <div class="skeleton skeleton-stat" style="width:300px;margin-bottom:16px"></div>
        <div class="skeleton skeleton-chart" style="margin-bottom:16px"></div>
        <div class="detail-grid">
          <div class="skeleton skeleton-card"></div>
          <div class="skeleton skeleton-card"></div>
        </div>
      </div>
    `;
  }

  if (!agent) {
    return html`
      <div class="page">
        <div class="card empty-state">
          <div class="empty-state-title">Agent not found</div>
          <div class="empty-state-text">Agent "${id}" could not be found. It may have expired or not been registered yet.</div>
        </div>
      </div>
    `;
  }

  const pressure = agent.pressure ?? 0;
  const level = agent.level || agent.escalation_level || 'OBSERVE';

  return html`
    <div class="page animate-in">
      <!-- Header -->
      <div class="page-header">
        <div class="breadcrumb">
          <a href="/" onClick=${(e) => { e.preventDefault(); history.pushState(null, '', '/'); dispatchEvent(new PopStateEvent('popstate')); }}>Overview</a>
          <span style="margin:0 6px;color:var(--text-tertiary)">/</span>
        </div>
        <h1>${agent.display_name || agent.agent_id}</h1>
        <span class="mode-badge ${modeClass(level)}">
          <span class="badge-dot"></span>
          ${String(level).toUpperCase()}
        </span>
        <span class="pressure-label" style="color:${pressureColor(pressure)};margin-left:auto;font-size:1.125rem">
          ${Math.round(pressure * 100)}%
        </span>
      </div>

      <!-- Pressure Chart -->
      <div class="card" style="margin-bottom:12px">
        <div class="card-header">
          <span class="card-title">Pressure History</span>
          ${predictions && predictions.predicted_pressure != null && html`
            <span class="mono" style="font-size:0.6875rem;color:var(--text-tertiary)">
              Predicted: ${Math.round(predictions.predicted_pressure * 100)}%
              (${Math.round((predictions.confidence || 0) * 100)}% conf)
            </span>
          `}
        </div>
        <${PressureChart} history=${pressureHistory} baselines=${baselines} />
      </div>

      <div class="detail-grid">
        <!-- Vitals Panel -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Vitals</span>
          </div>
          ${agent.vitals ? html`
            <div>
              ${Object.entries(VITAL_LABELS).map(([key, label]) => {
                const val = agent.vitals[key];
                const base = baselines ? baselines[key] : null;
                if (val == null) return null;
                return html`
                  <div key=${key} style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border-subtle)">
                    <span style="min-width:90px;font-size:0.75rem;color:var(--text-secondary)">${label}</span>
                    <div style="flex:1">
                      <div class="pressure-bar-container">
                        <div class="pressure-bar-fill"
                             style="width:${Math.min(val * 100, 100)}%;background:${pressureColor(val)}"></div>
                      </div>
                    </div>
                    <span class="mono" style="min-width:48px;text-align:right;font-size:0.75rem;color:${pressureColor(val)}">${formatPct(val)}</span>
                    ${base != null && html`
                      <span class="mono" style="font-size:0.625rem;color:var(--text-tertiary);min-width:55px;text-align:right">
                        base: ${formatPct(base)}
                      </span>
                    `}
                  </div>
                `;
              })}
            </div>
          ` : html`
            <div class="empty-state" style="padding:16px">
              <div class="empty-state-text">No vitals data available.</div>
            </div>
          `}
        </div>

        <!-- Guidance Panel -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Guidance</span>
          </div>
          ${guidance ? html`
            <div>
              <div class="config-row">
                <span class="config-key">Escalation Level</span>
                <span class="config-value mono" style="color:${guidance.escalation_level > 0 ? 'var(--warning)' : 'var(--text)'}">
                  ${guidance.escalation_level ?? 0}
                </span>
              </div>
              <div class="config-row">
                <span class="config-key">Dominant Signal</span>
                <span class="config-value mono">${guidance.dominant_signal || '--'}</span>
              </div>
              ${guidance.throttled_tool && html`
                <div class="config-row">
                  <span class="config-key">Throttled Tool</span>
                  <span class="config-value mono" style="color:var(--warning)">${guidance.throttled_tool}</span>
                </div>
              `}
              <div class="config-row">
                <span class="config-key">Consecutive Blocks</span>
                <span class="config-value mono">${guidance.consecutive_block ?? 0}</span>
              </div>
              <div class="config-row">
                <span class="config-key">Open Guidance</span>
                <span class="config-value mono">${guidance.is_open ? 'Yes' : 'No'}</span>
              </div>
            </div>
          ` : html`
            <div class="empty-state" style="padding:16px">
              <div class="empty-state-text">No guidance data available.</div>
            </div>
          `}
        </div>

        <!-- Tool Stats -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Tool Usage</span>
          </div>
          <${ToolStats} tools=${tools} />
        </div>

        <!-- Quality -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">Quality</span>
          </div>
          ${quality && quality.grade !== '-' ? html`
            <div>
              <div class="config-row">
                <span class="config-key">Writes</span>
                <span class="config-value mono">${quality.total_writes ?? 0}</span>
              </div>
              <div class="config-row">
                <span class="config-key">Bashes</span>
                <span class="config-value mono">${quality.total_bashes ?? 0}</span>
              </div>
              <div class="config-row">
                <span class="config-key">Write Error Rate</span>
                <span class="config-value mono" style="color:${(quality.write_error_rate || 0) > 0.2 ? 'var(--error)' : 'var(--text)'}">
                  ${formatPct(quality.write_error_rate)}
                </span>
              </div>
              <div class="config-row">
                <span class="config-key">Bash Error Rate</span>
                <span class="config-value mono" style="color:${(quality.bash_error_rate || 0) > 0.2 ? 'var(--error)' : 'var(--text)'}">
                  ${formatPct(quality.bash_error_rate)}
                </span>
              </div>
              ${quality.syntax_errors != null && html`
                <div class="config-row">
                  <span class="config-key">Syntax Errors</span>
                  <span class="config-value mono" style="color:${quality.syntax_errors > 0 ? 'var(--error)' : 'var(--text)'}">
                    ${quality.syntax_errors}
                  </span>
                </div>
              `}
              ${quality.lint_issues != null && html`
                <div class="config-row">
                  <span class="config-key">Lint Issues</span>
                  <span class="config-value mono">${quality.lint_issues}</span>
                </div>
              `}
            </div>
          ` : html`
            <div class="empty-state" style="padding:16px">
              <div class="empty-state-text">No quality data collected yet.</div>
            </div>
          `}
        </div>

        <!-- Audit Log -->
        <div class="card detail-grid-full">
          <div class="card-header">
            <span class="card-title">Audit Log</span>
          </div>
          <${AuditLog} events=${audit} />
        </div>

        <!-- Findings -->
        <div class="card detail-grid-full">
          <div class="card-header">
            <span class="card-title">Findings (${findings.length})</span>
          </div>
          <${Findings} findings=${findings} />
        </div>

        <!-- Timeline -->
        ${timeline.length > 0 && html`
          <div class="card detail-grid-full">
            <div class="card-header">
              <span class="card-title">Action Timeline (${timeline.length})</span>
            </div>
            <div class="scroll-panel" style="max-height:400px" role="list" aria-label="Agent timeline">
              ${timeline.map((a, i) => html`
                <div class="timeline-item" key=${i} role="listitem">
                  <span class="time">#${i + 1}</span>
                  <span class="tool-name">${a.tool_name || '--'}</span>
                  <span class="pressure-val" style="color:${pressureColor(a.pressure)}">
                    ${a.pressure != null ? `${Math.round(a.pressure * 100)}%` : '--'}
                  </span>
                  ${a.mode && html`
                    <span class="mode-badge ${modeClass(a.mode)}" style="font-size:0.5625rem;padding:1px 5px">
                      <span class="badge-dot" style="width:4px;height:4px"></span>
                      ${String(a.mode).toUpperCase()}
                    </span>
                  `}
                  ${a.token_count && html`
                    <span class="mono" style="color:var(--text-tertiary);font-size:0.6875rem">${a.token_count} tok</span>
                  `}
                  ${a.error && html`<span class="error-badge">ERR</span>`}
                </div>
              `)}
            </div>
          </div>
        `}
      </div>
    </div>
  `;
}

export default AgentPage;
