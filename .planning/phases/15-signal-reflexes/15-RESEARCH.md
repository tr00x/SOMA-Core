# Phase 15: Signal Reflexes - Research

**Researched:** 2026-04-01
**Domain:** Signal-driven reflexes — converting passive pipeline computations into active interventions
**Confidence:** HIGH

## Summary

Phase 15 converts five existing computational modules (predictor, drift/vitals, half-life, RCA, quality) from passive number-generators into active reflex triggers. The infrastructure from Phase 14 (reflex engine, mode-gated hooks, agent awareness, audit logging) provides the integration backbone. Each signal reflex follows a consistent pattern: check condition in hook -> evaluate threshold -> produce ReflexResult with block/inject message.

The key architectural decision is D-03: signal reflexes live in a NEW module `src/soma/signal_reflexes.py`, separate from `src/soma/reflexes.py` (pattern reflexes). This is correct because signal reflexes operate on computed vitals/state (predictor confidence, drift score, quality grade) rather than raw action log patterns. They compose with pattern reflexes rather than replacing them.

The five reflexes split cleanly into two integration points: (1) `pre_tool_use.py` handles the commit gate (RFX-09) since it must block tool calls, and (2) `notification.py` handles injections (RFX-05 through RFX-08) since they inject context into the agent's prompt. The auto-checkpoint (RFX-05) is the only reflex that performs a side effect beyond messaging (git stash).

**Primary recommendation:** Build `signal_reflexes.py` as a pure-function evaluator (like `reflexes.py`) returning `ReflexResult` objects. Hook integration follows the exact same wiring pattern as Phase 14's pattern reflexes. The git stash side effect is handled in the hook layer, not the evaluator.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** When predictor confidence > 70% and escalation within 3 actions -> auto `git stash push -m "soma-checkpoint-{N}"`
- **D-02:** In GUIDE mode: inject warning only. In REFLEX mode: auto-checkpoint
- **D-03:** Checkpoint logic in new module `src/soma/signal_reflexes.py` (separate from pattern reflexes)
- **D-04:** When drift > 0.4 -> inject original task into agent context
- **D-05:** Original task extracted from session context (first system prompt or task description)
- **D-06:** Format: "Your task: {X}. You're now doing: {Y}. Refocus."
- **D-07:** When predicted success rate < 40% -> inject handoff summary
- **D-08:** Summary includes: what was done, what's left, key files touched
- **D-09:** In multi-agent graph: reduce trust weight for degraded agent
- **D-10:** When error_rate > 30% -> run RCA, inject root cause into context
- **D-11:** Format: "[SOMA DIAGNOSIS] Root cause: {cause}. Fix: {suggestion}"
- **D-12:** Not a block -- injection only, agent decides what to do with diagnosis
- **D-13:** Grade D/F -> block git commit in PreToolUse
- **D-14:** Grade C -> inject warning but allow commit
- **D-15:** Uses existing quality.py grader, evaluated on recent actions
- **D-16:** `soma report` includes reflex stats: blocks count, top reflex, estimated errors prevented
- **D-17:** Notification channel logs signal reflex events same as pattern reflexes

### Claude's Discretion
- How to detect "original task" from session context
- How to compute handoff summary (what files, what progress)
- Quality grade computation timing (per-commit vs continuous)
- Git stash cleanup strategy for old checkpoints

### Deferred Ideas (OUT OF SCOPE)
- Circuit breaker for multi-agent graph -- Phase 16
- Session memory injection -- Phase 16
- Smart throttle -- Phase 16
- Context overflow management -- Phase 16
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RFX-05 | Predictor auto-checkpoint (git stash before predicted escalation) | `predictor.py` Prediction dataclass has `confidence` and `actions_ahead` fields; `subprocess.run(["git", "stash", ...])` for the actual checkpoint |
| RFX-06 | Drift scope guardian (inject original task when drifting) | `vitals.py` compute_drift returns 0-1 score; `task_tracker.py` TaskTracker has `_initial_focus` and `get_context()` for original task detection |
| RFX-07 | Half-life handoff suggestion (inject summary when degrading) | `halflife.py` already has `generate_handoff_suggestion()` and `predict_success_rate()`; `graph.py` has trust weight modification |
| RFX-08 | RCA diagnosis injection (inject root cause, not symptoms) | `rca.py` `diagnose()` returns plain-English root cause; already called in `post_tool_use.py` for level transitions |
| RFX-09 | Quality commit gate (block commit on grade D/F) | `quality.py` QualityTracker.get_report() returns grade; commit detection via `tool_name == "Bash"` + command contains "git commit" |
</phase_requirements>

## Standard Stack

### Core (all existing -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| soma.predictor | existing | PressurePredictor with Prediction dataclass | Already computes confidence + actions_ahead |
| soma.halflife | existing | compute_half_life, predict_success_rate, generate_handoff_suggestion | Already generates handoff text |
| soma.rca | existing | diagnose() returns plain-English root cause | Already produces structured explanations |
| soma.quality | existing | QualityTracker with A-F grading | Already grades session quality |
| soma.vitals | existing | compute_drift via behavior vector cosine similarity | Already detects behavioral drift |
| soma.reflexes | existing | ReflexResult dataclass, evaluate() pattern | Phase 14 infrastructure to reuse |
| subprocess | stdlib | git stash execution for auto-checkpoint | Standard Python subprocess |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| soma.graph | existing | PressureGraph trust weight modification | D-09: reduce trust for degraded agents |
| soma.task_tracker | existing | TaskTracker for original task detection | D-05/D-06: scope guardian context |
| soma.audit | existing | AuditLogger for reflex event logging | D-17: log signal reflex events |
| soma.state | existing | State persistence for all subsystems | Loading predictor, quality, task tracker |

**Installation:** No new packages needed. All dependencies are existing SOMA modules.

## Architecture Patterns

### Recommended Project Structure
```
src/soma/
    signal_reflexes.py       # NEW: signal reflex evaluator (pure functions)
    reflexes.py              # EXISTING: pattern reflex evaluator (unchanged)
    hooks/
        pre_tool_use.py      # MODIFIED: add commit gate check
        notification.py      # MODIFIED: add signal reflex injections
        common.py            # MODIFIED: add helpers for signal reflex state
    report.py                # MODIFIED: add reflex stats section
```

### Pattern 1: Signal Reflex Evaluator (Pure Functions)
**What:** `signal_reflexes.py` mirrors `reflexes.py` architecture -- pure functions that take computed state and return `ReflexResult` objects. No I/O, no side effects, no state mutation.
**When to use:** Every signal reflex evaluation.
**Example:**
```python
# signal_reflexes.py
from soma.reflexes import ReflexResult

def evaluate_predictor_checkpoint(
    prediction: Prediction,
    soma_mode: str,
) -> ReflexResult:
    """Check if predictor warrants auto-checkpoint or warning."""
    if prediction.confidence <= 0.7 or prediction.actions_ahead > 3:
        return ReflexResult(allow=True)

    if soma_mode == "reflex":
        return ReflexResult(
            allow=True,  # Don't block -- checkpoint is a side effect
            reflex_kind="predictor_checkpoint",
            inject_message="[SOMA] Auto-checkpoint created...",
        )
    # guide mode: warning only
    return ReflexResult(
        allow=True,
        reflex_kind="predictor_warning",
        inject_message=f"[SOMA] Escalation predicted in ~{prediction.actions_ahead} actions...",
    )
```

### Pattern 2: Commit Gate (Blocking Reflex in PreToolUse)
**What:** Quality commit gate checks `tool_name == "Bash"` and command contains `git commit`. If grade D/F, blocks with exit code 2.
**When to use:** In `pre_tool_use.py`, after pattern reflexes but before guidance evaluation.
**Example:**
```python
# In pre_tool_use.py, after pattern reflexes:
if tool_name == "Bash" and _is_git_commit(tool_input):
    from soma.signal_reflexes import evaluate_commit_gate
    gate_result = evaluate_commit_gate(agent_id)
    if not gate_result.allow:
        print(gate_result.block_message, file=sys.stderr)
        sys.exit(2)
    elif gate_result.inject_message:
        print(gate_result.inject_message, file=sys.stderr)
```

### Pattern 3: Signal Injection in Notification Hook
**What:** After collecting findings, evaluate signal reflexes and inject their messages into the notification output (stdout for Claude Code context injection).
**When to use:** In `notification.py` main(), after existing findings logic.
**Example:**
```python
# In notification.py, after findings:
from soma.signal_reflexes import evaluate_all_signals
signal_results = evaluate_all_signals(
    vitals=vitals, pressure=pressure, action_log=action_log,
    agent_id=agent_id, soma_mode=soma_mode,
)
for sr in signal_results:
    if sr.inject_message:
        lines.append(sr.inject_message)
```

### Pattern 4: Side Effect Isolation (Git Stash)
**What:** The `signal_reflexes.py` module returns a ReflexResult indicating a checkpoint is needed. The HOOK layer performs the actual `git stash push`. This keeps the evaluator testable.
**When to use:** Auto-checkpoint reflex (RFX-05).
**Example:**
```python
# In notification.py or a helper:
def _auto_checkpoint(checkpoint_number: int) -> bool:
    """Execute git stash push. Returns True on success."""
    try:
        result = subprocess.run(
            ["git", "stash", "push", "-m", f"soma-checkpoint-{checkpoint_number}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

### Anti-Patterns to Avoid
- **I/O in evaluator:** Never put subprocess calls or file reads in `signal_reflexes.py`. Keep it pure like `reflexes.py`.
- **Blocking on injections:** RFX-06/07/08 are injections, not blocks. Only RFX-09 (commit gate) blocks.
- **Evaluating quality on every action:** Quality grade is already tracked continuously by `post_tool_use.py`. The commit gate just reads the current grade -- no re-computation needed.
- **Modifying reflexes.py:** Signal reflexes are a separate concern. Don't merge them into the pattern reflex engine.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pressure prediction | New prediction logic | `predictor.py` PressurePredictor.predict() | Already has confidence, actions_ahead, R-squared |
| Quality grading | New quality scorer | `quality.py` QualityTracker.get_report() | Already tracks rolling window, produces A-F grades |
| Root cause analysis | New error analyzer | `rca.py` diagnose() | Already produces plain-English root causes |
| Handoff suggestion text | Template strings | `halflife.py` generate_handoff_suggestion() | Already formats agent-specific suggestion |
| Drift computation | New drift measure | `vitals.py` compute_drift() | Cosine similarity on behavior vectors |
| Audit logging | Custom log format | `audit.py` AuditLogger.append() | Already supports mode='reflex' + type='reflex' |
| Trust weight reduction | Custom graph ops | `graph.py` PressureGraph edge weight APIs | Already supports trust-weighted edges |

**Key insight:** Every signal reflex activates an EXISTING module. The new code is exclusively glue -- threshold checks and message formatting. Zero new algorithms.

## Common Pitfalls

### Pitfall 1: Git Stash in Non-Git Directories
**What goes wrong:** `git stash push` fails if cwd is not a git repo or has no changes.
**Why it happens:** SOMA hooks run in Claude Code's working directory, which is usually a git repo, but not always.
**How to avoid:** Check `subprocess.run(["git", "rev-parse", "--git-dir"], ...)` first. Silently skip checkpoint if not a git repo.
**Warning signs:** subprocess.CalledProcessError on stash command.

### Pitfall 2: Commit Gate False Positives on Non-Commit Bash
**What goes wrong:** Blocking `git commit` when the Bash command is actually `git commit --help` or `echo "git commit"`.
**Why it happens:** Naive string matching on command text.
**How to avoid:** Parse the command more carefully: check that `git` and `commit` appear as the main command, not in strings or comments. A simple regex like `r"^\s*git\s+commit\b"` handles most cases.
**Warning signs:** Agent blocked from running harmless git commands.

### Pitfall 3: Original Task Detection Failure
**What goes wrong:** Drift scope guardian can't find the original task, injects empty/meaningless message.
**Why it happens:** First action may not have a clear "task" -- session may start with various tool calls.
**How to avoid:** Use TaskTracker's `_initial_focus` (set of initial file directories) as proxy for task scope. For the "Your task" text, use the first user prompt if available, or fall back to "initial focus: {dirs}". Gracefully degrade -- if no original task detected, skip the injection rather than inject garbage.
**Warning signs:** inject_message contains placeholder text or empty task description.

### Pitfall 4: Notification Hook Becoming Too Verbose
**What goes wrong:** Five signal reflexes all fire simultaneously, flooding the agent with 5+ injection messages.
**Why it happens:** Multiple signals can be elevated at the same time (high drift + high error rate + low quality).
**How to avoid:** Cap signal reflex injections to 1-2 per notification cycle. Prioritize: commit gate > RCA > drift guardian > handoff > checkpoint. Only the highest-priority active reflex injects.
**Warning signs:** Long notification output that agent ignores due to information overload.

### Pitfall 5: Checkpoint Number Collisions
**What goes wrong:** Multiple checkpoints with the same number, or checkpoint counter resets between sessions.
**Why it happens:** Counter stored in session-scoped state but git stashes are repo-global.
**How to avoid:** Use a monotonic counter persisted in session state (like block_count). Or use timestamp-based naming: `soma-checkpoint-{epoch}`.
**Warning signs:** `git stash list` shows duplicate checkpoint names.

### Pitfall 6: Quality Grade Evaluation Timing
**What goes wrong:** Commit gate evaluates quality grade but quality tracker hasn't been updated yet for the current action.
**Why it happens:** PreToolUse runs BEFORE the tool call. Quality is updated in PostToolUse AFTER the call.
**How to avoid:** This is actually correct behavior -- the commit gate checks quality of work done SO FAR. The current git commit action hasn't produced any code yet. Quality grade from the rolling window of previous actions is the right thing to check.
**Warning signs:** None -- this is a non-issue once understood.

## Code Examples

### Existing Predictor Usage (from post_tool_use.py)
```python
# Source: src/soma/hooks/post_tool_use.py lines 214-226
predictor = get_predictor(agent_id=agent_id)
predictor.update(pressure, {"tool": tool_name, "error": error, "file": file_path})
boundaries = [0.25, 0.50, 0.75]
next_boundary = next((b for b in boundaries if b > pressure), None)
if next_boundary:
    pred = predictor.predict(next_boundary)
    if pred.will_escalate:
        # pred.confidence, pred.actions_ahead, pred.dominant_reason available
        pass
```

### Existing Quality Check (from findings.py)
```python
# Source: src/soma/findings.py lines 65-82
from soma.state import get_quality_tracker
qt = get_quality_tracker()
report = qt.get_report()
# report.grade: "A"|"B"|"C"|"D"|"F"
# report.score: 0-1
# report.issues: list[str]
```

### Existing RCA Diagnosis (from rca.py)
```python
# Source: src/soma/rca.py lines 16-63
from soma.rca import diagnose
rca = diagnose(action_log, vitals, pressure, level_name, action_count)
# Returns str | None -- plain English root cause
# Examples: "stuck in Edit->Bash->Edit loop on config.py (3 cycles)"
#           "error cascade: 4 consecutive Bash failures, error_rate=40%"
```

### Existing Half-life Usage
```python
# Source: src/soma/halflife.py lines 66-85
from soma.halflife import predict_success_rate, generate_handoff_suggestion
success_rate = predict_success_rate(action_count, half_life)
if success_rate < 0.4:
    msg = generate_handoff_suggestion(agent_id, action_count, half_life, success_rate)
    # msg: "Agent 'cc-123' half-life boundary ~5 actions away (currently 38% reliability)..."
```

### Existing ReflexResult Pattern (from reflexes.py)
```python
# Source: src/soma/reflexes.py lines 8-23
@dataclass(frozen=True, slots=True)
class ReflexResult:
    allow: bool
    reflex_kind: str = ""
    block_message: str | None = None
    inject_message: str | None = None
    detail: str = ""
```

### Git Commit Detection Pattern
```python
# For commit gate: detect git commit in Bash commands
import re
_GIT_COMMIT_RE = re.compile(r"^\s*git\s+commit\b")

def _is_git_commit(tool_input: dict) -> bool:
    cmd = tool_input.get("command", "")
    return bool(_GIT_COMMIT_RE.search(cmd))
```

### Original Task Detection (Claude's Discretion)
```python
# Recommended approach: use TaskTracker's initial focus + first files
from soma.state import get_task_tracker
tracker = get_task_tracker(agent_id=agent_id)
ctx = tracker.get_context()

# Option 1: Initial focus dirs (always available after 5 file actions)
if tracker._initial_focus:
    task_desc = f"initial focus: {', '.join(sorted(tracker._initial_focus)[:3])}"

# Option 2: Focus files as proxy
if ctx.focus_files:
    current_desc = f"working on: {', '.join(ctx.focus_files[:3])}"
```

### Handoff Summary (Claude's Discretion)
```python
# Recommended: combine task tracker + quality tracker for handoff
tracker = get_task_tracker(agent_id=agent_id)
ctx = tracker.get_context()
efficiency = tracker.get_efficiency()

summary_parts = []
if ctx.focus_files:
    summary_parts.append(f"Files touched: {', '.join(ctx.focus_files[:5])}")
if ctx.phase != "unknown":
    summary_parts.append(f"Phase: {ctx.phase}")
if efficiency.get("success_rate"):
    summary_parts.append(f"Success rate: {efficiency['success_rate']:.0%}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Passive predictor warnings in stderr | Active auto-checkpoint via git stash | Phase 15 | Insurance before escalation |
| Drift as a number in notification | Scope guardian injects original task | Phase 15 | Agent self-corrects drift |
| Half-life as informational finding | Handoff suggestion + trust reduction | Phase 15 | Multi-agent graph responds to degradation |
| RCA in findings list (low priority) | Diagnosis injection into agent context | Phase 15 | Agent gets actionable fix, not just "error rate high" |
| Quality grade as notification line | Commit gate blocks D/F quality commits | Phase 15 | Prevents low-quality code from being committed |

## Open Questions

1. **Handoff Summary Content**
   - What we know: TaskTracker has focus_files, focus_dirs, phase, scope_drift. QualityTracker has grade/issues.
   - What's unclear: There's no "what's left to do" information -- SOMA only tracks what was done, not the goal.
   - Recommendation: Include what was done (files, phase, quality), action count, and the half-life prediction. For "what's left," note it's unavailable -- the handoff message suggests the human/new agent assess remaining work.

2. **Git Stash Cleanup**
   - What we know: Git stashes accumulate over time. `soma-checkpoint-{N}` naming makes them identifiable.
   - What's unclear: When to clean up old checkpoints (session end? N stashes max?).
   - Recommendation: Don't auto-clean in Phase 15. Add a `soma stash-cleanup` CLI subcommand later. For now, users run `git stash list` and `git stash drop` manually. Stashes are lightweight.

3. **Trust Weight Reduction Amount (D-09)**
   - What we know: PressureGraph has trust-weighted edges. Half-life degradation triggers trust reduction.
   - What's unclear: How much to reduce trust weight. 50%? Proportional to degradation?
   - Recommendation: Multiply existing trust weight by `predicted_success_rate` (which is already 0-1). If success_rate=0.38, trust becomes 38% of original. This is proportional and self-healing (trust recovers if agent recovers).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | pyproject.toml (pytest section) |
| Quick run command | `python -m pytest tests/test_signal_reflexes.py -x` |
| Full suite command | `python -m pytest tests/ -x --timeout=30` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RFX-05 | Predictor checkpoint fires when confidence > 0.7 and actions <= 3 | unit | `python -m pytest tests/test_signal_reflexes.py::TestPredictorCheckpoint -x` | Wave 0 |
| RFX-05 | GUIDE mode: warning only. REFLEX mode: checkpoint | unit | `python -m pytest tests/test_signal_reflexes.py::TestPredictorCheckpoint::test_mode_gating -x` | Wave 0 |
| RFX-06 | Drift > 0.4 injects original task | unit | `python -m pytest tests/test_signal_reflexes.py::TestDriftGuardian -x` | Wave 0 |
| RFX-06 | Graceful degradation when no original task | unit | `python -m pytest tests/test_signal_reflexes.py::TestDriftGuardian::test_no_original_task -x` | Wave 0 |
| RFX-07 | Success rate < 40% injects handoff | unit | `python -m pytest tests/test_signal_reflexes.py::TestHandoffSuggestion -x` | Wave 0 |
| RFX-07 | Trust weight reduced for degraded agent | unit | `python -m pytest tests/test_signal_reflexes.py::TestHandoffSuggestion::test_trust_reduction -x` | Wave 0 |
| RFX-08 | Error rate > 30% triggers RCA injection | unit | `python -m pytest tests/test_signal_reflexes.py::TestRCAInjection -x` | Wave 0 |
| RFX-08 | Format matches D-11 spec | unit | `python -m pytest tests/test_signal_reflexes.py::TestRCAInjection::test_format -x` | Wave 0 |
| RFX-09 | Grade D/F blocks git commit | unit | `python -m pytest tests/test_signal_reflexes.py::TestCommitGate -x` | Wave 0 |
| RFX-09 | Grade C warns but allows | unit | `python -m pytest tests/test_signal_reflexes.py::TestCommitGate::test_grade_c_warning -x` | Wave 0 |
| RFX-09 | Non-commit Bash not blocked | unit | `python -m pytest tests/test_signal_reflexes.py::TestCommitGate::test_non_commit_allowed -x` | Wave 0 |
| D-16 | Report includes reflex stats | unit | `python -m pytest tests/test_report.py::test_reflex_stats -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_signal_reflexes.py -x`
- **Per wave merge:** `python -m pytest tests/ -x --timeout=30`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_signal_reflexes.py` -- covers RFX-05 through RFX-09
- [ ] No new conftest fixtures needed -- existing test patterns from test_reflexes.py are sufficient

## Sources

### Primary (HIGH confidence)
- `src/soma/predictor.py` -- Prediction dataclass with confidence, actions_ahead, will_escalate fields
- `src/soma/halflife.py` -- generate_handoff_suggestion(), predict_success_rate()
- `src/soma/rca.py` -- diagnose() returning plain-English root cause strings
- `src/soma/quality.py` -- QualityTracker with A-F grading, get_report()
- `src/soma/vitals.py` -- compute_drift() via cosine similarity
- `src/soma/reflexes.py` -- ReflexResult dataclass, evaluate() architecture pattern
- `src/soma/hooks/pre_tool_use.py` -- Mode-gated hook with reflex block support
- `src/soma/hooks/notification.py` -- Context injection via stdout
- `src/soma/hooks/common.py` -- get_soma_mode(), state persistence helpers
- `src/soma/task_tracker.py` -- TaskTracker with _initial_focus, get_context()
- `src/soma/hooks/post_tool_use.py` -- Predictor and quality tracker update flow

### Secondary (MEDIUM confidence)
- `src/soma/graph.py` -- Trust weight edge APIs (not deeply verified for modification)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all modules already exist and are well-understood from code review
- Architecture: HIGH -- follows exact same pattern as Phase 14 reflexes.py -> hooks integration
- Pitfalls: HIGH -- identified from actual code patterns (git stash edge cases, commit detection, verbosity)

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable -- all internal modules, no external dependencies)
