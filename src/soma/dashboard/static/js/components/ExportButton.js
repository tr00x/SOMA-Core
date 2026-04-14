/**
 * ExportButton — Download session data as JSON or CSV.
 */

import { html } from 'htm/preact';
import { useState } from 'preact/hooks';
import api from '../api.js';

export function ExportButton({ sessionId }) {
  const [open, setOpen] = useState(false);

  if (!sessionId) return null;

  function download(format) {
    const url = api.sessionExportUrl(sessionId, format);
    window.open(url, '_blank');
    setOpen(false);
  }

  return html`
    <div style="position:relative">
      <button class="btn btn-sm" onClick=${() => setOpen(!open)} aria-label="Export session data">
        Export
      </button>
      ${open && html`
        <div style="position:absolute;right:0;top:100%;margin-top:4px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;z-index:10;min-width:100px;box-shadow:var(--shadow-lg)"
             role="menu">
          <button style="display:block;width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:0.8125rem;cursor:pointer;text-align:left;font-family:var(--font-mono)"
                  onClick=${() => download('json')}
                  role="menuitem">
            JSON
          </button>
          <button style="display:block;width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:0.8125rem;cursor:pointer;text-align:left;font-family:var(--font-mono);border-top:1px solid var(--border-subtle)"
                  onClick=${() => download('csv')}
                  role="menuitem">
            CSV
          </button>
        </div>
      `}
    </div>
  `;
}

export default ExportButton;
