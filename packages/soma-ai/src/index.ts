/**
 * soma-ai — TypeScript/JavaScript SDK for SOMA behavioral monitoring.
 *
 * Quick start:
 *   import { quickstart, track } from "soma-ai";
 *
 *   const engine = quickstart({ agents: ["my-agent"] });
 *
 *   const t = track(engine, "my-agent", "generateText");
 *   try {
 *     const result = await myLLMCall();
 *     t.setOutput(result);
 *     t.setTokens(result.usage.totalTokens);
 *   } catch (e) {
 *     t.setError(true);
 *     throw e;
 *   } finally {
 *     t.end();
 *   }
 *   console.log(t.result?.mode); // "OBSERVE" | "GUIDE" | "WARN" | "BLOCK"
 */

export type {
  Action,
  ActionResult,
  AgentConfig,
  Budget,
  ResponseMode,
  SomaEngine,
  SomaTracker,
  VitalsSnapshot,
} from "./types.js";

export { SOMAEngine, quickstart } from "./engine.js";
export { track } from "./track.js";
export { wrapVercelAI, SomaLangChainCallback } from "./wrap.js";
