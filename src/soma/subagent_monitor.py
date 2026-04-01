"""Subagent monitoring — aggregate vitals from subagent log files.

Subagents spawned via Claude Code's Agent tool write JSONL logs to
~/.soma/subagents/{parent_id}/{sub_id}.jsonl. This module reads,
aggregates, and computes cascade risk from those logs.

Graceful degradation: if no logs exist (subagent didn't write them),
all functions return empty/zero results.
"""

from __future__ import annotations

import json
from pathlib import Path


SUBAGENTS_DIR = Path.home() / ".soma" / "subagents"


def _subagent_dir(parent_id: str) -> Path:
    return SUBAGENTS_DIR / parent_id


def watch(parent_id: str) -> dict[str, list[dict]]:
    """Read all subagent logs for a parent session.

    Returns {subagent_id: [action_entries]} dict.
    Empty dict if no logs exist.
    """
    result: dict[str, list[dict]] = {}
    parent_dir = _subagent_dir(parent_id)
    if not parent_dir.is_dir():
        return result

    for log_file in parent_dir.glob("*.jsonl"):
        sub_id = log_file.stem
        entries: list[dict] = []
        try:
            for line in log_file.read_text().strip().split("\n"):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except (json.JSONDecodeError, IOError):
            continue
        if entries:
            result[sub_id] = entries
    return result


def aggregate(parent_id: str) -> dict[str, dict]:
    """Compute vitals per subagent from their logs.

    Returns {subagent_id: {action_count, error_count, error_rate,
    total_tokens, tools_used}} dict.
    """
    logs = watch(parent_id)
    result: dict[str, dict] = {}

    for sub_id, entries in logs.items():
        action_count = len(entries)
        error_count = sum(1 for e in entries if e.get("error", False))
        total_tokens = sum(e.get("tokens", 0) for e in entries)

        tools: dict[str, int] = {}
        for e in entries:
            t = e.get("tool", "unknown")
            tools[t] = tools.get(t, 0) + 1

        result[sub_id] = {
            "action_count": action_count,
            "error_count": error_count,
            "error_rate": error_count / max(action_count, 1),
            "total_tokens": total_tokens,
            "tools_used": tools,
        }

    return result


def get_cascade_risk(parent_id: str, threshold: float = 0.3) -> float:
    """Compute cascade risk score for graph.py propagation.

    If any subagent has error_rate > threshold, returns a risk score
    between 0.0 and 1.0 based on the worst subagent.

    Returns 0.0 if no subagents are active or all are healthy.
    """
    vitals = aggregate(parent_id)
    if not vitals:
        return 0.0

    max_error_rate = max(v["error_rate"] for v in vitals.values())
    if max_error_rate <= threshold:
        return 0.0

    # Risk proportional to how far above threshold we are
    # 0.3 threshold, 0.5 error_rate → risk = (0.5 - 0.3) / (1.0 - 0.3) ≈ 0.29
    return min(1.0, (max_error_rate - threshold) / (1.0 - threshold))


def get_subagent_summary(parent_id: str) -> dict[str, dict]:
    """Summary dict for notification display.

    Returns {subagent_id: {actions, errors, error_rate, top_tool}} dict.
    """
    vitals = aggregate(parent_id)
    result: dict[str, dict] = {}

    for sub_id, v in vitals.items():
        top_tool = ""
        if v["tools_used"]:
            top_tool = max(v["tools_used"], key=v["tools_used"].get)

        result[sub_id] = {
            "actions": v["action_count"],
            "errors": v["error_count"],
            "error_rate": round(v["error_rate"], 2),
            "top_tool": top_tool,
        }

    return result
