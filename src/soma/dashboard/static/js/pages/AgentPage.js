/**
 * AgentPage — Agent detail with pressure chart, vitals, tools, guidance.
 * Empty sections are hidden, timeline capped at 50.
 */

import { html } from 'htm/preact';
import { useEffect, useState } from 'preact/hooks';
import api from '../api.js';
import PressureChart from '../components/PressureChart.js';
import ToolStats from '../components/ToolStats.js';
import AuditLog from '../components/AuditLog.js';
import Findings from '../components/Findings.js';

function modeClass(level) {
  const l = String(level || '').toLowerCase();
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
  uncertainty: 'Uncertainty', drift: 'Drift', error_rate: 'Error Rate',
  token_usage: 'Token Usage', cost: 'Cost',
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
  const [timelineLimit, setTimelineLimit] = useState(50);

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
    return html`<div class="page"><div class="skeleton skeleton-chart" style="margin-bottom:16px"></div></div>`;
  }
  if (!agent) {
    return html`<div class="page"><div class="card empty-state"><div class="empty-state-title">Agent "${id}" not found</div></div></div>`;
  }

  const pressure = agent.pressure ?? 0;
  const level = agent.level || 'OBSERVE';
  const hasQuality = quality && quality.grade !== '-' && (quality.total_writes > 0 || quality.total_bashes > 0);
  const hasGuidanceActivity = guidance && (guidance.escalation_level > 0 || guidance.dominant_signal || guidance.throttled_tool);

  return html`
    <div class="page animate-in">
      <!-- Header -->
      <div class="page-header">
        <div class="breadcrumb">
          <a href="/" onClick=${(e) => { e.preventDefault(); history.pushState(null, '', '/'); dispatchEvent(new PopStateEvent('popstate')); }}>Overview</a>
          <span style="margin:0 6px;color:var(--text-tertiary)">/</span>
        </div>
        <h1>${agent.display_name || agent.agent_id}</h1>
        <span class="mode-badge ${modeClass(level)}"><span class="badge-dot"></span>${String(level).toUpperCase()}</span>
        <span style="margin-left:4px;font-size:0.75rem;color:var(--text-tertiary)">${agent.agent_id}</span>
        <span class="pressure-label" style="color:${pressureColor(pressure)};margin-left:auto;font-size:1.125rem">
          ${pressure > 0 && pressure < 0.005 ? '<1' : Math.round(pressure * 100)}%
        </span>
      </div>

      <!-- Pressure Chart -->
      <div class="card" style="margin-bottom:12px">
        <div class="card-header">
          <span class="card-title">Pressure History</span>
          <span class="mono" style="font-size:0.6875rem;color:var(--text-tertiary)">
            ${pressureHistory.length} data points
            ${predictions && predictions.predicted_pressure != null ? ` · Predicted: ${Math.round(predictions.predicted_pressure * 100)}%` : ''}
          </span>
        </div>
        <${PressureChart} history=${pressureHistory} baselines=${baselines} />
      </div>

      <!-- Vitals + Guidance (side by side) -->
      <div class="detail-grid">
        <div class="card">
          <div class="card-header"><span class="card-title">Vitals</span></div>
          ${agent.vitals ? html`
            <div>
              ${Object.entries(VITAL_LABELS).map(([key, label]) => {
                const val = agent.vitals[key];
                const base = baselines ? baselines[key] : null;
                if (val == null) return null;
                return html`
                  <div key=${key} style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border-subtle)">
                    <span style="min-width:80px;font-size:0.75rem;color:var(--text-secondary)">${label}</span>
                    <div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                      <div style="width:${Math.min(val * 100, 100)}%;height:100%;background:${pressureColor(val)};border-radius:3px"></div>
                    </div>
                    <span class="mono" style="min-width:42px;text-align:right;font-size:0.75rem;color:${pressureColor(val)}">${formatPct(val)}</span>
                    ${base != null && html`<span class="mono" style="font-size:0.625rem;color:var(--text-tertiary)">(${formatPct(base)})</span>`}
                  </div>
                `;
              })}
            </div>
          ` : html`<div class="empty-state-text">No vitals</div>`}
        </div>

        <!-- Guidance + Quality combined -->
        <div class="card">
          <div class="card-header"><span class="card-title">Guidance State</span></div>
          ${guidance ? html`
            <div>
              <div class="config-row">
                <span class="config-key">Escalation</span>
                <span class="config-value mono" style="color:${guidance.escalation_level > 0 ? 'var(--warning)' : 'var(--success)'}">
                  Level ${guidance.escalation_level ?? 0}
                </span>
              </div>
              ${guidance.dominant_signal && html`
                <div class="config-row">
                  <span class="config-key">Dominant Signal</span>
                  <span class="config-value mono">${guidance.dominant_signal}</span>
                </div>
              `}
              ${guidance.throttled_tool && html`
                <div class="config-row">
                  <span class="config-key">Throttled</span>
                  <span class="config-value mono" style="color:var(--warning)">${guidance.throttled_tool}</span>
                </div>
              `}
              <div class="config-row">
                <span class="config-key">Blocks</span>
                <span class="config-value mono">${guidance.consecutive_block ?? 0}</span>
              </div>
              <div class="config-row">
                <span class="config-key">Circuit</span>
                <span class="config-value mono" style="color:${guidance.is_open ? 'var(--error)' : 'var(--success)'}">${guidance.is_open ? 'OPEN' : 'Closed'}</span>
              </div>
            </div>
          ` : html`<div style="padding:8px 0;font-size:0.75rem;color:var(--text-tertiary)">No guidance triggered yet — agent is healthy</div>`}

          ${hasQuality && html`
            <div style="border-top:1px solid var(--border);margin-top:8px;padding-top:8px">
              <div style="font-size:0.6875rem;color:var(--text-tertiary);margin-bottom:6px;font-weight:600">Quality</div>
              <div class="config-row">
                <span class="config-key">Write errors</span>
                <span class="config-value mono" style="color:${quality.write_error_rate > 0.2 ? 'var(--error)' : 'var(--text)'}">${formatPct(quality.write_error_rate)}</span>
              </div>
              <div class="config-row">
                <span class="config-key">Bash errors</span>
                <span class="config-value mono" style="color:${quality.bash_error_rate > 0.2 ? 'var(--error)' : 'var(--text)'}">${formatPct(quality.bash_error_rate)}</span>
              </div>
            </div>
          `}
        </div>
      </div>

      <!-- Tool Stats -->
      ${tools.length > 0 && html`
        <div class="card" style="margin-top:12px">
          <div class="card-header"><span class="card-title">Tool Usage</span></div>
          <${ToolStats} tools=${tools} />
        </div>
      `}

      <!-- Audit + Findings: only show if they have data -->
      ${audit.length > 0 && html`
        <div class="card" style="margin-top:12px">
          <div class="card-header"><span class="card-title">Audit Log (${audit.length})</span></div>
          <${AuditLog} events=${audit} />
        </div>
      `}

      ${findings.length > 0 && html`
        <div class="card" style="margin-top:12px">
          <div class="card-header"><span class="card-title">Findings (${findings.length})</span></div>
          <${Findings} findings=${findings} />
        </div>
      `}

      <!-- Timeline: capped, with "show more" -->
      ${timeline.length > 0 && html`
        <div class="card" style="margin-top:12px">
          <div class="card-header">
            <span class="card-title">Action Timeline</span>
            <span class="mono" style="font-size:0.6875rem;color:var(--text-tertiary)">${timeline.length} total</span>
          </div>
          <div class="scroll-panel" style="max-height:400px" role="list">
            ${timeline.slice(0, timelineLimit).map((a, i) => html`
              <div class="timeline-item" key=${i} role="listitem">
                <span class="time" style="min-width:28px">#${i + 1}</span>
                <span class="tool-name" style="min-width:100px">${a.tool_name || '--'}</span>
                <span class="pressure-val" style="color:${pressureColor(a.pressure)};min-width:35px">
                  ${a.pressure != null ? `${Math.round(a.pressure * 100)}%` : '--'}
                </span>
                ${a.mode && a.mode !== 'OBSERVE' && html`
                  <span class="mode-badge ${modeClass(a.mode)}" style="font-size:0.5625rem;padding:1px 5px">
                    ${String(a.mode).toUpperCase()}
                  </span>
                `}
                ${a.token_count ? html`<span class="mono" style="color:var(--text-tertiary);font-size:0.6875rem">${a.token_count} tok</span>` : null}
                ${a.error ? html`<span class="error-badge">ERR</span>` : null}
              </div>
            `)}
          </div>
          ${timeline.length > timelineLimit && html`
            <div style="text-align:center;padding:8px">
              <button class="btn btn-ghost" onClick=${() => setTimelineLimit(l => l + 100)}>
                Show more (${timeline.length - timelineLimit} remaining)
              </button>
            </div>
          `}
        </div>
      `}
    </div>
  `;
}

export default AgentPage;
