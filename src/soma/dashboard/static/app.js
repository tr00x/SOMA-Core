/* ============================================================
   SOMA Dashboard v2 — App (Alpine.js init + shared state)
   ============================================================ */

document.addEventListener('alpine:init', () => {
  Alpine.data('dashboard', () => ({
    // --- Connection state ---
    connected: false,
    clock: '--:--:--',
    _clockInterval: null,
    _sseSource: null,

    // --- Tab routing ---
    activeTab: 'overview',
    tabs: [
      { id: 'overview',   label: 'Overview' },
      { id: 'deep-dive',  label: 'Deep Dive' },
      { id: 'settings',   label: 'Settings' },
      { id: 'logs',       label: 'Logs' },
      { id: 'sessions',   label: 'Sessions' },
      { id: 'analytics',  label: 'Analytics' },
    ],

    // --- Shared data (populated by SSE or fetch) ---
    agents: [],
    budgetData: { health: 1, limits: {}, spent: {}, used_pct: {}, remaining: {} },
    findings: [],
    config: {},
    prevModes: {},

    // --- Toast system ---
    toasts: [],
    _toastId: 0,

    // --- Overlays ---
    showSearch: false,
    searchQuery: '',
    searchResults: [],
    showHelp: false,
    keyboardShortcuts: [
      { key: '1', desc: 'Overview tab' },
      { key: '2', desc: 'Deep Dive tab' },
      { key: '3', desc: 'Settings tab' },
      { key: '4', desc: 'Logs tab' },
      { key: '5', desc: 'Sessions tab' },
      { key: '6', desc: 'Analytics tab' },
      { key: 'Ctrl+K', desc: 'Global search' },
      { key: '?', desc: 'Keyboard shortcuts' },
      { key: 'Esc', desc: 'Close overlays' },
    ],

    // --- Spread in tab mixins ---
    ...SOMA.tabs.overview(),
    ...SOMA.tabs.deepDive(),
    ...SOMA.tabs.settings(),
    ...SOMA.tabs.logs(),
    ...SOMA.tabs.sessions(),
    ...SOMA.tabs.analytics(),

    // =========================================================
    // Init
    // =========================================================
    async init() {
      this.readHash();
      this.updateClock();
      this._clockInterval = setInterval(() => this.updateClock(), 1000);

      // Connect SSE for real-time updates
      SOMA.api.connectSSE(this);

      // Initial data load
      try {
        const overview = await SOMA.api.fetchOverview();
        this.agents = overview.agents || [];
        this.findings = overview.findings || [];
      } catch (_) { /* handled in api.js */ }

      try {
        this.budgetData = await SOMA.api.fetchBudget();
      } catch (_) {}

      try {
        this.config = await SOMA.api.fetchConfig();
      } catch (_) {}

      // Keyboard shortcuts
      document.addEventListener('keydown', (e) => this._handleKeydown(e));
      window.addEventListener('hashchange', () => this.readHash());

      // Re-init Lucide icons after DOM settles
      this.$nextTick(() => {
        if (typeof lucide !== 'undefined') lucide.createIcons();
      });
    },

    // =========================================================
    // Tab routing
    // =========================================================
    readHash() {
      const hash = window.location.hash.replace('#', '');
      const valid = this.tabs.map(t => t.id);
      if (valid.includes(hash)) this.switchTab(hash);
    },

    switchTab(id) {
      this.activeTab = id;
      window.location.hash = id;
      this.$nextTick(() => {
        if (typeof lucide !== 'undefined') lucide.createIcons();
        // Trigger tab data load
        if (id === 'overview' && typeof this.loadOverviewTab === 'function') this.loadOverviewTab();
        if (id === 'settings' && typeof this.loadSettingsTab === 'function') this.loadSettingsTab();
        if (id === 'logs' && typeof this.loadLogsTab === 'function') this.loadLogsTab();
        if (id === 'sessions' && typeof this.loadSessionsTab === 'function') this.loadSessionsTab();
        if (id === 'analytics' && typeof this.loadAnalyticsTab === 'function') this.loadAnalyticsTab();
      });
    },

    // =========================================================
    // Keyboard shortcuts
    // =========================================================
    _handleKeydown(e) {
      // Skip when inside form elements
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

      const tabKeys = { '1': 'overview', '2': 'deep-dive', '3': 'settings', '4': 'logs', '5': 'sessions', '6': 'analytics' };
      if (tabKeys[e.key]) {
        this.switchTab(tabKeys[e.key]);
        return;
      }

      if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        this.showHelp = !this.showHelp;
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        this.showSearch = !this.showSearch;
        if (this.showSearch) {
          this.$nextTick(() => this.$refs.searchInput && this.$refs.searchInput.focus());
        }
        return;
      }

      if (e.key === 'Escape') {
        this.showSearch = false;
        this.showHelp = false;
      }
    },

    // =========================================================
    // Clock
    // =========================================================
    updateClock() {
      const now = new Date();
      this.clock = [now.getHours(), now.getMinutes(), now.getSeconds()]
        .map(n => String(n).padStart(2, '0')).join(':');
    },

    // =========================================================
    // Toast system
    // =========================================================
    addToast(type, title, message) {
      const id = ++this._toastId;
      this.toasts.push({ id, type, title, message, removing: false });
      setTimeout(() => this.removeToast(id), 5000);
    },

    removeToast(id) {
      const toast = this.toasts.find(t => t.id === id);
      if (toast) {
        toast.removing = true;
        setTimeout(() => {
          this.toasts = this.toasts.filter(t => t.id !== id);
        }, 300);
      }
    },

    // =========================================================
    // Formatting helpers (shared across tabs)
    // =========================================================
    pressureColor(p) {
      if (p >= 0.8) return '#ff4444';
      if (p >= 0.6) return '#ff8c00';
      if (p >= 0.4) return '#ffaa00';
      return '#00ff88';
    },

    modeBadgeClass(mode) {
      const m = this.modeLabel(mode).toLowerCase();
      if (m === 'block') return 'mode-block';
      if (m === 'warn') return 'mode-warn';
      if (m === 'guide') return 'mode-guide';
      return 'mode-observe';
    },

    modeLabel(mode) {
      if (!mode) return 'OBSERVE';
      const s = String(mode).toUpperCase();
      if (s.includes('BLOCK')) return 'BLOCK';
      if (s.includes('WARN')) return 'WARN';
      if (s.includes('GUIDE')) return 'GUIDE';
      return 'OBSERVE';
    },

    pctFmt(v) {
      if (v == null) return '--';
      return (v * 100).toFixed(1) + '%';
    },

    stripPrefix(agentId) {
      if (!agentId) return '';
      // Show display_name if available
      const agent = (this.agents || []).find(a => a.agent_id === agentId);
      if (agent && agent.display_name) return agent.display_name;
      return agentId.replace(/^agent[_-]/i, '');
    },

    // =========================================================
    // Search
    // =========================================================
    runSearch() {
      const q = (this.searchQuery || '').toLowerCase().trim();
      if (!q) { this.searchResults = []; return; }

      const results = [];

      // Search agents
      (this.agents || []).forEach(a => {
        const id = a.agent_id || '';
        if (id.toLowerCase().includes(q)) {
          results.push({ id: 'agent-' + id, label: id, type: 'agent', data: a });
        }
      });

      // Search findings
      (this.findings || []).forEach((f, i) => {
        const text = (f.title || f.message || '').toLowerCase();
        if (text.includes(q)) {
          results.push({ id: 'finding-' + i, label: f.title || f.message, type: 'finding', data: f });
        }
      });

      this.searchResults = results.slice(0, 10);
    },

    navigateSearch(result) {
      this.showSearch = false;
      this.searchQuery = '';
      if (result.type === 'agent') {
        this.switchTab('deep-dive');
        this.$nextTick(() => this.ddSelectAgent(result.data.agent_id));
      }
    },
  }));
});
