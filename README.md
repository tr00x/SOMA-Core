# SOMA Core

The nervous system for AI agents.

---

## What Makes SOMA Different

Most observability tools for AI agents record tokens, cost, and latency after the fact. SOMA monitors agent *behavior* in real time and acts on what it finds — modifying the context the agent sees, restricting its tools, or triggering a restart before a problem compounds.

| Capability | SOMA Core | LangSmith | AgentOps | Arize |
|---|---|---|---|---|
| Primary signals | Behavioral: uncertainty, semantic drift | Tokens, cost, latency | Tokens, cost, errors | Model performance metrics |
| Multi-agent model | Pressure graph with live trust dynamics | Trace linking | Session grouping | Dataset-level |
| Response to pressure | Directive context control (rewrites agent context) | Alerts only | Alerts only | Alerts only |
| Escalation ladder | Six levels: HEALTHY through SAFE_MODE | None | None | None |
| Session replay | Built-in | Limited | No | No |

**Behavioral signals** — uncertainty and semantic drift — are computed from the rolling window of agent actions, not from metadata. SOMA detects that an agent is confused or veering off-task before it surfaces as an error or an unexpected API call.

**Directive context control** physically modifies what the agent sees: trimming message history, removing expensive tools, or clearing context entirely, depending on the current escalation level.

**The pressure graph** models relationships between agents in a multi-agent system. Pressure propagates along trust-weighted edges, so a struggling sub-agent raises the effective pressure of the orchestrator that depends on it. Trust weights decay when an agent is uncertain and recover as it stabilizes.

---

## Install

```
pip install soma-core
```

Requires Python 3.11 or later.

---

## Quick Start

```python
from soma.engine import SOMAEngine
from soma.types import Action, Level

engine = SOMAEngine(budget={"tokens": 50_000, "cost_usd": 5.0})
engine.register_agent("planner", tools=["search", "code_exec", "write_file"])

action = Action(
    tool_name="search",
    output_text="Found 12 results for query.",
    token_count=340,
    cost=0.0004,
)

result = engine.record_action("planner", action)

print(result.level)      # Level.HEALTHY
print(result.pressure)   # 0.03
print(result.vitals.uncertainty)  # 0.11
```

Each call to `record_action` runs the full SOMA pipeline — vitals, baseline comparison, pressure aggregation, graph propagation, and ladder evaluation — and returns an `ActionResult` with the current escalation level.

---

## Multi-Agent

Register agents and connect them with directed trust edges. Pressure flows from the source to the target, damped by the trust weight.

```python
from soma.engine import SOMAEngine
from soma.types import Action

engine = SOMAEngine(budget={"tokens": 200_000})
engine.register_agent("orchestrator")
engine.register_agent("sub_agent_a")
engine.register_agent("sub_agent_b")

# orchestrator depends on both sub-agents
engine.add_edge("sub_agent_a", "orchestrator", trust_weight=0.9)
engine.add_edge("sub_agent_b", "orchestrator", trust_weight=0.7)

# Subscribe to escalation events
def on_level_change(event: dict) -> None:
    print(
        f"{event['agent_id']}: {event['old_level'].name} -> {event['new_level'].name}"
        f" (pressure={event['pressure']:.2f})"
    )

engine.events.on("level_changed", on_level_change)

# When sub_agent_a accumulates pressure, it propagates to orchestrator
for i in range(20):
    engine.record_action(
        "sub_agent_a",
        Action(tool_name="search", output_text="", error=(i % 3 == 0), token_count=500),
    )
```

Trust weights are dynamic: they decay when an agent's uncertainty exceeds 0.5 and recover as the agent stabilizes. Effective pressure for each agent is `max(internal_pressure, damping * weighted_avg_of_incoming)`.

---

## How It Works

```
Agent Action
     |
     v
  Vitals
  (uncertainty, drift, error_rate, token_usage, cost)
     |
     v
  Baseline
  (rolling mean + std per signal)
     |
     v
  Pressure
  (per-signal z-score normalization, then weighted aggregate)
     |
     v
  Graph
  (trust-weighted propagation across agent edges)
     |
     v
  Ladder
  (pressure + budget_health -> escalation level)
     |
     v
  Context Control
  (modifies messages, tools, system_prompt the agent receives)
```

**Vitals** are computed from the last 10 actions in the ring buffer. Uncertainty is a composite of output entropy, tool-call deviation from baseline, and format divergence. Drift is the cosine distance between the current behavior vector and the established baseline vector.

**Baseline** tracks rolling mean and standard deviation for each signal using exponential weighting, so early cold-start values are replaced as the agent accumulates history.

**Pressure** per signal is a clamped z-score: `(value - mean) / (std + epsilon)`, normalized to [0, 1]. Signals are weighted with uncertainty and drift carrying the highest weight in DIRECTIVE drift mode.

**Context control** is the only component that reaches back into the agent: it returns a modified copy of the context dict the caller passes it, never mutating the original.

---

## Six Escalation Levels

| Level | Pressure threshold | Context control applied |
|---|---|---|
| `HEALTHY` | < 0.25 | None. Full context and tools. |
| `CAUTION` | >= 0.25 | Newest 80% of messages retained. |
| `DEGRADE` | >= 0.50 | Newest 50% of messages. Expensive tools removed. |
| `QUARANTINE` | >= 0.75 | Message history cleared. Minimal tool set only. |
| `RESTART` | >= 0.90 | Message history cleared. Full tool list restored for fresh start. |
| `SAFE_MODE` | budget_health <= 0 | Message history cleared. Minimal tools. Latches until budget recovers above 10%. |

De-escalation uses hysteresis: the ladder only drops one level per evaluation cycle, and only when pressure falls below the de-escalate threshold (5 points below the escalate threshold for each level).

---

## Testing Your Agents

SOMA ships with `soma.testing.Monitor`, a pytest-compatible context manager that wraps the engine and exposes assertions.

```python
from soma.testing import Monitor
from soma.types import Action, Level

def test_planner_stays_healthy():
    with Monitor(budget={"tokens": 10_000}) as mon:
        # Warm up the baseline so cold-start uncertainty settles before asserting.
        for i in range(5):
            mon.record(
                "planner",
                Action(tool_name="search", output_text=f"warmup {i}", token_count=200),
            )
        mon.checkpoint()  # Reset history/cost tracking; engine baseline is preserved.

        for i in range(10):
            mon.record(
                "planner",
                Action(
                    tool_name="search",
                    output_text=f"result {i}",
                    token_count=200,
                ),
            )

    mon.assert_healthy()                   # current_level == HEALTHY
    mon.assert_below(Level.DEGRADE)        # max_level never reached DEGRADE


def test_erratic_agent_escalates():
    with Monitor(budget={"tokens": 10_000}) as mon:
        for i in range(20):
            mon.record(
                "agent",
                Action(
                    tool_name=f"tool_{i % 7}",   # high tool diversity -> uncertainty
                    output_text="",
                    error=True,
                    token_count=800,
                ),
            )

    assert mon.max_level >= Level.CAUTION
```

`Monitor` auto-registers agents on first use. Call `mon.checkpoint()` after a warm-up phase to reset history and cost tracking without resetting the underlying engine state.

---

## Session Replay

Record a live session to disk and replay it through a fresh engine — useful for regression testing, auditing, and debugging escalation sequences.

```python
from soma.recorder import SessionRecorder
from soma.replay import replay_session
from soma.types import Action

# --- record ---
recorder = SessionRecorder()
recorder.record("planner", Action(tool_name="search", output_text="ok", token_count=300))
recorder.record("planner", Action(tool_name="code_exec", output_text="done", token_count=700))
recorder.export("session.json")

# --- replay ---
loaded = SessionRecorder.load("session.json")
results = replay_session(
    loaded,
    budget={"tokens": 50_000},
    edges=[("sub_agent", "planner", 0.8)],
)

for r in results:
    print(r.level.name, r.pressure)
```

The replay function creates a fresh `SOMAEngine`, auto-registers all agents found in the recording, wires any edges you provide, and replays actions in chronological order.

---

## Claude Code Integration

`ClaudeCodeWrapper` is a persistent middleware layer designed for Claude Code sessions. It combines the engine, the session recorder, and context-action mapping into a single object.

```python
from soma.wrappers.claude_code import ClaudeCodeWrapper
from soma.types import Action, AutonomyMode

wrapper = ClaudeCodeWrapper(budget={"tokens": 100_000, "cost_usd": 10.0})
wrapper.register_agent(
    "claude",
    autonomy=AutonomyMode.HUMAN_ON_THE_LOOP,
    tools=["read_file", "write_file", "bash", "search"],
    expensive_tools=["bash", "write_file"],
)

def handle_tool_call(tool_name: str, output: str, tokens: int, cost: float) -> None:
    action = Action(tool_name=tool_name, output_text=output, token_count=tokens, cost=cost)
    result = wrapper.on_action("claude", action)

    if wrapper.should_block_tool("claude", tool_name):
        raise PermissionError(f"Tool {tool_name!r} blocked at level {result.level.name}")

    print(f"Level: {result.level.name}  Context action: {result.context_action}")
    # context_action is one of: "pass" | "truncate" | "block_tools" | "restart"

# Save the session for later replay or audit
wrapper.get_recording().export("claude_session.json")
```

---

## Build a Layer

SOMA Core is the foundation. The intended extension point is a **layer** package that adapts a specific framework, runtime, or tool to the SOMA pipeline.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide on building and publishing a layer.

**Planned community layers:**

- `soma-langchain` — LangChain agent executor integration
- `soma-autogen` — AutoGen multi-agent conversation monitoring
- `soma-crewai` — CrewAI crew and task monitoring
- `soma-openai` — OpenAI Assistants API integration
- `soma-llamaindex` — LlamaIndex query pipeline monitoring

If you are building a layer, open an issue to coordinate and avoid duplication.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Author

Tim Hunt ([@tr00x](https://github.com/tr00x))
