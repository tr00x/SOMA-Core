/* ============================================================
   SOMA Dashboard v2 — Overview Tab
   ============================================================ */

window.SOMA = window.SOMA || {};
SOMA.tabs = SOMA.tabs || {};

SOMA.tabs.overview = () => ({
  // --- Overview tab state ---
  overviewToolUsage: [],
  overviewHeatmap: [],
  overviewPredictions: {},
  overviewPatterns: [],
  overviewHeatmapChart: null,
  overviewToolChart: null,
  _overviewSparklines: {},
  _overviewLoaded: false,

  // =========================================================
  // Computed helpers
  // =========================================================

  /** Max pressure across all agents */
  overviewMaxPressure() {
    if (!this.agents || this.agents.length === 0) return 0;
    return Math.max(...this.agents.map(a => a.pressure || 0));
  },

  /** Worst mode across all agents */
  overviewWorstMode() {
    const order = ['OBSERVE', 'GUIDE', 'WARN', 'BLOCK'];
    let worst = 0;
    (this.agents || []).forEach(a => {
      const m = this.modeLabel(a.level || a.mode);
      const idx = order.indexOf(m);
      if (idx > worst) worst = idx;
    });
    return order[worst];
  },

  /** Budget health as percentage */
  overviewBudgetHealth() {
    if (!this.budgetData) return 100;
    const h = this.budgetData.health;
    if (h != null) return Math.round(h * 100);
    // Fallback: compute from used_pct
    const pcts = Object.values(this.budgetData.used_pct || {});
    if (pcts.length === 0) return 100;
    const maxUsed = Math.max(...pcts);
    return Math.round((1 - maxUsed) * 100);
  },

  /** Active agent count */
  overviewAgentCount() {
    return (this.agents || []).length;
  },

  /** Session capacity — sum of remaining actions across agents */
  overviewCapacity() {
    let total = 0;
    let hasCapacity = false;
    (this.agents || []).forEach(a => {
      if (a.capacity_remaining != null) {
        total += a.capacity_remaining;
        hasCapacity = true;
      }
    });
    return hasCapacity ? total : null;
  },

  /** Cascade risk — true if any agent has subagents */
  overviewHasCascadeRisk() {
    return (this.agents || []).some(a => a.has_subagents || a.cascade_risk > 0);
  },

  /** Agents with RCA diagnoses */
  overviewRCAAgents() {
    return (this.agents || []).filter(a => a.rca_diagnosis);
  },

  /** Agents predicted to escalate */
  overviewEscalationAgents() {
    const preds = this.overviewPredictions || {};
    const results = [];
    for (const [aid, pred] of Object.entries(preds)) {
      if (pred && pred.will_escalate) {
        results.push({
          agent_id: aid,
          actions_ahead: pred.actions_ahead || '?',
          reason: pred.dominant_reason || pred.reason || 'pressure trend',
          confidence: pred.confidence,
        });
      }
    }
    return results;
  },

  /** Top 5 findings sorted by priority */
  overviewTopFindings() {
    const priorityOrder = { critical: 0, important: 1, warning: 2, info: 3, positive: 4 };
    return (this.findings || [])
      .slice()
      .sort((a, b) => {
        const pa = priorityOrder[a.priority] ?? 3;
        const pb = priorityOrder[b.priority] ?? 3;
        return pa - pb;
      })
      .slice(0, 5);
  },

  /** Budget dimensions for sidebar gauges */
  overviewBudgetDimensions() {
    const dims = [];
    const limits = this.budgetData?.limits || {};
    const spent = this.budgetData?.spent || {};
    const usedPct = this.budgetData?.used_pct || {};
    const remaining = this.budgetData?.remaining || {};
    for (const dim of Object.keys(limits)) {
      dims.push({
        name: dim,
        limit: limits[dim],
        spent: spent[dim] || 0,
        pct: (usedPct[dim] || 0) / 100,
        remaining: remaining[dim] || 0,
      });
    }
    return dims;
  },

  // =========================================================
  // Data loading
  // =========================================================

  async loadOverviewTab() {
    // Fetch sidebar data in parallel
    const [toolUsage, heatmap, predictions, patterns] = await Promise.all([
      SOMA.api.fetchToolUsage().catch(() => []),
      SOMA.api.fetchHeatmap().catch(() => []),
      SOMA.api.fetchPredictions ? SOMA.api.fetchPredictions().catch(() => ({})) : Promise.resolve({}),
      SOMA.api.fetchPatterns ? SOMA.api.fetchPatterns().catch(() => []) : Promise.resolve([]),
    ]);

    // API may return dict {tool: count} or array [{name, count}] — normalize
    if (toolUsage && !Array.isArray(toolUsage)) {
      this.overviewToolUsage = Object.entries(toolUsage).map(([name, count]) => ({ name, count }));
    } else {
      this.overviewToolUsage = toolUsage || [];
    }
    this.overviewHeatmap = Array.isArray(heatmap) ? heatmap : (heatmap?.hours || []);
    this.overviewPredictions = predictions || {};
    this.overviewPatterns = Array.isArray(patterns) ? patterns : [];

    this._overviewLoaded = true;

    // Render charts after DOM updates
    this.$nextTick(() => {
      this._renderOverviewCharts();
      this._renderOverviewSparklines();
      if (typeof lucide !== 'undefined') lucide.createIcons();
    });
  },

  // =========================================================
  // Chart rendering
  // =========================================================

  _renderOverviewCharts() {
    // Heatmap
    this.overviewHeatmapChart = SOMA.charts.destroyChart(this.overviewHeatmapChart);
    if (this.overviewHeatmap.length > 0) {
      this.overviewHeatmapChart = SOMA.charts.createHeatmap('overview-heatmap', this.overviewHeatmap);
    }

    // Tool usage bar chart
    this.overviewToolChart = SOMA.charts.destroyChart(this.overviewToolChart);
    const tools = (this.overviewToolUsage || []).slice(0, 5);
    if (tools.length > 0) {
      const labels = tools.map(t => t.tool || t.name || t[0] || '');
      const values = tools.map(t => t.count || t.usage || t[1] || 0);
      this.overviewToolChart = SOMA.charts.createBarChart('overview-tool-usage', labels, values);
    }
  },

  _renderOverviewSparklines() {
    // Destroy old sparklines
    for (const [key, chart] of Object.entries(this._overviewSparklines)) {
      SOMA.charts.destroyChart(chart);
    }
    this._overviewSparklines = {};

    // Create sparklines for each agent
    (this.agents || []).forEach((agent, idx) => {
      const canvasId = 'sparkline-' + idx;
      const trajectory = agent.trajectory || agent.pressure_history || [];
      if (trajectory.length > 0) {
        const chart = SOMA.charts.createSparkline(canvasId, trajectory);
        if (chart) this._overviewSparklines[canvasId] = chart;
      }
    });
  },

  // =========================================================
  // Agent card interactions
  // =========================================================

  selectAgent(agent) {
    this.ddAgent = agent;
    this.ddAgentId = agent.agent_id;
    this.switchTab('deep-dive');
    this.$nextTick(() => {
      if (typeof this.ddSelectAgent === 'function') {
        this.ddSelectAgent(agent.agent_id);
      }
    });
  },

  // =========================================================
  // Formatting helpers specific to Overview
  // =========================================================

  halfLifeColor(agent) {
    const hl = agent.half_life;
    if (hl == null) return '#555';
    if (hl >= 0.7) return '#00ff88';
    if (hl >= 0.4) return '#ffaa00';
    return '#ff4444';
  },

  halfLifeLabel(agent) {
    const hl = agent.half_life;
    if (hl == null) return 'N/A';
    if (hl >= 0.7) return 'Healthy';
    if (hl >= 0.4) return 'Declining';
    return 'Critical';
  },

  findingColor(priority, category) {
    // Handle numeric priorities (0=critical, 1=important, 2=info)
    if (priority === 0) return { bg: 'rgba(255,68,68,0.08)', border: '#ff4444', text: '#ff4444', icon: 'alert-triangle' };
    if (priority === 1) return { bg: 'rgba(255,140,0,0.08)', border: '#ff8c00', text: '#ff8c00', icon: 'alert-circle' };
    // Category-based for priority 2
    if (category === 'positive') return { bg: 'rgba(0,255,136,0.08)', border: '#00ff88', text: '#00ff88', icon: 'check-circle' };
    if (category === 'rca') return { bg: 'rgba(255,170,0,0.08)', border: '#ffaa00', text: '#ffaa00', icon: 'search' };
    if (category === 'fingerprint') return { bg: 'rgba(255,45,120,0.08)', border: '#ff2d78', text: '#ff2d78', icon: 'fingerprint' };
    if (category === 'pattern') return { bg: 'rgba(255,140,0,0.08)', border: '#ff8c00', text: '#ff8c00', icon: 'activity' };
    if (category === 'predict') return { bg: 'rgba(255,170,0,0.08)', border: '#ffaa00', text: '#ffaa00', icon: 'trending-up' };
    return { bg: 'rgba(255,255,255,0.03)', border: '#333', text: '#999', icon: 'info' };
  },

  circuitBreakerBadge(state) {
    if (!state) return null;
    const s = String(state).toUpperCase();
    if (s === 'OPEN') return 'badge-open';
    if (s === 'HALF_OPEN' || s === 'HALF-OPEN') return 'badge-half-open';
    return 'badge-closed';
  },

  patternIcon(type) {
    switch (type) {
      case 'loop': return 'repeat';
      case 'thrashing': return 'shuffle';
      case 'escalation': return 'trending-up';
      case 'recovery': return 'trending-down';
      default: return 'activity';
    }
  },

  budgetBarColor(pct) {
    if (pct >= 0.9) return '#ff4444';
    if (pct >= 0.7) return '#ff8c00';
    if (pct >= 0.5) return '#ffaa00';
    return '#ff2d78';
  },

  formatDimName(name) {
    return String(name).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  },
});

// ---------------------------------------------------------
// Fetch predictions + patterns (add to api if missing)
// ---------------------------------------------------------
(function() {
  if (!SOMA.api.fetchPredictions) {
    SOMA.api.fetchPredictions = async function() {
      try {
        const r = await fetch('/api/predictions');
        if (!r.ok) return {};
        return r.json();
      } catch (_) { return {}; }
    };
  }
  if (!SOMA.api.fetchPatterns) {
    SOMA.api.fetchPatterns = async function() {
      try {
        const r = await fetch('/api/patterns');
        if (!r.ok) return [];
        return r.json();
      } catch (_) { return []; }
    };
  }
})();
