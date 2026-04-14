/**
 * SOMA Dashboard — API Client
 *
 * Thin fetch wrapper for all /api/* endpoints.
 */

const BASE = '';

async function request(path, opts = {}) {
  const url = `${BASE}${path}`;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
    });
    if (!res.ok) {
      throw new Error(`API ${res.status}: ${res.statusText}`);
    }
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      return await res.json();
    }
    return await res.text();
  } catch (err) {
    console.error(`[api] ${opts.method || 'GET'} ${path} failed:`, err);
    throw err;
  }
}

export const api = {
  // Overview
  overview: () => request('/api/overview'),

  // Agents
  agents: () => request('/api/agents'),
  agent: (id) => request(`/api/agents/${encodeURIComponent(id)}`),
  agentTimeline: (id) => request(`/api/agents/${encodeURIComponent(id)}/timeline`),
  agentPressureHistory: (id) => request(`/api/agents/${encodeURIComponent(id)}/pressure-history`),
  agentPredictions: (id) => request(`/api/agents/${encodeURIComponent(id)}/predictions`),
  agentTools: (id) => request(`/api/agents/${encodeURIComponent(id)}/tools`),
  agentAudit: (id) => request(`/api/agents/${encodeURIComponent(id)}/audit`),
  agentGuidance: (id) => request(`/api/agents/${encodeURIComponent(id)}/guidance`),
  agentQuality: (id) => request(`/api/agents/${encodeURIComponent(id)}/quality`),
  agentFingerprint: (id) => request(`/api/agents/${encodeURIComponent(id)}/fingerprint`),
  agentBaselines: (id) => request(`/api/agents/${encodeURIComponent(id)}/baselines`),
  agentLearning: (id) => request(`/api/agents/${encodeURIComponent(id)}/learning`),
  agentFindings: (id) => request(`/api/agents/${encodeURIComponent(id)}/findings`),

  // Sessions
  sessions: () => request('/api/sessions'),
  session: (id) => request(`/api/sessions/${encodeURIComponent(id)}`),
  sessionExportUrl: (id, format = 'json') =>
    `/api/sessions/${encodeURIComponent(id)}/export?format=${format}`,

  // Budget
  budget: () => request('/api/budget'),

  // Graph
  graph: () => request('/api/graph'),

  // Heatmap
  heatmap: (agentId) => request(`/api/heatmap?agent_id=${encodeURIComponent(agentId)}`),

  // Config
  config: () => request('/api/config'),
  updateConfig: (data) =>
    request('/api/config', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

export default api;
