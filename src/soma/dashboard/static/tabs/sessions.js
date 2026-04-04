/* ============================================================
   SOMA Dashboard v2 — Sessions Tab
   ============================================================ */

window.SOMA = window.SOMA || {};
SOMA.tabs = SOMA.tabs || {};

SOMA.tabs.sessions = () => ({
  // --- Sessions tab state ---
  sessionsList: [],
  sessionsLoading: false,
  selectedSession: null,
  sessionDetail: null,
  sessionDetailLoading: false,
  sessionRecord: null,
  sessionPressureChart: null,
  sessionToolChart: null,
  sessionTrendChart: null,
  sessionsSortCol: 'started',
  sessionsSortAsc: false,
  sessionsView: 'list', // 'list' | 'detail'

  // =========================================================
  // Load sessions list
  // =========================================================
  async loadSessionsTab() {
    this.sessionsLoading = true;
    try {
      const data = await SOMA.api.fetchSessions();
      this.sessionsList = data || [];
    } catch (_) {
      // Fallback to overview
      try {
        const overview = await SOMA.api.fetchOverview();
        this.sessionsList = overview.sessions || [];
      } catch (_) {}
    }
    this.sessionsLoading = false;
  },

  // =========================================================
  // Session list: sorted
  // =========================================================
  get sortedSessions() {
    const list = [...(this.sessionsList || [])];
    const col = this.sessionsSortCol;
    const asc = this.sessionsSortAsc;
    list.sort((a, b) => {
      let va = a[col] ?? '';
      let vb = b[col] ?? '';
      if (typeof va === 'number' && typeof vb === 'number') {
        return asc ? va - vb : vb - va;
      }
      va = String(va);
      vb = String(vb);
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    return list;
  },

  sortSessions(col) {
    if (this.sessionsSortCol === col) {
      this.sessionsSortAsc = !this.sessionsSortAsc;
    } else {
      this.sessionsSortCol = col;
      this.sessionsSortAsc = true;
    }
  },

  sessionSortIcon(col) {
    if (this.sessionsSortCol !== col) return '';
    return this.sessionsSortAsc ? '\u25B2' : '\u25BC';
  },

  // =========================================================
  // Load session detail
  // =========================================================
  async loadSessionDetail(session) {
    if (!session) return;
    this.selectedSession = session;
    this.sessionsView = 'detail';
    this.sessionDetailLoading = true;

    const id = session.session_id || session.agent_id || '';

    // Fetch report + record in parallel
    try {
      const [report, record] = await Promise.all([
        SOMA.api.fetchSessionReport(id),
        SOMA.api.fetchSessionRecord(id),
      ]);
      this.sessionDetail = report || {};
      this.sessionRecord = record || {};
    } catch (_) {
      this.sessionDetail = {};
      this.sessionRecord = {};
    }

    this.sessionDetailLoading = false;

    // Build charts after DOM update
    this.$nextTick(() => {
      this._buildSessionCharts();
      if (typeof lucide !== 'undefined') lucide.createIcons();
    });
  },

  // =========================================================
  // Build charts for session detail
  // =========================================================
  _buildSessionCharts() {
    // Pressure chart
    this.sessionPressureChart = SOMA.charts.destroyChart(this.sessionPressureChart);
    const trajectory = this.sessionRecord?.trajectory || this.sessionRecord?.pressure_trajectory || [];
    if (trajectory.length > 0) {
      this.sessionPressureChart = SOMA.charts.createPressureChart(
        'session-pressure-chart',
        trajectory,
        this.settingsThresholds
      );
    }

    // Tool distribution
    this.sessionToolChart = SOMA.charts.destroyChart(this.sessionToolChart);
    const toolDist = this.sessionRecord?.tool_distribution || this.sessionDetail?.tool_distribution || {};
    const toolLabels = Object.keys(toolDist);
    const toolValues = Object.values(toolDist);
    if (toolLabels.length > 0) {
      this.sessionToolChart = SOMA.charts.createBarChart('session-tool-chart', toolLabels, toolValues);
    }

    // Cross-session trend chart
    this.sessionTrendChart = SOMA.charts.destroyChart(this.sessionTrendChart);
    if (this.sessionsList.length >= 2) {
      this.sessionTrendChart = SOMA.charts.createTrendChart('session-trend-chart', this.sessionsList);
    }
  },

  // =========================================================
  // Back to list
  // =========================================================
  backToSessionList() {
    this.sessionsView = 'list';
    this.selectedSession = null;
    this.sessionDetail = null;
    this.sessionRecord = null;
    this.sessionPressureChart = SOMA.charts.destroyChart(this.sessionPressureChart);
    this.sessionToolChart = SOMA.charts.destroyChart(this.sessionToolChart);
  },

  // =========================================================
  // Phase visualization helpers
  // =========================================================
  phaseColor(phase) {
    const p = (phase || '').toLowerCase();
    if (p.includes('research')) return '#4a9eff';
    if (p.includes('implement')) return '#00ff88';
    if (p.includes('test')) return '#ffaa00';
    if (p.includes('debug')) return '#ff4444';
    return '#666';
  },

  phaseSequenceBlocks(session) {
    const seq = session.phase_sequence || session.phases || [];
    if (!Array.isArray(seq) || seq.length === 0) return [];
    return seq.map(p => ({
      label: (p || '').slice(0, 3).toUpperCase(),
      color: this.phaseColor(p),
    }));
  },

  // =========================================================
  // Quality score color
  // =========================================================
  qualityColor(score) {
    if (score == null) return '#666';
    if (score >= 90) return '#00ff88';
    if (score >= 70) return '#ffaa00';
    if (score >= 50) return '#ff8c00';
    return '#ff4444';
  },

  // =========================================================
  // Export session JSON
  // =========================================================
  exportSessionJSON() {
    if (!this.sessionRecord && !this.sessionDetail) {
      this.addToast('info', 'Export', 'No session data to export');
      return;
    }
    const data = this.sessionRecord || this.sessionDetail;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const id = this.selectedSession?.session_id || this.selectedSession?.agent_id || 'session';
    a.download = 'soma-session-' + id + '.json';
    a.click();
    URL.revokeObjectURL(url);
    this.addToast('info', 'Export', 'Session JSON downloaded');
  },

  // =========================================================
  // Mode transitions count
  // =========================================================
  modeTransitions(session) {
    return session.mode_transitions || session.mode_changes || 0;
  },

  // =========================================================
  // Has replay indicator
  // =========================================================
  hasReplay(session) {
    return !!(session.has_replay || session.replay_available);
  },
});
