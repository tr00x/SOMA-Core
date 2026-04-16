# SOMA Impact Validation — Design Plan

**Date:** 2026-04-16
**Goal:** Prove SOMA makes AI agents measurably better, or kill the project.

## Current state (honest)

- 14,065 actions, 104 sessions of production data
- 891 BLOCKs (all Bash destructive ops) — useful but trivial regex
- 476 GUIDEs — messages sent, no proof agent changed behavior
- 103/104 sessions show 0 errors — error detection is broken
- Pressure clusters at 38% for most sessions — baseline bias
- Mirror/Guidance: theoretically sound, practically unvalidated

## What needs to happen

### Phase 1: Fix the measurement (must do first)

Without correct measurement, nothing else matters.

**1.1 Fix error detection in post_tool_use**
- Bash errors: check exit code AND stderr content
- Edit/Write errors: check for "file not found", syntax errors, lint failures
- Read errors: file doesn't exist
- Agent errors: subagent failures
- Currently: only the old `claude-code` session detects errors (29.4% rate), all others show 0%

**1.2 Fix pressure diversity**
- Most sessions stuck at ~38% — means baseline isn't adapting
- Baseline EMA should converge to actual behavior, not stay at initial defaults
- Cold-start blending may be too aggressive

**1.3 Add session-end summary**
- After every session, print one line: "SOMA: 42 actions, 3 errors caught, 2 blocks, pressure 12→45%"
- This is the minimum viable proof that SOMA is doing something

### Phase 2: A/B test framework

Prove SOMA helps vs. hurts vs. does nothing.

**2.1 Benchmark task set**
Create 10 reproducible tasks of varying difficulty:
1. Fix a real bug (provided test case)
2. Add a feature (clear spec)
3. Refactor a module
4. Debug a failing test
5. Write documentation
6. Create a CLI command
7. Fix a security vulnerability
8. Optimize performance
9. Add test coverage
10. Multi-file refactor

**2.2 Run each task 3x with SOMA, 3x without**
Measure per run:
- Total actions to completion
- Total tokens consumed
- Error count
- Time to completion
- Task success (binary: did it work?)
- Number of retries/loops

**2.3 Statistical comparison**
- Paired t-test or Wilcoxon signed-rank
- Need p < 0.05 to claim SOMA helps
- If p > 0.05, SOMA doesn't help and we need to rethink

### Phase 3: Make guidance actually work

Currently Mirror injects text but we don't track if the agent responds.

**3.1 Guidance effectiveness tracking**
After each guidance injection:
- Record the guidance message + action number
- Watch next 5 actions
- Did pressure drop? Did error rate drop? Did behavior change?
- Track: `guidance_effective_rate = improved / total_guided`

**3.2 Adaptive guidance**
- If agent ignores guidance 3x → escalate (this exists in v2, verify it works)
- If agent always ignores a specific message → stop sending it
- If a message type has >60% effectiveness → prioritize it

**3.3 The killer feature: context-aware suggestions**
Not just "high error rate" but:
- "Your last 3 Bash commands failed with exit code 1. Try reading the error output first."
- "You edited config.py without reading it. The function you're looking for is on line 42."
- "You've used 80% of your token budget with 3 tasks remaining."

### Phase 4: User-facing value

**4.1 Session report card**
At end of session, generate a report:
```
SOMA Session Report
───────────────────
Duration: 23 min | Actions: 67 | Tokens: 145K
Errors caught: 4 (blind edit, 2x bash fail, retry loop)  
Blocks: 1 (rm -rf prevented)
Guidance: 3 messages sent, 2 effective (67%)
Pressure: started 5%, peaked 42%, ended 12%
Estimated savings: ~$0.30 (12 prevented retries × $0.025/action)
```

**4.2 Trend dashboard**
Show across sessions:
- Error rate trending down? (SOMA learning)
- Token efficiency improving?
- Fewer blocks needed? (agent learning from SOMA)

**4.3 Comparison mode**
Side-by-side: "Your last 10 sessions WITH SOMA vs 10 sessions WITHOUT"

## Implementation order

1. **Fix error detection** — 1 session, critical
2. **Session-end summary** — 1 session, quick win
3. **Guidance effectiveness tracking** — 1 session
4. **A/B benchmark framework** — 1-2 sessions
5. **Run A/B tests** — manual, 1 day
6. **Analyze results** — decide: iterate or pivot

## Success criteria

- Error detection catches >80% of real errors
- Guidance effectiveness rate >40%
- A/B test shows statistically significant improvement in at least ONE metric
- Session summary shows non-zero value in every session

## Kill criteria

If after Phase 2 A/B tests:
- No statistical difference in any metric → Mirror approach doesn't work
- Agents ignore all guidance → feedback-via-tool-response thesis is wrong
- Only blocks are useful → simplify to just a safety layer, drop the monitoring
