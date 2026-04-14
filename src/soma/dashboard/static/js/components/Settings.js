/**
 * Settings — Config editor with inline editing and save.
 */

import { html } from 'htm/preact';
import { useState, useCallback } from 'preact/hooks';
import api from '../api.js';

function isObject(v) {
  return v != null && typeof v === 'object' && !Array.isArray(v);
}

function ConfigValue({ path, value, onChange }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  function startEdit() {
    setDraft(typeof value === 'string' ? value : JSON.stringify(value));
    setEditing(true);
  }

  function commit() {
    setEditing(false);
    let parsed = draft;
    // Try parsing as number or boolean
    if (draft === 'true') parsed = true;
    else if (draft === 'false') parsed = false;
    else if (draft !== '' && !isNaN(Number(draft))) parsed = Number(draft);
    onChange(path, parsed);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') commit();
    if (e.key === 'Escape') setEditing(false);
  }

  if (editing) {
    return html`
      <input class="config-input"
             value=${draft}
             onInput=${(e) => setDraft(e.target.value)}
             onBlur=${commit}
             onKeyDown=${handleKeyDown}
             autoFocus />
    `;
  }

  const display = value === true ? 'true' :
                  value === false ? 'false' :
                  value == null ? 'null' :
                  typeof value === 'number' ? String(value) :
                  String(value);

  return html`
    <span class="config-value"
          onClick=${startEdit}
          onKeyDown=${(e) => (e.key === 'Enter') && startEdit()}
          tabindex="0"
          role="button"
          aria-label="Edit ${path}"
          style="cursor:pointer;border-bottom:1px dashed var(--border)">
      ${display}
    </span>
  `;
}

function ConfigSection({ title, data, basePath = '', onChange }) {
  if (!data || typeof data !== 'object') return null;

  const entries = Object.entries(data);

  return html`
    <div class="config-section">
      ${title && html`<div class="config-section-title">${title}</div>`}
      ${entries.map(([key, val]) => {
        const fullPath = basePath ? `${basePath}.${key}` : key;
        if (isObject(val)) {
          return html`<${ConfigSection} key=${fullPath} title=${key} data=${val} basePath=${fullPath} onChange=${onChange} />`;
        }
        if (Array.isArray(val)) {
          return html`
            <div class="config-row" key=${fullPath}>
              <span class="config-key">${key}</span>
              <span class="config-value mono" style="font-size:0.6875rem">[${val.join(', ')}]</span>
            </div>
          `;
        }
        return html`
          <div class="config-row" key=${fullPath}>
            <span class="config-key">${key}</span>
            <${ConfigValue} path=${fullPath} value=${val} onChange=${onChange} />
          </div>
        `;
      })}
    </div>
  `;
}

export function Settings({ config }) {
  const [saving, setSaving] = useState(false);
  const [changes, setChanges] = useState({});
  const [saveStatus, setSaveStatus] = useState(null);

  const handleChange = useCallback((path, value) => {
    setChanges(prev => ({ ...prev, [path]: value }));
  }, []);

  async function handleSave() {
    if (!Object.keys(changes).length) return;
    setSaving(true);
    setSaveStatus(null);
    try {
      // Build nested object from dot paths
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
      await api.updateConfig(payload);
      setSaveStatus('saved');
      setChanges({});
      setTimeout(() => setSaveStatus(null), 2000);
    } catch (e) {
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  }

  if (!config || Object.keys(config).length === 0) {
    return html`
      <div class="card empty-state">
        <div class="empty-state-title">No configuration loaded</div>
        <div class="empty-state-text">Configuration will appear once soma.toml is detected.</div>
      </div>
    `;
  }

  const changeCount = Object.keys(changes).length;

  return html`
    <div class="animate-in">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div>
          <span style="font-size:0.75rem;color:var(--text-tertiary)">
            Click any value to edit. Changes are saved to soma.toml.
          </span>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          ${saveStatus === 'saved' && html`
            <span style="font-size:0.75rem;color:var(--success)">Saved</span>
          `}
          ${saveStatus === 'error' && html`
            <span style="font-size:0.75rem;color:var(--error)">Save failed</span>
          `}
          <button class="btn btn-primary"
                  onClick=${handleSave}
                  disabled=${saving || changeCount === 0}>
            ${saving ? 'Saving...' : `Save${changeCount > 0 ? ` (${changeCount})` : ''}`}
          </button>
        </div>
      </div>

      <div class="card">
        <${ConfigSection} data=${config} onChange=${handleChange} />
      </div>
    </div>
  `;
}

export default Settings;
