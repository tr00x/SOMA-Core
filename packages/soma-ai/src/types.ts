/**
 * Core types for the SOMA TypeScript SDK.
 */

/** Behavioral pressure level for an agent. */
export type ResponseMode = "OBSERVE" | "GUIDE" | "WARN" | "BLOCK";

/** A single recorded action from an agent. */
export interface Action {
  toolName: string;
  outputText?: string;
  tokenCount?: number;
  durationSec?: number;
  error?: boolean;
  cost?: number;
  retried?: boolean;
}

/** Behavioral health metrics at a point in time. */
export interface VitalsSnapshot {
  uncertainty: number;
  drift: number;
  errorRate: number;
  tokenUsage: number;
  cost: number;
  calibrationScore?: number;
}

/** Result returned after recording an action. */
export interface ActionResult {
  mode: ResponseMode;
  pressure: number;
  vitals: VitalsSnapshot;
  guidance?: string;
}

/** Budget configuration keyed by dimension name. */
export interface Budget {
  tokens?: number;
  cost_usd?: number;
  [key: string]: number | undefined;
}

/** Configuration for a SOMA agent. */
export interface AgentConfig {
  systemPrompt?: string;
  allowedTools?: string[];
  budget?: Budget;
}

/** SOMA engine interface. */
export interface SomaEngine {
  registerAgent(agentId: string, config?: AgentConfig): void;
  recordAction(agentId: string, action: Action): ActionResult;
  getSnapshot(agentId: string): { pressure: number; level: ResponseMode; mode: ResponseMode };
}

/** Tracker returned by soma.track() — use inside a using/try block. */
export interface SomaTracker {
  /** Mark the action output. */
  setOutput(text: string): void;
  /** Mark the action as errored. */
  setError(isError: boolean): void;
  /** Override token count. */
  setTokens(count: number): void;
  /** Override cost. */
  setCost(cost: number): void;
  /** Mark as retried. */
  setRetried(retried: boolean): void;
  /** Result populated after the tracking block ends. */
  result: ActionResult | null;
}
