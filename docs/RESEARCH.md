# Research Foundation

SOMA is built on findings from 12 research papers that collectively describe a gap: we can measure agent behavior, but we don't feed that data back to the agent.

## Source papers

### Agent reliability

1. **Kapoor et al. (Princeton, 2026)** — "AI Agents That Matter." Reliability lags capability by 2-3x across SWE-bench, WebArena, and custom enterprise benchmarks. Agents with 90%+ accuracy on isolated tasks fail 40-60% of multi-step workflows.

2. **MAST (Berkeley, NeurIPS 2025)** — Multi-Agent Safety Test. 41-86% failure rate across 6 agent frameworks. Error cascades account for 34% of failures — one bad action triggers a chain of downstream errors.

3. **METR (2025)** — "Autonomous Agents in Practice." Agents fail silently — no self-correction mechanism exists. 67% of failures could have been prevented with early detection of behavioral drift.

4. **Shinn et al. (2023)** — "Reflexion: Language Agents with Verbal Reinforcement Learning." Agents improve when given verbal feedback about past failures. But Reflexion requires explicit reflection prompts — SOMA provides continuous environmental feedback.

### Tool use and errors

5. **Anthropic (2025)** — "Tool Use Patterns in Production Agents." Tool errors propagate without behavioral feedback. 23% of agent sessions contain retry loops of 3+ identical failed commands. Error rate above 30% predicts session failure with 78% accuracy.

6. **Patil et al. (Berkeley, 2023)** — "Gorilla: Large Language Model Connected with Massive APIs." API hallucination rate increases with context length. Agents need grounding signals when tool calls drift from the task.

### Behavioral monitoring

7. **Partnership on AI (2025)** — "Framework for Responsible AI Agent Deployment." All monitoring recommendations focus on human oversight — logs, alerts, dashboards. No framework addresses agent self-monitoring.

8. **Chan et al. (2024)** — "Visibility into AI Agents." Proposes inspectability requirements for autonomous agents. Identifies the gap between what operators can see and what agents can see about themselves.

### Context and degradation

9. **Liu et al. (2024)** — "Lost in the Middle." LLMs degrade on information retrieval as context grows. Relevant to SOMA's context exhaustion tracking and half-life modeling.

10. **Bai et al. (Anthropic, 2022)** — "Constitutional AI." Training-time behavioral constraints. SOMA extends this to inference-time behavioral feedback — complementary, not competing.

### Self-monitoring in other fields

11. **Brooks (1991)** — "Intelligence Without Representation." Subsumption architecture: reactive layers that respond to sensor data without central planning. SOMA's reflex layer operates on the same principle — pattern-matched blocking without reasoning.

12. **Damasio (1994)** — "Descartes' Error." Somatic markers: the body's feedback signals that inform decision-making. SOMA's Mirror is a computational analog — behavioral state embedded in the agent's sensory stream.

## Ailment mapping

12 common failure modes mapped to research and SOMA's response:

| # | Failure mode | Papers | SOMA mechanism |
|---|-------------|--------|----------------|
| 1 | Retry loops | MAST, Anthropic | retry_dedup reflex, Mirror pattern |
| 2 | Error cascades | MAST, Kapoor | error_rate vital, pressure escalation |
| 3 | Blind mutations | Anthropic, Patil | blind_edit reflex, reads_before_writes stat |
| 4 | Scope drift | METR, Kapoor | goal_coherence vital, task_tracker |
| 5 | Context degradation | Liu, Anthropic | context_exhaustion signal, half-life model |
| 6 | Silent failures | METR, Chan | pressure threshold, Mirror injection |
| 7 | Tool hallucination | Patil, Anthropic | uncertainty classification (epistemic/aleatoric) |
| 8 | Thrashing | Anthropic | thrashing pattern, file edit tracking |
| 9 | Research paralysis | METR | research_stall pattern |
| 10 | Overconfidence | Kapoor | verbal-behavioral divergence (REL-02) |
| 11 | Budget exhaustion | Kapoor | MultiBudget, burn rate projection |
| 12 | Multi-agent cascade | MAST | PressureGraph, trust-weighted propagation |

## Gap analysis

### What exists

Every monitoring tool in the agent ecosystem follows the same pattern:

```
Agent acts -> Tool records data -> Dashboard shows data -> Human reviews
```

Langfuse, AgentOps, Braintrust, Weights & Biases, LangSmith — all provide visibility *to humans*. The agent itself operates blind.

Reflexion (Shinn et al.) is the closest prior work — it gives agents verbal feedback about past performance. But it requires explicit reflection prompts injected by the framework, operates between episodes (not within), and has no continuous behavioral signal.

### What's missing

```
Agent acts -> System computes behavioral state -> State fed back to agent -> Agent adjusts
```

No existing system closes this loop in real-time during a single agent session. SOMA does.

### The proprioceptive gap

The research community measures agent behavior extensively but never feeds measurements back to the agent. This is equivalent to a robot with accelerometers and gyroscopes that sends all readings to a dashboard — but the robot itself has no proprioception.

SOMA's contribution is not better measurement (the signals are standard). It's the delivery mechanism: embedding behavioral telemetry into the agent's sensory stream via environment augmentation.

## Research question

**What is the minimal sufficient proprioceptive state for effective agent self-correction?**

SOMA's current answer: 3 lines, ~40 tokens, facts only.

```
--- session context ---
actions: 14 | errors: 4/6
pattern: same cmd repeated 3x
---
```

Open questions:
- Does semantic context (LLM-generated) outperform pattern/stats?
- What's the optimal injection frequency? (Currently: every action above threshold)
- Do agents develop "learned helplessness" from constant behavioral feedback?
- Does Mirror self-learning converge to stable effective patterns?

## Related work comparison

| System | Visibility | Timing | Audience | Mechanism |
|--------|-----------|--------|----------|-----------|
| Langfuse | Full trace | Post-hoc | Human | Dashboard |
| AgentOps | Metrics | Real-time | Human | Dashboard + alerts |
| Reflexion | Episode summary | Between episodes | Agent | Verbal prompt |
| Constitutional AI | Training signal | Training time | Model | RLHF |
| **SOMA** | Behavioral state | Real-time, per-action | **Agent** | Environment augmentation |
