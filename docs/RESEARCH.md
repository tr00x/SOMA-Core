# Research Foundation

SOMA is built on findings from 12 research papers that collectively describe a gap: we can measure agent behavior, but we don't feed that data back to the agent.

See also: [Architecture](ARCHITECTURE.md) for system design, [Technical Reference](TECHNICAL.md) for formulas and constants, [Paper](PAPER.md) for the full academic treatment.

## Source papers

### Agent reliability

1. **Kapoor et al. (Princeton, 2026)** — "AI Agents That Matter." Reliability lags capability by 2–3× across SWE-bench, WebArena, and custom enterprise benchmarks. Agents with 90%+ accuracy on isolated tasks fail 40–60% of multi-step workflows. → SOMA response: real-time behavioral feedback via pressure model and Mirror.

2. **MAST (Berkeley, NeurIPS 2025)** — Multi-Agent Safety Test. 41–86% failure rate across 6 agent frameworks. Error cascades account for 34% of failures — one bad action triggers a chain of downstream errors. → SOMA response: error_rate vital, pattern detection, PressureGraph cascade propagation.

3. **METR (2025)** — "Autonomous Agents in Practice." Agents fail silently — no self-correction mechanism exists. 67% of failures could have been prevented with early detection of behavioral drift. → SOMA response: drift vital, goal_coherence tracking, Mirror proprioceptive injection.

4. **Shinn et al. (NeurIPS 2023)** — "Reflexion: Language Agents with Verbal Reinforcement Learning." Agents improve when given verbal feedback about past failures. But Reflexion requires explicit reflection prompts between episodes. → SOMA provides continuous real-time environmental feedback during execution, not between episodes.

5. **Madaan et al. (NeurIPS 2023)** — "Self-Refine: Iterative Refinement with Self-Feedback." Iterative self-improvement through explicit prompting. Operates episodically. → SOMA operates continuously via environment augmentation rather than prompts.

### Tool use and errors

6. **Anthropic (2025)** — "Tool Use Patterns in Production Agents." Tool errors propagate without behavioral feedback. 23% of agent sessions contain retry loops of 3+ identical failed commands. Error rate above 30% predicts session failure with 78% accuracy. → SOMA response: retry_dedup reflex, error_rate floor, predictive modeling with pattern boosts.

7. **Patil et al. (Berkeley, 2023)** — "Gorilla: Large Language Model Connected with Massive APIs." API hallucination rate increases with context length. Agents need grounding signals when tool calls drift from the task. → SOMA response: uncertainty classification (epistemic vs aleatoric), goal coherence tracking.

### Behavioral monitoring

8. **Partnership on AI (2025)** — "Framework for Responsible AI Agent Deployment." All monitoring recommendations focus on human oversight — logs, alerts, dashboards. No framework addresses agent self-monitoring. → SOMA closes this gap.

9. **Chan et al. (2024)** — "Visibility into AI Agents." arXiv:2401.13138. Proposes inspectability requirements for autonomous agents. Identifies the gap between what operators can see and what agents can see about themselves. → SOMA provides both operator visibility (stderr, dashboards) and agent visibility (stdout, environment augmentation).

### Context and degradation

10. **Liu et al. (TACL, 2024)** — "Lost in the Middle." LLMs degrade on information retrieval as context grows. → SOMA response: context_exhaustion signal, half-life modeling, handoff suggestions.

11. **Bai et al. (Anthropic, 2022)** — "Constitutional AI: Harmlessness from AI Feedback." Training-time behavioral constraints. → SOMA extends this to inference-time behavioral feedback — complementary, not competing.

### Biological and architectural foundations

12. **Brooks (1991)** — "Intelligence Without Representation." *Artificial Intelligence, 47.* Subsumption architecture: reactive layers that respond to sensor data without central planning. → SOMA's reflex layer operates on the same principle — pattern-matched blocking without reasoning.

13. **Damasio (1994)** — *Descartes' Error: Emotion, Reason, and the Human Brain.* Somatic markers: the body's feedback signals that inform decision-making. → Mirror is a computational analog — behavioral state embedded in the agent's sensory stream.

### Trust and control theory

14. **Slovic (1993)** — "Perceived Risk, Trust, and Democracy." *Risk Analysis, 13(6).* Trust is more easily destroyed than created. → SOMA encodes this in PressureGraph trust dynamics: 2.5:1 decay-to-recovery ratio.

15. **Shewhart (1931)** — *Economic Control of Quality of Manufactured Product.* Statistical process control with sigma-based control limits. → SOMA's z-score normalization is a direct descendant of Shewhart's control charts.

16. **Kendall & Gal (NeurIPS 2017)** — "What Uncertainties Do We Need in Bayesian Deep Learning?" Epistemic vs aleatoric uncertainty decomposition. → Adapted from neural network context to behavioral monitoring in SOMA's uncertainty classification.

17. **Kamvar et al. (WWW 2003)** — "The EigenTrust Algorithm for Reputation Management." → SOMA's PressureGraph trust-weighted propagation builds on this framework.

## Ailment mapping

12 common failure modes mapped to research and SOMA's response:

| # | Failure mode | Papers | SOMA mechanism | Status |
|---|-------------|--------|----------------|--------|
| 1 | Retry loops | [2], [6] | retry_dedup reflex, Mirror pattern | Proven |
| 2 | Error cascades | [2], [1] | error_rate vital, pressure escalation, error floor | Code exists |
| 3 | Blind mutations | [6], [7] | blind_edit reflex, reads_before_writes stat | Code exists |
| 4 | Scope drift | [3], [1] | goal_coherence vital, task_tracker, scope drift score | Code exists |
| 5 | Context degradation | [10], [6] | context_exhaustion signal, half-life model | Code exists |
| 6 | Silent failures | [3], [9] | pressure threshold, Mirror injection | Code exists |
| 7 | Tool hallucination | [7], [6] | uncertainty classification (epistemic/aleatoric) | Code exists |
| 8 | Thrashing | [6] | thrashing pattern, file edit tracking | Code exists |
| 9 | Research paralysis | [3] | research_stall pattern | Code exists |
| 10 | Overconfidence | [1] | verbal-behavioral divergence detection | Code exists |
| 11 | Budget exhaustion | [1] | MultiBudget, burn rate projection, half-life | Code exists |
| 12 | Multi-agent cascade | [2] | PressureGraph, trust-weighted propagation, cascade risk | Code exists |

## Gap analysis

### What exists

Every monitoring tool in the agent ecosystem follows the same pattern:

```
Agent acts → Tool records data → Dashboard shows data → Human reviews
```

Langfuse, AgentOps, Braintrust, Weights & Biases, LangSmith — all provide visibility *to humans*. The agent itself operates blind.

Reflexion [4] is the closest prior work — it gives agents verbal feedback about past performance. But it requires explicit reflection prompts, operates between episodes (not within), and has no continuous behavioral signal.

### What SOMA adds

```
Agent acts → SOMA computes behavioral state → State fed back to agent → Agent adjusts
```

No existing system closes this loop in real-time during a single agent session. SOMA does, via environment augmentation — embedding telemetry in tool responses rather than instructions.

### The proprioceptive gap

The research community measures agent behavior extensively but never feeds measurements back to the agent. This is equivalent to a robot with accelerometers and gyroscopes that sends all readings to a dashboard — but the robot itself has no proprioception.

SOMA's contribution is not better measurement (the signals are standard). It's the delivery mechanism: embedding behavioral telemetry into the agent's sensory stream.

## Research questions

**Primary:** What is the minimal sufficient proprioceptive state for effective agent self-correction?

SOMA's current answer: 3 lines, ~40 tokens, facts only.

```
--- session context ---
actions: 14 | errors: 4/6
pattern: same cmd repeated 3x
---
```

**Open questions:**
- Does semantic context (LLM-generated) outperform pattern/stats?
- What's the optimal injection frequency?
- Do agents develop "learned helplessness" from constant behavioral feedback?
- Does Mirror self-learning converge to stable effective patterns?
- Does environment augmentation transfer across LLM architectures?

## Related work comparison

| System | Visibility | Timing | Audience | Mechanism |
|--------|-----------|--------|----------|-----------|
| Langfuse | Full trace | Post-hoc | Human | Dashboard |
| AgentOps | Metrics | Real-time | Human | Dashboard + alerts |
| Reflexion [4] | Episode summary | Between episodes | Agent | Verbal prompt |
| Self-Refine [5] | Iteration feedback | Between iterations | Agent | Explicit prompt |
| Constitutional AI [11] | Training signal | Training time | Model | RLHF |
| **SOMA** | Behavioral state | Real-time, per-action | **Agent** | Environment augmentation |

## Further reading

- [Architecture](ARCHITECTURE.md) — full system design and data flow
- [Technical Reference](TECHNICAL.md) — every formula, constant, and algorithm
- [Paper](PAPER.md) — academic treatment with formal analysis
- [Guide](guide.md) — practical user guide
- [API Reference](api.md) — programmatic interface
