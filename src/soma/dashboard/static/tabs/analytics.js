/* ============================================================
   SOMA Dashboard v2 — Analytics Tab
   ============================================================ */

window.SOMA = window.SOMA || {};
SOMA.tabs = SOMA.tabs || {};

SOMA.tabs.analytics = () => ({
  // --- Analytics tab state ---
  analyticsTrends: [],
  analyticsTools: [],
  analyticsTrendChart: null,
  analyticsToolChart: null,
  analyticsSelectedAgent: null,
  analyticsLoading: false,

  // Mirror effectiveness
  analyticsMirror: {},
  analyticsMirrorChart: null,

  // Threshold performance
  analyticsThreshold: {},

  // Session comparison
  analyticsCompareA: null,
  analyticsCompareB: null,
  analyticsCompareDataA: null,
  analyticsCompareDataB: null,

  // =========================================================
  // Load analytics
  // =========================================================
  async loadAnalyticsTab(agentId) {
    this.analyticsLoading = true;
    // Wait for agents to load if needed
    if (!this.agents || this.agents.length === 0) {
      try {
        const overview = await SOMA.api.fetchOverview();
        this.agents = overview.agents || [];
      } catch (_) {}
    }
    const id = agentId || this.analyticsSelectedAgent || (this.agents && this.agents[0] && this.agents[0].agent_id) || '';
    if (!id) {
      this.analyticsLoading = false;
      return;
    }
    this.analyticsSelectedAgent = id;

    // Fetch all data in parallel
    try {
      const [trends, tools, mirror, threshold] = await Promise.all([
        SOMA.api.fetchAnalyticsTrends(id),
        SOMA.api.fetchAnalyticsTools(id),
        SOMA.api.fetchMirror(id).catch(() => ({})),
        SOMA.api.fetchThresholdTuner().catch(() => ({})),
      ]);
      this.analyticsTrends = Array.isArray(trends) ? trends : [];
      // Tools API returns {name: count} dict — normalize to array
      if (tools && !Array.isArray(tools) && typeof tools === 'object') {
        this.analyticsTools = Object.entries(tools).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
      } else {
        this.analyticsTools = tools || [];
      }
      const mr = mirror || {};
      this.analyticsMirror = { ...(mr.stats || {}), patterns: mr.stats?.patterns || mr.patterns || {} };
      this.analyticsThreshold = threshold || {};
      console.log('[SOMA analytics] trends:', this.analyticsTrends.length, 'tools:', this.analyticsTools.length);
    } catch (e) { console.error('[SOMA analytics] error:', e); }

    this.analyticsLoading = false;

    // Build charts after DOM update
    this.$nextTick(() => {
      this._buildAnalyticsCharts();
      if (typeof lucide !== 'undefined') lucide.createIcons();
    });
  },

  // =========================================================
  // Build charts
  // =========================================================
  _buildAnalyticsCharts() {
    // Trend chart
    this.analyticsTrendChart = SOMA.charts.destroyChart(this.analyticsTrendChart);
    if (this.analyticsTrends.length >= 1) {
      this.analyticsTrendChart = SOMA.charts.createTrendChart('analytics-trend-chart', this.analyticsTrends);
    }

    // Tool histogram
    this.analyticsToolChart = SOMA.charts.destroyChart(this.analyticsToolChart);
    const toolData = this.analyticsTools || [];
    if (toolData.length > 0) {
      const labels = toolData.map(t => t.tool || t.name || '');
      const values = toolData.map(t => t.count || t.usage || 0);
      this.analyticsToolChart = SOMA.charts.createBarChart('analytics-tool-chart', labels, values);
    }

    // Mirror chart
    this.analyticsMirrorChart = SOMA.charts.destroyChart(this.analyticsMirrorChart);
    const mirrorHistory = this.analyticsMirror?.effectiveness_history || [];
    if (mirrorHistory.length >= 2) {
      const canvas = document.getElementById('analytics-mirror-chart');
      if (canvas) {
        this.analyticsMirrorChart = new Chart(canvas.getContext('2d'), {
          type: 'line',
          data: {
            labels: mirrorHistory.map((_, i) => i + 1),
            datasets: [{
              label: 'Effectiveness %',
              data: mirrorHistory.map(d => typeof d === 'number' ? d : d.rate || 0),
              borderColor: '#ff2d78',
              backgroundColor: 'rgba(255, 45, 120, 0.1)',
              fill: true,
              tension: 0.3,
              pointRadius: 3,
              pointBackgroundColor: '#ff2d78',
              borderWidth: 2,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { color: '#1e1e1e' }, ticks: { color: '#666', font: { size: 10 } } },
              y: { grid: { color: '#1e1e1e' }, ticks: { color: '#666', font: { size: 10 } }, min: 0, max: 100 },
            },
          },
        });
      }
    }
  },

  // =========================================================
  // Session comparison
  // =========================================================
  async loadComparison() {
    if (!this.analyticsCompareA || !this.analyticsCompareB) return;
    try {
      const [a, b] = await Promise.all([
        SOMA.api.fetchSessionRecord(this.analyticsCompareA),
        SOMA.api.fetchSessionRecord(this.analyticsCompareB),
      ]);
      this.analyticsCompareDataA = a || {};
      this.analyticsCompareDataB = b || {};
    } catch (_) {}
  },

  comparisonMetrics() {
    if (!this.analyticsCompareDataA || !this.analyticsCompareDataB) return [];
    const a = this.analyticsCompareDataA;
    const b = this.analyticsCompareDataB;
    return [
      { label: 'Actions', a: a.action_count || a.actions?.length || 0, b: b.action_count || b.actions?.length || 0 },
      { label: 'Max Pressure', a: this.pctFmt(a.max_pressure), b: this.pctFmt(b.max_pressure) },
      { label: 'Errors', a: a.error_count || 0, b: b.error_count || 0 },
      { label: 'Duration', a: a.duration_fmt || '--', b: b.duration_fmt || '--' },
      { label: 'Quality', a: a.quality_score ?? '--', b: b.quality_score ?? '--' },
    ];
  },

  // =========================================================
  // Threshold performance helpers
  // =========================================================
  thresholdFPR() {
    const t = this.analyticsThreshold;
    if (t && t.false_positive_rate != null) return (t.false_positive_rate * 100).toFixed(1) + '%';
    return '--';
  },

  thresholdOptimal() {
    const t = this.analyticsThreshold;
    if (!t || !t.optimal) return null;
    return t.optimal;
  },

  thresholdAdjustments() {
    const t = this.analyticsThreshold;
    return (t && t.adjustments) || [];
  },

  // =========================================================
  // Mirror stats helpers
  // =========================================================
  mirrorEffectiveness() {
    const m = this.analyticsMirror;
    if (m && m.effectiveness != null) return (m.effectiveness * 100).toFixed(1) + '%';
    if (m && m.injection_success_rate != null) return (m.injection_success_rate * 100).toFixed(1) + '%';
    return '--';
  },

  mirrorPatternCount() {
    const m = this.analyticsMirror;
    if (!m) return 0;
    if (m.pattern_count != null) return m.pattern_count;
    if (Array.isArray(m.patterns)) return m.patterns.length;
    if (m.patterns && typeof m.patterns === 'object') return Object.keys(m.patterns).length;
    return 0;
  },

  mirrorPrunedCount() {
    const m = this.analyticsMirror;
    return (m && m.pruned_count) || 0;
  },
});
