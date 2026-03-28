"""SOMA Notification hook — injects agent state into LLM context.

Runs on UserPromptSubmit — before the agent starts reasoning.

v2: Actionable feedback. Instead of raw numbers, SOMA now tells the agent
WHAT to do differently based on detected patterns. Raw metrics are still
available but secondary to the behavioral nudge.

The output goes to stdout as "additional context" that Claude Code
injects into the conversation.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def _analyze_patterns(action_log: list[dict]) -> list[str]:
    """Analyze recent action log and return actionable tips.

    Each tip is a short, specific instruction — not a metric.
    Returns at most 2 tips to avoid noise.
    """
    if not action_log:
        return []

    tips: list[str] = []
    recent = action_log[-10:]  # Last 10 actions

    # Pattern 1: Writes without Reads — blind mutation
    writes_since_read = 0
    for entry in reversed(recent):
        if entry["tool"] in ("Write", "Edit", "NotebookEdit"):
            writes_since_read += 1
        elif entry["tool"] == "Read":
            break
    if writes_since_read >= 2:
        tips.append(
            f"[pattern] {writes_since_read} writes without a Read — "
            f"read the file before editing to avoid blind mutations"
        )

    # Pattern 2: Consecutive Bash failures
    consecutive_bash_errors = 0
    for entry in reversed(recent):
        if entry["tool"] == "Bash" and entry.get("error"):
            consecutive_bash_errors += 1
        elif entry["tool"] == "Bash":
            break
        else:
            continue
    if consecutive_bash_errors >= 2:
        tips.append(
            f"[pattern] {consecutive_bash_errors} consecutive Bash failures — "
            f"stop retrying, check assumptions and environment first"
        )

    # Pattern 3: High error rate overall
    if len(recent) >= 5:
        error_count = sum(1 for e in recent if e.get("error"))
        error_rate = error_count / len(recent)
        if error_rate >= 0.3:
            tips.append(
                f"[pattern] {error_count}/{len(recent)} recent actions failed — "
                f"slow down, read relevant files and verify approach before acting"
            )

    # Pattern 4: Same file edited multiple times (thrashing)
    if len(recent) >= 4:
        edit_files = [
            e["file"] for e in recent
            if e["tool"] in ("Write", "Edit") and e.get("file")
        ]
        if edit_files:
            from collections import Counter
            file_counts = Counter(edit_files)
            thrashed = [(f, c) for f, c in file_counts.items() if c >= 3]
            if thrashed:
                fname, count = thrashed[0]
                short = fname.rsplit("/", 1)[-1] if "/" in fname else fname
                tips.append(
                    f"[pattern] edited {short} {count}x in {len(recent)} actions — "
                    f"plan the full change before editing, avoid incremental fixes"
                )

    # Pattern 5: No Grep/Glob before Write to new file (no research)
    if len(recent) >= 3:
        last_3_tools = [e["tool"] for e in recent[-3:]]
        if "Write" in last_3_tools:
            research_tools = {"Grep", "Glob", "Read", "WebSearch", "Agent"}
            has_research = any(t in research_tools for t in last_3_tools[:-1])
            if not has_research and tips.count == 0:  # Only if no other tips
                pass  # Too noisy, skip for now

    return tips[:2]  # Max 2 tips to stay focused


def main():
    try:
        from soma.hooks.common import STATE_PATH, _get_session_agent_id, read_action_log
        from soma.types import Level

        if not STATE_PATH.exists():
            return

        state = json.loads(STATE_PATH.read_text())
        agents = state.get("agents", {})

        my_id = _get_session_agent_id()
        agent = agents.get(my_id)
        if agent is None:
            for aid, adata in agents.items():
                if aid.startswith("cc-") or aid == "claude-code":
                    agent = adata
                    break
        if agent is None:
            return

        level_name = agent.get("level", "HEALTHY")
        pressure = agent.get("pressure", 0.0)
        actions = agent.get("action_count", 0)
        vitals = agent.get("vitals", {})

        # ── Analyze patterns from action log ──
        action_log = read_action_log()

        # Stale log detection: if last action >30min ago, this is a new session
        if action_log:
            last_ts = action_log[-1].get("ts", 0)
            if time.time() - last_ts > 1800:
                action_log = []
                try:
                    from soma.hooks.common import ACTION_LOG_PATH
                    ACTION_LOG_PATH.unlink(missing_ok=True)
                except OSError:
                    pass

        tips = _analyze_patterns(action_log)

        # HEALTHY with low pressure and no tips — stay silent
        if level_name == "HEALTHY" and pressure < 0.15 and not tips:
            return

        lines = []

        # Status line — always compact
        u = vitals.get("uncertainty", 0)
        d = vitals.get("drift", 0)
        e = vitals.get("error_rate", 0)
        lines.append(f"SOMA: p={pressure:.0%} #{actions} [u={u:.2f} d={d:.2f} e={e:.2f}]")

        # Prediction — warn before escalation
        try:
            from soma.hooks.common import get_predictor
            from soma.ladder import THRESHOLDS as _LADDER_THRESHOLDS
            predictor = get_predictor()
            if predictor._pressures:
                thresholds = sorted(t[0] for t in _LADDER_THRESHOLDS if t[0] > pressure)
                if thresholds:
                    pred = predictor.predict(thresholds[0])
                    if pred.will_escalate:
                        lines.append(
                            f"[predict] escalation likely in ~{pred.actions_ahead} actions "
                            f"({pred.dominant_reason}, conf={pred.confidence:.0%}) — slow down"
                        )
        except Exception:
            pass  # Prediction is optional

        # Fingerprint divergence — detect behavior shifts
        try:
            from soma.hooks.common import get_fingerprint_engine, _get_session_agent_id
            fp_engine = get_fingerprint_engine()
            div, explanation = fp_engine.check_divergence(_get_session_agent_id(), action_log)
            if div >= 0.3 and explanation:
                lines.append(f"[fingerprint] behavior diverging from profile ({div:.0%}): {explanation}")
        except Exception:
            pass

        # Actionable tips — the main value add
        if tips:
            for tip in tips:
                lines.append(tip)

        # Level-specific guidance (only at elevated levels)
        if level_name == "CAUTION":
            lines.append("[status] CAUTION — verify before mutating, Write/Edit may be restricted")
        elif level_name == "DEGRADE":
            lines.append("[status] DEGRADED — Bash/Agent blocked, use Read/Edit/Grep only")
        elif level_name in ("QUARANTINE", "RESTART", "SAFE_MODE"):
            lines.append(f"[status] {level_name} — only Read/Glob/Grep available")

        # Root cause analysis — plain English explanation
        try:
            from soma.rca import diagnose
            rca = diagnose(action_log, vitals, pressure, level_name, actions)
            if rca:
                lines.append(f"[why] {rca}")
        except Exception:
            # Fallback to dominant signal
            if level_name != "HEALTHY" and vitals:
                worst_key = max(
                    ((k, v) for k, v in vitals.items() if isinstance(v, (int, float))),
                    key=lambda kv: kv[1],
                    default=None,
                )
                if worst_key:
                    lines.append(f"[dominant] {worst_key[0]}={worst_key[1]:.2f}")

        if lines:
            print("\n".join(lines))

    except Exception:
        pass  # Never crash


if __name__ == "__main__":
    main()
