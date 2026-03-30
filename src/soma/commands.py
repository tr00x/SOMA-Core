"""SOMA Command Queue — file-based IPC for external control."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

COMMANDS_DIR = Path.home() / ".soma" / "commands"
RESULTS_DIR = Path.home() / ".soma" / "results"


def ensure_dirs():
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def write_command(action: str, params: dict[str, Any] | None = None) -> str:
    """Write a command file. Returns the command ID."""
    ensure_dirs()
    cmd_id = f"{int(time.time() * 1000)}-{action}"
    cmd = {"id": cmd_id, "action": action, "params": params or {}, "timestamp": time.time()}
    (COMMANDS_DIR / f"{cmd_id}.json").write_text(json.dumps(cmd, indent=2))
    return cmd_id


def read_pending() -> list[dict[str, Any]]:
    """Read all pending command files, sorted by timestamp."""
    ensure_dirs()
    commands = []
    for f in sorted(COMMANDS_DIR.glob("*.json")):
        try:
            commands.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            f.unlink(missing_ok=True)
    return commands


def complete_command(cmd_id: str, result: dict[str, Any]):
    """Mark a command as completed — write result and delete command file."""
    ensure_dirs()
    result_data = {"id": cmd_id, "result": result, "completed_at": time.time()}
    (RESULTS_DIR / f"{cmd_id}.json").write_text(json.dumps(result_data, indent=2))
    cmd_file = COMMANDS_DIR / f"{cmd_id}.json"
    cmd_file.unlink(missing_ok=True)


def read_result(cmd_id: str) -> dict[str, Any] | None:
    """Read a command result. Returns None if not yet completed."""
    result_file = RESULTS_DIR / f"{cmd_id}.json"
    if result_file.exists():
        try:
            return json.loads(result_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def cleanup_old_results(max_age_seconds: float = 300):
    """Remove result files older than max_age_seconds."""
    ensure_dirs()
    now = time.time()
    for f in RESULTS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if now - data.get("completed_at", 0) > max_age_seconds:
                f.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            f.unlink(missing_ok=True)


def process_commands(engine) -> list[dict[str, Any]]:
    """Process all pending commands against a SOMAEngine. Returns results."""
    from soma.types import ResponseMode

    results = []
    for cmd in read_pending():
        cmd_id = cmd.get("id", f"auto-{int(time.time() * 1000)}")
        action = cmd.get("action", "")
        params = cmd.get("params", {})
        if not action:
            continue

        try:
            if action == "force_level":
                agent_id = params["agent"]
                level_name = params["level"]
                level = ResponseMode[level_name]
                if agent_id in engine._agents:
                    engine._agents[agent_id].mode = level
                    result = {"ok": True, "agent": agent_id, "level": level_name}
                else:
                    result = {"ok": False, "error": f"Agent {agent_id} not found"}

            elif action == "replenish_budget":
                amount = params.get("amount", {})
                for dim, amt in amount.items():
                    engine._budget.replenish(dim, float(amt))
                result = {"ok": True, "health": engine._budget.health()}

            elif action == "reset_baseline":
                agent_id = params["agent"]
                if agent_id in engine._agents:
                    engine._agents[agent_id].baseline = type(engine._agents[agent_id].baseline)()
                    engine._agents[agent_id].baseline_vector = None
                    result = {"ok": True, "agent": agent_id}
                else:
                    result = {"ok": False, "error": f"Agent {agent_id} not found"}

            elif action == "set_trust":
                source = params["source"]
                target = params["target"]
                weight = params["weight"]
                engine._graph.add_edge(source, target, weight)
                result = {"ok": True, "source": source, "target": target, "weight": weight}

            elif action == "get_snapshot":
                agent_id = params.get("agent")
                if agent_id and agent_id in engine._agents:
                    result = {"ok": True, "snapshot": engine.get_snapshot(agent_id)}
                else:
                    result = {"ok": True, "agents": {
                        aid: engine.get_snapshot(aid) for aid in engine._agents
                    }}

            elif action == "set_thresholds":
                # Update custom thresholds on the engine
                thresholds = params.get("thresholds", {})
                if engine._custom_thresholds is None:
                    engine._custom_thresholds = {}
                engine._custom_thresholds.update(thresholds)
                result = {"ok": True, "thresholds": thresholds}

            elif action == "set_budget_limits":
                limits = params.get("limits", {})
                for k, v in limits.items():
                    engine._budget.limits[k] = float(v)
                result = {"ok": True, "limits": engine._budget.limits, "health": engine._budget.health()}

            elif action == "export_state":
                engine.export_state()
                result = {"ok": True}

            else:
                result = {"ok": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            result = {"ok": False, "error": str(e)}

        complete_command(cmd_id, result)
        results.append(result)

    cleanup_old_results()
    return results
