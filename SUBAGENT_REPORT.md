# Subagent Visibility — Implementation Report

## Problem

When Claude Code spawns subagents via `Agent` tool, their actions (Read, Edit, Write, Bash) bypass SOMA hooks entirely. SOMA is blind to 50%+ of real Claude Code activity.

## Solution

Two parts implemented:

### Part 1: Prompt Injection (pre_tool_use.py)

When `tool_name == "Agent"`, SOMA prepends a monitoring block to the subagent's prompt. The block instructs the subagent to write JSONL logs after every tool call.

**Example modified prompt:**

```
[SOMA Subagent Monitor Active]
You are a subagent being monitored for behavioral health.
After EVERY tool call, append one JSON line to ~/.soma/subagents/cc-12345/a1b2c3d4.jsonl:
{"action": N, "tool": "ToolName", "error": false, "tokens": 0, "output_preview": "first 100 chars..."}
Where N is your action counter (starting at 1).
Parent session: cc-12345
Your subagent ID: a1b2c3d4
This logging is mandatory. Do not skip it.

[Original task prompt follows unchanged...]
```

The injection is transparent — it does NOT modify the task. The original prompt appears in full after the awareness block.

Subagent spawns are audit-logged with type `subagent` for tracking.

### Part 2: Aggregation Module (subagent_monitor.py)

New module with four functions:

| Function | Input | Output |
|----------|-------|--------|
| `watch(parent_id)` | parent session ID | `{sub_id: [entries]}` — raw JSONL data |
| `aggregate(parent_id)` | parent session ID | `{sub_id: {action_count, error_count, error_rate, total_tokens, tools_used}}` |
| `get_cascade_risk(parent_id)` | parent session ID | `float 0.0-1.0` — cascade risk score |
| `get_subagent_summary(parent_id)` | parent session ID | `{sub_id: {actions, errors, error_rate, top_tool}}` |

**Example vitals from subagent logs:**

```json
{
  "sub-a1b2c3d4": {
    "action_count": 11,
    "error_count": 2,
    "error_rate": 0.18,
    "total_tokens": 3200,
    "tools_used": {"Read": 4, "Write": 2, "Edit": 3, "Bash": 2}
  }
}
```

**Cascade risk calculation:**

If any subagent's `error_rate > 0.3` (threshold), risk score = `(max_error_rate - threshold) / (1.0 - threshold)`.

Example: subagent has 75% error rate → risk = (0.75 - 0.3) / 0.7 = 0.64

This risk score is used in `post_tool_use.py` to boost the parent agent's internal pressure on the graph: `boosted = min(1.0, current + cascade * 0.3)`. A failing subagent raises the parent's pressure, which can trigger GUIDE/WARN/BLOCK escalation.

### Wiring

| Hook | Integration |
|------|-------------|
| `pre_tool_use.py` | Injects awareness block into Agent prompts |
| `post_tool_use.py` | Reads cascade risk, boosts parent pressure on graph |
| `notification.py` | Shows `[subagents] N active, M errors, cascade risk=X%` line |
| `stop.py` | Saves subagent vitals to `~/.soma/sessions/{id}/subagents.json` |

## What Works

1. **Injection**: Awareness block prepended to every Agent tool call. Tested — original task preserved verbatim.
2. **Log reading**: JSONL files parsed correctly, malformed files skipped gracefully.
3. **Aggregation**: Per-subagent vitals computed (action count, error rate, token usage, tool distribution).
4. **Cascade detection**: Risk score computed from worst subagent. Propagated to parent via graph pressure boost.
5. **Notification**: Subagent summary shown in SOMA status line when subagents are active.
6. **Session persistence**: Subagent data saved to session store on stop.
7. **17 tests passing**, full suite 1079 passed.

## What Doesn't Work (Yet)

### 1. Subagent compliance is voluntary

The injection ASKS the subagent to write JSONL logs. It doesn't FORCE it. The subagent is an LLM — it might:
- Ignore the instruction entirely
- Write malformed JSON
- Forget after a few actions
- Decide the logging is unnecessary

**Mitigation**: The instruction says "mandatory" and uses imperative tone. But there's no enforcement mechanism. If the subagent doesn't write logs, `watch()` returns empty and all downstream functions degrade to zero/empty gracefully.

**To fix properly**: Would need Claude Code to expose a subagent action callback, or a filesystem watcher that detects subagent file writes independently of the subagent's cooperation.

### 2. No real-time feedback to subagent

SOMA can read subagent logs after the fact, but can't inject mid-session guidance INTO the subagent. The awareness block is one-shot at spawn time. If the subagent starts thrashing at action 50, SOMA can't tell it to stop.

**To fix**: Would need Claude Code's `SendMessage` API to push SOMA guidance into running subagents, or a polling mechanism where the subagent reads `~/.soma/subagents/{parent}/{sub_id}_guidance.txt` before each action.

### 3. Token overhead

The awareness block adds ~200 tokens to every subagent prompt. For short subagent tasks (3-5 actions), the logging instruction itself may cost more than the monitoring value it provides.

### 4. Log file cleanup

Subagent JSONL files accumulate in `~/.soma/subagents/`. No rotation or cleanup implemented. Long-running sessions with many subagents will leave orphaned files.

### 5. Graph propagation is approximate

Cascade risk boosts parent pressure by `cascade * 0.3` — this is a rough heuristic, not derived from the actual trust graph topology. If the parent has complex graph relationships, the boost may over- or under-weight subagent failures.

## Test Results

```
tests/test_subagent_monitor.py — 17 passed
Full suite — 1079 passed, 5 skipped, 0 failed
```
