/**
 * soma.track() — universal context manager for TypeScript (SDK-05).
 *
 * Usage:
 *   const engine = soma.quickstart();
 *   engine.registerAgent("my-agent");
 *
 *   const tracker = soma.track(engine, "my-agent", "Bash");
 *   try {
 *     const output = await runCommand();
 *     tracker.setOutput(output);
 *   } catch (e) {
 *     tracker.setError(true);
 *     throw e;
 *   } finally {
 *     tracker.end();
 *   }
 *   console.log(tracker.result?.mode);
 */

import type { Action, ActionResult, SomaEngine, SomaTracker } from "./types.js";

class _SomaTracker implements SomaTracker {
  private _engine: SomaEngine;
  private _agentId: string;
  private _toolName: string;
  private _startTime: number;
  private _outputText: string = "";
  private _error: boolean = false;
  private _tokens: number;
  private _cost: number;
  private _retried: boolean = false;
  result: ActionResult | null = null;

  constructor(
    engine: SomaEngine,
    agentId: string,
    toolName: string,
    tokenCount = 0,
    cost = 0,
  ) {
    this._engine = engine;
    this._agentId = agentId;
    this._toolName = toolName;
    this._tokens = tokenCount;
    this._cost = cost;
    this._startTime = Date.now();
  }

  setOutput(text: string): void {
    this._outputText = text;
  }

  setError(isError: boolean): void {
    this._error = isError;
  }

  setTokens(count: number): void {
    this._tokens = count;
  }

  setCost(cost: number): void {
    this._cost = cost;
  }

  setRetried(retried: boolean): void {
    this._retried = retried;
  }

  /** Finalize the tracked action and record it in the engine. */
  end(): ActionResult {
    const durationSec = (Date.now() - this._startTime) / 1000;
    const action: Action = {
      toolName: this._toolName,
      outputText: this._outputText,
      tokenCount: this._tokens,
      durationSec,
      error: this._error,
      cost: this._cost,
      retried: this._retried,
    };
    this.result = this._engine.recordAction(this._agentId, action);
    return this.result;
  }
}

/**
 * Create a tracker for a single agent action.
 *
 * You must call `.end()` (or use a try/finally block) to record the action.
 *
 * @param engine   - SOMA engine instance
 * @param agentId  - Registered agent to track
 * @param toolName - Name of the tool or operation
 * @param options  - Optional initial token count and cost
 */
export function track(
  engine: SomaEngine,
  agentId: string,
  toolName: string,
  options: { tokenCount?: number; cost?: number } = {},
): SomaTracker & { end(): ActionResult } {
  return new _SomaTracker(engine, agentId, toolName, options.tokenCount, options.cost);
}
