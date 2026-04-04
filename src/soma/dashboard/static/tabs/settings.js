/* ============================================================
   SOMA Dashboard v2 — Settings Tab
   ============================================================ */

window.SOMA = window.SOMA || {};
SOMA.tabs = SOMA.tabs || {};

SOMA.tabs.settings = () => ({
  // --- Settings tab state ---
  settingsSubTab: 'mode',
  settingsLoading: false,
  settingsSaving: false,

  // Mode
  settingsMode: 'advisory',

  // Thresholds
  settingsThresholds: { guide: 0.4, warn: 0.6, block: 0.8 },

  // Weights
  settingsWeights: {
    uncertainty: 1.0,
    drift: 1.0,
    error_rate: 1.0,
    resource: 0.5,
    coherence: 0.8,
  },

  // Budget
  settingsBudget: { tokens: 1000000, cost_usd: 50 },
  settingsBudgetSpent: { tokens: 0, cost_usd: 0 },

  // Graph
  settingsGraph: {
    damping: 0.15,
    trust_decay_rate: 0.05,
    trust_recovery_rate: 0.02,
  },

  // Vitals
  settingsVitals: {
    goal_coherence_threshold: 0.5,
    warmup: 5,
    error_ratio: 0.2,
    min_samples: 3,
  },

  // Hooks (feature toggles)
  settingsHooks: {
    validate_python: true,
    validate_js: false,
    lint_python: true,
    predict: true,
    fingerprint: true,
    quality: true,
    task_tracking: true,
  },

  // Agents
  settingsAgents: [],
  settingsSelectedAgentIdx: -1,

  // Policies
  settingsPolicies: [],
  settingsNewPolicyName: '',
  settingsNewPolicyCondition: '',
  settingsNewPolicyAction: '',

  // Raw TOML
  rawToml: '',

  // Sub-tab definitions
  settingsSubTabs: [
    { id: 'mode',       label: 'Mode',       icon: 'zap' },
    { id: 'thresholds', label: 'Thresholds',  icon: 'sliders-horizontal' },
    { id: 'weights',    label: 'Weights',     icon: 'bar-chart-2' },
    { id: 'budget',     label: 'Budget',      icon: 'wallet' },
    { id: 'graph',      label: 'Graph',       icon: 'git-branch' },
    { id: 'vitals',     label: 'Vitals',      icon: 'activity' },
    { id: 'hooks',      label: 'Hooks',       icon: 'toggle-left' },
    { id: 'agents',     label: 'Agents',      icon: 'users' },
    { id: 'policies',   label: 'Policies',    icon: 'shield' },
    { id: 'raw',        label: 'Raw TOML',    icon: 'file-text' },
  ],

  // =========================================================
  // Load settings from config
  // =========================================================
  async loadSettingsTab() {
    this.settingsLoading = true;
    try {
      const config = await SOMA.api.fetchConfig();
      this.config = config;
      this._applyConfigToSettings(config);
    } catch (_) {}

    // Load budget spent
    try {
      const budget = await SOMA.api.fetchBudget();
      this.settingsBudgetSpent = {
        tokens: (budget.spent && budget.spent.tokens) || 0,
        cost_usd: (budget.spent && budget.spent.cost_usd) || 0,
      };
    } catch (_) {}

    // Load policies
    try {
      this.settingsPolicies = await SOMA.api.fetchPolicies();
    } catch (_) {}

    // Load agents for per-agent config
    try {
      const agents = await SOMA.api.fetchAgents();
      this.settingsAgents = (agents || []).map(a => ({
        agent_id: a.agent_id,
        autonomy: a.autonomy || 'supervised',
        sensitivity: a.sensitivity || 1.0,
        tools: (a.known_tools || []).join(', '),
      }));
    } catch (_) {}

    // Load raw TOML
    try {
      const resp = await fetch('/api/config/raw');
      if (resp.ok) {
        this.rawToml = await resp.text();
      } else {
        // Fallback: stringify config
        this.rawToml = JSON.stringify(this.config, null, 2);
      }
    } catch (_) {
      this.rawToml = JSON.stringify(this.config || {}, null, 2);
    }

    this.settingsLoading = false;
    this.$nextTick(() => { if (typeof lucide !== 'undefined') lucide.createIcons(); });
  },

  _applyConfigToSettings(cfg) {
    if (!cfg) return;
    // Mode
    this.settingsMode = cfg.mode || cfg.soma?.mode || 'advisory';

    // Thresholds
    const t = cfg.thresholds || cfg.soma?.thresholds || {};
    this.settingsThresholds = {
      guide: t.guide ?? 0.4,
      warn: t.warn ?? 0.6,
      block: t.block ?? 0.8,
    };

    // Weights
    const w = cfg.weights || cfg.soma?.weights || {};
    this.settingsWeights = {
      uncertainty: w.uncertainty ?? 1.0,
      drift: w.drift ?? 1.0,
      error_rate: w.error_rate ?? 1.0,
      resource: w.resource ?? 0.5,
      coherence: w.coherence ?? 0.8,
    };

    // Budget
    const b = cfg.budget || {};
    this.settingsBudget = {
      tokens: b.tokens ?? 1000000,
      cost_usd: b.cost_usd ?? 50,
    };

    // Graph
    const g = cfg.graph || {};
    this.settingsGraph = {
      damping: g.damping ?? 0.15,
      trust_decay_rate: g.trust_decay_rate ?? 0.05,
      trust_recovery_rate: g.trust_recovery_rate ?? 0.02,
    };

    // Vitals
    const v = cfg.vitals || {};
    this.settingsVitals = {
      goal_coherence_threshold: v.goal_coherence_threshold ?? 0.5,
      warmup: v.warmup ?? 5,
      error_ratio: v.error_ratio ?? 0.2,
      min_error_rate: v.min_error_rate ?? 0.01,
      min_samples: v.min_samples ?? 3,
    };

    // Hooks
    const h = cfg.hooks || {};
    this.settingsHooks = {
      validate_python: h.validate_python ?? true,
      validate_js: h.validate_js ?? false,
      lint_python: h.lint_python ?? true,
      predict: h.predict ?? true,
      fingerprint: h.fingerprint ?? true,
      quality: h.quality ?? true,
      task_tracking: h.task_tracking ?? true,
    };
  },

  // =========================================================
  // Save helpers
  // =========================================================
  async saveSettings(section) {
    this.settingsSaving = true;
    let data = {};
    switch (section) {
      case 'mode':
        data = { mode: this.settingsMode };
        break;
      case 'thresholds':
        data = { ...this.settingsThresholds };
        break;
      case 'weights':
        data = { ...this.settingsWeights };
        break;
      case 'budget':
        data = { ...this.settingsBudget };
        break;
      case 'graph':
        data = { ...this.settingsGraph };
        break;
      case 'vitals':
        data = { ...this.settingsVitals };
        break;
      case 'hooks':
        data = { ...this.settingsHooks };
        break;
      default:
        break;
    }

    const result = await SOMA.api.patchSettings(section, data);
    this.settingsSaving = false;

    if (result && !result.error) {
      this.addToast('info', 'Settings Saved', section + ' updated successfully');
    } else {
      this.addToast('error', 'Save Failed', 'Could not save ' + section + ' settings');
    }
  },

  async saveRawToml() {
    this.settingsSaving = true;
    try {
      const resp = await fetch('/api/settings/raw-toml', {
        method: 'PATCH',
        headers: { 'Content-Type': 'text/plain' },
        body: this.rawToml,
      });
      if (resp.ok) {
        this.addToast('info', 'Settings Saved', 'Raw TOML saved successfully');
        // Reload config
        this.config = await SOMA.api.fetchConfig();
        this._applyConfigToSettings(this.config);
      } else {
        this.addToast('error', 'Save Failed', 'Invalid TOML or write error');
      }
    } catch (_) {
      this.addToast('error', 'Save Failed', 'Could not save raw TOML');
    }
    this.settingsSaving = false;
  },

  async resetDefaults(section) {
    const defaults = {
      mode: { mode: 'advisory' },
      thresholds: { guide: 0.4, warn: 0.6, block: 0.8 },
      weights: { uncertainty: 1.0, drift: 1.0, error_rate: 1.0, resource: 0.5, coherence: 0.8 },
      budget: { tokens: 1000000, cost_usd: 50 },
      graph: { damping: 0.15, trust_decay_rate: 0.05, trust_recovery_rate: 0.02 },
      vitals: { goal_coherence_threshold: 0.5, warmup: 5, error_ratio: 0.2, min_error_rate: 0.01, min_samples: 3 },
      hooks: { validate_python: true, validate_js: false, lint_python: true, predict: true, fingerprint: true, quality: true, task_tracking: true },
    };
    const d = defaults[section];
    if (!d) return;

    switch (section) {
      case 'mode': this.settingsMode = d.mode; break;
      case 'thresholds': this.settingsThresholds = { ...d }; break;
      case 'weights': this.settingsWeights = { ...d }; break;
      case 'budget': this.settingsBudget = { ...d }; break;
      case 'graph': this.settingsGraph = { ...d }; break;
      case 'vitals': this.settingsVitals = { ...d }; break;
      case 'hooks': this.settingsHooks = { ...d }; break;
    }
    this.addToast('info', 'Defaults', section + ' reset to defaults');
  },

  // =========================================================
  // Policy management
  // =========================================================
  async addPolicy() {
    if (!this.settingsNewPolicyName.trim()) return;
    try {
      const resp = await fetch('/api/policies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: this.settingsNewPolicyName,
          condition: this.settingsNewPolicyCondition,
          action: this.settingsNewPolicyAction,
        }),
      });
      if (resp.ok) {
        this.settingsNewPolicyName = '';
        this.settingsNewPolicyCondition = '';
        this.settingsNewPolicyAction = '';
        this.settingsPolicies = await SOMA.api.fetchPolicies();
        this.addToast('info', 'Policy Added', 'Rule created successfully');
      } else {
        this.addToast('error', 'Failed', 'Could not add policy');
      }
    } catch (_) {
      this.addToast('error', 'Failed', 'Could not add policy');
    }
  },

  async deletePolicy(name) {
    try {
      const resp = await fetch('/api/policies/' + encodeURIComponent(name), { method: 'DELETE' });
      if (resp.ok) {
        this.settingsPolicies = await SOMA.api.fetchPolicies();
        this.addToast('info', 'Policy Deleted', name + ' removed');
      } else {
        this.addToast('error', 'Failed', 'Could not delete policy');
      }
    } catch (_) {
      this.addToast('error', 'Failed', 'Could not delete policy');
    }
  },

  // Budget reset
  async resetBudget() {
    await SOMA.api.patchSettings('budget', { reset: true });
    this.settingsBudgetSpent = { tokens: 0, cost_usd: 0 };
    this.addToast('info', 'Budget', 'Budget counters reset');
  },

  // Threshold zone label helper
  thresholdZoneLabel(val) {
    if (val >= 0.8) return 'BLOCK zone';
    if (val >= 0.6) return 'WARN zone';
    if (val >= 0.4) return 'GUIDE zone';
    return 'OBSERVE zone';
  },
});
