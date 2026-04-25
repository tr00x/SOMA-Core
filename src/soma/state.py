"""SOMA State — core state persistence for all subsystems.

Loads and saves state for quality tracker, predictor, fingerprint engine,
and task tracker from ~/.soma/. This is a core module — no hooks or CLI deps.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data: dict | list) -> None:
    """Atomic JSON write: mkstemp → fsync → os.replace.

    The previous ``path.write_text(json.dumps(...))`` was a single
    non-atomic syscall — a crash mid-write left a truncated file, which
    the loaders then silently reset to defaults on the next boot. That
    means a SIGKILL during a predictor save was wiping the
    cross-session learning state. Mirrors the pattern used in
    blocks.py and persistence.py.

    Caller is responsible for ensuring ``path.parent`` exists.
    """
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

SOMA_DIR = Path.home() / ".soma"
FINGERPRINT_PATH = SOMA_DIR / "fingerprint.json"

# Legacy paths (used by tests and non-hook code)
PREDICTOR_PATH = SOMA_DIR / "predictor.json"
TASK_TRACKER_PATH = SOMA_DIR / "task_tracker.json"
QUALITY_PATH = SOMA_DIR / "quality.json"

# Session-scoped state directory
SESSIONS_DIR = SOMA_DIR / "sessions"


def _session_path(agent_id: str, name: str) -> Path:
    """Return session-scoped file path: ~/.soma/sessions/{agent_id}/{name}.json"""
    return SESSIONS_DIR / agent_id / f"{name}.json"


def get_quality_tracker(agent_id: str = ""):
    """Load or create quality tracker (session-scoped if agent_id provided)."""
    from soma.quality import QualityTracker
    path = _session_path(agent_id, "quality") if agent_id else QUALITY_PATH
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return QualityTracker.from_dict(data)
    except (json.JSONDecodeError, IOError):
        pass
    return QualityTracker()


def save_quality_tracker(tracker, agent_id: str = "") -> None:
    """Persist quality tracker state."""
    path = _session_path(agent_id, "quality") if agent_id else QUALITY_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, tracker.to_dict())
    except Exception:
        log.warning("Failed to save quality tracker to %s", path, exc_info=True)


def get_predictor(agent_id: str = ""):
    """Load or create pressure predictor (session-scoped if agent_id provided).

    Returns a CrossSessionPredictor that blends local predictions with
    historical session trajectories when local confidence is low.
    Falls back to base PressurePredictor if cross_session module fails.
    """
    path = _session_path(agent_id, "predictor") if agent_id else PREDICTOR_PATH
    try:
        from soma.cross_session import CrossSessionPredictor
        if path.exists():
            data = json.loads(path.read_text())
            predictor = CrossSessionPredictor.from_dict(data)
        else:
            predictor = CrossSessionPredictor()
        # Load historical session trajectories for cross-session blending
        try:
            if not predictor._session_patterns:
                predictor.load_history()
        except Exception:
            pass
        return predictor
    except Exception:
        # Fallback to base predictor if cross_session unavailable
        from soma.predictor import PressurePredictor
        try:
            if path.exists():
                data = json.loads(path.read_text())
                return PressurePredictor.from_dict(data)
        except (json.JSONDecodeError, IOError):
            pass
        return PressurePredictor()


def save_predictor(predictor, agent_id: str = "") -> None:
    """Persist predictor state."""
    path = _session_path(agent_id, "predictor") if agent_id else PREDICTOR_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, predictor.to_dict())
    except Exception:
        log.warning("Failed to save predictor to %s", path, exc_info=True)


def get_fingerprint_engine():
    """Load or create fingerprint engine (persists across sessions)."""
    from soma.fingerprint import FingerprintEngine
    try:
        if FINGERPRINT_PATH.exists():
            data = json.loads(FINGERPRINT_PATH.read_text())
            return FingerprintEngine.from_dict(data)
    except (json.JSONDecodeError, IOError):
        pass
    return FingerprintEngine()


def save_fingerprint_engine(engine) -> None:
    """Persist fingerprint engine."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(FINGERPRINT_PATH, engine.to_dict())
    except Exception:
        log.warning("Failed to save fingerprint engine to %s", FINGERPRINT_PATH, exc_info=True)


def get_task_tracker(cwd: str = "", agent_id: str = ""):
    """Load or create task tracker (session-scoped if agent_id provided)."""
    from soma.task_tracker import TaskTracker
    path = _session_path(agent_id, "task_tracker") if agent_id else TASK_TRACKER_PATH
    try:
        if path.exists():
            data = json.loads(path.read_text())
            tracker = TaskTracker.from_dict(data)
            if cwd:
                tracker.cwd = cwd
            return tracker
    except (json.JSONDecodeError, IOError):
        pass
    return TaskTracker(cwd=cwd)


def save_task_tracker(tracker, agent_id: str = "") -> None:
    """Persist task tracker state."""
    path = _session_path(agent_id, "task_tracker") if agent_id else TASK_TRACKER_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, tracker.to_dict())
    except Exception:
        log.warning("Failed to save task tracker to %s", path, exc_info=True)


def cleanup_session(agent_id: str) -> None:
    """Remove all session-scoped files for an agent."""
    session_dir = SESSIONS_DIR / agent_id
    try:
        if session_dir.exists():
            for f in session_dir.iterdir():
                f.unlink(missing_ok=True)
            session_dir.rmdir()
    except Exception:
        pass
