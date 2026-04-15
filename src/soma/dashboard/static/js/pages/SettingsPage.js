/**
 * SettingsPage — Config editor page.
 */

import { html } from 'htm/preact';
import { useEffect, useState } from 'preact/hooks';
import api from '../api.js';
import Settings from '../components/Settings.js';

export function SettingsPage() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.config()
      .then(c => { setConfig(c); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return html`
    <div class="page animate-in">
      <div class="page-header">
        <h1>Settings</h1>
      </div>

      ${loading
        ? html`
          <div class="card">
            ${[1, 2, 3, 4, 5, 6].map(i => html`<div class="skeleton skeleton-row" key=${i}></div>`)}
          </div>
        `
        : html`<${Settings} config=${config} onConfigUpdate=${(c) => setConfig(c)} />`
      }
    </div>
  `;
}

export default SettingsPage;
