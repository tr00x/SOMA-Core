/* ============================================================
   SOMA Dashboard v2 — Agent Deep Dive Tab
   ============================================================ */

window.SOMA = window.SOMA || {};
SOMA.tabs = SOMA.tabs || {};

SOMA.tabs.deepDive = () => ({
  ddAgent: null, ddAgentId: '', ddTrajectory: [], ddActions: [], ddQuality: {},
  ddReflexes: [], ddRCA: {}, ddMirror: {}, ddContext: {}, ddSessionMemory: {},
  ddCapacity: {}, ddCircuitBreaker: {}, ddScope: {},
  ddSubagents: { cascade_risk: 0, subagents: [] },
  ddPredictions: {}, ddFingerprint: {},
  _ddPressureChart: null, _ddRadarChart: null, _ddGraphCanvas: null, _ddGraphNodes: [],
  ddLoading: false,
  ddSections: { header:true, charts:true, signals:true, intelligence:true, reflexes:true, mirror:true, session:true, graph:false, subagents:true, history:true },

  ddToggle(s) { this.ddSections[s] = !this.ddSections[s]; if (s==='graph' && this.ddSections.graph) this.$nextTick(() => this._ddRenderGraph()); },

  async ddSelectAgent(agentId) {
    if (!agentId) return;
    this.ddAgentId = agentId;
    this.ddLoading = true;
    this._ddPressureChart = SOMA.charts.destroyChart(this._ddPressureChart);
    this._ddRadarChart = SOMA.charts.destroyChart(this._ddRadarChart);

    const [agent, trajectory, actions, quality, reflexes, rca, mirror, context, sessionMemory, capacity, circuitBreaker, scope, subagents, allPred, allFP] = await Promise.all([
      SOMA.api.fetchAgent(agentId), SOMA.api.fetchTrajectory(agentId),
      SOMA.api.fetchActions(agentId), SOMA.api.fetchQuality(agentId),
      SOMA.api.fetchReflexes(agentId), SOMA.api.fetchRCA(agentId),
      SOMA.api.fetchMirror(agentId), SOMA.api.fetchContext(agentId),
      SOMA.api.fetchSessionMemory(agentId), SOMA.api.fetchCapacity(agentId),
      SOMA.api.fetchCircuitBreaker(agentId), SOMA.api.fetchScope(agentId),
      SOMA.api.fetchSubagents(agentId),
      SOMA.api.fetchPredictions().catch(() => ({})),
      SOMA.api.fetchFingerprints().catch(() => ({})),
    ]);

    this.ddAgent = agent; this.ddTrajectory = trajectory; this.ddActions = actions;
    this.ddQuality = quality; this.ddReflexes = Array.isArray(reflexes) ? reflexes : [];
    this.ddRCA = rca || {};
    const mr = mirror || {}; this.ddMirror = { ...(mr.stats || {}), patterns: mr.stats?.patterns || mr.patterns || {} };
    this.ddContext = context || {};
    this.ddSessionMemory = sessionMemory || {}; this.ddCapacity = capacity || {};
    this.ddCircuitBreaker = circuitBreaker || {}; this.ddScope = scope || {};
    this.ddSubagents = subagents || { cascade_risk: 0, subagents: [] };

    // Predictions from raw predictor
    const rawPred = (allPred || {})[agentId] || {};
    const pressures = rawPred.pressures || [];
    if (pressures.length >= 3) {
      const recent = pressures.slice(-5);
      const trend = recent.length >= 2 ? (recent[recent.length-1] - recent[0]) / recent.length : 0;
      const current = recent[recent.length-1] || 0;
      const predicted = Math.min(1, Math.max(0, current + trend * (rawPred.horizon || 5)));
      const nextThresh = current < 0.4 ? 0.4 : current < 0.6 ? 0.6 : 0.8;
      this.ddPredictions = { current_pressure: current, predicted_pressure: predicted, will_escalate: predicted > nextThresh, confidence: Math.min(1, pressures.length / 20), actions_ahead: rawPred.horizon || 5, dominant_reason: trend > 0.02 ? 'rising trend' : trend < -0.02 ? 'declining' : 'stable' };
    } else { this.ddPredictions = {}; }

    // Fingerprint
    const fps = (allFP || {}).fingerprints || allFP || {};
    const fp = fps[agentId] || fps['claude-code'] || {};
    if (fp.tool_distribution && Object.keys(fp.tool_distribution).length > 0) {
      const fpDist = fp.tool_distribution;
      const knownTools = (agent || {}).known_tools || [];
      const fpTools = Object.keys(fpDist);
      const allTools = [...new Set([...knownTools, ...fpTools])];
      const newTools = knownTools.filter(t => !fpDist[t]);
      this.ddFingerprint = { divergence: allTools.length > 0 ? newTools.length / allTools.length : 0, tool_distribution: fpDist, avg_error_rate: fp.avg_error_rate || 0, read_write_ratio: fp.read_write_ratio || 0, sample_count: fp.sample_count || 0 };
    } else { this.ddFingerprint = {}; }

    this.ddLoading = false;
    this.$nextTick(() => { this._ddRenderPressureChart(); this._ddRenderRadarChart(); this._ddRenderGraph(); if (typeof lucide !== 'undefined') lucide.createIcons(); });
  },

  _ddRenderPressureChart() {
    const canvas = document.getElementById('dd-pressure-chart');
    if (!canvas || !this.ddTrajectory || this.ddTrajectory.length === 0) return;
    this._ddPressureChart = SOMA.charts.destroyChart(this._ddPressureChart);
    this._ddPressureChart = SOMA.charts.createPressureChart('dd-pressure-chart', this.ddTrajectory, { guide: 0.4, warn: 0.6, block: 0.8 });
  },
  _ddRenderRadarChart() {
    const canvas = document.getElementById('dd-radar-chart');
    if (!canvas || !this.ddAgent) return;
    this._ddRadarChart = SOMA.charts.destroyChart(this._ddRadarChart);
    const v = this.ddAgent.vitals || {}, b = (this.ddAgent.baseline || {}).value || {};
    this._ddRadarChart = SOMA.charts.createRadarChart('dd-radar-chart',
      { uncertainty: v.uncertainty||0, drift: v.drift||0, error_rate: v.error_rate||0, cost: v.cost||0, coherence: v.goal_coherence||0, context: v.context_usage||0 },
      { uncertainty: b.uncertainty||0, drift: b.drift||0, error_rate: b.error_rate||0, cost: b.cost||0, coherence: b.goal_coherence||0, context: 0 });
  },
  _ddRenderGraph() {
    const canvas = document.getElementById('dd-agent-graph');
    if (!canvas || !this.agents || this.agents.length <= 1) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth, H = canvas.height = Math.max(300, canvas.offsetHeight);
    ctx.clearRect(0, 0, W, H);
    const nodes = this.agents.map((a, i) => {
      const angle = (2*Math.PI*i)/this.agents.length - Math.PI/2;
      return { id: a.agent_id, x: W/2 + W*0.35*Math.cos(angle), y: H/2 + H*0.35*Math.sin(angle), pressure: a.pressure||0, mode: a.level||a.mode||'OBSERVE' };
    });
    this._ddGraphNodes = nodes;
    for (const n of nodes) {
      const r = 12 + n.pressure * 20, sel = n.id === this.ddAgentId;
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI*2);
      const m = (n.mode||'').toUpperCase();
      ctx.fillStyle = m==='BLOCK'?'#ff4444':m==='WARN'?'#ff8c00':m==='GUIDE'?'#ffaa00':'#00ff88';
      ctx.globalAlpha = sel ? 1 : 0.7; ctx.fill(); ctx.globalAlpha = 1;
      if (sel) { ctx.strokeStyle='#ff2d78'; ctx.lineWidth=2; ctx.stroke(); }
      ctx.fillStyle='#000'; ctx.font='bold 10px monospace'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(Math.round(n.pressure*100)+'%', n.x, n.y);
      ctx.fillStyle='#999'; ctx.font='10px monospace'; ctx.fillText(n.id.replace(/^cc-/,''), n.x, n.y+r+12);
    }
    const self = this;
    canvas.ondblclick = (e) => { const rect=canvas.getBoundingClientRect(), mx=e.clientX-rect.left, my=e.clientY-rect.top; for (const n of self._ddGraphNodes) { const dx=mx-n.x, dy=my-n.y, r=12+n.pressure*20; if (dx*dx+dy*dy<r*r) { self.ddSelectAgent(n.id); return; } } };
  },

  ddPressurePercent() { return ((this.ddAgent?.pressure||0)*100).toFixed(1); },
  ddUptimeStr() { const a=this.ddAgent; if(!a||!a.action_count) return '--'; return a.action_count+' actions'; },
  ddPhaseLabel() { const p=this.ddScope?.phase||this.ddAgent?.phase||this.ddQuality?.phase; return (p&&p!=='unknown')?p:'unknown'; },
  ddHalfLifeColor() { const sr=this.ddCapacity?.success_rate; if(sr==null) return '#666'; if(sr>0.6) return '#00ff88'; if(sr>0.3) return '#ffaa00'; return '#ff4444'; },
  ddCapacityRemaining() { const c=this.ddCapacity; if(!c) return '--'; if(c.capacity_actions!=null) return '~'+c.capacity_actions; if(c.actions_remaining!=null) return '~'+c.actions_remaining; return '--'; },
  ddCbState() { const cb=this.ddCircuitBreaker; if(!cb) return null; if(cb.state) return cb.state; if(cb.is_open===true) return 'OPEN'; if(cb.is_open===false) return 'CLOSED'; return null; },
  ddCbBadgeClass() { const s=(this.ddCbState()||'').toLowerCase(); if(s==='open') return 'badge-open'; if(s.includes('half')) return 'badge-half-open'; return 'badge-closed'; },
  ddPressureVector() {
    const a=this.ddAgent; if(!a) return [];
    const pv = a.pressure_vector || a.vitals || {};
    if(!pv||Object.keys(pv).length===0) return [];
    return ['uncertainty','drift','error_rate','cost','token_usage'].filter(s=>pv[s]!=null).map(signal=>({signal,value:pv[signal]||0,weight:(a.weights||{})[signal]||1})).sort((a,b)=>b.value*b.weight-a.value*a.weight);
  },
  ddCalibration() { return this.ddAgent?.calibration || {}; },
  ddBaselineHealth() { return this.ddAgent?.baseline_health || {}; },
  ddInterventionHistory() { return this.ddAgent?.intervention_history || []; },
  ddRecentActions() { return (this.ddActions||[]).slice(0, 20); },
  ddContextBurn() {
    const v=this.ddAgent?.vitals||{}, cb=this.ddAgent?.context_burn;
    if(cb&&Object.keys(cb).length) return cb;
    const burn=v.context_burn_rate, usage=v.context_usage;
    if(burn!=null||usage!=null) return { burn_rate:burn, remaining_estimate:usage!=null&&burn?Math.round((1-usage)/burn):null, trend:burn>100?'increasing':burn>0?'stable':null };
    return {};
  },
  ddHasSubagents() { return (this.ddSubagents?.subagents||[]).length > 0; },
});
