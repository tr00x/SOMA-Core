"""Shared utilities for SOMA Claude Code hooks."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from soma.state import (  # noqa: F401
    PREDICTOR_PATH, FINGERPRINT_PATH, TASK_TRACKER_PATH, QUALITY_PATH,
    get_predictor, save_predictor,
    get_fingerprint_engine, save_fingerprint_engine,
    get_task_tracker, save_task_tracker,
    get_quality_tracker, save_quality_tracker,
)

SOMA_DIR = Path.home() / ".soma"
SESSIONS_DIR = SOMA_DIR / "sessions"
ENGINE_STATE_PATH = SOMA_DIR / "engine_state.json"
STATE_PATH = SOMA_DIR / "state.json"
ACTION_LOG_PATH = SOMA_DIR / "action_log.json"  # legacy fallback


def _action_log_path(agent_id: str = "") -> Path:
    """Session-scoped action log path."""
    if agent_id:
        return SESSIONS_DIR / agent_id / "action_log.json"
    return ACTION_LOG_PATH

CLAUDE_TOOLS = [
    "Bash", "Edit", "Read", "Write", "Grep", "Glob",
    "Agent", "WebSearch", "WebFetch", "Skill", "NotebookEdit",
]

# Maximum actions to keep in the log
ACTION_LOG_MAX = 20

# Default hook config (overridden by soma.toml [hooks] section)
DEFAULT_HOOK_CONFIG = {
    "verbosity": "normal",  # minimal, normal, verbose
    "validate_python": True,
    "validate_js": True,
    "lint_python": True,
    "predict": True,
    "fingerprint": True,
    "quality": True,
    "task_tracking": True,
}


def get_hook_config() -> dict:
    """Load hook configuration from soma.toml or use defaults."""
    try:
        from soma.cli.config_loader import load_config
        config = load_config()
        hook_cfg = config.get("hooks", {})
        merged = dict(DEFAULT_HOOK_CONFIG)
        merged.update(hook_cfg)
        return merged
    except Exception:
        return dict(DEFAULT_HOOK_CONFIG)


def get_guidance_thresholds() -> dict[str, float] | None:
    """Load guidance thresholds from soma.toml config."""
    try:
        from soma.cli.config_loader import load_config
        config = load_config()
        thresholds = config.get("thresholds")
        if thresholds and any(k in thresholds for k in ("guide", "warn", "block")):
            return thresholds
    except Exception:
        pass
    return None


def detect_workflow_mode() -> str:
    """Detect current GSD workflow mode. Delegates to soma.context."""
    try:
        from soma.context import detect_workflow_mode as _detect
        return _detect()
    except Exception:
        return ""


def read_action_log(agent_id: str = "") -> list[dict]:
    """Read recent action log for pattern analysis."""
    path = _action_log_path(agent_id)
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, IOError):
        pass
    return []


def append_action_log(tool_name: str, error: bool = False, file_path: str = "",
                      agent_id: str = "") -> list[dict]:
    """Append an action to the log and return updated log.

    Uses file locking to prevent race conditions when multiple
    PostToolUse hooks run concurrently.
    """
    import fcntl

    entry = {
        "tool": tool_name,
        "error": error,
        "file": file_path,
        "ts": time.time(),
    }

    path = _action_log_path(agent_id)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.parent / "action_log.lock"

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                log = read_action_log(agent_id)
                log.append(entry)
                log = log[-ACTION_LOG_MAX:]
                path.write_text(json.dumps(log))
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

        return log
    except Exception:
        # Fallback: try without lock
        log = read_action_log(agent_id)
        log.append(entry)
        log = log[-ACTION_LOG_MAX:]
        try:
            path.write_text(json.dumps(log))
        except IOError:
            pass
        return log


SESSION_ID_PATH = SOMA_DIR / "session_id"


def _get_session_agent_id() -> str:
    """Return a unique agent ID per Claude Code session.

    Uses PPID (the Claude Code process that spawned this hook) so each
    terminal/session gets isolated monitoring. Context compressions
    within the same session keep the same PPID, so state is preserved.

    Fallback to 'claude-code' if PPID detection fails.
    """
    import os
    try:
        ppid = os.getppid()
        if ppid > 1:  # 1 = init/launchd, not useful
            return f"cc-{ppid}"
    except Exception:
        pass
    return "claude-code"


_TOML_MIGRATED = False


def _maybe_migrate_soma_toml() -> None:
    """If soma.toml exists with old threshold keys, migrate in place."""
    global _TOML_MIGRATED
    if _TOML_MIGRATED:
        return
    _TOML_MIGRATED = True
    try:
        import tomllib
        toml_path = Path("soma.toml")
        if not toml_path.exists():
            return
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        thresholds = config.get("thresholds", {})
        if any(k in thresholds for k in ("caution", "degrade", "quarantine")):
            from soma.cli.config_loader import migrate_config, save_config
            migrated = migrate_config(config)
            save_config(migrated, str(toml_path))
    except Exception:
        pass


def get_engine():
    """Load or create SOMA engine with session-scoped agent registered.

    Uses Claude Code optimized config (higher thresholds, relaxed sensitivity).
    Returns (engine, agent_id) tuple. Returns (None, None) on import failure.
    """
    _maybe_migrate_soma_toml()

    try:
        from soma.engine import SOMAEngine
        from soma.persistence import load_engine_state
        from soma.cli.config_loader import CLAUDE_CODE_CONFIG
    except ImportError:
        return None, None

    SOMA_DIR.mkdir(parents=True, exist_ok=True)

    engine = load_engine_state(str(ENGINE_STATE_PATH))
    if engine is None:
        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )

    # Always ensure Claude Code config is applied (may be lost on state reload)
    if engine._custom_weights is None:
        engine._custom_weights = CLAUDE_CODE_CONFIG["weights"]
    if engine._custom_thresholds is None:
        engine._custom_thresholds = CLAUDE_CODE_CONFIG["thresholds"]

    agent_id = _get_session_agent_id()
    try:
        engine.get_level(agent_id)
    except Exception:
        engine.register_agent(agent_id, tools=CLAUDE_TOOLS)

    return engine, agent_id


def _inherit_baseline(engine, new_agent_id: str) -> None:
    """Copy baseline from the most active previous session.

    This gives the new session a warm start — SOMA already knows what
    'normal' looks like for this user instead of starting cold.
    """
    try:
        best_id = None
        best_count = 0
        for aid, s in engine._agents.items():
            if aid == new_agent_id or aid == "default":
                continue
            if s.action_count > best_count:
                best_count = s.action_count
                best_id = aid

        if best_id and best_count >= 10:
            donor = engine._agents[best_id]
            new_agent = engine._agents[new_agent_id]

            # Copy baseline (the learned signal averages)
            from soma.baseline import Baseline
            new_agent.baseline = Baseline.from_dict(donor.baseline.to_dict())

            # Copy baseline behavior vector (for drift detection)
            if donor.baseline_vector is not None:
                new_agent.baseline_vector = list(donor.baseline_vector)

            # Copy known tools
            new_agent.known_tools = list(donor.known_tools)

            # Skip grace period — baseline is inherited, not cold
            # Set action_count to min_samples so pressure is applied immediately
            new_agent.action_count = new_agent.baseline.min_samples
    except Exception:
        pass  # Never crash


def _cleanup_old_agents(engine, current_id: str, keep: int = 2) -> None:
    """Remove old session agents, keeping only the N most active + current."""
    try:
        agents = {
            aid: s for aid, s in engine._agents.items()
            if aid != current_id and aid != "default"
        }
        if len(agents) <= keep:
            return

        # Sort by action_count descending, keep top N
        sorted_agents = sorted(agents.items(), key=lambda x: x[1].action_count, reverse=True)
        to_remove = [aid for aid, _ in sorted_agents[keep:]]
        for aid in to_remove:
            del engine._agents[aid]
            engine._graph._nodes.pop(aid, None)
    except Exception:
        pass  # Never crash


def save_state(engine):
    """Persist engine state for dashboard, Paperclip, and status line."""
    try:
        from soma.persistence import save_engine_state

        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        engine.export_state(str(STATE_PATH))
        save_engine_state(engine, str(ENGINE_STATE_PATH))
    except Exception:
        pass



def read_stdin() -> dict:
    """Read JSON payload from stdin (Claude Code passes hook data this way)."""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if raw:
                return json.loads(raw)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


# ── Reflex helpers ──────────────────────────────────────────────────

BASH_HISTORY_MAX = 10


def get_soma_mode() -> str:
    """Return the configured SOMA mode ('observe', 'guide', or 'reflex').

    Defaults to 'guide' if config is missing or unreadable.
    """
    try:
        from soma.cli.config_loader import load_config
        config = load_config()
        return config.get("soma", {}).get("mode", "guide")
    except Exception:
        return "guide"


def get_reflex_config() -> dict:
    """Return the [reflexes] section from soma.toml config.

    Returns empty dict on missing config or error.
    """
    try:
        from soma.cli.config_loader import load_config
        config = load_config()
        return config.get("reflexes", {})
    except Exception:
        return {}


def read_bash_history(agent_id: str = "") -> list[str]:
    """Read recent bash command history for retry dedup.

    Returns list of normalized command strings, capped at BASH_HISTORY_MAX.
    """
    if agent_id:
        path = SESSIONS_DIR / agent_id / "bash_history.json"
    else:
        path = SOMA_DIR / "bash_history.json"
    try:
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data[-BASH_HISTORY_MAX:]
    except (json.JSONDecodeError, IOError):
        pass
    return []


def write_bash_history(command: str, agent_id: str = "") -> None:
    """Append a normalized bash command to history for retry dedup.

    Truncates to last BASH_HISTORY_MAX entries. Never crashes.
    """
    try:
        if agent_id:
            path = SESSIONS_DIR / agent_id / "bash_history.json"
        else:
            path = SOMA_DIR / "bash_history.json"
        normalized = " ".join(command.split())
        if not normalized:
            return
        history = read_bash_history(agent_id)
        history.append(normalized)
        history = history[-BASH_HISTORY_MAX:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history))
    except Exception:
        pass


def get_block_count(agent_id: str = "") -> int:
    """Read the reflex block count for this session.

    Returns 0 on missing file or error.
    """
    if agent_id:
        path = SESSIONS_DIR / agent_id / "block_count"
    else:
        path = SOMA_DIR / "block_count"
    try:
        if path.exists():
            return int(path.read_text().strip())
    except (ValueError, IOError):
        pass
    return 0


def increment_block_count(agent_id: str = "") -> None:
    """Increment the reflex block counter by 1. Never crashes."""
    try:
        if agent_id:
            path = SESSIONS_DIR / agent_id / "block_count"
        else:
            path = SOMA_DIR / "block_count"
        count = get_block_count(agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(count + 1))
    except Exception:
        pass


def get_checkpoint_count(agent_id: str = "") -> int:
    """Read the auto-checkpoint count for this session.

    Returns 0 on missing file or error.
    """
    if agent_id:
        path = SESSIONS_DIR / agent_id / "checkpoint_count"
    else:
        path = SOMA_DIR / "checkpoint_count"
    try:
        if path.exists():
            return int(path.read_text().strip())
    except (ValueError, IOError):
        pass
    return 0


def increment_checkpoint_count(agent_id: str = "") -> int:
    """Increment the checkpoint counter by 1. Returns new count. Never crashes."""
    try:
        if agent_id:
            path = SESSIONS_DIR / agent_id / "checkpoint_count"
        else:
            path = SOMA_DIR / "checkpoint_count"
        count = get_checkpoint_count(agent_id)
        new_count = count + 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(new_count))
        return new_count
    except Exception:
        return 0


def get_circuit_breaker_state(agent_id: str = ""):
    """Load circuit breaker state from disk. Returns default if missing.

    Never raises -- returns fresh state on any error.
    """
    try:
        from soma.graph_reflexes import CircuitBreakerState

        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        if path.exists():
            data = json.loads(path.read_text())
            return CircuitBreakerState(
                agent_id=data.get("agent_id", aid),
                consecutive_block=data.get("consecutive_block", 0),
                consecutive_observe=data.get("consecutive_observe", 0),
                is_open=data.get("is_open", False),
            )
        return CircuitBreakerState(agent_id=aid)
    except Exception:
        try:
            from soma.graph_reflexes import CircuitBreakerState
            return CircuitBreakerState(agent_id=agent_id or "default")
        except Exception:
            return None  # type: ignore[return-value]


def append_pressure_trajectory(pressure: float, agent_id: str = "") -> None:
    """Append one pressure reading to the per-session trajectory buffer.

    Stored as a simple JSON array in ~/.soma/sessions/{agent_id}/trajectory.json.
    Read by stop.py to build complete SessionRecord.pressure_trajectory.
    """
    try:
        if agent_id:
            path = SESSIONS_DIR / agent_id / "trajectory.json"
        else:
            path = SOMA_DIR / "trajectory.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        traj: list[float] = []
        if path.exists():
            try:
                traj = json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                traj = []

        traj.append(round(pressure, 4))
        path.write_text(json.dumps(traj))
    except Exception:
        pass  # Never crash


def read_pressure_trajectory(agent_id: str = "") -> list[float]:
    """Read the full pressure trajectory for this session."""
    if agent_id:
        path = SESSIONS_DIR / agent_id / "trajectory.json"
    else:
        path = SOMA_DIR / "trajectory.json"
    try:
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
    except (json.JSONDecodeError, IOError):
        pass
    return []


def save_circuit_breaker_state(state, agent_id: str = "") -> None:
    """Persist circuit breaker state to disk. Never raises."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "agent_id": state.agent_id,
            "consecutive_block": state.consecutive_block,
            "consecutive_observe": state.consecutive_observe,
            "is_open": state.is_open,
        }
        path.write_text(json.dumps(data))
    except Exception:
        pass


def _auto_checkpoint(checkpoint_number: int) -> bool:
    """Run git stash push as an auto-checkpoint. Returns True on success.

    Checks for git repo first (never crashes in non-git directories).
    """
    import subprocess

    try:
        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False

        # Run git stash push
        result = subprocess.run(
            ["git", "stash", "push", "-m", f"soma-checkpoint-{checkpoint_number}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
