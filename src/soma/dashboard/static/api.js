/* ============================================================
   SOMA Dashboard v2 — API Layer (fetch + SSE)
   ============================================================ */

window.SOMA = window.SOMA || {};

SOMA.api = (() => {
  let _sseSource = null;
  let _pollInterval = null;
  let _pollContext = null;
  let _reconnectTimer = null;
  const POLL_INTERVAL = 3000;

  // ---------------------------------------------------------
  // SSE Connection
  // ---------------------------------------------------------
  function connectSSE(ctx) {
    _pollContext = ctx;

    if (typeof EventSource === 'undefined') {
      _startPolling(ctx);
      return;
    }

    try {
      _sseSource = new EventSource('/api/stream');

      _sseSource.onopen = () => {
        ctx.connected = true;
        _stopPolling();
        if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
      };

      _sseSource.addEventListener('agents', (e) => {
        try {
          const data = JSON.parse(e.data);
          _updateAgents(ctx, data);
        } catch (_) {}
      });

      _sseSource.addEventListener('budget', (e) => {
        try {
          const b = JSON.parse(e.data);
          // Compute used_pct if missing
          if (!b.used_pct && b.limits && b.spent) {
            b.used_pct = {};
            for (const k of Object.keys(b.limits)) {
              b.used_pct[k] = b.limits[k] > 0 ? (b.spent[k] || 0) / b.limits[k] * 100 : 0;
            }
          }
          ctx.budgetData = b;
        } catch (_) {}
      });

      _sseSource.addEventListener('alert', (e) => {
        try {
          const data = JSON.parse(e.data);
          ctx.addToast('warn', 'Alert', data.message || 'Mode change detected');
        } catch (_) {}
      });

      _sseSource.addEventListener('reflex', (e) => {
        try {
          const data = JSON.parse(e.data);
          ctx.addToast('info', 'Reflex', data.kind || 'Reflex triggered');
        } catch (_) {}
      });

      _sseSource.addEventListener('findings', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (Array.isArray(data) && data.length > 0) ctx.findings = data;
        } catch (_) {}
      });

      // RCA events silently update state — no toast spam
      _sseSource.addEventListener('rca', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.agent_id && ctx.agents) {
            const agent = ctx.agents.find(a => a.agent_id === data.agent_id);
            if (agent) agent.rca_diagnosis = data.diagnosis;
          }
        } catch (_) {}
      });

      _sseSource.onerror = () => {
        ctx.connected = false;
        _sseSource.close();
        _sseSource = null;
        // Fallback to polling after 5s
        if (!_reconnectTimer) {
          _reconnectTimer = setTimeout(() => {
            _reconnectTimer = null;
            _startPolling(ctx);
            // Try reconnecting SSE after another 10s
            setTimeout(() => connectSSE(ctx), 10000);
          }, 5000);
        }
      };
    } catch (_) {
      _startPolling(ctx);
    }
  }

  function _updateAgents(ctx, agents) {
    const oldModes = { ...ctx.prevModes };
    ctx.agents = agents || [];
    ctx.connected = true;
    ctx.agents.forEach(a => {
      const m = ctx.modeLabel(a.level || a.mode);
      const prev = oldModes[a.agent_id];
      if (prev && prev !== m) {
        ctx.addToast(
          m === 'BLOCK' || m === 'WARN' ? 'warn' : 'info',
          'Mode Change',
          ctx.stripPrefix(a.agent_id) + ': ' + prev + ' -> ' + m
        );
      }
      ctx.prevModes[a.agent_id] = m;
    });
  }

  function _startPolling(ctx) {
    if (_pollInterval) return;
    _pollInterval = setInterval(async () => {
      try {
        const overview = await fetchOverview();
        _updateAgents(ctx, overview.agents || []);
        // Only replace findings if API has data (don't clear with empty)
        if (overview.findings && overview.findings.length > 0) {
          ctx.findings = overview.findings;
        }
      } catch (_) { ctx.connected = false; }
      try {
        ctx.budgetData = await fetchBudget();
      } catch (_) {}
    }, POLL_INTERVAL);
  }

  function _stopPolling() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  // ---------------------------------------------------------
  // Generic fetch helper
  // ---------------------------------------------------------
  async function _fetch(url, options) {
    const r = await fetch(url, options);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    if (_pollContext) _pollContext.connected = true;
    return r.json();
  }

  async function _fetchSafe(url, fallback) {
    try {
      return await _fetch(url);
    } catch (_) {
      if (_pollContext) _pollContext.connected = false;
      return fallback;
    }
  }

  // ---------------------------------------------------------
  // Data fetchers
  // ---------------------------------------------------------
  async function fetchOverview() {
    return _fetchSafe('/api/overview', { agents: [], findings: [], sessions: [], audit: [] });
  }

  async function fetchAgents() {
    return _fetchSafe('/api/agents', []);
  }

  async function fetchAgent(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id), {});
  }

  async function fetchTrajectory(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/trajectory', []);
  }

  async function fetchActions(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/actions', []);
  }

  async function fetchQuality(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/quality', {});
  }

  async function fetchBudget() {
    return _fetchSafe('/api/budget', { health: 1, limits: {}, spent: {}, used_pct: {}, remaining: {} });
  }

  async function fetchConfig() {
    return _fetchSafe('/api/config', {});
  }

  async function fetchToolUsage() {
    return _fetchSafe('/api/tool-usage', []);
  }

  async function fetchHeatmap() {
    return _fetchSafe('/api/activity-heatmap', []);
  }

  async function fetchDetailedLogs() {
    return _fetchSafe('/api/audit', []);
  }

  async function fetchReflexes(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/reflexes', []);
  }

  async function fetchRCA(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/rca', {});
  }

  async function fetchMirror(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/mirror', {});
  }

  async function fetchContext(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/context', {});
  }

  async function fetchSessionMemory(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/session-memory', {});
  }

  async function fetchCapacity(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/capacity', {});
  }

  async function fetchCircuitBreaker(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/circuit-breaker', {});
  }

  async function fetchScope(id) {
    return _fetchSafe('/api/agent/' + encodeURIComponent(id) + '/scope', {});
  }

  async function fetchSubagents(parentId) {
    return _fetchSafe('/api/subagents/' + encodeURIComponent(parentId), { cascade_risk: 0, subagents: [] });
  }

  async function fetchAnalyticsTrends(id) {
    return _fetchSafe('/api/analytics/trends/' + encodeURIComponent(id), []);
  }

  async function fetchAnalyticsTools(id) {
    return _fetchSafe('/api/analytics/tools/' + encodeURIComponent(id), []);
  }

  async function fetchSessions() {
    return _fetchSafe('/api/sessions', []);
  }

  async function fetchPolicies() {
    return _fetchSafe('/api/policies', []);
  }

  async function fetchSessionReport(id) {
    return _fetchSafe('/api/sessions/' + encodeURIComponent(id) + '/report', {});
  }

  async function fetchSessionRecord(id) {
    return _fetchSafe('/api/sessions/' + encodeURIComponent(id) + '/record', {});
  }

  async function fetchThresholdTuner() {
    return _fetchSafe('/api/threshold-tuner/status', {});
  }

  async function saveConfig(section, values) {
    try {
      return await _fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section, values }),
      });
    } catch (_) {
      return { error: true };
    }
  }

  async function patchSettings(section, data) {
    try {
      return await _fetch('/api/settings/' + encodeURIComponent(section), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    } catch (_) {
      return { error: true };
    }
  }

  async function fetchPredictions() {
    return _fetchSafe('/api/predictions', {});
  }

  async function fetchFingerprints() {
    return _fetchSafe('/api/fingerprints', {});
  }

  async function fetchPatterns() {
    return _fetchSafe('/api/patterns', {});
  }

  // ---------------------------------------------------------
  // Public API
  // ---------------------------------------------------------
  return {
    connectSSE,
    fetchOverview,
    fetchAgents,
    fetchAgent,
    fetchTrajectory,
    fetchActions,
    fetchQuality,
    fetchBudget,
    fetchConfig,
    fetchToolUsage,
    fetchHeatmap,
    fetchDetailedLogs,
    fetchReflexes,
    fetchRCA,
    fetchMirror,
    fetchContext,
    fetchSessionMemory,
    fetchCapacity,
    fetchCircuitBreaker,
    fetchScope,
    fetchSubagents,
    fetchAnalyticsTrends,
    fetchAnalyticsTools,
    fetchSessions,
    fetchPolicies,
    fetchSessionReport,
    fetchSessionRecord,
    fetchThresholdTuner,
    fetchPredictions,
    fetchFingerprints,
    fetchPatterns,
    saveConfig,
    patchSettings,
  };
})();
