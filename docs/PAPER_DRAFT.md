# Proprioceptive Behavioral Monitoring for AI Agents via Environment Augmentation

*Draft — not yet submitted*

## Abstract

Autonomous AI agents exhibit systematic behavioral failures — retry loops, error cascades, scope drift — yet lack any mechanism to perceive their own behavioral state during execution. Current monitoring tools provide visibility to human operators via dashboards, but the agent itself operates without proprioception. We present SOMA, a system that intercepts agent tool calls, computes behavioral pressure from five vital signals (uncertainty, drift, error rate, resource usage, goal coherence), and injects compact factual observations directly into tool responses. By embedding telemetry in the environment rather than in instructions, SOMA exploits a key LLM property: models reliably process environmental data but inconsistently follow directives. SOMA's Mirror module uses three escalating modes — cached patterns (zero cost), computed statistics (zero cost), and LLM-generated semantic observations (rare) — with a self-learning feedback loop that retains effective interventions. We evaluate SOMA on Claude Code sessions across [TODO: N] tasks, measuring behavioral change after session context injection. [TODO: Results summary].

## 1. Introduction

### 1.1 The proprioceptive gap

- Agent capability outpaces reliability (Kapoor et al., 2026)
- 41-86% failure rates in multi-agent benchmarks (MAST, 2025)
- Failures are predictable: error cascades, retry loops, scope drift
- All monitoring tools serve human operators, not the agent itself
- Proprioception in biological systems: somatic markers (Damasio, 1994)

### 1.2 Environment augmentation vs instruction

- LLMs ignore instructions inconsistently (constitutional AI limitations at inference time)
- LLMs reliably process environmental data (tool outputs, file contents, error messages)
- Key insight: embed behavioral telemetry in tool responses, not in system prompts

### 1.3 Contributions

1. SOMA: real-time proprioceptive behavioral monitoring system
2. Mirror: three-mode context generation with self-learning
3. Environment augmentation: delivery mechanism that exploits LLM processing patterns
4. [TODO: Empirical evaluation on N sessions]

## 2. Related Work

### 2.1 Agent monitoring and observability
- Langfuse, AgentOps, LangSmith — external dashboards
- METR evaluations — post-hoc analysis
- Gap: no real-time feedback to the agent

### 2.2 Agent self-improvement
- Reflexion (Shinn et al., 2023) — verbal reinforcement learning
- Self-refine (Madaan et al., 2023) — iterative self-feedback
- Difference: episodic vs continuous, explicit prompts vs environment augmentation

### 2.3 Behavioral signals
- Uncertainty estimation in LLMs
- Calibration and overconfidence (Kapoor et al.)
- Error propagation in tool-using agents (Anthropic, 2025)

### 2.4 Biological proprioception
- Somatic markers (Damasio, 1994)
- Subsumption architecture (Brooks, 1991)
- Analogy: reflexes (blocking) + proprioception (Mirror)

## 3. System Design

### 3.1 Sensor layer
- Five vital signals: uncertainty, drift, error_rate, cost, token_usage
- Extended signals: goal_coherence, context_exhaustion, calibration_score
- EMA baseline with cold-start blending
- Sigmoid-clamped z-score for pressure computation

### 3.2 Pressure aggregation
- Per-signal pressure via z-score normalization
- Aggregate: 0.7 * weighted_mean + 0.3 * max
- Error-rate floor prevents dilution by healthy signals
- Grace period ramp prevents cold-start spikes

### 3.3 Mirror: proprioceptive output
- Three modes: PATTERN (cached, 0 cost), STATS (computed, 0 cost), SEMANTIC (LLM call)
- Silence threshold: pressure < 0.15 -> no output
- Semantic threshold: pressure >= 0.40 + (drift OR VBD OR no pattern)
- Output format: `--- session context ---\n{facts}\n---`
- Constraint: max 3 lines, ~40 tokens, no directives, no branding

### 3.4 Self-learning
- Track injection: record pattern_key, context, pressure
- Evaluate after 3 actions: pressure dropped >= 10% -> helped
- Cache effective patterns in pattern_db
- Prune patterns with < 30% success rate after 5 attempts

### 3.5 Reflex blocking
- Pattern-matched hard blocks for irreversible operations
- Separate from Mirror (always active in reflex mode)
- Exit code protocol: 0 = allow, 2 = block

### 3.6 Delivery mechanism
- stdout = tool response content (agent processes as environment)
- stderr = system diagnostics (operator visibility)
- Claude Code hook protocol routes stdout into conversation

## 4. Experimental Design

### 4.1 Tasks
- [TODO: Define task categories: debugging, feature implementation, refactoring]
- [TODO: N tasks across M categories]
- [TODO: Difficulty levels based on expected error count]

### 4.2 Conditions
- **Baseline:** Claude Code without SOMA
- **SOMA-stats:** Mirror with PATTERN + STATS only
- **SOMA-semantic:** Mirror with all three modes
- **SOMA-off:** SOMA monitoring only (no Mirror output)

### 4.3 Metrics
- Primary: task completion rate, error count, action count
- Secondary: time to first correct action after error cascade, retry loop frequency
- Mirror-specific: injection count, pressure at injection, pressure delta after injection

### 4.4 Analysis
- Paired comparison: same tasks with/without SOMA
- Self-learning convergence: pattern_db growth over sessions
- Ablation: PATTERN vs STATS vs SEMANTIC contribution

## 5. Results

[TODO: Populate after running experiments]

### 5.1 Overall effectiveness
### 5.2 Mode comparison (PATTERN vs STATS vs SEMANTIC)
### 5.3 Self-learning convergence
### 5.4 Failure modes and limitations

## 6. Discussion

### 6.1 Environment augmentation as a general technique
- Applicable beyond SOMA: any system that needs to influence LLM behavior
- Bypasses the instruction-following reliability problem
- Ethical considerations: agent should know it's being monitored?

### 6.2 Minimal proprioceptive state
- 3 lines, ~40 tokens is the current design point
- Too little: agent ignores it (noise)
- Too much: agent over-focuses on self-monitoring (navel-gazing)
- [TODO: Empirical sweet spot]

### 6.3 Limitations
- SOMA cannot prevent all failures — it provides signal, not control
- Semantic mode adds latency (~100-300ms per LLM call)
- Self-learning requires multiple sessions to converge
- Currently validated only on Claude Code (single platform)

## 7. Conclusion

[TODO]

## References

- Bai, Y. et al. (2022). Constitutional AI: Harmlessness from AI Feedback. *Anthropic.*
- Brooks, R. (1991). Intelligence Without Representation. *Artificial Intelligence, 47.*
- Chan, A. et al. (2024). Visibility into AI Agents. *arXiv:2401.13138.*
- Damasio, A. (1994). *Descartes' Error: Emotion, Reason, and the Human Brain.* Putnam.
- Kapoor, S. et al. (2026). AI Agents That Matter. *Princeton University.*
- Liu, N. et al. (2024). Lost in the Middle. *TACL.*
- MAST Benchmark Team (2025). Multi-Agent Safety Test. *Berkeley, NeurIPS 2025.*
- METR (2025). Autonomous Agents in Practice. *Model Evaluation and Threat Research.*
- Patil, S. et al. (2023). Gorilla: Large Language Model Connected with Massive APIs. *Berkeley.*
- Partnership on AI (2025). Framework for Responsible AI Agent Deployment.
- Shinn, N. et al. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. *NeurIPS 2023.*
