/**
 * Settings — Human-friendly config editor with grouped sections.
 */

import { html } from 'htm/preact';
import { useState, useCallback, useMemo } from 'preact/hooks';
import api from '../api.js';

const SCHEMA = {
  soma: {
    _title: 'General',
    _desc: 'Core SOMA settings',
    mode: { type: 'select', options: ['observe', 'guide', 'reflex'], label: 'Operating Mode', desc: 'observe = silent metrics, guide = suggestions, reflex = auto-correct' },
    profile: { type: 'select', options: ['claude-code', 'strict', 'relaxed', 'autonomous'], label: 'Agent Profile', desc: 'Preset sensitivity levels' },
    version: { type: 'readonly', label: 'Version' },
    store: { type: 'readonly', label: 'State File' },
  },
  budget: {
    _title: 'Budget Limits',
    _desc: 'Token and cost caps per session',
    tokens: { type: 'number', label: 'Token Limit', desc: 'Max tokens per session (0 = unlimited)', step: 10000 },
    cost_usd: { type: 'number', label: 'Cost Limit ($)', desc: 'Max cost in USD (0 = unlimited)', step: 1 },
  },
  thresholds: {
    _title: 'Pressure Thresholds',
    _desc: 'When SOMA escalates response mode',
    guide: { type: 'slider', label: 'GUIDE', desc: 'Start suggesting corrections', min: 0, max: 1, step: 0.01 },
    warn: { type: 'slider', label: 'WARN', desc: 'Show warnings about behavior', min: 0, max: 1, step: 0.01 },
    block: { type: 'slider', label: 'BLOCK', desc: 'Block destructive actions', min: 0, max: 1, step: 0.01 },
  },
  hooks: {
    _title: 'Features',
    _desc: 'Toggle monitoring features on/off',
    validate_python: { type: 'toggle', label: 'Python Validation', desc: 'Check syntax on Write' },
    validate_js: { type: 'toggle', label: 'JS Validation', desc: 'Check JS syntax on Write' },
    lint_python: { type: 'toggle', label: 'Python Linting', desc: 'Run ruff checks' },
    predict: { type: 'toggle', label: 'Pressure Prediction', desc: 'Predict future spikes' },
    fingerprint: { type: 'toggle', label: 'Behavioral Fingerprint', desc: 'Track behavior patterns' },
    quality: { type: 'toggle', label: 'Quality Tracking', desc: 'Track error rates' },
    task_tracking: { type: 'toggle', label: 'Task Tracking', desc: 'Detect scope drift' },
    verbosity: { type: 'select', options: ['quiet', 'normal', 'verbose'], label: 'Verbosity', desc: 'Output level' },
    stale_timeout: { type: 'number', label: 'Stale Timeout (s)', desc: 'Mark session stale after N seconds', step: 60 },
  },
  weights: {
    _title: 'Signal Weights',
    _desc: 'How much each signal contributes to pressure',
    uncertainty: { type: 'number', label: 'Uncertainty', desc: 'Weight for action uncertainty signal', step: 0.1 },
    drift: { type: 'number', label: 'Drift', desc: 'Weight for scope drift signal', step: 0.1 },
    error_rate: { type: 'number', label: 'Error Rate', desc: 'Weight for error frequency signal', step: 0.1 },
    cost: { type: 'number', label: 'Cost', desc: 'Weight for cost signal', step: 0.1 },
    token_usage: { type: 'number', label: 'Token Usage', desc: 'Weight for token consumption signal', step: 0.1 },
    resource: { type: 'number', label: 'Resource', desc: 'Weight for resource usage signal', step: 0.1 },
    coherence: { type: 'number', label: 'Coherence', desc: 'Weight for goal coherence signal', step: 0.1 },
  },
  guidance: {
    _title: 'Guidance Settings',
    _desc: 'Smart Guidance v2 behavior',
    cooldown_actions: { type: 'number', label: 'Cooldown Actions', desc: 'Actions between guidance messages', step: 1 },
    escalation_enabled: { type: 'toggle', label: 'Escalation', desc: 'Enable escalation on ignored guidance' },
    throttle_enabled: { type: 'toggle', label: 'Throttling', desc: 'Enable tool throttling on repeated issues' },
    max_escalation_level: { type: 'number', label: 'Max Escalation', desc: 'Maximum escalation level (0-5)', step: 1 },
  },
  graph: {
    _title: 'Pressure Graph',
    _desc: 'Inter-agent pressure propagation',
    damping: { type: 'number', label: 'Damping Factor', desc: 'How quickly pressure propagates between agents (0-1)', step: 0.01 },
    trust_decay_rate: { type: 'number', label: 'Trust Decay', desc: 'Rate of trust decay between agents', step: 0.01 },
    trust_recovery_rate: { type: 'number', label: 'Trust Recovery', desc: 'Rate of trust recovery', step: 0.01 },
  },
  vitals: {
    _title: 'Vital Signals',
    _desc: 'Fine-tune vital signal computation',
    goal_coherence_threshold: { type: 'number', label: 'Coherence Threshold', desc: 'Min coherence before flagging drift', step: 0.05 },
    goal_coherence_warmup_actions: { type: 'number', label: 'Coherence Warmup', desc: 'Actions before coherence kicks in', step: 1 },
    baseline_integrity_error_ratio: { type: 'number', label: 'Baseline Error Ratio', desc: 'Error ratio threshold for baseline reset', step: 0.1 },
    baseline_integrity_min_error_rate: { type: 'number', label: 'Min Error Rate', desc: 'Minimum error rate to trigger baseline check', step: 0.05 },
    baseline_integrity_min_samples: { type: 'number', label: 'Min Samples', desc: 'Minimum samples before baseline checks', step: 1 },
  },
};

const AGENT_SCHEMA = {
  autonomy: { type: 'select', options: ['human_in_the_loop', 'human_on_the_loop', 'full_autonomy'], label: 'Autonomy', desc: 'How much human oversight required' },
  sensitivity: { type: 'select', options: ['strict', 'relaxed', 'autonomous'], label: 'Sensitivity', desc: 'How aggressively SOMA intervenes' },
  tools: { type: 'readonly', label: 'Allowed Tools', desc: 'Tools this agent can use' },
};

function Toggle({ value, onChange }) {
  const on = !!value;
  return html`
    <div onClick=${() => onChange(!on)} tabindex="0" role="switch" aria-checked=${on}
         onKeyDown=${(e) => e.key === 'Enter' && onChange(!on)}
         style="width:36px;height:20px;border-radius:10px;cursor:pointer;transition:background 0.2s;position:relative;
                background:${on ? 'var(--accent)' : 'var(--border)'}">
      <div style="width:16px;height:16px;border-radius:50%;background:white;position:absolute;top:2px;
                  transition:left 0.2s;left:${on ? '18px' : '2px'}"></div>
    </div>
  `;
}

function Slider({ value, onChange, min = 0, max = 1, step = 0.01 }) {
  return html`
    <div style="display:flex;align-items:center;gap:8px;min-width:160px">
      <input type="range" min=${min} max=${max} step=${step} value=${value || 0}
             onInput=${(e) => onChange(parseFloat(e.target.value))}
             style="flex:1;accent-color:var(--accent)" />
      <span class="mono" style="min-width:36px;text-align:right;font-size:0.75rem">${((value || 0) * 100).toFixed(0)}%</span>
    </div>
  `;
}

export function Settings({ config, onConfigUpdate }) {
  const [changes, setChanges] = useState({});
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  const merged = useMemo(() => {
    if (!config) return {};
    const c = JSON.parse(JSON.stringify(config));
    for (const [path, val] of Object.entries(changes)) {
      const parts = path.split('.');
      let obj = c;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!obj[parts[i]]) obj[parts[i]] = {};
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = val;
    }
    return c;
  }, [config, changes]);

  const handleChange = useCallback((path, value) => {
    setChanges(prev => ({ ...prev, [path]: value }));
    setStatus(null);
  }, []);

  async function handleSave() {
    if (!Object.keys(changes).length) return;
    setSaving(true);
    try {
      const payload = {};
      for (const [path, val] of Object.entries(changes)) {
        const parts = path.split('.');
        let obj = payload;
        for (let i = 0; i < parts.length - 1; i++) {
          if (!obj[parts[i]]) obj[parts[i]] = {};
          obj = obj[parts[i]];
        }
        obj[parts[parts.length - 1]] = val;
      }
      const updated = await api.updateConfig(payload);
      // Reload fresh config from server to confirm save
      const fresh = await api.config();
      if (onConfigUpdate) onConfigUpdate(fresh || updated);
      setChanges({});
      setStatus('saved');
      setTimeout(() => setStatus(null), 3000);
    } catch {
      setStatus('error');
    } finally {
      setSaving(false);
    }
  }

  if (!config || Object.keys(config).length === 0) {
    return html`<div class="card empty-state"><div class="empty-state-title">No configuration</div><div class="empty-state-text">Create soma.toml to configure SOMA.</div></div>`;
  }

  const changeCount = Object.keys(changes).length;

  function getValue(section, key) {
    return (merged[section] || {})[key];
  }

  function renderSection(sectionKey) {
    const schema = SCHEMA[sectionKey];
    if (!schema) return null;
    const sectionData = merged[sectionKey];
    if (!sectionData && sectionKey !== 'thresholds') return null;

    return html`
      <div class="card" style="margin-bottom:12px" key=${sectionKey}>
        <div class="card-header">
          <span class="card-title">${schema._title}</span>
          <span style="font-size:0.6875rem;color:var(--text-tertiary)">${schema._desc || ''}</span>
        </div>
        ${Object.entries(schema).filter(([k]) => !k.startsWith('_')).map(([key, field]) => {
          const path = `${sectionKey}.${key}`;
          const val = getValue(sectionKey, key);
          if (val === undefined && field.type !== 'slider') return null;

          return html`
            <div class="config-row" key=${path} style="padding:10px 0;border-bottom:1px solid var(--border-subtle);display:flex;align-items:center;gap:12px">
              <div style="flex:1;min-width:0">
                <div style="font-size:0.8125rem;color:var(--text);font-weight:500">${field.label}</div>
                ${field.desc && html`<div style="font-size:0.6875rem;color:var(--text-tertiary);margin-top:1px">${field.desc}</div>`}
              </div>
              <div style="display:flex;align-items:center;justify-content:flex-end">
                ${field.type === 'toggle' && html`<${Toggle} value=${!!val} onChange=${(v) => handleChange(path, v)} />`}
                ${field.type === 'slider' && html`<${Slider} value=${val || 0} onChange=${(v) => handleChange(path, v)} min=${field.min} max=${field.max} step=${field.step} />`}
                ${field.type === 'number' && html`<input type="number" class="config-input" value=${val || 0} step=${field.step || 1} style="width:100px;text-align:right" onChange=${(e) => handleChange(path, parseFloat(e.target.value) || 0)} />`}
                ${field.type === 'select' && html`<select class="config-input" value=${val || field.options[0]} onChange=${(e) => handleChange(path, e.target.value)}>${field.options.map(o => html`<option key=${o} value=${o}>${o}</option>`)}</select>`}
                ${field.type === 'readonly' && html`<span class="mono" style="font-size:0.75rem;color:var(--text-secondary)">${val || '--'}</span>`}
              </div>
            </div>
          `;
        })}
      </div>
    `;
  }

  const knownSections = ['soma', 'budget', 'thresholds', 'hooks', 'weights', 'guidance', 'graph', 'vitals', 'agents'];
  const unknownSections = Object.keys(merged).filter(k => !knownSections.includes(k) && typeof merged[k] === 'object');

  return html`
    <div class="animate-in">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:8px 12px;background:var(--surface);border-radius:8px;border:1px solid var(--border)">
        <span style="font-size:0.75rem;color:var(--text-tertiary)">
          ${changeCount > 0 ? `${changeCount} unsaved change${changeCount > 1 ? 's' : ''}` : 'All settings saved'}
        </span>
        <div style="display:flex;gap:8px;align-items:center">
          ${status === 'saved' && html`<span style="font-size:0.75rem;color:var(--success)">Saved</span>`}
          ${status === 'error' && html`<span style="font-size:0.75rem;color:var(--error)">Failed</span>`}
          ${changeCount > 0 && html`<button class="btn btn-ghost" onClick=${() => { setChanges({}); setStatus(null); }}>Discard</button>`}
          <button class="btn btn-primary" onClick=${handleSave} disabled=${saving || changeCount === 0}>
            ${saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      ${knownSections.map(s => renderSection(s))}

      ${merged.agents && Object.keys(merged.agents).length > 0 && html`
        <div class="card" style="margin-bottom:12px">
          <div class="card-header">
            <span class="card-title">Agent Profiles</span>
            <span style="font-size:0.6875rem;color:var(--text-tertiary)">Per-agent configuration</span>
          </div>
          ${Object.entries(merged.agents).map(([agentName, agentConf]) => html`
            <div key=${agentName} style="margin-bottom:12px">
              <div style="font-size:0.75rem;font-weight:600;color:var(--accent);padding:8px 0 4px;border-bottom:1px solid var(--border)">${agentName}</div>
              ${Object.entries(AGENT_SCHEMA).map(([key, field]) => {
                const val = agentConf[key];
                if (val === undefined) return null;
                const path = 'agents.' + agentName + '.' + key;
                return html`
                  <div class="config-row" key=${path} style="padding:8px 0;border-bottom:1px solid var(--border-subtle);display:flex;align-items:center;gap:12px">
                    <div style="flex:1">
                      <div style="font-size:0.8125rem;color:var(--text);font-weight:500">${field.label}</div>
                      ${field.desc && html`<div style="font-size:0.6875rem;color:var(--text-tertiary);margin-top:1px">${field.desc}</div>`}
                    </div>
                    <div style="display:flex;align-items:center;justify-content:flex-end">
                      ${field.type === 'select' && html`<select class="config-input" value=${val} onChange=${(e) => handleChange(path, e.target.value)}>${field.options.map(o => html`<option key=${o} value=${o}>${o}</option>`)}</select>`}
                      ${field.type === 'readonly' && html`<span class="mono" style="font-size:0.6875rem;color:var(--text-secondary)">${Array.isArray(val) ? val.join(', ') : String(val)}</span>`}
                    </div>
                  </div>
                `;
              })}
            </div>
          `)}
        </div>
      `}

      ${unknownSections.map(s => html`
        <div class="card" style="margin-bottom:12px" key=${s}>
          <div class="card-header"><span class="card-title">${s}</span></div>
          ${Object.entries(merged[s] || {}).map(([k, v]) => html`
            <div class="config-row" key="${s}.${k}" style="padding:8px 0">
              <span style="flex:1;font-size:0.8125rem">${k}</span>
              <span class="mono" style="font-size:0.75rem;color:var(--text-secondary)">${typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
            </div>
          `)}
        </div>
      `)}
    </div>
  `;
}

export default Settings;
