# SOMA: Proprioceptive Behavioral Monitoring for AI Agents

**Tim Hunt** — tr00x@proton.me

**April 2026 — Draft**

---

## Abstract

Autonomous AI agents exhibit systematic behavioral failures — retry loops, error cascades, scope drift — yet lack any mechanism to perceive their own behavioral state during execution. Current monitoring tools provide visibility to human operators via dashboards, but the agent itself operates without proprioception. We present SOMA, a real-time behavioral monitoring system that intercepts agent tool calls, computes behavioral pressure from multiple vital signals, detects failure patterns, enforces safety reflexes, and injects compact factual observations directly into tool responses. By embedding telemetry in the environment rather than in instructions, SOMA exploits a key LLM property: models reliably process environmental data but inconsistently follow directives. The system introduces a deterministic pressure model that normalizes heterogeneous behavioral signals via z-score sigmoid transformation, aggregates them through a weighted mean-max blend, and maps the result to four graduated response modes. SOMA includes a self-learning Mirror module that caches effective interventions, multi-agent pressure propagation over trust-weighted directed graphs, cross-session behavioral fingerprinting, and predictive modeling that anticipates failures before they occur. The system is open-source (MIT), validated through 74 test files across 90 modules (19k lines), and published on PyPI as `soma-ai`.

---

## 1. Introduction

### 1.1 The proprioceptive gap

The deployment of LLM agents in software engineering, research, and operational contexts has revealed a fundamental tension: the capabilities that make agents useful — autonomy, tool access, long-horizon planning — are precisely the capabilities that make them dangerous when they malfunction.

This is not anecdotal:
- **41–86% failure rate** across agent benchmarks (MAST, Berkeley NeurIPS 2025)
- **Reliability lags capability by 2–3×** (Kapoor et al., Princeton 2026)
- Agents degrade predictably — error cascades, retry loops, scope drift — but have no signal to self-correct

Every existing tool monitors agents *externally for humans*. Dashboards and alerts for the operator. The agent itself never sees the data.

In biological systems, proprioception — the sense of one's own body position and state — enables organisms to self-correct without conscious reasoning (Damasio, 1994). SOMA provides this missing sense for AI agents.

### 1.2 Environment augmentation vs. instruction

LLMs ignore instructions inconsistently. Constitutional AI constraints, system prompts, and behavioral directives all suffer from the same limitation: the model may or may not attend to them, and compliance degrades over long contexts (Liu et al., 2024).

LLMs reliably process environmental data. Tool outputs, file contents, and error messages are treated as facts about the world, not suggestions to follow.

**Key insight:** Embed behavioral telemetry in tool responses, not in system prompts. The agent processes it like any other environmental fact and adjusts.

### 1.3 Contributions

1. **Deterministic pressure model** — normalizes heterogeneous behavioral signals into a unified 0–1 scalar through z-score sigmoid transformation with learned baselines
2. **Graduated response system** — four modes (OBSERVE → GUIDE → WARN → BLOCK) with configurable thresholds and adaptive learning
3. **Mirror** — proprioceptive output layer with three cost-tiered modes (PATTERN/STATS/SEMANTIC) and self-learning feedback loop
4. **Reflex system** — pattern-matched hard blocks for irreversible operations, independent of pressure
5. **Multi-agent pressure propagation** — trust-weighted directed graph with per-signal vector propagation and coordination SNR
6. **Epistemic-aleatoric uncertainty decomposition** — modulates pressure based on whether uncertainty stems from knowledge gaps or inherent task variability
7. **Cross-session memory** — behavioral fingerprinting via Jensen-Shannon divergence, trajectory matching, learned pattern database
8. **Predictive modeling** — linear trend extrapolation with pattern-based boosters and cross-session trajectory matching
9. **Self-learning engine** — adapts thresholds and signal weights from intervention outcomes with bounded convergence
10. **Open-source implementation** — 90 modules, 74 test files, 19k lines, MIT license, published as `soma-ai` on PyPI

---

## 2. Related Work

### 2.1 Agent monitoring and observability

Langfuse, AgentOps, and LangSmith provide post-hoc dashboards for human operators. METR evaluations analyze agent behavior after execution. These tools serve an essential purpose but share a fundamental limitation: the agent never sees the data. SOMA addresses this gap by providing real-time feedback to the agent itself.

### 2.2 Agent self-improvement

Reflexion (Shinn et al., 2023) uses verbal reinforcement learning — the agent reflects on past episodes via explicit prompts. Self-Refine (Madaan et al., 2023) iterates through self-feedback cycles. Both operate episodically (between episodes, not during execution) and use explicit prompts (which models may ignore). SOMA operates continuously during execution and uses environment augmentation rather than prompts.

### 2.3 Biological proprioception

The human nervous system provides the architectural template. Peripheral nerves detect stimuli and transmit signals to the spinal cord. The response is graduated: mild stimuli produce awareness, moderate stimuli trigger reflexive withdrawal, extreme stimuli invoke emergency shutdown. This system operates without conscious reasoning — fast, deterministic, statistical deviation from baseline.

SOMA adopts this architecture: actions are stimuli, vitals computation extracts signal intensity, pressure aggregation produces a unified threat assessment, and the guidance system maps pressure to response modes. Reflexes (hard blocks) operate independently from Mirror (proprioceptive feedback), mirroring the biological separation of reflexive and perceptual systems (Brooks, 1991).

### 2.4 Control theory foundations

Shewhart's statistical process control (1931) introduced monitoring process variables against statistically derived control limits — exactly the pattern SOMA applies to behavioral signals. The z-score normalization is a direct descendant of Shewhart's sigma-based control limits. SOMA deliberately omits hysteresis, integral terms, and derivative terms to maintain explainability: each pressure computation depends only on current signals and learned baselines, never on previous pressure values.

Trust dynamics in the multi-agent graph draw on Slovic's work on asymmetric trust (1993): trust is more easily destroyed than created, encoded in SOMA's 2.5:1 decay-to-recovery ratio.

---

## 3. System Architecture

### 3.1 Design principles

**Determinism.** Same action history + same configuration = identical output. No randomness, no sampling. Essential for debugging, testing, and trust.

**Zero inference (core).** The monitoring pipeline never calls an LLM. Every computation is closed-form: EMA, cosine similarity, sigmoid, weighted sums. Sub-5ms per action. Mirror's SEMANTIC mode is the sole exception — optional, rare, cheap (~$0.001), with 3s timeout and fallback.

**Boundedness.** Every computation has known worst-case complexity. O(k×n) per action where k = signal count, n = window size (bounded constant).

**Explainability.** Every pressure value decomposes into constituent signals. Every signal traces to specific action properties. Mode mapping is a threshold lookup.

**Non-destructiveness.** SOMA never modifies agent state or alters agent outputs. Even in BLOCK mode, only specific destructive operations are prevented.

### 3.2 Pipeline overview

```
Tool Call → PreToolUse (reflexes) → Tool Execution → PostToolUse (sensing + Mirror) → Tool Response
```

The PreToolUse hook evaluates reflexes (hard blocks for destructive operations, retry dedup, blind edit prevention). The PostToolUse hook runs the full sensing pipeline: vitals computation, baseline updates, pressure aggregation, pattern detection, Mirror context generation, and state persistence.

### 3.3 The record_action pipeline

26-step sequential pipeline per action:

1. Tool tracking → ring buffer append → action count
2. Task complexity capture → initial task vector (after 5 actions)
3. Uncertainty computation (4 sub-signals) → drift (cosine distance) → time anomaly boost
4. Resource vitals (error_rate, token_usage, cost) → drift mode classification
5. Baseline EMA updates (α=0.15) → per-signal pressure (sigmoid z-scores)
6. Uncertainty classification (epistemic ×1.3 / aleatoric ×0.7) → goal coherence → context exhaustion
7. Burn rate → learning weight adjustments → upstream vector influence
8. Aggregate pressure (0.7×mean + 0.3×max) → error floor → grace period ramp
9. Graph propagation → trust dynamics → reliability metrics → mode determination
10. Events → state export → ActionResult

---

## 4. The Pressure Model

### 4.1 Signal definitions

| Signal | Weight | Description |
|--------|--------|-------------|
| Uncertainty | 2.0 | Composite: retry rate, tool call deviation, format deviation, entropy deviation |
| Drift | 1.8 | Cosine distance from baseline behavior vector (phase-aware) |
| Error rate | 1.5 | Fraction of errored actions in sliding window |
| Goal coherence | 1.5 | Cosine distance from initial task vector |
| Context exhaustion | 1.5 | Sigmoid of context window consumption |
| Cost | 1.0 | Budget utilization |
| Token usage | 0.8 | Token budget utilization |

### 4.2 Signal normalization

All signals normalized to [0, 1] via z-score sigmoid:

$$p_i = \text{sigmoid\_clamp}\left(\frac{x_i - \mu_i}{\max(\sigma_i, 0.05)}\right)$$

Where sigmoid_clamp(x) = 0 if x ≤ 0, 1 if x > 6, else 1/(1 + exp(−x + 3)). Floor of 0.05 on σ prevents extreme z-scores during cold start.

### 4.3 Pressure aggregation

$$P = 0.7 \cdot \frac{\sum w_i p_i}{\sum w_i} + 0.3 \cdot \max_i(p_i)$$

The weighted mean provides stability; the max provides sensitivity to single extreme signals.

**Error-rate floor** (linear ramp): when error pressure er_p ∈ [0.20, 1.00]:

$$\text{floor} = 0.10 + 0.60 \cdot \frac{er_p - 0.20}{0.80}$$

This prevents baseline normalization of errors — high error rates always produce proportional aggregate pressure.

**Signal-level floors:** error_rate > 0.3 → error_pressure = max(error_pressure, error_rate). Same for retry_rate → uncertainty_pressure.

### 4.4 Uncertainty decomposition

Output entropy (Shannon entropy over character bigrams) classifies uncertainty:
- **Epistemic** (low entropy + high uncertainty): agent lacks knowledge → pressure ×1.3
- **Aleatoric** (high entropy + high uncertainty): task inherently variable → pressure ×0.7

---

## 5. Baseline Learning

### 5.1 EMA with cold-start blending

Per-signal exponential moving average (α = 0.15, half-life ≈ 4.3 observations):

$$\mu_{t+1} = 0.15 \cdot x_t + 0.85 \cdot \mu_t$$
$$v_{t+1} = 0.15 \cdot (x_t - \mu_t)^2 + 0.85 \cdot v_t$$

During cold start (first 10 actions):

$$\text{result} = \text{blend} \cdot \text{computed} + (1 - \text{blend}) \cdot \text{default}$$

Where blend = min(count/10, 1.0). Defaults: uncertainty=0.05, drift=0.05, error_rate=0.01.

### 5.2 Grace period

Effective pressure linearly ramps during first 10 actions: pressure × (action_count / 10). This replaces the earlier force-to-zero approach that caused bimodal pressure distributions with cliff behavior at action 11.

Baselines are inherited across sessions — new sessions warm-start from the most active prior session.

---

## 6. Graduated Response

### 6.1 Response modes

| Mode | Default Threshold | Claude Code | Behavior |
|------|------------------|-------------|----------|
| OBSERVE | 0–25% | 0–40% | Silent monitoring |
| GUIDE | 25–50% | 40–60% | Soft suggestions, Mirror active |
| WARN | 50–75% | 60–80% | Insistent warnings, predictions |
| BLOCK | 75–100% | 80–100% | Destructive ops blocked only |

### 6.2 Reflex system

Pattern-matched hard blocks independent of pressure. 9 destructive bash patterns (rm -rf, git push -f, git reset --hard, etc.), 5 sensitive file patterns (.env, .pem, .key, credentials, secret). Additional reflexes: retry dedup (2+ identical commands), blind edit prevention (3+ writes without read), commit gate (blocks git commit at quality grade D/F).

### 6.3 Adaptive learning

The learning engine tracks intervention outcomes:
- **Success** (pressure dropped after escalation) → lower threshold, recover signal weights
- **Failure** (pressure unchanged) → raise threshold (+0.02), lower signal weights (−0.05)
- Bounded convergence: max threshold shift ±0.10, min signal weight 0.2

---

## 7. Mirror: Proprioceptive Output

### 7.1 Three modes

| Mode | Cost | Trigger | Output |
|------|------|---------|--------|
| PATTERN | $0 | Known pattern + cached context (success ≥ 60%) | Reused effective context |
| STATS | $0 | Elevated pressure, no pattern match | Raw numbers: errors, rates, signals |
| SEMANTIC | ~$0.001 | Pressure ≥ 40% + drift/VBD + no pattern | LLM-generated behavioral observation |

### 7.2 Delivery mechanism

stdout = tool response content (agent sees as environment data). stderr = system diagnostics (operator sees). Claude Code hooks route stdout into the conversation. The agent cannot distinguish SOMA context from real tool output.

Output format: `--- session context ---\n{facts}\n---`. Max 3 lines, ~40 tokens. No directives, no branding, no suggestions — only facts.

### 7.3 Self-learning

After each injection, Mirror tracks the pattern key, context text, and pressure at injection time. After 3 actions, it evaluates: if pressure dropped ≥ 10%, the context helped and is cached in the pattern database. Patterns with < 30% success rate after 5 attempts are pruned.

The pattern database persists at `~/.soma/patterns.json` and is reused across sessions. Over time, SOMA learns which behavioral observations are effective for each failure pattern and which are noise.

---

## 8. Multi-Agent Intelligence

### 8.1 PressureGraph

Directed graph with trust-weighted edges. Each node holds internal_pressure, effective_pressure, and a PressureVector (uncertainty, drift, error_rate, cost).

Propagation (max 3 iterations, damping=0.6):

$$\text{effective} = \max(\text{internal},\; 0.6 \cdot \text{weighted\_avg}(\text{upstream\_effective}))$$

Per-signal vector propagation preserves causality — downstream agents know *why* upstream is struggling, not just that it is.

### 8.2 Coordination SNR

Signal-to-noise ratio isolates healthy agents from noisy upstream:

$$\text{SNR} = \frac{\text{confirmed\_error\_pressure}}{\max(\text{total\_incoming}, 0.001)}$$

If SNR < 0.5 and total_incoming > 0.05, the node uses only internal pressure.

### 8.3 Trust dynamics

Trust decays when upstream uncertainty > 0.5 (−0.05 × uncertainty per action), recovers when healthy (+0.02 × (1 − uncertainty)). Decay:recovery ratio = 2.5:1, reflecting that trust is harder to rebuild than to lose (Slovic, 1993).

---

## 9. Cross-Session Memory

### 9.1 Behavioral fingerprinting

Per-agent fingerprints track tool distribution, error rate, read/write ratio, average duration, and session length. Updated via EMA (α=0.1) after each session.

Divergence detection via Jensen-Shannon divergence on tool distributions + error rate and read/write ratio deltas. Alert threshold: divergence ≥ 0.2. Requires ≥ 10 sessions.

### 9.2 Cross-session prediction

Past session trajectories (pressure curves) stored in `history.jsonl`. Current trajectory matched against historical patterns via cosine similarity. Final prediction blends 60% current trend + 40% historical match.

### 9.3 Session history

Append-only JSONL log per session: action count, pressure trajectory, mode transitions, tool distribution, phase sequence, error/retry counts, fingerprint divergence.

---

## 10. Predictive Modeling

Linear trend extrapolation via OLS regression on last 10 pressure readings, extrapolated 5 actions ahead.

**Pattern boosts** (additive):
- Error streak (3+ consecutive): +0.15
- Retry storm (error rate > 40%): +0.12
- Blind writes (2+ without Read): +0.10
- Thrashing (same file 3+ edits): +0.08

**Confidence:** 0.6 × sample_confidence + 0.4 × R² fit. Warning fires only when confidence > 0.3 AND predicted pressure crosses next threshold.

---

## 11. Quality and Root Cause Analysis

### 11.1 Quality scoring

Rolling window (30 events) of write and bash outcomes. Validation: py_compile + ruff (Python), node --check (JavaScript).

$$Q = \text{weighted\_avg}(\text{write\_score}, \text{bash\_score}) \times \max(0.5, 1 - 0.15 \times \text{syntax\_errors})$$

Grades: A (≥0.9), B (≥0.8), C (≥0.7), D (≥0.5), F (<0.5). Commit gate blocks git commit at D/F.

### 11.2 Root cause analysis

5 detectors: loop detection (severity 0.90), error cascade (0.50 + 0.10 per error), blind mutation (0.60 + 0.05 per write), research stall (0.50), drift explanation (0.40 + 0.50 × drift). Plain English output: "stuck in Edit→Bash loop on config.py (4 cycles)".

---

## 12. Evaluation

### 12.1 Implementation validation

- 90 modules, 19,000 lines of Python
- 74 test files with comprehensive coverage
- All core computations verified: pressure formulas, baseline convergence, graph propagation, self-learning convergence
- Determinism verified: same action sequence produces identical output across runs

### 12.2 Preliminary observations

SOMA has been operational in production on Claude Code sessions since March 2026. Preliminary observations:

- Mirror PATTERN mode (zero cost) handles the majority of interventions after pattern database is established
- Error-rate floor prevents the baseline normalization problem that previously allowed sustained high error rates to become "normal"
- Grace period linear ramp eliminates the bimodal pressure distribution observed with the earlier force-to-zero approach
- Self-learning converges within ~3 sessions for common failure patterns

### 12.3 Planned evaluation

Controlled A/B comparison across task categories (debugging, feature implementation, refactoring):
- **Baseline:** Claude Code without SOMA
- **SOMA-stats:** Mirror PATTERN + STATS only
- **SOMA-semantic:** All three Mirror modes
- **SOMA-off:** Monitoring only (no Mirror output)

Primary metrics: task completion rate, error count, action count. Secondary: time to recovery after error cascade, retry loop frequency.

---

## 13. Limitations

- SOMA provides signal, not control — it cannot prevent all failures
- Currently validated primarily on Claude Code (single platform)
- Self-learning requires multiple sessions to converge
- SEMANTIC mode adds latency (~100–300ms per LLM call)
- Cross-session prediction requires sufficient session history
- Behavioral fingerprinting requires ≥ 10 sessions for meaningful divergence detection
- The environment augmentation technique may not transfer to all LLM architectures

---

## 14. Conclusion

SOMA demonstrates that real-time proprioceptive feedback — agents sensing their own behavioral state — is both technically feasible and architecturally sound. The core insight is delivery mechanism: embedding telemetry in tool responses rather than instructions exploits a fundamental LLM property and bypasses the instruction-following reliability problem.

The system is deterministic, bounded, explainable, and non-destructive. It adapts to each agent through EMA baselines, learns from intervention outcomes, remembers across sessions, and predicts failures before they occur. The reflex system provides hard safety guarantees for irreversible operations, while Mirror provides continuous proprioceptive feedback.

SOMA is open-source under the MIT license, published as `soma-ai` on PyPI, and operational in production.

---

## References

1. Kapoor, S. et al. (2026). [AI Agents That Matter](https://arxiv.org/abs/2407.01502). *Princeton University.*
2. MAST Benchmark Team (2025). [Multi-Agent Safety Test](https://arxiv.org/abs/2401.05778). *Berkeley, NeurIPS 2025.*
3. METR (2025). [Autonomous Agents in Practice](https://metr.org/research). *Model Evaluation and Threat Research.*
4. Kamvar, S. et al. (2003). [The EigenTrust Algorithm](https://doi.org/10.1145/775152.775242). *WWW 2003.*
5. Slovic, P. (1993). Perceived Risk, Trust, and Democracy. *Risk Analysis, 13(6).*
6. Shewhart, W. (1931). *Economic Control of Quality of Manufactured Product.* Van Nostrand.
7. Astrom, K. & Murray, R. (2008). [Feedback Systems](https://fbswiki.org/wiki/index.php/Main_Page). *Princeton University Press.*
8. Bai, Y. et al. (2022). [Constitutional AI](https://arxiv.org/abs/2212.08073). *Anthropic.*
9. Kendall, A. & Gal, Y. (2017). [What Uncertainties Do We Need in Bayesian Deep Learning?](https://arxiv.org/abs/1703.04977) *NeurIPS 2017.*
10. Brooks, R. (1991). [Intelligence Without Representation](https://doi.org/10.1016/0004-3702(91)90053-M). *Artificial Intelligence, 47.*
11. Damasio, A. (1994). *Descartes' Error: Emotion, Reason, and the Human Brain.* Putnam.
12. Shinn, N. et al. (2023). [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366). *NeurIPS 2023.*
13. Madaan, A. et al. (2023). [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651). *NeurIPS 2023.*
14. Liu, N. et al. (2024). [Lost in the Middle](https://arxiv.org/abs/2307.03172). *TACL.*
15. Chan, A. et al. (2024). [Visibility into AI Agents](https://arxiv.org/abs/2401.13138). *arXiv:2401.13138.*
16. Anthropic (2025). [Tool Use Documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use). *Anthropic.*
17. Partnership on AI (2025). [Framework for Responsible AI Agent Deployment](https://partnershiponai.org/).

## Links

- **GitHub:** https://github.com/tr00x/SOMA-Core
- **PyPI:** https://pypi.org/project/soma-ai/
- **Docs:** [Quick Start](QUICKSTART.md) | [Architecture](ARCHITECTURE.md) | [Research](RESEARCH.md)
- **Dashboard:** `soma dashboard` (requires `pip install soma-ai[dashboard]`)
- **License:** MIT
