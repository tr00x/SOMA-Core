# SOMA Guide — Version 0.5.0

## Quick Start
```bash
pip install soma-ai
soma setup-claude
```
Installs 4 hooks + status line. Creates ~/.soma/ for state.

## What Happens After Setup
Every tool call flows through SOMA:
- **PreToolUse** — evaluate guidance (allow/block destructive)
- **PostToolUse** — record action, validate code (py_compile + ruff + node --check), compute pressure
- **UserPromptSubmit** — inject findings into agent context
- **Stop** — save state, update fingerprint, session summary

SOMA is active after 3 actions. Grace period (first 10) = zero pressure.

## The Pressure Model
6 behavioral signals:

| Signal | What | Weight |
|--------|------|--------|
| uncertainty | Retries, output entropy, tool deviation, format deviation | 2.0 |
| drift | Cosine distance from baseline behavior vector | 1.8 |
| error_rate | Fraction of errored actions | 1.5 |
| goal_coherence | Cosine distance from initial task vector | 1.5 |
| cost | Budget utilization (cost_usd) | 1.0 |
| token_usage | Token budget utilization | 0.8 |

Aggregation:
```
pressure = 0.7 * weighted_mean + 0.3 * max_signal
```
Plus error-rate floor: if signal >= 0.50, aggregate guaranteed >= 0.40 (GUIDE).

Mode mapping:

| Mode | Range | Effect |
|------|-------|--------|
| OBSERVE | 0-25% | Silent. Metrics + positive feedback. |
| GUIDE | 25-50% | Soft suggestions. Never blocks. |
| WARN | 50-75% | Insistent warnings. Never blocks. |
| BLOCK | 75-100% | Blocks ONLY destructive ops. |

## Baselines and Learning
EMA with alpha=0.15 (~4.3 action half-life):
- First 10 actions: grace period (zero pressure)
- Actions 1-10: cold-start blending from defaults toward observed
- After 10: pure EMA

Learning engine tracks intervention outcomes:
- Success (pressure dropped) — lower threshold (catch earlier)
- Failure (pressure didn't drop) — raise threshold (fewer false alarms)
- Adaptive step: consistent outcomes — larger adjustments (up to 2x)
- Bounded: max shift +/-0.10

## Cross-Session Memory
Engine state persists: baselines, learning adjustments, thresholds.
Agent fingerprints persist: tool distribution, error rate, read/write ratio.
Session-scoped data resets: action log, predictor, quality, task tracker.

## Uncertainty Classification
Classifies via output entropy (Shannon entropy over character bigrams):
- uncertainty <= 0.3 — no classification
- low entropy (< 0.35) + high uncertainty — epistemic (1.3x pressure)
- high entropy (> 0.65) + high uncertainty — aleatoric (0.7x pressure)

Epistemic = agent lacks knowledge (stuck). Aleatoric = task is genuinely ambiguous.

## Goal Coherence
At action #5, SOMA captures initial task signature (behavior vector).
Ongoing: cosine similarity between current behavior and initial.
Low coherence = agent drifted from original task = higher pressure.

## Policy Engine
Declarative rules in YAML or TOML:
```yaml
rules:
  - name: high-errors
    when:
      error_rate: {">": 0.5}
    do:
      action: warn
      message: "Error rate above 50%"
```
Load: `PolicyEngine.from_file("rules.yaml")` or `from_dict()` or `from_url()`

## Guardrail Decorator
```python
@soma.guardrail(engine, "agent-1", threshold=0.8)
def risky_operation():
    ...  # Raises SomaBlocked when pressure >= 0.8
```
Works with async functions too.

## Half-Life Modeling
Models agent reliability decay: P(t) = exp(-ln(2) * t / half_life)
Shorter half-life = faster degradation. When projected success < 50%, suggests handoff.

## Reliability Metrics
Calibration: (1 - error_rate) * (0.5 + 0.5 * hedging_rate)
Verbal-behavioral divergence: fires when (pressure - hedging_rate) > 0.4. Forces GUIDE.

## Pattern Analysis
7 behavioral patterns detected from last 10 actions:
- Blind edits (3+ without Read, checks last 30 for context)
- Consecutive bash failures (>=2)
- High error rate (>=30%)
- File thrashing (same file >=3 edits)
- Agent spam (>=3 spawns, suppressed in plan/discuss)
- Research stall (7+ reads, 0 writes, suppressed in plan/discuss)
- Runaway mutations (15+ edits, 0 user check-ins, suppressed in execute/plan)

Plus positive patterns: read-before-edit (3+ pairs), clean streak (10+ error-free).
Workflow-aware: patterns suppressed when irrelevant to current phase.

## Predictive Intervention
After each action, fits trend to recent pressure + pattern boosters:
- error_streak: +15%, retry_storm: +12%, blind_writes: +10%, thrashing: +8%
- Warns only when confidence > 30%

## Quality Scoring
Every Write/Edit: py_compile + ruff (Python), node --check (JS)
Score: write success * bash success * syntax penalty (0.15 per error)
Grades: A >=90%, B >=80%, C >=70%, D >=50%, F <50%

## Root Cause Analysis
Plain English diagnosis:
- "stuck in Edit->Bash->Edit loop on config.py (3 cycles)"
- "error cascade: 4 consecutive Bash failures (error_rate=40%)"
- "blind mutation: 5 writes without reading"
- "possible stall: 7/8 recent actions are reads"

## Configuration
soma.toml — everything tunable:
```toml
[hooks]
verbosity = "normal"      # minimal | normal | verbose
validate_python = true
lint_python = true
validate_js = true
predict = true
quality = true
fingerprint = true
task_tracking = true

[budget]
tokens = 1_000_000
cost_usd = 50.0

[thresholds]
guide = 0.25
warn = 0.50
block = 0.75

[weights]
uncertainty = 2.0
drift = 1.8
error_rate = 1.5
goal_coherence = 1.5
cost = 1.0
token_usage = 0.8
```

## CLI Commands
```
soma                  # TUI dashboard
soma status           # Quick text summary
soma setup-claude     # Install hooks
soma doctor           # Check installation health
soma agents           # List monitored agents
soma replay <file>    # Replay session
soma init             # Create soma.toml
soma version          # Print version
soma stop             # Disable hooks
soma start            # Re-enable hooks
soma uninstall-claude # Remove hooks
soma reset <id>       # Reset agent baseline
soma config show      # View config
soma config set k v   # Change config
soma mode <name>      # Switch mode (strict/relaxed/autonomous)
```

## Files
| Path | Purpose |
|------|---------|
| soma.toml | Project configuration |
| ~/.soma/engine_state.json | Full engine state (baselines, learning) |
| ~/.soma/state.json | Snapshot for dashboard/statusline |
| ~/.soma/action_log.json | Recent actions (max 20, session-scoped) |
| ~/.soma/predictor.json | Predictor state (session-scoped) |
| ~/.soma/task_tracker.json | Task context (session-scoped) |
| ~/.soma/quality.json | Quality tracker (session-scoped) |
| ~/.soma/fingerprint.json | Agent fingerprints (persists across sessions) |

## Disabling
```bash
soma stop               # Pause (easy resume with soma start)
soma uninstall-claude   # Remove hooks from Claude Code
rm -rf ~/.soma          # Remove all state
```
