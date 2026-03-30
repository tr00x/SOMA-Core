"""Shared utilities for SOMA Claude Code hooks."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


SOMA_DIR = Path.home() / ".soma"
ENGINE_STATE_PATH = SOMA_DIR / "engine_state.json"
STATE_PATH = SOMA_DIR / "state.json"
ACTION_LOG_PATH = SOMA_DIR / "action_log.json"
PREDICTOR_PATH = SOMA_DIR / "predictor.json"
FINGERPRINT_PATH = SOMA_DIR / "fingerprint.json"
TASK_TRACKER_PATH = SOMA_DIR / "task_tracker.json"
QUALITY_PATH = SOMA_DIR / "quality.json"

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
    """Detect current GSD workflow mode from environment.

    Returns: "" (default), "plan", "execute", "discuss", "fast"
    """
    import os
    cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", "")
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            return ""
    planning_dir = os.path.join(cwd, ".planning")
    if not os.path.isdir(planning_dir):
        return ""
    state_path = os.path.join(planning_dir, "STATE.md")
    if not os.path.exists(state_path):
        return ""
    try:
        with open(state_path) as f:
            content = f.read(500)
        lower = content.lower()
        if "executing" in lower:
            return "execute"
        if "planning" in lower or "discussing" in lower:
            return "plan"
    except Exception:
        pass
    return ""


def read_action_log() -> list[dict]:
    """Read recent action log for pattern analysis."""
    try:
        if ACTION_LOG_PATH.exists():
            return json.loads(ACTION_LOG_PATH.read_text())
    except (json.JSONDecodeError, IOError):
        pass
    return []


def append_action_log(tool_name: str, error: bool = False, file_path: str = "") -> list[dict]:
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

    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = SOMA_DIR / "action_log.lock"

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                log = read_action_log()
                log.append(entry)
                log = log[-ACTION_LOG_MAX:]
                ACTION_LOG_PATH.write_text(json.dumps(log))
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

        return log
    except Exception:
        # Fallback: try without lock
        log = read_action_log()
        log.append(entry)
        log = log[-ACTION_LOG_MAX:]
        try:
            ACTION_LOG_PATH.write_text(json.dumps(log))
        except IOError:
            pass
        return log


SESSION_ID_PATH = SOMA_DIR / "session_id"


def _get_session_agent_id() -> str:
    """Return a fixed agent ID for Claude Code.

    One agent per machine. No sessions, no PIDs, no complexity.
    Claude Code context compressions, reconnects, and subprocess spawning
    all see the same agent with accumulated history.
    """
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


def get_predictor():
    """Load or create predictor for this session."""
    try:
        from soma.predictor import PressurePredictor
        if PREDICTOR_PATH.exists():
            data = json.loads(PREDICTOR_PATH.read_text())
            return PressurePredictor.from_dict(data)
        return PressurePredictor()
    except Exception:
        from soma.predictor import PressurePredictor
        return PressurePredictor()


def save_predictor(predictor) -> None:
    """Persist predictor state."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        PREDICTOR_PATH.write_text(json.dumps(predictor.to_dict()))
    except Exception:
        pass


def get_fingerprint_engine():
    """Load or create fingerprint engine (persists across sessions)."""
    try:
        from soma.fingerprint import FingerprintEngine
        if FINGERPRINT_PATH.exists():
            data = json.loads(FINGERPRINT_PATH.read_text())
            return FingerprintEngine.from_dict(data)
        return FingerprintEngine()
    except Exception:
        from soma.fingerprint import FingerprintEngine
        return FingerprintEngine()


def save_fingerprint_engine(engine) -> None:
    """Persist fingerprint engine."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        FINGERPRINT_PATH.write_text(json.dumps(engine.to_dict()))
    except Exception:
        pass


def get_task_tracker(cwd: str = ""):
    """Load or create task tracker for this session."""
    try:
        from soma.task_tracker import TaskTracker
        if TASK_TRACKER_PATH.exists():
            data = json.loads(TASK_TRACKER_PATH.read_text())
            tracker = TaskTracker.from_dict(data)
            # Update cwd if provided (may change between sessions)
            if cwd:
                tracker.cwd = cwd
            return tracker
        return TaskTracker(cwd=cwd)
    except Exception:
        from soma.task_tracker import TaskTracker
        return TaskTracker(cwd=cwd)


def save_task_tracker(tracker) -> None:
    """Persist task tracker state."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        TASK_TRACKER_PATH.write_text(json.dumps(tracker.to_dict()))
    except Exception:
        pass


def get_quality_tracker():
    """Load or create quality tracker for this session."""
    try:
        from soma.quality import QualityTracker
        if QUALITY_PATH.exists():
            data = json.loads(QUALITY_PATH.read_text())
            return QualityTracker.from_dict(data)
        return QualityTracker()
    except Exception:
        from soma.quality import QualityTracker
        return QualityTracker()


def save_quality_tracker(tracker) -> None:
    """Persist quality tracker state."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        QUALITY_PATH.write_text(json.dumps(tracker.to_dict()))
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
