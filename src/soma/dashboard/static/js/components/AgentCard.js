/**
 * AgentCard — Overview card for a single agent.
 *
 * Shows: display name, mode badge, pressure bar, vitals chips,
 * action count, escalation level. Click navigates to agent detail.
 */

import { html } from 'htm/preact';
import { useMemo, useState, useEffect, useRef } from 'preact/hooks';
import { route } from 'preact-router';

function modeClass(level) {
  if (!level) return 'mode-observe';
  const l = String(level).toLowerCase();
  if (l === 'block') return 'mode-block';
  if (l === 'warn') return 'mode-warn';
  if (l === 'guide') return 'mode-guide';
  return 'mode-observe';
}

function pressureClass(p) {
  if (p >= 0.75) return 'critical';
  if (p >= 0.5) return 'elevated';
  if (p >= 0.25) return 'moderate';
  return 'low';
}

function pressureColor(p) {
  if (p >= 0.75) return 'var(--mode-block)';
  if (p >= 0.5) return 'var(--mode-warn)';
  if (p >= 0.25) return 'var(--mode-guide)';
  return 'var(--mode-observe)';
}

const VITAL_KEYS = ['uncertainty', 'drift', 'error_rate', 'token_usage', 'cost'];
const VITAL_LABELS = { uncertainty: 'UNC', drift: 'DFT', error_rate: 'ERR', token_usage: 'TOK', cost: 'CST' };

export function AgentCard({ agent }) {
  const pressure = agent.pressure ?? 0;
  const pct = pressure > 0 && pressure < 0.005 ? '<1' : Math.round(pressure * 100);
  const level = agent.level || agent.escalation_level || 'OBSERVE';

  // Track if agent is live (action_count changed recently)
  const prevCount = useRef(agent.action_count);
  const [isLive, setIsLive] = useState(false);
  useEffect(() => {
    if (agent.action_count !== prevCount.current) {
      prevCount.current = agent.action_count;
      setIsLive(true);
      const t = setTimeout(() => setIsLive(false), 5000);
      return () => clearTimeout(t);
    }
  }, [agent.action_count]);

  const vitals = useMemo(() => {
    if (!agent.vitals) return [];
    return VITAL_KEYS.map(k => ({
      key: k,
      label: VITAL_LABELS[k],
      value: agent.vitals[k] ?? 0,
    })).filter(v => v.value !== undefined);
  }, [agent.vitals]);

  function handleClick() {
    route(`/agents/${agent.agent_id}`);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  }

  return html`
    <div class="card card-interactive animate-in"
         onClick=${handleClick}
         onKeyDown=${handleKeyDown}
         role="button"
         tabindex="0"
         aria-label="View agent ${agent.display_name || agent.agent_id}">

      <div class="card-header">
        <div>
          <div class="agent-card-name">${agent.display_name || agent.agent_id}</div>
          ${agent.display_name && agent.display_name !== agent.agent_id && html`
            <div class="agent-card-id">${agent.agent_id}</div>
          `}
        </div>
        <span class="mode-badge ${modeClass(level)}">
          <span class="badge-dot"></span>
          ${String(level).toUpperCase()}
        </span>
        ${isLive && html`<span style="font-size:0.5625rem;color:var(--success);font-weight:600;animation:pulse 1.5s infinite;margin-left:4px">LIVE</span>`}
      </div>

      <div style="margin-bottom: 10px">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
          <span style="font-size:0.6875rem;color:var(--text-tertiary)">Pressure</span>
          <span class="pressure-label" style="color:${pressureColor(pressure)}">${pct}%</span>
        </div>
        <div class="pressure-bar-container">
          <div class="pressure-bar-fill ${pressureClass(pressure)}"
               style="width:${pct}%"
               role="progressbar"
               aria-valuenow=${pct}
               aria-valuemin="0"
               aria-valuemax="100"
               aria-label="Pressure ${pct}%"></div>
        </div>
      </div>

      ${vitals.length > 0 && html`
        <div class="vitals-row" style="margin-bottom:10px">
          ${vitals.map(v => html`
            <div class="vital-chip" key=${v.key}>
              <span>${v.label}</span>
              <span class="mono" style="font-size:0.625rem;color:var(--text-secondary)">${v.value < 0.01 ? '<1%' : (v.value * 100).toFixed(0) + '%'}</span>
            </div>
          `)}
        </div>
      `}

      <div class="agent-card-stats">
        <div class="agent-stat">
          <span class="agent-stat-label">Actions</span>
          <span class="agent-stat-value mono">${agent.action_count ?? 0}</span>
        </div>
        ${agent.dominant_signal && html`
          <div class="agent-stat">
            <span class="agent-stat-label">Signal</span>
            <span class="agent-stat-value mono" style="font-size:0.75rem">${agent.dominant_signal}</span>
          </div>
        `}
        ${(agent.escalation_level > 0) && html`
          <div class="agent-stat">
            <span class="agent-stat-label">Escalation</span>
            <span class="agent-stat-value mono" style="color:var(--warning)">${agent.escalation_level}</span>
          </div>
        `}
      </div>
    </div>
  `;
}

export default AgentCard;
