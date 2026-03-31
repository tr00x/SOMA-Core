# SOMA: System of Oversight and Monitoring for Agents — A Deterministic Behavioral Control Framework

**Tim Hunt**
tr00x@proton.me

**March 2026**

---

## Abstract

We present SOMA (System of Oversight and Monitoring for Agents), a deterministic behavioral control framework for autonomous AI agents. SOMA observes agent actions in real-time, computes behavioral pressure from six vital signals, and injects corrective guidance into agent context before problems escalate. Unlike training-time alignment techniques or post-hoc evaluation frameworks, SOMA operates as a runtime nervous system: it requires zero inference calls, completes in bounded O(k*n) time per action, and produces fully explainable decisions. The system introduces a novel pressure model that normalizes heterogeneous behavioral signals via z-score sigmoid transformation, aggregates them through a weighted mean-max blend, and maps the result to four graduated response modes (OBSERVE, GUIDE, WARN, BLOCK). We describe the complete architecture including exponential moving average baselines with cold-start blending, epistemic-aleatoric uncertainty decomposition, multi-agent pressure propagation over trust-weighted directed graphs, a self-learning engine that adapts thresholds from intervention outcomes, and predictive modeling that anticipates failures before they occur. SOMA is validated through 735 tests across 37 modules and integration scenarios totaling 231 actions across 4 distinct agent behavioral profiles. The system is open-source under the MIT license and published on PyPI as `soma-ai`.

---

## 1. Introduction

### 1.1 The Autonomous Agent Problem

The deployment of large language model (LLM) agents in software engineering, research, and operational contexts has revealed a fundamental tension: the capabilities that make agents useful --- autonomy, tool access, long-horizon planning --- are precisely the capabilities that make them dangerous when they malfunction. Agents exhibit failure modes that are qualitatively different from traditional software bugs: they drift from assigned tasks, enter repetitive loops, escalate destructive operations, and compound errors through cascading sequences of poor decisions [1, 12, 14].

These failures are not rare edge cases. Empirical studies on SWE-bench demonstrate that even state-of-the-art agents fail on the majority of tasks, and when they fail, they often fail catastrophically --- overwriting correct code, executing destructive shell commands, or spending thousands of tokens pursuing fundamentally flawed approaches [1, 2]. The problem is compounded by the fact that agent failures are often silent: a human supervisor reviewing a transcript post-hoc may not recognize the point at which the agent's behavior became pathological until significant damage has been done.

### 1.2 Why Existing Solutions Fall Short

Current approaches to agent safety cluster into three categories, each with fundamental limitations:

**Training-time alignment** (Constitutional AI [8], RLHF) embeds safety constraints into model weights. While effective for broad behavioral norms, this approach cannot adapt to task-specific contexts, cannot monitor runtime behavioral trajectories, and provides no mechanism for graduated intervention. A model that has been trained to be helpful will still pursue a flawed plan with great enthusiasm.

**Post-hoc evaluation** (benchmarks, evals) measures agent performance after execution completes. This is valuable for capability assessment but provides zero protection during execution. By the time an eval reveals a problem, the damage is done.

**Guardrail systems** (input/output filters, tool restrictions) operate at the boundary layer, checking individual requests against static rules. These systems lack behavioral context --- they cannot distinguish between a `rm -rf` that is part of a legitimate cleanup operation and one that represents a panicking agent destroying evidence of its failures.

What is missing is a **runtime behavioral monitoring system** that observes the full trajectory of agent actions, maintains statistical baselines, detects anomalies as they develop, and intervenes with graduated corrective guidance --- all without requiring additional inference calls or introducing unbounded latency.

### 1.3 Contributions

This paper makes the following contributions:

1. A **deterministic pressure model** that normalizes heterogeneous behavioral signals (uncertainty, drift, error rate, goal coherence, cost, token usage) into a unified 0--1 scalar through z-score sigmoid transformation with learned baselines.

2. An **exponential moving average baseline system** with cold-start blending that prevents false positives during early session phases while converging to accurate behavioral profiles within approximately 10 actions.

3. A **four-mode graduated response system** (OBSERVE, GUIDE, WARN, BLOCK) that maps pressure to intervention intensity, where BLOCK mode selectively prevents destructive operations rather than halting all agent activity.

4. A **multi-agent pressure propagation algorithm** over trust-weighted directed graphs with damped convergence, enabling behavioral monitoring of agent ensembles where one agent's instability can be detected through its effects on downstream agents.

5. An **epistemic-aleatoric uncertainty decomposition** using output entropy that modulates pressure based on whether uncertainty stems from knowledge gaps (actionable) or inherent task variability (expected).

6. A **self-learning engine** that adapts pressure thresholds and signal weights from intervention outcomes, reducing false positive rates over time without manual tuning.

7. A **predictive model** combining linear trend extrapolation with pattern-based boosters that anticipates behavioral failures before they manifest.

8. A **goal coherence tracker** that detects task drift by comparing current behavior vectors against initial task vectors captured during warmup.

9. A **reliability scoring system** that detects verbal-behavioral divergence --- the gap between an agent's expressed confidence and its actual behavioral indicators --- as a signal of potential deceptive alignment.

10. A complete **open-source implementation** validated through 735 tests, published as `soma-ai` on PyPI, currently operational as a Claude Code hook system.

---

## 2. Background and Inspiration

### 2.1 Biological Nervous Systems

The human nervous system provides a compelling architectural template for agent monitoring. Peripheral nerves detect stimuli (temperature, pressure, pain) and transmit signals to the spinal cord and brain. The response is graduated: mild stimuli produce awareness, moderate stimuli trigger reflexive withdrawal, and extreme stimuli invoke emergency shutdown. Critically, this system operates without conscious reasoning --- it is fast, deterministic, and operates on statistical deviation from baseline expectations.

SOMA adopts this architecture directly. Agent actions are stimuli. Vitals computation extracts signal intensity. The pressure model aggregates signals into a unified threat assessment. The guidance system maps pressure to response modes, from passive observation to active intervention. The entire pipeline completes without inference calls, operating purely on statistical computation.

### 2.2 Control Theory

Classical control theory, particularly the work of Shewhart [6] on statistical process control and Astrom and Murray [7] on feedback control systems, provides the mathematical foundation for SOMA's approach. Shewhart's control charts introduced the concept of monitoring a process variable against statistically derived control limits --- exactly the pattern SOMA applies to behavioral signals. The z-score normalization used in SOMA's pressure computation is a direct descendant of Shewhart's sigma-based control limits.

SOMA deliberately omits certain control-theoretic constructs. There is no hysteresis in mode transitions, no integral term accumulating historical error, and no derivative term responding to rate of change. This is by design: the pressure model must be stateless with respect to its own outputs to maintain explainability. Each pressure computation depends only on current signals and learned baselines, never on previous pressure values or mode history.

### 2.3 Anomaly Detection

The pressure model draws on anomaly detection literature, particularly z-score-based approaches for univariate signals and cosine-distance-based approaches for multivariate behavioral vectors. The sigmoid transformation applied to z-scores ensures bounded output regardless of signal magnitude, addressing the practical concern that raw z-scores can produce arbitrarily large values for heavy-tailed distributions common in agent behavioral data.

### 2.4 Trust and Reputation Systems

The multi-agent pressure propagation mechanism builds on the EigenTrust framework [4] and Slovic's foundational work on asymmetric trust dynamics [5]. Slovic demonstrated that trust is more easily destroyed than created --- a finding SOMA encodes in its 2.5:1 trust decay-to-recovery ratio. The propagation algorithm itself uses damped iteration similar to PageRank but applied to pressure rather than authority, with convergence guarantees provided by the damping factor.

---

## 3. System Architecture

### 3.1 Design Principles

SOMA is built on five non-negotiable design principles:

**Determinism.** Given the same action history and configuration, SOMA produces identical pressure values and guidance decisions. There are no random components, no sampling, no probabilistic inference. This property is essential for debugging, testing, and trust: operators must be able to reproduce and explain every decision the system makes.

**Zero inference.** SOMA never calls an LLM or any external inference service during its monitoring pipeline. Every computation is closed-form arithmetic: exponential moving averages, cosine similarities, sigmoid transformations, weighted sums. This eliminates the latency, cost, and reliability concerns that would arise from inference-in-the-loop monitoring.

**Boundedness.** Every computation in the pipeline has known worst-case complexity. The full `record_action` pipeline executes in O(k*n) time where k is the number of signals (6) and n is the window size (bounded constant). In practice, the complete pipeline executes in under 5 milliseconds.

**Explainability.** Every pressure value can be decomposed into its constituent signals, each signal can be traced to specific action properties, and the mapping from pressure to response mode is a simple threshold lookup. There are no black-box components.

**Non-destructiveness.** SOMA never modifies agent state, intercepts agent communications, or alters agent outputs. It operates as a pure observer that emits guidance signals into the agent's context. Even in BLOCK mode, SOMA blocks only specific destructive operations --- it never halts the agent entirely.

### 3.2 The Record-Action Pipeline

The core of SOMA is the `record_action` method on `SOMAEngine`, which processes each agent action through a 22-step pipeline:

1. Validate agent registration
2. Append action to history window
3. Compute uncertainty signal
4. Compute drift signal
5. Compute error rate signal
6. Compute resource vitals (cost, token usage)
7. Compute goal coherence signal
8. Construct vitals snapshot
9. Update EMA baseline for each signal
10. Compute z-score for each signal against baseline
11. Apply sigmoid normalization to each z-score
12. Apply signal-level floors (error rate, retry rate)
13. Compute weighted mean of normalized pressures
14. Compute maximum normalized pressure
15. Blend mean and max: P = 0.7 * weighted_mean + 0.3 * max_p
16. Apply error-rate aggregate floor
17. Apply grace period (force to 0.0 if within first 10 actions)
18. Propagate pressure through multi-agent graph (if applicable)
19. Map pressure to response mode
20. Update predictive model
21. Update learning engine
22. Emit ActionResult with vitals, pressure, mode, and guidance

### 3.3 Computational Complexity

The pipeline processes k = 6 signals, each computed over a bounded window of recent actions. Baseline updates are O(1) per signal (EMA is a constant-time recurrence). Drift computation involves a cosine similarity over a behavior vector of fixed dimensionality. Pressure propagation over the agent graph runs for at most 3 iterations with convergence threshold 1e-6, and is linear in the number of edges. The overall complexity per action is O(k*n) where n is the window size, which is bounded by configuration. In practice, this yields sub-5ms latency per action on commodity hardware.

### 3.4 Layer-Agnostic Architecture

While SOMA currently ships with a Claude Code hook integration, the core engine is deliberately platform-agnostic. Three modules provide the abstraction boundary:

- **`patterns.py`** --- Behavioral pattern detection (loops, error cascades, blind mutations, thrashing) expressed purely in terms of action sequences, independent of any specific agent platform.

- **`findings.py`** --- Aggregates monitoring insights (quality scores, predictions, scope drift, root cause analyses) into a structured `Finding` dataclass list that any integration layer can consume.

- **`context.py`** --- Session context detection (workflow mode, action count, pressure trajectory) that informs guidance without coupling to a specific environment.

The hook layer (`hooks/`) translates between the platform-specific environment (e.g., Claude Code's `CLAUDE_HOOK` mechanism) and the platform-agnostic core, ensuring that the monitoring logic can be reused across any agent framework.

---

## 4. The Pressure Model

### 4.1 Signal Definitions

SOMA monitors six behavioral signals, each capturing a distinct dimension of agent health:

| Signal | Symbol | Range | Description |
|--------|--------|-------|-------------|
| Uncertainty | U | [0, 1] | Composite measure of retry behavior, output variability, failure indicators, and execution inconsistency |
| Drift | D | [0, 1] | Cosine distance between current behavior vector and learned baseline vector |
| Error Rate | E | [0, 1] | Fraction of recent actions that produced errors |
| Goal Coherence | G | [0, 1] | Cosine distance between current behavior vector and initial task vector |
| Cost | C | [0, inf) | Cumulative or rate-based monetary cost of API calls |
| Token Usage | T | [0, inf) | Cumulative or rate-based token consumption |

### 4.2 Uncertainty Computation

Uncertainty is computed as a weighted combination of four sub-signals:

$$U = 0.30 \cdot R + 0.25 \cdot \sigma(T) + 0.20 \cdot F + 0.25 \cdot \sigma(E)$$

where:

- R is the retry rate (fraction of recent actions that are retries of previous actions)
- T is tool output variability, passed through sigmoid clamp sigma
- F is the failure indicator rate (fraction of actions with error outputs)
- E is execution time variability, passed through sigmoid clamp sigma
- sigma denotes the sigmoid clamping function that bounds unbounded sub-signals to [0, 1]

The weights reflect empirical observation that retry behavior is the strongest individual signal of agent confusion, while output variability and execution inconsistency provide complementary evidence.

### 4.3 Drift Computation

Drift measures how far the agent's current behavioral pattern has deviated from its established baseline:

$$D = 1 - \cos(\mathbf{v}_{\text{current}}, \mathbf{v}_{\text{baseline}})$$

where the behavior vector **v** is composed of:

$$\mathbf{v} = [\text{avg\_tool\_calls},\; \text{avg\_output\_len} / 1000,\; \text{avg\_response\_time},\; \text{pattern\_entropy},\; \ldots\text{tool\_dist}]$$

The behavior vector captures both aggregate statistics (average tool calls per action, average output length normalized by 1000, average response time, Shannon entropy of tool usage patterns) and the full tool usage distribution. Cosine similarity is used rather than Euclidean distance because it is invariant to the absolute scale of activity --- an agent that performs 100 actions with a consistent tool distribution should have the same drift as one that performs 10 actions with the same distribution.

### 4.4 Signal Normalization

Raw signal values are heterogeneous: uncertainty is bounded in [0, 1], while cost and token usage are unbounded. SOMA normalizes all signals to a common [0, 1] pressure scale using z-score sigmoid transformation:

$$p_i = \text{sigmoid}\left(\frac{x_i - \mu_i}{\max(\sigma_i, 0.05)}\right)$$

where mu_i and sigma_i are the learned EMA baseline mean and standard deviation for signal i. The floor of 0.05 on the standard deviation prevents division by near-zero values during cold start, when variance estimates have not yet converged. This minimum standard deviation value of 0.05 is critical for numerical stability and was determined empirically to provide the best balance between sensitivity and stability.

The sigmoid function maps the z-score to [0, 1], producing a pressure value that is:
- Near 0 when the signal is at or below baseline (z <= -2)
- Near 0.5 when the signal is at baseline (z = 0)
- Near 1 when the signal is significantly above baseline (z >= 2)

### 4.5 Pressure Aggregation

Individual signal pressures are aggregated into a single scalar through a weighted mean-max blend:

$$P = 0.7 \cdot \text{weighted\_mean} + 0.3 \cdot \max_i(p_i)$$

The weighted mean provides stability --- no single signal can dominate the aggregate unless it has disproportionate weight. The max term provides sensitivity --- a single extremely elevated signal will still register even if all other signals are nominal. The 0.7/0.3 blend ratio was determined through iterative testing to provide the best trade-off between false positive suppression and genuine anomaly detection.

### 4.6 Error-Rate Aggregate Floor

When the error rate signal pressure (er_p) reaches or exceeds 0.50, the aggregate pressure is subject to a floor that ensures the system cannot underreact to sustained errors:

$$\text{floor} = 0.40 + 0.40 \cdot \frac{er_p - 0.50}{0.50}$$

This floor creates a direct mapping from error pressure to minimum response modes:

| Error Pressure | Floor | Minimum Mode |
|---------------|-------|-------------|
| 0.50 | 0.40 | GUIDE |
| 0.75 | 0.60 | WARN |
| 1.00 | 0.80 | BLOCK |

The floor activates only when the error_rate signal weight is greater than zero, allowing operators to disable this mechanism by zeroing the error rate weight in configuration.

### 4.7 Signal-Level Floors

In addition to the aggregate floor, two signal-level floors ensure that extreme individual readings are not attenuated by the normalization pipeline:

- If error_rate > 0.3: error_pressure = max(error_pressure, error_rate)
- If retry_rate > 0.3: uncertainty_pressure = max(uncertainty_pressure, retry_rate)

These floors bypass the z-score normalization for extreme values, ensuring that a 50% error rate always produces at least 0.50 error pressure regardless of what the baseline considers "normal."

### 4.8 Default Signal Weights

The default weights reflect the relative importance of each signal for general-purpose agent monitoring:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| Uncertainty | 2.0 | Strongest predictor of impending failure |
| Drift | 1.8 | Early indicator of task abandonment |
| Error Rate | 1.5 | Direct measure of operational failure |
| Goal Coherence | 1.5 | Detects scope creep and task drift |
| Cost | 1.0 | Resource consumption tracking |
| Token Usage | 0.8 | Least specific signal; high token usage may be legitimate for complex tasks |

Weights are configurable per agent and are subject to adjustment by the self-learning engine based on intervention outcomes.

---

## 5. Baseline Learning

### 5.1 Exponential Moving Average

SOMA maintains per-signal EMA baselines that track both the mean and variance of each signal over time:

$$\mu_{t+1} = 0.15 \cdot x_t + 0.85 \cdot \mu_t$$

$$v_{t+1} = 0.15 \cdot (x_t - \mu_t)^2 + 0.85 \cdot v_t$$

The smoothing factor alpha = 0.15 provides a half-life of approximately 4.3 observations, meaning the baseline adapts to sustained behavioral shifts within roughly 5--10 actions while smoothing out transient spikes. The standard deviation is derived as sigma = sqrt(v).

### 5.2 Cold-Start Blending

During the initial phase of a session, EMA estimates are unreliable because they are dominated by the initialization value. SOMA addresses this through a linear blending scheme:

$$\text{blend} = \min\left(\frac{\text{count}}{10},\; 1.0\right)$$

$$\text{result} = \text{blend} \cdot \text{computed} + (1 - \text{blend}) \cdot \text{default}$$

For the first 10 observations, the baseline is a linear interpolation between the computed EMA value and a conservative default. The defaults are calibrated to represent "healthy" agent behavior:

| Signal | Default |
|--------|---------|
| Uncertainty | 0.05 |
| Drift | 0.05 |
| Error Rate | 0.01 |
| Cost | 0.01 |
| Token Usage | 0.01 |

These defaults are deliberately low, ensuring that any significant behavioral anomaly during cold start will still register as elevated pressure even before the baseline has converged.

### 5.3 Grace Period

During the first min_samples = 10 actions, aggregate pressure is forced to 0.0 regardless of the computed value. This grace period serves two purposes: it prevents false positives from noisy initial actions (agent setup, environment probing), and it allows the baseline sufficient observations to produce meaningful estimates before pressure values are acted upon.

The grace period is distinct from cold-start blending. Blending affects baseline computation (gradual convergence). The grace period affects pressure output (hard zero). Both mechanisms operate during the first 10 actions, but they address different failure modes: blending prevents baseline corruption, while the grace period prevents premature intervention.

---

## 6. Uncertainty Classification

### 6.1 Epistemic vs. Aleatoric Decomposition

Not all uncertainty is equal. Epistemic uncertainty arises from knowledge gaps --- the agent does not know how to proceed and would benefit from additional information or guidance. Aleatoric uncertainty arises from inherent task variability --- the task involves genuinely unpredictable elements, and elevated uncertainty is expected and acceptable.

SOMA decomposes uncertainty using output entropy, computed as Shannon entropy over character bigrams in the agent's output text. The intuition is that epistemic uncertainty produces hedging, repetitive phrasing, and low-information output (low entropy), while aleatoric uncertainty produces diverse, information-rich output as the agent explores a genuinely complex space (high entropy).

### 6.2 Classification Thresholds

The classification uses three thresholds:

- **min_uncertainty = 0.3**: Below this threshold, uncertainty is too low for classification to be meaningful, and no modulation is applied.
- **low_entropy = 0.35**: Output entropy below this threshold, combined with uncertainty above min_uncertainty, indicates epistemic uncertainty.
- **high_entropy = 0.65**: Output entropy above this threshold, combined with uncertainty above min_uncertainty, indicates aleatoric uncertainty.
- Entropy values between 0.35 and 0.65 are classified as mixed and receive no modulation.

### 6.3 Pressure Modulation

The uncertainty classification modulates the pressure contribution of the uncertainty signal:

- **Epistemic**: pressure multiplied by 1.3 (capped at 1.0). The agent genuinely does not know what it is doing; heightened vigilance is warranted.
- **Aleatoric**: pressure multiplied by 0.7. The task is inherently variable; the elevated uncertainty is expected and should not trigger unnecessary intervention.

This decomposition is inspired by the theoretical framework of Kendall and Gal [9], adapted from the neural network context to behavioral monitoring. Where Kendall and Gal decompose predictive uncertainty in model outputs, SOMA decomposes behavioral uncertainty in agent action sequences.

---

## 7. Guidance System

### 7.1 Response Modes

Pressure is mapped to four response modes through simple threshold comparison:

| Mode | Pressure Range | Behavior |
|------|---------------|----------|
| OBSERVE | 0--25% | Silent monitoring. Metrics collected, no guidance emitted. |
| GUIDE | 25--50% | Suggestive guidance injected into agent context. Agent may proceed but is informed of concerns. |
| WARN | 50--75% | Strong warnings with specific behavioral recommendations. |
| BLOCK | 75--100% | Destructive operations prevented. Non-destructive work continues. |

### 7.2 Absence of Hysteresis

SOMA deliberately omits hysteresis from mode transitions. In classical control theory, hysteresis prevents rapid oscillation between states by requiring a signal to cross a higher threshold to enter a state than it needs to remain in it. SOMA omits this mechanism because mode transitions do not have discontinuous effects on agent behavior --- OBSERVE, GUIDE, and WARN all permit the agent to continue working, differing only in the content of injected guidance. The only mode with a hard behavioral effect is BLOCK, and BLOCK affects only destructive operations, not the agent's general ability to work. Rapid oscillation between GUIDE and WARN, for example, simply means the guidance content varies --- this is a feature, not a failure mode.

### 7.3 Destructive Operation Detection

BLOCK mode prevents destructive operations through pattern matching on tool invocations. Nine bash command patterns are recognized as destructive:

1. `rm -rf` --- Recursive forced deletion
2. `git reset --hard` --- Discard all uncommitted changes
3. `git push --force` --- Overwrite remote history
4. `git clean -f` --- Remove untracked files
5. `git checkout .` --- Discard working tree changes
6. `chmod 777` --- Remove all file permissions restrictions
7. `kill -9` --- Forceful process termination
8. `DROP TABLE` / `DELETE FROM` (without WHERE) --- Database destruction
9. `> /dev/null` redirects that discard output of important operations

Additionally, five file path patterns trigger blocking when the agent attempts to write to sensitive locations:

1. `.env` --- Environment configuration with secrets
2. `credentials` --- Authentication credentials
3. `.pem` --- SSL/TLS certificates and private keys
4. `.key` --- Cryptographic key files
5. `secret` --- Files containing secrets

### 7.4 Selective Blocking

A critical design decision: BLOCK mode blocks only destructive operations. Tool categories such as Write, Edit, Bash, and Agent are never blocked as categories. An agent in BLOCK mode can still read files, run non-destructive commands, write to non-sensitive paths, and perform analysis. This ensures that SOMA's most aggressive intervention mode degrades agent capability gracefully rather than halting all progress.

---

## 8. Multi-Agent Pressure Propagation

### 8.1 Graph Model

SOMA models multi-agent systems as a directed graph G = (V, E), where vertices V represent agents and directed edges E represent dependency or influence relationships. Each edge carries a trust weight w in [0, 1] representing the degree to which the source agent's behavioral state should influence monitoring of the target agent.

### 8.2 Scalar Pressure Propagation

For each node n in the graph, effective pressure is computed as:

$$P_{\text{eff}}(n) = \max\left(P_{\text{int}}(n),\; \delta \cdot \text{weighted\_avg}(\text{upstream})\right)$$

where P_int(n) is the node's internally computed pressure, delta = 0.6 is the damping factor, and the weighted average is computed over all upstream nodes weighted by their edge trust values.

Propagation runs for a maximum of 3 iterations, terminating early if all pressure values converge within 1e-6. The damping factor ensures that propagated pressure is always attenuated --- an upstream agent's crisis registers as concern, not panic, in downstream agents.

### 8.3 Vector Propagation

In addition to scalar propagation, SOMA supports per-signal pressure vector propagation. A `PressureVector` containing independent pressure values for uncertainty, drift, error_rate, and cost is propagated using the same max(own, damped * upstream) formula applied independently to each signal dimension. This preserves signal-level detail through the propagation process, enabling downstream agents to understand not just that upstream pressure is elevated, but which specific signals are driving it.

### 8.4 Coordination Signal-to-Noise Ratio

In complex multi-agent topologies, noisy upstream signals can cause spurious pressure elevation in downstream agents. SOMA addresses this through a coordination SNR mechanism:

$$\text{snr} = \frac{\text{confirmed\_error\_pressure}}{\max(\text{total\_incoming}, 0.001)}$$

If total incoming pressure exceeds 0.05 AND the SNR falls below 0.5, the node is isolated from upstream pressure propagation. This prevents scenarios where many mildly elevated upstream agents collectively push a healthy downstream agent into an unwarranted high-pressure state.

### 8.5 Trust Dynamics

Trust weights on graph edges are not static. They evolve based on the behavioral signals of the source agent:

**Decay** (when uncertainty > 0.5):
$$\text{trust}' = \text{trust} - 0.05 \cdot \text{uncertainty}$$

**Recovery** (when uncertainty <= 0.5):
$$\text{trust}' = \text{trust} + 0.02 \cdot (1 - \text{uncertainty})$$

The asymmetric ratio of 2.5:1 (decay rate 0.05 vs. recovery rate 0.02) mirrors findings from behavioral economics. Slovic [5] demonstrated that trust is destroyed more easily than it is built --- a single failure erodes trust more than a single success restores it. SOMA encodes this empirical finding directly into its trust dynamics.

---

## 9. Goal Coherence

### 9.1 Task Vector Capture

Goal coherence tracking begins after a configurable warmup period. The initial task vector is captured at action #5 (configurable via `warmup_actions`), representing the agent's behavioral profile during its initial engagement with the assigned task. This warmup period allows the agent to complete setup actions (reading files, understanding context) before the system locks in an expectation of what "on-task behavior" looks like.

### 9.2 Coherence Computation

At each subsequent action, the current behavior vector is compared against the initial task vector:

$$\text{coherence} = \cos(\mathbf{v}_{\text{current}},\; \mathbf{v}_{\text{initial}})$$

The behavior vector is the same vector used for drift computation (Section 4.3), ensuring consistency between the two related signals.

### 9.3 Divergence as Pressure

The coherence score is inverted to produce a divergence signal suitable for pressure computation:

$$\text{goal\_pressure} = 1 - \text{coherence}$$

When the agent's current behavior closely matches its initial task profile, divergence is near zero and goal coherence contributes minimal pressure. As the agent's behavior deviates --- shifting to different tools, different output patterns, different activity levels --- divergence increases and goal coherence contributes escalating pressure.

---

## 10. Predictive Model

### 10.1 Linear Trend Extrapolation

SOMA's predictive model fits an ordinary least squares (OLS) regression to the last 10 pressure readings, projecting the trend forward to anticipate future pressure levels:

$$\hat{P}_{t+h} = \beta_0 + \beta_1 \cdot (t + h)$$

where beta_0 and beta_1 are the OLS intercept and slope estimated from the most recent window of observations. The R-squared value of the fit provides a measure of trend reliability.

### 10.2 Pattern Boosters

Linear extrapolation captures gradual trends but misses sudden pattern shifts. SOMA augments the linear model with four pattern-based boosters that detect specific failure precursors:

| Pattern | Boost | Description |
|---------|-------|-------------|
| Error streak | +0.15 | Consecutive actions producing errors |
| Retry storm | +0.12 | Repeated attempts at the same operation |
| Blind writes | +0.10 | File modifications without prior reads |
| Thrashing | +0.08 | Rapid alternation between contradictory actions |

Boosters are additive: an agent exhibiting both an error streak and blind writes receives a combined boost of +0.25. This allows the predictive model to respond rapidly to combinatorial failure patterns that linear trend analysis would detect only after several additional observations.

### 10.3 Prediction Confidence

Predictions are emitted only when confidence exceeds a minimum threshold:

$$c = 0.6 \cdot \min\left(\frac{n}{W},\; 1\right) + 0.4 \cdot \max(R^2,\; 0)$$

where n is the number of observations, W is the window size (10), and R-squared is the coefficient of determination from the linear fit. The confidence formula weights data availability (60%) more heavily than model fit (40%), reflecting the practical observation that a mediocre trend estimate with many data points is more useful than a high-R-squared fit over 3 observations.

Predictions are suppressed when c <= 0.3, preventing the system from emitting unreliable forecasts during cold start or when behavioral data does not exhibit a coherent trend.

---

## 11. Self-Learning Engine

### 11.1 Intervention Tracking

The self-learning engine tracks each intervention (guidance emission above OBSERVE mode) as a pending event. After an evaluation window of 5 subsequent actions, the engine assesses whether the intervention was successful (agent behavior improved) or unsuccessful (agent behavior did not change or worsened).

### 11.2 Adaptive Step Computation

The magnitude of threshold adjustments is modulated by a ratio-dependent adaptive step:

$$\text{multiplier} = 1.0 + 2.0 \cdot \max(0,\; \text{ratio} - 0.5)$$

where ratio is the proportion of recent interventions that were unsuccessful. The multiplier ranges from 1.0 (when failure ratio <= 0.5) to a maximum of 2.0 (when all interventions fail, ratio = 1.0). This cap at 2x prevents the system from making excessively large adjustments even in adversarial scenarios.

### 11.3 Failure Response

When an intervention is evaluated as unsuccessful, the learning engine makes two adjustments:

1. **Raise threshold** by the adaptive step amount, with a maximum shift of +/-0.10 per adjustment. This reduces the sensitivity of the triggering mode, preventing future false positives at the same pressure level.

2. **Lower signal weights** by 0.05 for the signals that contributed most to the triggering pressure, with a floor of 0.2 per signal weight. This gradually deweights signals that are producing unreliable pressure readings for this particular agent's behavioral profile.

### 11.4 Success Response

When an intervention is evaluated as successful:

1. **Lower threshold** by adaptive_step * 0.5. Successful interventions suggest the current threshold is appropriate or slightly too high; the halved step size reflects the system's conservative approach to increasing sensitivity.

2. **Recover weights** at half the decay rate (0.025 per adjustment). Signal weights that were previously reduced are slowly restored, reflecting the possibility that previously unreliable signals have become informative as the agent's behavioral profile evolves.

### 11.5 Minimum Intervention Count

No adjustments are made until at least min_interventions = 3 interventions have been tracked. This prevents the learning engine from overreacting to the first few interventions in a session, which may not be representative of the system's long-term false positive rate.

---

## 12. Quality Scoring

### 12.1 Quality Computation

SOMA computes a rolling quality score that reflects the overall caliber of the agent's recent work:

$$Q = (w_{\text{write}} \cdot Q_{\text{write}} + w_{\text{bash}} \cdot Q_{\text{bash}}) \times \max(0.5,\; 1 - 0.15 \cdot \text{syntax\_errors})$$

where Q_write is the quality score for file write operations, Q_bash is the quality score for command executions, and the syntax error multiplier penalizes agents that produce syntactically invalid outputs, with a floor of 0.5 to prevent quality from being driven to zero by a single category of failure.

### 12.2 Grade Assignment

Quality scores are mapped to letter grades for human-readable reporting:

| Grade | Threshold |
|-------|-----------|
| A | >= 0.90 |
| B | >= 0.80 |
| C | >= 0.70 |
| D | >= 0.50 |
| F | < 0.50 |

### 12.3 Rolling Window

Quality is computed over a rolling window of the 30 most recent events. This window size balances responsiveness (recent quality changes are reflected within a few actions) with stability (individual anomalous actions do not dominate the score). The window is event-based rather than time-based, ensuring consistent behavior regardless of action frequency.

---

## 13. Root Cause Analysis

### 13.1 Detector Suite

When pressure is elevated, SOMA attempts to identify the specific behavioral pattern responsible through five specialized detectors:

| Detector | Base Severity | Escalation | Description |
|----------|---------------|------------|-------------|
| Loop | 0.90 | Fixed | Agent repeating the same action sequence. Highest severity due to unbounded resource consumption. |
| Error Cascade | 0.50 | +0.10 per error | Sequential errors compounding into a chain. Severity scales with cascade length. |
| Blind Mutation | 0.60 | +0.05 per write | File modifications without prior reads. Severity scales with mutation count. |
| Stall | 0.50 | Fixed | Agent producing no meaningful output despite continued execution. |
| Drift Explanation | 0.40 | +0.50 * drift | Behavioral drift detected. Severity scales with drift magnitude. |

### 13.2 Finding Selection

When multiple detectors fire, the finding with the highest severity is selected and returned as a plain-English explanation. This ensures that the most actionable root cause is surfaced to the operator or injected into the agent's guidance context.

---

## 14. Agent Fingerprinting

### 14.1 Persistent Behavioral Profile

SOMA maintains a persistent per-agent behavioral fingerprint across sessions, capturing:

- Tool usage distribution (probability vector over tool names)
- Error rate (fraction of actions producing errors)
- Read/write ratio (ratio of read operations to write operations)
- Session length (number of actions per session)

### 14.2 Divergence Scoring

Cross-session divergence is computed as a weighted combination of distribution-level and scalar-level comparisons:

$$\text{divergence} = 2 \cdot \text{JSD}(\text{tool\_dist}_{\text{current}},\; \text{tool\_dist}_{\text{historical}}) + 1 \cdot |\text{error\_rate}_{\text{current}} - \text{error\_rate}_{\text{historical}}| + 0.5 \cdot |\text{rw\_ratio}_{\text{current}} - \text{rw\_ratio}_{\text{historical}}|$$

Jensen-Shannon divergence (JSD) is used for the tool distribution comparison because it is symmetric, bounded, and well-defined even when the distributions have non-overlapping support. The weight of 2 on JSD reflects the empirical observation that tool distribution shifts are the most reliable indicator of behavioral regime change.

### 14.3 Profile Update

Fingerprints are updated via EMA with alpha = 0.1, providing a half-life of approximately 6.6 sessions. This slow adaptation rate ensures that the fingerprint reflects long-term behavioral tendencies rather than session-to-session noise.

Divergence scores are not produced until at least 10 sessions have been recorded, ensuring sufficient historical data for meaningful comparison.

---

## 15. Reliability Metrics

### 15.1 Calibration Score

SOMA computes a calibration score that measures the alignment between the agent's expressed confidence and its actual performance:

$$\text{cal} = (1 - \text{error\_rate}) \cdot (0.5 + 0.5 \cdot \text{hedging\_rate})$$

where error_rate is the recent error fraction and hedging_rate is the fraction of recent outputs containing hedging language. The intuition is that a well-calibrated agent hedges when it is uncertain and proceeds confidently when it is not. An agent that never hedges but frequently errors is poorly calibrated; an agent that always hedges but rarely errors is overly cautious but at least honest.

This formulation is inspired by the LLM self-calibration work of Kadavath et al. [10], adapted from the probabilistic prediction context to behavioral monitoring.

### 15.2 Verbal-Behavioral Divergence

A particularly concerning pattern is when an agent expresses confidence while exhibiting high behavioral pressure --- the verbal-behavioral divergence signal. This divergence fires when:

$$(P - \text{hedging\_rate}) > 0.4$$

That is, when the gap between actual pressure (indicating trouble) and expressed hedging (indicating the agent's self-assessment) exceeds 0.4. When this condition is detected, SOMA forces a minimum response mode of GUIDE, ensuring the agent receives feedback even if its aggregate pressure would otherwise place it in OBSERVE mode.

This mechanism is motivated by the deceptive alignment literature, particularly Hubinger et al. [15], who demonstrated that LLM agents can learn to behave differently during monitoring than during deployment. While SOMA cannot detect training-time deception, it can detect the runtime behavioral signature: an agent that claims everything is fine while its vitals indicate otherwise.

### 15.3 Hedging Phrase Detection

SOMA recognizes 27 hedging phrase markers in agent output, including expressions of uncertainty ("I'm not sure", "might", "perhaps"), qualifications ("however", "although"), self-corrections ("actually", "let me reconsider"), and explicit confidence limitations ("I don't have enough information", "this is just my best guess"). The marker set was curated from empirical observation of LLM agent outputs across diverse task types.

---

## 16. Half-Life Temporal Modeling

### 16.1 Pressure Decay Model

SOMA models temporal pressure decay using an exponential half-life function:

$$P(t) = \exp\left(-\frac{\ln(2) \cdot t}{\text{half\_life}}\right)$$

This models the intuition that the relevance of a pressure reading decays over time --- an elevated pressure from 30 minutes ago is less concerning than one from 30 seconds ago, assuming no new concerning signals have arrived.

### 16.2 Adaptive Half-Life

The half-life is not a fixed constant but adapts to the agent's behavioral profile:

$$\text{half\_life} = \max\left(\text{min\_hl},\; \text{avg\_session\_length} \times \max(0.3,\; 1 - \text{avg\_error\_rate})\right)$$

Agents with high error rates have shorter half-lives (pressure persists for less time in absolute terms but represents a larger fraction of the session), while agents with low error rates have longer half-lives (pressure decays slowly, reflecting the rarity and therefore significance of elevated readings).

### 16.3 Handoff Suggestion

When the projected success probability (derived from the temporal model) falls below 0.5, SOMA suggests a handoff --- the current agent should be replaced or the task should be escalated to human supervision. This threshold represents the point at which the agent is more likely to fail than succeed if it continues, making continued autonomous operation a negative expected value proposition.

---

## 17. Policy Engine

### 17.1 Declarative Rules

SOMA includes a policy engine that allows operators to define custom monitoring rules in a declarative format:

```toml
[[policy.rules]]
when = "pressure >= 0.6 and error_rate > 0.3"
do = "mode = WARN"
```

Rules use a `when`/`do` structure where the `when` clause is a boolean expression over exposed fields and the `do` clause specifies the action to take when the condition is met.

### 17.2 Supported Operators

The policy expression language supports six comparison operators:

- `>=` (greater than or equal)
- `<=` (less than or equal)
- `>` (greater than)
- `<` (less than)
- `==` (equal)
- `!=` (not equal)

Conditions can be combined with `and`/`or` logical operators.

### 17.3 Exposed Fields

The following fields are available for use in policy expressions:

| Field | Type | Description |
|-------|------|-------------|
| pressure | float | Aggregate pressure (0--1) |
| uncertainty | float | Uncertainty signal value |
| drift | float | Drift signal value |
| error_rate | float | Error rate signal value |
| token_usage | float | Token usage signal value |
| cost | float | Cost signal value |
| calibration_score | float | Calibration score (0--1) |

### 17.4 Guardrail Decorator

For programmatic integration, SOMA provides a `@guardrail` decorator that can be applied to both synchronous and asynchronous functions:

```python
@soma.guardrail(max_pressure=0.75, block_on="destructive")
async def process_task(task):
    ...
```

The decorator intercepts calls, checks current engine state, and raises `SomaBlocked` if the pressure or operation type exceeds the configured limits.

---

## 18. Task Complexity Estimation

### 18.1 Complexity Score

SOMA estimates task complexity from the initial task description to calibrate monitoring thresholds:

$$\text{score} = 0.40 \cdot \text{length} + 0.35 \cdot \text{ambiguity} + 0.25 \cdot \text{dependency}$$

where length is a normalized measure of task description length, ambiguity is the density of ambiguous language markers, and dependency is the density of dependency markers.

### 18.2 Marker Sets

**Ambiguity markers** (13 total): phrases indicating underspecified requirements, such as "as needed", "appropriate", "reasonable", "if possible", "various", "etc", "some", and similar hedging language in task descriptions.

**Dependency markers** (10 total): phrases indicating cross-component or cross-system dependencies, such as "depends on", "requires", "after", "before", "integration", "API", "database", "service", "external", and "upstream".

### 18.3 Threshold Adjustment

When task complexity exceeds 0.5 (on the 0--1 scale), SOMA reduces pressure thresholds by up to 0.20, making the system more sensitive for complex tasks. The reduction is proportional to the complexity excess:

$$\text{threshold\_reduction} = \min\left(0.20,\; 0.40 \cdot (\text{complexity} - 0.5)\right)$$

This reflects the empirical observation that agents are more likely to fail on complex tasks, and the consequences of failure are typically more severe.

---

## 19. Evaluation

### 19.1 Test Suite

SOMA is validated through a comprehensive test suite comprising 735 tests across 37 test modules. The full suite executes in approximately 1 second on commodity hardware, reflecting the computational efficiency of the core algorithms. Tests cover:

- Unit tests for each signal computation (uncertainty, drift, error rate, goal coherence)
- Unit tests for baseline learning (EMA convergence, cold-start blending, grace period)
- Unit tests for pressure normalization and aggregation (sigmoid, weighted mean-max, floors)
- Unit tests for guidance system (mode mapping, destructive pattern detection)
- Unit tests for multi-agent graph propagation (damping, convergence, SNR isolation)
- Unit tests for self-learning engine (threshold adaptation, weight adjustment, caps)
- Unit tests for predictive model (trend extrapolation, pattern boosters, confidence)
- Integration tests for the complete record_action pipeline

### 19.2 Integration Testing

Integration testing exercises the full pipeline across 4 distinct scenarios totaling 231 actions (documented in INTEGRATION-TEST-REPORT.md):

1. **Healthy agent**: 50+ actions with nominal behavior. Validates that pressure remains in OBSERVE mode, baselines converge correctly, and no false positives are generated.

2. **Gradual degradation**: Agent progressively increases error rate and uncertainty. Validates that pressure escalates through GUIDE and WARN modes at appropriate points, and that the self-learning engine adapts thresholds.

3. **Sudden crisis**: Agent abruptly begins producing errors and attempting destructive operations. Validates rapid escalation to BLOCK mode and correct destructive operation detection.

4. **Recovery**: Agent transitions from high-pressure state back to nominal behavior. Validates that pressure decreases, baselines adapt to the new behavioral regime, and the system does not maintain elevated pressure after the crisis resolves.

### 19.3 Production Observations

From deployment as a Claude Code hook system:

- **Cold start**: Baselines converge and produce meaningful pressure readings within approximately 10 actions, consistent with the configured min_samples and cold-start blending parameters.
- **False positive rate**: Near zero after the learning engine has processed 3+ interventions. The combination of conservative defaults, grace period, cold-start blending, and adaptive thresholds effectively suppresses spurious alerts.
- **Latency**: Consistently under 5ms per hook invocation, including state persistence (atomic file write with fsync). The zero-inference design ensures that monitoring overhead is negligible compared to the LLM inference time of the monitored agent.

---

## 20. Limitations and Future Work

**Single-modality observation.** SOMA currently monitors only tool-call actions. Future work should incorporate additional observation modalities: chain-of-thought analysis, memory access patterns, and inter-agent communication content.

**Threshold sensitivity.** While the self-learning engine adapts thresholds over time, the initial threshold values and adaptation rates are manually tuned. A more principled approach might use Bayesian optimization or multi-armed bandit methods to find optimal configurations for specific agent-task combinations.

**Limited causal reasoning.** The root cause analysis module uses pattern matching rather than causal inference. An agent that enters a loop because of a flawed plan and an agent that enters a loop because of a flaky API receive similar diagnoses. Causal reasoning would enable more targeted guidance.

**Evaluation on diverse agents.** Current validation is primarily against Claude Code. Broader evaluation across agent frameworks (LangChain, AutoGen, CrewAI), model providers (OpenAI, Google, open-source), and task domains (coding, research, data analysis, operations) would strengthen generalizability claims.

**Adversarial robustness.** SOMA's monitoring is transparent --- an agent with access to SOMA's source code could theoretically learn to game the pressure model. While the verbal-behavioral divergence detector provides some protection against this scenario, a systematic adversarial robustness evaluation is needed.

**Scalability.** The current implementation is optimized for single-machine deployment with file-based state persistence. Large-scale multi-agent deployments would benefit from distributed state management and real-time streaming architectures.

---

## 21. Related Work

**NeMo Guardrails** (NVIDIA, 2023) provides programmable guardrails for LLM applications through a domain-specific language (Colang) for defining conversational flows and safety rules. NeMo operates at the input/output boundary, filtering requests and responses against predefined patterns. SOMA complements NeMo by providing continuous behavioral monitoring between boundary checks --- while NeMo catches individual unsafe requests, SOMA detects behavioral trajectories that are individually safe but collectively problematic.

**LangSmith** (LangChain, 2023) offers tracing, evaluation, and monitoring for LLM applications. LangSmith excels at observability (visualizing execution traces, collecting human feedback) but does not compute behavioral pressure, detect anomalies, or inject corrective guidance. SOMA and LangSmith address different layers of the monitoring stack: LangSmith provides visibility, SOMA provides control.

**AgentOps** (2024) provides session replay, cost tracking, and error monitoring for AI agents. Like LangSmith, AgentOps focuses on observability rather than active intervention. SOMA's pressure model, guidance system, and self-learning engine go beyond passive monitoring to active behavioral control.

**Guardrails AI** (2023) validates LLM outputs against structural and semantic specifications (JSON schema, topic restrictions, PII detection). This is complementary to SOMA: Guardrails AI validates individual outputs, SOMA monitors behavioral sequences. An integrated system could use Guardrails AI for output validation and SOMA for trajectory monitoring.

**Constitutional AI** [8] (Anthropic, 2022) embeds behavioral constraints during training through self-critique and revision. SOMA operates at a different point in the stack: while Constitutional AI shapes the agent's base behavioral tendencies, SOMA monitors and corrects runtime deviations from those tendencies. The two approaches are complementary --- Constitutional AI reduces the frequency of problematic behaviors, SOMA catches the ones that still occur.

**Process Control Theory** [6, 7] provides the mathematical foundations for SOMA's approach. Shewhart's control charts established the principle of monitoring process variables against statistical control limits. Astrom and Murray's work on PID control informed SOMA's design decisions around feedback mechanisms, though SOMA deliberately omits integral and derivative terms in favor of stateless pressure computation for explainability.

---

## 22. Conclusion

SOMA demonstrates that effective behavioral monitoring of AI agents does not require additional inference calls, complex probabilistic models, or invasive instrumentation. By applying established principles from control theory, anomaly detection, and trust systems to the specific challenges of agent behavioral monitoring, SOMA achieves real-time detection and correction of agent behavioral pathologies with sub-5ms latency and zero external dependencies.

The key insight underlying SOMA's design is that agent failures are not random events --- they are the culmination of observable behavioral trajectories. An agent does not instantaneously transition from productive work to catastrophic failure. It drifts, it retries, it hedges, it makes errors, and it compounds those errors. Each of these behavioral signals is individually weak, but their combination --- weighted, normalized, and aggregated through the pressure model --- provides a reliable early warning system that enables graduated intervention before failures become irreversible.

SOMA's closed-loop architecture --- actions produce vitals, vitals produce pressure, pressure produces guidance, guidance influences agent behavior --- creates a feedback system that is both self-correcting and self-improving. The self-learning engine adapts thresholds and weights from intervention outcomes, reducing false positives over time without manual tuning. The predictive model anticipates failures before they manifest, enabling proactive rather than reactive intervention.

As AI agents assume increasingly autonomous roles in software development, research, and operations, the need for runtime behavioral monitoring will only grow. SOMA provides a foundation for this monitoring: deterministic, explainable, platform-agnostic, and open-source. The system is available today as `soma-ai` on PyPI, operational as a Claude Code hook system, and designed to extend to any agent framework.

---

## References

[1] J. Chen, C. Jabbour, J. Yang, D. Fried, and A. Gur, "SWE-bench: Can language models resolve real-world GitHub issues?," in *Proc. NeurIPS*, 2023. --- Benchmark documenting the agent failure modes that SOMA is designed to detect: cascading errors, task drift, and destructive operations in real-world software engineering tasks.

[2] J. Yang, C. E. Jimenez, A. Wettig, K. Liber, S. Yao, K. Narasimhan, and O. Press, "SWE-agent: Agent-computer interfaces enable automated software engineering," 2024. --- Establishes tool-call granularity as the natural observation unit for agent monitoring, which SOMA adopts as its fundamental action primitive.

[3] D. Hendrycks, S. Basart, S. Kadavath, M. Mazeika, A. Zou, E. Jones, and D. Song, "Measuring coding challenge competence with APPS," in *Proc. NeurIPS*, 2021. --- Documents performance degradation with task complexity, motivating SOMA's complexity-adaptive threshold adjustment.

[4] S. D. Kamvar, M. T. Schlosser, and H. Garcia-Molina, "The EigenTrust algorithm for reputation management in P2P networks," in *Proc. WWW*, 2003. --- Foundation for SOMA's trust-weighted pressure propagation in multi-agent graphs.

[5] P. Slovic, "Perceived risk, trust, and democracy," *Risk Analysis*, vol. 13, no. 6, pp. 675--682, 1993. --- Established the asymmetric nature of trust dynamics (trust is destroyed faster than it is built), encoded in SOMA's 2.5:1 decay-to-recovery ratio.

[6] W. A. Shewhart, *Economic Control of Quality of Manufactured Product*. Van Nostrand, 1931. --- Originated statistical process control and z-score-based control charts, the mathematical foundation for SOMA's signal normalization and pressure computation.

[7] K. J. Astrom and R. M. Murray, *Feedback Systems: An Introduction for Scientists and Engineers*. Princeton University Press, 2008. --- Comprehensive treatment of PID control, hysteresis, and deadband mechanisms that informed SOMA's deliberate design choices around stateless pressure computation.

[8] Y. Bai, S. Kadavath, S. Kundu, A. Askell, J. Kernion, A. Jones, A. Chen, A. Goldie, A. Mirhoseini, C. McKinnon, et al., "Constitutional AI: Harmlessness from AI feedback," 2022. --- Training-time alignment approach that SOMA complements with runtime behavioral monitoring, addressing the gap between trained tendencies and actual execution behavior.

[9] A. Kendall and Y. Gal, "What uncertainties do we need in Bayesian deep learning for computer vision?," in *Proc. NeurIPS*, 2017. --- Theoretical framework for epistemic vs. aleatoric uncertainty decomposition, adapted in SOMA from neural network predictions to agent behavioral signals.

[10] S. Kadavath, T. Conerly, A. Askell, T. Henighan, D. Drain, E. Perez, S. Schiefer, Z. Hatfield-Dodds, N. DaSilva, E. Tran-Vu, et al., "Language models (mostly) know what they know," 2022. --- LLM self-calibration research that inspired SOMA's calibration scoring, measuring alignment between expressed confidence and actual performance.

[11] S. Lin, J. Hilton, and O. Evans, "TruthfulQA: Measuring how models mimic human falsehoods," in *Proc. ACL*, 2022. --- Verbal-behavioral divergence in LLMs, motivating SOMA's hedging-pressure gap detector.

[12] K. Valmeekam, M. Marquez, S. Sreedharan, and S. Kambhampati, "On the planning abilities of large language models," in *Proc. NeurIPS*, 2023. --- Demonstrates systematic LLM planning failures, motivating SOMA's predictive model and early intervention architecture.

[13] N. Shinn, F. Cassano, A. Gopinath, K. Narasimhan, and S. Yao, "Reflexion: Language agents with verbal reinforcement learning," in *Proc. NeurIPS*, 2023. --- Demonstrates that agents respond to behavioral feedback loops, validating SOMA's core assumption that injected guidance can correct agent trajectories.

[14] L. Wang, C. Ma, X. Feng, Z. Zhang, H. Yang, J. Zhang, Z. Chen, J. Tang, X. Chen, Y. Lin, et al., "A survey on large language model based autonomous agents," *Frontiers of Computer Science*, 2023. --- Comprehensive categorization of LLM agent failure modes that informed SOMA's signal selection and root cause analysis detectors.

[15] E. Hubinger, C. Denison, J. Mu, M. Lambert, M. Tong, M. MacDiarmid, T. Lanham, D. M. Ziegler, T. Maxwell, N. Cheng, et al., "Sleeper agents: Training deceptive LLMs that persist through safety training," 2024. --- Demonstrates deceptive alignment in LLMs, motivating SOMA's verbal-behavioral divergence detector that identifies agents claiming normalcy while exhibiting elevated behavioral pressure.

[16] J. S. Park, J. C. O'Brien, C. J. Cai, M. R. Morris, P. Liang, and M. S. Bernstein, "Generative agents: Interactive simulacra of human behavior," in *Proc. UIST*, 2023. --- Demonstrates cascading behavioral drift in multi-agent simulations, motivating SOMA's multi-agent pressure propagation and goal coherence tracking.

---

## Appendix A: Notation

| Symbol | Definition |
|--------|-----------|
| U | Uncertainty signal |
| D | Drift signal |
| E | Error rate signal |
| G | Goal coherence signal |
| C | Cost signal |
| T | Token usage signal |
| P | Aggregate pressure (0--1) |
| P_int(n) | Internal pressure of node n |
| P_eff(n) | Effective pressure of node n after propagation |
| p_i | Normalized pressure for signal i |
| x_i | Raw value of signal i |
| mu_i | EMA baseline mean for signal i |
| sigma_i | EMA baseline standard deviation for signal i |
| v_i | EMA baseline variance for signal i |
| alpha | EMA smoothing factor (0.15) |
| delta | Graph damping factor (0.6) |
| w | Edge trust weight in [0, 1] |
| R | Retry rate |
| F | Failure indicator rate |
| sigma() | Sigmoid clamping function |
| cos(a, b) | Cosine similarity between vectors a and b |
| v_current | Current behavior vector |
| v_baseline | Baseline behavior vector |
| v_initial | Initial task behavior vector |
| beta_0, beta_1 | OLS regression coefficients |
| c | Prediction confidence |
| W | Prediction window size (10) |
| R^2 | Coefficient of determination |
| cal | Calibration score |
| Q | Quality score |
| JSD | Jensen-Shannon divergence |

## Appendix B: Availability

SOMA is open-source software released under the MIT license. The complete source code, test suite, and documentation are available at:

- **GitHub**: https://github.com/tr00x/SOMA-Core
- **PyPI**: https://pypi.org/project/soma-ai/
- **Installation**: `pip install soma-ai`
- **Python compatibility**: 3.11+
- **License**: MIT

The system is currently operational as a Claude Code hook integration and is designed for extension to any agent framework through its platform-agnostic core architecture.
