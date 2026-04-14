/**
 * OverviewPage — Main dashboard landing page.
 *
 * Fetches overview + agents + sessions + budget data on mount,
 * then subscribes to store for live updates.
 */

import { html } from 'htm/preact';
import { useEffect, useState } from 'preact/hooks';
import store from '../store.js';
import api from '../api.js';
import Overview from '../components/Overview.js';

export function OverviewPage() {
  const [state, setState] = useState(store.getState());

  useEffect(() => {
    // Initial data fetch
    async function loadData() {
      try {
        const [overview, agents, sessions, budget] = await Promise.all([
          api.overview().catch(() => null),
          api.agents().catch(() => []),
          api.sessions().catch(() => []),
          api.budget().catch(() => null),
        ]);
        store.update({ overview, agents, sessions, budget, loading: false });
      } catch (e) {
        store.update({ loading: false, error: e.message });
      }
    }
    loadData();

    // Subscribe to store updates
    const unsub = store.subscribe((s) => setState({ ...s }));
    return unsub;
  }, []);

  return html`
    <div class="page">
      <${Overview}
        overview=${state.overview}
        agents=${state.agents}
        sessions=${state.sessions}
        budget=${state.budget}
        loading=${state.loading}
      />
    </div>
  `;
}

export default OverviewPage;
