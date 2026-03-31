/**
 * Framework adapters for Vercel AI SDK and LangChain.js (SDK-05).
 *
 * Vercel AI SDK usage:
 *   import { wrapVercelAI } from "soma-ai/wrap";
 *   const { text } = await generateText({
 *     model: openai("gpt-4o"),
 *     ...wrapVercelAI(engine, "my-agent"),
 *     prompt: "...",
 *   });
 *
 * LangChain.js usage:
 *   import { SomaLangChainCallback } from "soma-ai/wrap";
 *   const llm = new ChatOpenAI({
 *     callbacks: [new SomaLangChainCallback(engine, "my-agent")],
 *   });
 */

import type { Action, SomaEngine } from "./types.js";

// ---------------------------------------------------------------------------
// Vercel AI SDK adapter (SDK-05)
// ---------------------------------------------------------------------------

/**
 * Returns `onFinish` and `onError` callbacks compatible with the Vercel AI SDK.
 *
 * Pass the returned object as spread props to `generateText`, `streamText`, etc.
 *
 * @param engine  - SOMA engine instance
 * @param agentId - Registered agent to track
 */
export function wrapVercelAI(
  engine: SomaEngine,
  agentId: string,
): {
  onFinish: (result: { text?: string; usage?: { totalTokens?: number }; finishReason?: string }) => void;
  onError: (error: { error: unknown }) => void;
} {
  const startTime = Date.now();

  return {
    onFinish(result) {
      const action: Action = {
        toolName: "llm",
        outputText: result.text?.slice(0, 4000) ?? "",
        tokenCount: result.usage?.totalTokens ?? 0,
        durationSec: (Date.now() - startTime) / 1000,
        error: false,
      };
      engine.recordAction(agentId, action);
    },
    onError({ error }) {
      const action: Action = {
        toolName: "llm",
        outputText: String(error).slice(0, 4000),
        durationSec: (Date.now() - startTime) / 1000,
        error: true,
      };
      engine.recordAction(agentId, action);
    },
  };
}

// ---------------------------------------------------------------------------
// LangChain.js adapter (SDK-05)
// ---------------------------------------------------------------------------

/** Minimal type for LangChain BaseCallbackHandler compatibility. */
interface _LangChainCallbackHandler {
  handleLLMStart(llm: Record<string, unknown>, prompts: string[], runId: string): void;
  handleLLMEnd(output: unknown, runId: string): void;
  handleLLMError(error: Error, runId: string): void;
  handleToolStart(tool: Record<string, unknown>, input: string, runId: string): void;
  handleToolEnd(output: string, runId: string): void;
  handleToolError(error: Error, runId: string): void;
}

/**
 * LangChain.js callback handler that records every LLM call and tool use.
 *
 * Attach as a callback to any LangChain LLM, chain, or agent.
 */
export class SomaLangChainCallback implements _LangChainCallbackHandler {
  private _engine: SomaEngine;
  private _agentId: string;
  private _pending: Map<string, { startTime: number; toolName: string }> = new Map();

  constructor(engine: SomaEngine, agentId: string) {
    this._engine = engine;
    this._agentId = agentId;
  }

  handleLLMStart(_llm: Record<string, unknown>, _prompts: string[], runId: string): void {
    this._pending.set(runId, { startTime: Date.now(), toolName: "llm" });
  }

  handleLLMEnd(output: unknown, runId: string): void {
    const pending = this._pending.get(runId);
    const startTime = pending?.startTime ?? Date.now();
    this._pending.delete(runId);

    let outputText = "";
    let tokenCount = 0;
    try {
      const out = output as Record<string, unknown>;
      const generations = out["generations"] as Array<Array<{ text?: string }>> | undefined;
      if (generations) {
        for (const genList of generations) {
          for (const gen of genList) {
            outputText += gen.text ?? "";
          }
        }
      }
      const llmOutput = out["llmOutput"] as Record<string, unknown> | undefined;
      if (llmOutput) {
        const usage = llmOutput["tokenUsage"] as Record<string, number> | undefined;
        tokenCount = usage?.["totalTokens"] ?? 0;
      }
    } catch {
      // best-effort extraction
    }

    this._engine.recordAction(this._agentId, {
      toolName: "llm",
      outputText: outputText.slice(0, 4000),
      tokenCount,
      durationSec: (Date.now() - startTime) / 1000,
      error: false,
    });
  }

  handleLLMError(error: Error, runId: string): void {
    const pending = this._pending.get(runId);
    const startTime = pending?.startTime ?? Date.now();
    this._pending.delete(runId);

    this._engine.recordAction(this._agentId, {
      toolName: "llm",
      outputText: String(error).slice(0, 4000),
      durationSec: (Date.now() - startTime) / 1000,
      error: true,
    });
  }

  handleToolStart(tool: Record<string, unknown>, _input: string, runId: string): void {
    const toolName = (tool["name"] as string) ?? "tool";
    this._pending.set(runId, { startTime: Date.now(), toolName });
  }

  handleToolEnd(output: string, runId: string): void {
    const pending = this._pending.get(runId);
    const startTime = pending?.startTime ?? Date.now();
    const toolName = pending?.toolName ?? "tool";
    this._pending.delete(runId);

    this._engine.recordAction(this._agentId, {
      toolName,
      outputText: String(output).slice(0, 4000),
      durationSec: (Date.now() - startTime) / 1000,
      error: false,
    });
  }

  handleToolError(error: Error, runId: string): void {
    const pending = this._pending.get(runId);
    const startTime = pending?.startTime ?? Date.now();
    const toolName = pending?.toolName ?? "tool";
    this._pending.delete(runId);

    this._engine.recordAction(this._agentId, {
      toolName,
      outputText: String(error).slice(0, 4000),
      durationSec: (Date.now() - startTime) / 1000,
      error: true,
    });
  }
}
