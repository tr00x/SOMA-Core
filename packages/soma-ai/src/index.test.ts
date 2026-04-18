/**
 * Tests for the soma-ai TypeScript SDK.
 */

import { describe, it, expect, vi } from "vitest";
import { SOMAEngine, quickstart } from "./engine.js";
import { track } from "./track.js";
import { wrapVercelAI, SomaLangChainCallback } from "./wrap.js";

// ---------------------------------------------------------------------------
// SOMAEngine
// ---------------------------------------------------------------------------

describe("SOMAEngine", () => {
  it("registers an agent", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const snap = engine.getSnapshot("a");
    expect(snap.pressure).toBe(0);
    expect(snap.mode).toBe("OBSERVE");
  });

  it("records an action and returns a result", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const result = engine.recordAction("a", { toolName: "Bash", outputText: "ok" });
    expect(result.mode).toBeDefined();
    expect(result.pressure).toBeGreaterThanOrEqual(0);
    expect(result.pressure).toBeLessThanOrEqual(1);
  });

  it("tracks error rate", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    engine.recordAction("a", { toolName: "Bash", error: true });
    const snap = engine.getSnapshot("a");
    expect(snap.pressure).toBeGreaterThan(0);
  });

  it("auto-registers agent on first action", () => {
    const engine = new SOMAEngine();
    const result = engine.recordAction("auto", { toolName: "Test" });
    expect(result).toBeDefined();
  });

  it("returns OBSERVE for zero-pressure agent", () => {
    const engine = new SOMAEngine();
    const snap = engine.getSnapshot("unknown");
    expect(snap.mode).toBe("OBSERVE");
  });
});

// ---------------------------------------------------------------------------
// quickstart
// ---------------------------------------------------------------------------

describe("quickstart", () => {
  it("returns an engine with default agent", () => {
    const engine = quickstart();
    const snap = engine.getSnapshot("default");
    expect(snap.mode).toBe("OBSERVE");
  });

  it("registers named agents", () => {
    const engine = quickstart({ agents: ["a", "b"] });
    expect(engine.getSnapshot("a").mode).toBe("OBSERVE");
    expect(engine.getSnapshot("b").mode).toBe("OBSERVE");
  });
});

// ---------------------------------------------------------------------------
// track()
// ---------------------------------------------------------------------------

describe("track", () => {
  it("records action after end()", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");

    const t = track(engine, "a", "Bash");
    t.setOutput("hello");
    t.end();

    expect(t.result).not.toBeNull();
    expect(t.result!.mode).toBeDefined();
  });

  it("marks error when setError(true) called", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");

    const t = track(engine, "a", "Bash");
    t.setOutput("fail");
    t.setError(true);
    t.end();

    expect(t.result!.vitals.errorRate).toBeGreaterThan(0);
  });

  it("result is null before end()", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const t = track(engine, "a", "Bash");
    expect(t.result).toBeNull();
  });

  it("accepts initial tokenCount and cost options", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");

    const t = track(engine, "a", "LLM", { tokenCount: 500, cost: 0.01 });
    t.setOutput("response");
    t.end();

    expect(t.result!.vitals.tokenUsage).toBe(500);
    expect(t.result!.vitals.cost).toBeCloseTo(0.01);
  });
});

// ---------------------------------------------------------------------------
// wrapVercelAI
// ---------------------------------------------------------------------------

describe("wrapVercelAI", () => {
  it("records action on onFinish", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");

    const { onFinish } = wrapVercelAI(engine, "a");
    onFinish({ text: "result text", usage: { totalTokens: 100 } });

    const snap = engine.getSnapshot("a");
    expect(snap).toBeDefined();
  });

  it("records error on onError", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");

    const { onError } = wrapVercelAI(engine, "a");
    onError({ error: new Error("LLM failure") });

    const snap = engine.getSnapshot("a");
    expect(snap.pressure).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// SomaLangChainCallback
// ---------------------------------------------------------------------------

describe("SomaLangChainCallback", () => {
  it("records LLM call on handleLLMEnd", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const cb = new SomaLangChainCallback(engine, "a");

    cb.handleLLMStart({}, ["prompt"], "run-1");
    cb.handleLLMEnd(
      { generations: [[{ text: "reply" }]], llmOutput: { tokenUsage: { totalTokens: 50 } } },
      "run-1",
    );

    const snap = engine.getSnapshot("a");
    expect(snap).toBeDefined();
  });

  it("records error on handleLLMError", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const cb = new SomaLangChainCallback(engine, "a");

    cb.handleLLMStart({}, ["prompt"], "run-2");
    cb.handleLLMError(new Error("timeout"), "run-2");

    const snap = engine.getSnapshot("a");
    expect(snap.pressure).toBeGreaterThan(0);
  });

  it("records tool call on handleToolEnd", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const cb = new SomaLangChainCallback(engine, "a");

    cb.handleToolStart({ name: "search" }, "query", "run-3");
    cb.handleToolEnd("search results", "run-3");

    // No crash, action was recorded
    expect(engine.getSnapshot("a")).toBeDefined();
  });

  it("records tool error on handleToolError", () => {
    const engine = new SOMAEngine();
    engine.registerAgent("a");
    const cb = new SomaLangChainCallback(engine, "a");

    cb.handleToolStart({ name: "search" }, "query", "run-4");
    cb.handleToolError(new Error("tool failed"), "run-4");

    expect(engine.getSnapshot("a").pressure).toBeGreaterThan(0);
  });
});
