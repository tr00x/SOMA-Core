/**
 * SessionPage — Detail page for a single session or session list.
 */

import { html } from 'htm/preact';
import { useEffect, useState } from 'preact/hooks';
import api from '../api.js';
import store from '../store.js';
import SessionDetail from '../components/SessionDetail.js';
import SessionList from '../components/SessionList.js';

export function SessionPage({ id }) {
  // If we have an id, show detail; otherwise show list
  if (id) {
    return html`<${SessionDetailView} id=${id} />`;
  }
  return html`<${SessionListView} />`;
}

function SessionListView() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.sessions()
      .then(s => { setSessions(Array.isArray(s) ? s : []); setLoading(false); })
      .catch(() => setLoading(false));

    const unsub = store.subscribe((s) => {
      if (s.sessions && s.sessions.length) setSessions(s.sessions);
    });
    return unsub;
  }, []);

  return html`
    <div class="page animate-in">
      <div class="page-header">
        <h1>Sessions</h1>
        <span style="font-size:0.8125rem;color:var(--text-tertiary);margin-left:8px">
          ${sessions.length} total
        </span>
      </div>

      ${loading
        ? html`
          <div class="card">
            ${[1, 2, 3, 4, 5].map(i => html`<div class="skeleton skeleton-row" key=${i}></div>`)}
          </div>
        `
        : html`
          <div class="card">
            <${SessionList} sessions=${sessions} showAll=${true} />
          </div>
        `
      }
    </div>
  `;
}

function SessionDetailView({ id }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.session(id)
      .then(s => { setSession(s); setLoading(false); })
      .catch(() => setLoading(false));
  }, [id]);

  if (loading) {
    return html`
      <div class="page">
        <div class="skeleton skeleton-stat" style="width:200px;margin-bottom:16px"></div>
        <div class="skeleton skeleton-chart"></div>
      </div>
    `;
  }

  if (!session) {
    return html`
      <div class="page">
        <div class="card empty-state">
          <div class="empty-state-title">Session not found</div>
          <div class="empty-state-text">Session "${id}" could not be found.</div>
        </div>
      </div>
    `;
  }

  return html`
    <div class="page animate-in">
      <div class="page-header">
        <div class="breadcrumb">
          <a href="/sessions"
             onClick=${(e) => { e.preventDefault(); history.pushState(null, '', '/sessions'); dispatchEvent(new PopStateEvent('popstate')); }}>
            Sessions
          </a>
          <span style="margin:0 6px;color:var(--text-tertiary)">/</span>
        </div>
        <h1 style="font-family:var(--font-mono);font-size:1rem">${session.session_id}</h1>
      </div>

      <${SessionDetail} session=${session} />
    </div>
  `;
}

export default SessionPage;
