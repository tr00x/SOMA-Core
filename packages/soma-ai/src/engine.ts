/**
 * In-process SOMA engine for TypeScript environments.
 *
 * Implements a lightweight behavioral monitoring engine compatible with
 * the SomaEngine interface, suitable for use in Node.js and edge runtimes
 * where the Python SOMA server is not available.
 */

import type {
  Action,
  ActionResult,
  AgentConfig,
  Budget,
  ResponseMode,
  SomaEngine,
  VitalsSnapshot,
} from "./types.js";

interface _AgentState {
  config: AgentConfig;
  actionCount: number;
  errorCount: number;
  totalTokens: number;
  totalCost: number;
  recentOutputs: string[];
}

function _computeVitals(state: _AgentState, action: Action): VitalsSnapshot {
  const errorRate = state.actionCount > 0 ? state.errorCount / state.actionCount : 0;
  const tokenUsage = state.totalTokens;
  const cost = state.totalCost;

  // Simple uncertainty: error rate + retried signal
  const uncertainty = Math.min(1.0, errorRate + (action.retried ? 0.1 : 0));

  // Drift: 0 for now — would require output fingerprinting
  const drift = 0;

  return { uncertainty, drift, errorRate, tokenUsage, cost };
}

function _pressureToMode(pressure: number): ResponseMode {
  if (pressure >= 0.75) return "BLOCK";
  if (pressure >= 0.5) return "WARN";
  if (pressure >= 0.25) return "GUIDE";
  return "OBSERVE";
}

function _computePressure(vitals: VitalsSnapshot): number {
  const signals = [
    vitals.uncertainty,
    vitals.errorRate,
    vitals.drift,
  ];
  const mean = signals.reduce((a, b) => a + b, 0) / signals.length;
  const max = Math.max(...signals);
  return Math.min(1.0, 0.7 * mean + 0.3 * max);
}

/** Lightweight in-process SOMA engine for TypeScript. */
export class SOMAEngine implements SomaEngine {
  private _agents: Map<string, _AgentState> = new Map();
  private _budget: Budget;

  constructor(options: { budget?: Budget } = {}) {
    this._budget = options.budget ?? {};
  }

  registerAgent(agentId: string, config: AgentConfig = {}): void {
    if (!this._agents.has(agentId)) {
      this._agents.set(agentId, {
        config,
        actionCount: 0,
        errorCount: 0,
        totalTokens: 0,
        totalCost: 0,
        recentOutputs: [],
      });
    }
  }

  recordAction(agentId: string, action: Action): ActionResult {
    if (!this._agents.has(agentId)) {
      this.registerAgent(agentId);
    }
    const state = this._agents.get(agentId)!;

    state.actionCount += 1;
    if (action.error) state.errorCount += 1;
    if (action.tokenCount) state.totalTokens += action.tokenCount;
    if (action.cost) state.totalCost += action.cost;
    if (action.outputText) {
      state.recentOutputs.push(action.outputText.slice(0, 200));
      if (state.recentOutputs.length > 10) state.recentOutputs.shift();
    }

    const vitals = _computeVitals(state, action);
    const pressure = _computePressure(vitals);
    const mode = _pressureToMode(pressure);

    return { mode, pressure, vitals };
  }

  getSnapshot(agentId: string): { pressure: number; level: ResponseMode; mode: ResponseMode } {
    if (!this._agents.has(agentId)) {
      return { pressure: 0, level: "OBSERVE", mode: "OBSERVE" };
    }
    const state = this._agents.get(agentId)!;
    if (state.actionCount === 0) {
      return { pressure: 0, level: "OBSERVE", mode: "OBSERVE" };
    }
    const vitals = _computeVitals(state, { toolName: "_snapshot" });
    const pressure = _computePressure(vitals);
    const mode = _pressureToMode(pressure);
    return { pressure, level: mode, mode };
  }
}

/** Create a pre-configured engine with sensible defaults. */
export function quickstart(options: { budget?: Budget; agents?: string[] } = {}): SOMAEngine {
  const engine = new SOMAEngine({ budget: options.budget ?? { tokens: 100_000 } });
  for (const agentId of options.agents ?? ["default"]) {
    engine.registerAgent(agentId);
  }
  return engine;
}
