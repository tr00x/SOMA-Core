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
                      agent_id: str = "", output: str = "") -> list[dict]:
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
    if output and error:
        entry["output"] = output[:200]  # Only store error output, truncated

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


def _get_display_name(agent_id: str) -> str:
    """Generate human-readable display name for an agent session.

    Uses CLAUDE_WORKING_DIRECTORY to derive project name, then assigns
    sequential numbers: "my-project #1", "my-project #2", etc.

    Results are persisted in SOMA_DIR/agent_names.json so names survive
    across hook invocations.
    """
    import os

    registry_path = SOMA_DIR / "agent_names.json"

    # Load existing registry
    registry: dict[str, str] = {}
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Already named?
    if agent_id in registry:
        return registry[agent_id]

    # Derive project name from working directory
    cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
    project_name = Path(cwd).name or "session"

    # Find next sequence number for this project
    existing_nums = []
    for name in registry.values():
        if name.startswith(f"{project_name} #"):
            try:
                existing_nums.append(int(name.split("#")[1]))
            except (ValueError, IndexError):
                pass
    seq = max(existing_nums, default=0) + 1

    display_name = f"{project_name} #{seq}"
    registry[agent_id] = display_name

    # Save atomically
    try:
        tmp = registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(registry))
        tmp.rename(registry_path)
    except OSError:
        pass

    return display_name


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
    _display_name = _get_display_name(agent_id)

    is_new_session = False
    try:
        engine.get_level(agent_id)
    except Exception:
        engine.register_agent(agent_id, tools=CLAUDE_TOOLS, display_name=_display_name)
        is_new_session = True

    # Detect recycled PID: agent exists in persisted state but belongs
    # to a previous OS process. Check via session marker file.
    if not is_new_session and _is_stale_session(agent_id):
        engine.register_agent(agent_id, tools=CLAUDE_TOOLS, display_name=_display_name)
        is_new_session = True

    if is_new_session:
        _inherit_baseline(engine, agent_id)
        _cleanup_old_agents(engine, agent_id)
        # Archive sessions with data; clear empty ones
        if _should_clear_stale_session(agent_id):
            _clear_session_files(agent_id)
        else:
            _clear_session_files(agent_id, archive=True)
        _write_session_marker(agent_id)

    return engine, agent_id


def _get_ppid_start_time() -> float:
    """Get the start time of the parent process (PPID).

    Returns 0.0 on failure. Uses `ps` which works on macOS and Linux.
    """
    import os
    import subprocess
    try:
        ppid = os.getppid()
        result = subprocess.run(
            ["ps", "-o", "etime=", "-p", str(ppid)],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            # etime format: [[dd-]hh:]mm:ss — convert to elapsed seconds
            etime = result.stdout.strip()
            parts = etime.replace("-", ":").split(":")
            parts = [int(p) for p in parts]
            if len(parts) == 2:
                return time.time() - (parts[0] * 60 + parts[1])
            elif len(parts) == 3:
                return time.time() - (parts[0] * 3600 + parts[1] * 60 + parts[2])
            elif len(parts) == 4:
                return time.time() - (parts[0] * 86400 + parts[1] * 3600 + parts[2] * 60 + parts[3])
    except Exception:
        pass
    return 0.0


def _is_stale_session(agent_id: str) -> bool:
    """Detect if a persisted agent_id belongs to a dead process (recycled PID).

    The session marker stores the PPID's start time. If the current PPID
    started at a different time, the PID was recycled and this is a new session.
    """
    try:
        marker = SESSIONS_DIR / agent_id / ".session_marker"
        if not marker.exists():
            return False

        stored_start = float(marker.read_text().strip())
        current_start = _get_ppid_start_time()

        if current_start == 0.0:
            # Can't determine PPID start time — not stale (conservative)
            return False

        # If stored start time differs by more than 5 seconds, PID was recycled
        return abs(stored_start - current_start) > 5.0
    except Exception:
        pass
    return False


def _write_session_marker(agent_id: str) -> None:
    """Write session marker with PPID start time for recycled-PID detection."""
    try:
        session_dir = SESSIONS_DIR / agent_id
        session_dir.mkdir(parents=True, exist_ok=True)
        marker = session_dir / ".session_marker"
        start_time = _get_ppid_start_time()
        if start_time == 0.0:
            start_time = time.time()  # fallback
        marker.write_text(str(start_time))
    except Exception:
        pass  # Never crash


def _should_clear_stale_session(agent_id: str) -> bool:
    """Return True only if a stale session has no recorded action data.

    Sessions with action logs or trajectory data are preserved (archived
    instead of cleared) to avoid losing valuable behavioral history.
    """
    session_dir = SESSIONS_DIR / agent_id
    if not session_dir.exists():
        return True

    action_log = session_dir / "action_log.jsonl"
    if action_log.exists() and action_log.stat().st_size > 0:
        return False

    # action_log.json is the older format used by append_action_log
    action_log_json = session_dir / "action_log.json"
    if action_log_json.exists() and action_log_json.stat().st_size > 2:
        return False

    trajectory = session_dir / "trajectory.json"
    if trajectory.exists() and trajectory.stat().st_size > 2:
        return False

    return True


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


def _clear_session_files(agent_id: str, archive: bool = False) -> None:
    """Remove or archive stale per-session files so new session starts fresh.

    Called when a new agent is registered (new PPID = new session).
    Clears trajectory, action_log, bash_history, quality, predictor,
    task_tracker, block_count, and checkpoint_count.

    When archive=True, moves the entire session directory to
    SOMA_DIR/archive/agent_id instead of deleting files.
    """
    try:
        session_dir = SESSIONS_DIR / agent_id
        if not session_dir.exists():
            return

        if archive:
            import shutil
            # Timestamped archive to avoid overwriting previous archives
            ts = int(time.time())
            archive_dir = SOMA_DIR / "archive" / f"{agent_id}_{ts}"
            archive_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(session_dir), str(archive_dir))
            return

        for f in session_dir.iterdir():
            # Keep subagents.json (cross-session data) and lock files
            if f.name.endswith(".lock"):
                continue
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
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
            # Archive session files on disk (preserve data for analysis)
            _clear_session_files(aid, archive=True)
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


# ── Transcript-based context estimation ─────────────────────────────

# Conservative chars/token ratio for Claude Code transcripts. The raw
# tokenizer is ~4 chars/token for English prose; JSONL wrapping adds
# overhead (role/type keys) but assistant reasoning text dominates in
# long sessions, so 4 keeps the estimate honestly conservative.
_TRANSCRIPT_CHARS_PER_TOKEN = 4


def estimate_context_tokens_from_transcript(transcript_path: str | None) -> int:
    """Return an O(1) byte-size token estimate for a Claude Code transcript.

    Returns 0 on missing/unreadable paths. Safe to call on every hook —
    only performs a single stat().
    """
    if not transcript_path:
        return 0
    try:
        size = Path(transcript_path).stat().st_size
    except OSError:
        return 0
    if size <= 0:
        return 0
    return size // _TRANSCRIPT_CHARS_PER_TOKEN


def estimate_context_usage_from_transcript(
    transcript_path: str | None, context_window: int = 200_000,
) -> float:
    """Transcript-size proxy for context window fullness, clamped to [0, 1]."""
    if context_window <= 0:
        return 0.0
    tokens = estimate_context_tokens_from_transcript(transcript_path)
    return max(0.0, min(1.0, tokens / context_window))


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


def read_guidance_state(agent_id: str = "") -> "GuidanceState":
    """Read guidance escalation state from circuit file. Never raises."""
    from soma.guidance_state import GuidanceState
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        if path.exists():
            data = json.loads(path.read_text())
            gs_data = data.get("guidance_state", {})
            return GuidanceState.from_dict(gs_data)
    except Exception:
        pass
    return GuidanceState()


def write_guidance_state(state: "GuidanceState", agent_id: str = "") -> None:
    """Persist guidance state into circuit file. Merges with existing data. Never raises."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                data = {}
        data["guidance_state"] = state.to_dict()
        path.write_text(json.dumps(data))
    except Exception:
        pass


def write_signal_pressures(signal_pressures: dict[str, float], agent_id: str = "") -> None:
    """Persist last signal pressures into circuit file. Never raises."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                data = {}
        data["signal_pressures"] = {k: round(v, 4) for k, v in signal_pressures.items()}
        path.write_text(json.dumps(data))
    except Exception:
        pass


def read_signal_pressures(agent_id: str = "") -> dict[str, float]:
    """Read last signal pressures from circuit file. Never raises."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        if path.exists():
            data = json.loads(path.read_text())
            sp = data.get("signal_pressures", {})
            if isinstance(sp, dict):
                return sp
    except Exception:
        pass
    return {}


def read_guidance_followthrough(agent_id: str = "") -> dict | None:
    """Read pending contextual guidance follow-through from circuit file."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        if path.exists():
            data = json.loads(path.read_text())
            ft = data.get("guidance_followthrough")
            if isinstance(ft, dict) and ft.get("pattern"):
                return ft
    except Exception:
        pass
    return None


def write_guidance_followthrough(pending: dict | None, agent_id: str = "") -> None:
    """Persist pending contextual guidance follow-through into circuit file."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                data = {}
        if pending is None:
            data.pop("guidance_followthrough", None)
        else:
            data["guidance_followthrough"] = pending
        path.write_text(json.dumps(data))
    except Exception:
        pass


def read_guidance_cooldowns(agent_id: str = "") -> dict[str, int]:
    """Read pattern cooldown state (pattern → last action_number) from circuit file."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        if path.exists():
            data = json.loads(path.read_text())
            cd = data.get("guidance_cooldowns")
            if isinstance(cd, dict):
                return cd
    except Exception:
        pass
    return {}


def write_guidance_cooldowns(cooldowns: dict[str, int], agent_id: str = "") -> None:
    """Persist pattern cooldown state into circuit file."""
    try:
        aid = agent_id or "default"
        path = SOMA_DIR / f"circuit_{aid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                data = {}
        data["guidance_cooldowns"] = cooldowns
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
