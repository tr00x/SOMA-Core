/* ============================================================
   SOMA Dashboard v2 — Logs Tab
   ============================================================ */

window.SOMA = window.SOMA || {};
SOMA.tabs = SOMA.tabs || {};

SOMA.tabs.logs = () => ({
  // --- Logs tab state ---
  detailedLogs: [],
  logsLoading: false,
  logsAgentFilter: '',
  logsTextFilter: '',
  logsModeFilter: [],
  logsTypeFilter: [],
  logsAutoRefresh: true,
  logsSortCol: 'timestamp',
  logsSortAsc: false,
  logsPage: 0,
  logsPerPage: 100,

  // Available filter options
  logsModeOptions: ['OBSERVE', 'GUIDE', 'WARN', 'BLOCK'],
  logsTypeOptions: ['action', 'reflex', 'policy', 'mode_change'],

  // =========================================================
  // Computed — as methods (getters don't survive spread)
  // =========================================================
  getFilteredLogs() {
    let entries = (this.detailedLogs || []).filter(e => {
      if (this.logsAgentFilter && (e.agent_id || '') !== this.logsAgentFilter) return false;
      if (this.logsTextFilter) {
        const q = this.logsTextFilter.toLowerCase();
        const hay = [e.agent_id||'', e.tool_name||'', e.file||'', e.mode||'', e.reflex_kind||'', e.policy_rule||''].join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (this.logsModeFilter.length > 0) {
        const mode = (e.mode || e.level || 'OBSERVE').toUpperCase();
        if (!this.logsModeFilter.includes(mode)) return false;
      }
      if (this.logsTypeFilter.length > 0) {
        const type = e.event_type || e.type || 'action';
        if (!this.logsTypeFilter.includes(type)) return false;
      }
      return true;
    });

    const col = this.logsSortCol;
    const asc = this.logsSortAsc;
    entries.sort((a, b) => {
      let va = a[col] ?? '', vb = b[col] ?? '';
      if (typeof va === 'number' && typeof vb === 'number') return asc ? va - vb : vb - va;
      va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    return entries;
  },

  getPagedLogs() {
    const all = this.getFilteredLogs();
    const start = this.logsPage * this.logsPerPage;
    return all.slice(start, start + this.logsPerPage);
  },

  getLogsTotalPages() {
    return Math.max(1, Math.ceil(this.getFilteredLogs().length / this.logsPerPage));
  },

  getLogsUniqueAgents() {
    const ids = new Set();
    (this.detailedLogs || []).forEach(e => { if (e.agent_id) ids.add(e.agent_id); });
    return Array.from(ids).sort();
  },

  // =========================================================
  // Load
  // =========================================================
  async loadLogsTab() {
    if (this.logsLoading) return;
    this.logsLoading = true;
    try {
      const data = await SOMA.api.fetchDetailedLogs();
      this.detailedLogs = Array.isArray(data) ? data : (data.entries || data.audit || []);
    } catch (e) {
      console.error('[SOMA logs] fetch error', e);
    }
    this.logsLoading = false;
  },

  // =========================================================
  // Sort
  // =========================================================
  sortLogs(col) {
    if (this.logsSortCol === col) { this.logsSortAsc = !this.logsSortAsc; }
    else { this.logsSortCol = col; this.logsSortAsc = true; }
  },
  sortIcon(col) {
    if (this.logsSortCol !== col) return '';
    return this.logsSortAsc ? '\u25B2' : '\u25BC';
  },

  // =========================================================
  // Filter toggles
  // =========================================================
  toggleModeFilter(mode) {
    const idx = this.logsModeFilter.indexOf(mode);
    if (idx >= 0) this.logsModeFilter.splice(idx, 1);
    else this.logsModeFilter.push(mode);
    this.logsPage = 0;
  },
  toggleTypeFilter(type) {
    const idx = this.logsTypeFilter.indexOf(type);
    if (idx >= 0) this.logsTypeFilter.splice(idx, 1);
    else this.logsTypeFilter.push(type);
    this.logsPage = 0;
  },
  isModeActive(mode) { return this.logsModeFilter.includes(mode); },
  isTypeActive(type) { return this.logsTypeFilter.includes(type); },

  // =========================================================
  // Row styling
  // =========================================================
  logRowClass(entry) {
    const isError = !!(entry.error || entry.is_error);
    let cls = 'h-9 text-xs border-b border-[#1e1e1e] hover:bg-white/5 transition-colors';
    if (isError) cls += ' border-l-[3px] border-l-[#ff4444]';
    else cls += ' border-l-[3px] border-l-transparent';
    return cls;
  },
  logRowBg(entry, idx) { return idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)'; },
  logModeColor(entry) {
    const mode = (entry.mode || entry.level || 'OBSERVE').toUpperCase();
    if (mode === 'BLOCK') return '#ff4444';
    if (mode === 'WARN') return '#ff8c00';
    if (mode === 'GUIDE') return '#ffaa00';
    return '#666';
  },

  // =========================================================
  // CSV Export
  // =========================================================
  exportLogsCSV() {
    const rows = this.getFilteredLogs();
    if (!rows.length) { this.addToast('info', 'Export', 'No log entries to export'); return; }
    const cols = ['timestamp', 'time_fmt', 'agent_id', 'tool_name', 'file', 'pressure', 'mode', 'error', 'reflex_kind', 'policy_rule'];
    const header = cols.join(',');
    const lines = rows.map(r => cols.map(c => {
      let v = String(r[c] ?? '').replace(/"/g, '""');
      if (v.includes(',') || v.includes('"') || v.includes('\n')) v = '"' + v + '"';
      return v;
    }).join(','));
    const blob = new Blob([header + '\n' + lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'soma-logs-' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    this.addToast('info', 'Export', 'CSV downloaded (' + rows.length + ' entries)');
  },

  // =========================================================
  // Pagination
  // =========================================================
  logsNextPage() { if (this.logsPage < this.getLogsTotalPages() - 1) this.logsPage++; },
  logsPrevPage() { if (this.logsPage > 0) this.logsPage--; },

  // =========================================================
  // Clear
  // =========================================================
  clearLogsFilters() {
    this.logsAgentFilter = '';
    this.logsTextFilter = '';
    this.logsModeFilter = [];
    this.logsTypeFilter = [];
    this.logsPage = 0;
  },
});
