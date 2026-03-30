"""SOMA State — core state persistence for all subsystems.

Loads and saves state for quality tracker, predictor, fingerprint engine,
and task tracker from ~/.soma/. This is a core module — no hooks or CLI deps.
"""

from __future__ import annotations

import json
from pathlib import Path

SOMA_DIR = Path.home() / ".soma"
PREDICTOR_PATH = SOMA_DIR / "predictor.json"
FINGERPRINT_PATH = SOMA_DIR / "fingerprint.json"
TASK_TRACKER_PATH = SOMA_DIR / "task_tracker.json"
QUALITY_PATH = SOMA_DIR / "quality.json"


def get_quality_tracker():
    """Load or create quality tracker."""
    from soma.quality import QualityTracker
    try:
        if QUALITY_PATH.exists():
            data = json.loads(QUALITY_PATH.read_text())
            return QualityTracker.from_dict(data)
    except (json.JSONDecodeError, IOError):
        pass
    return QualityTracker()


def save_quality_tracker(tracker) -> None:
    """Persist quality tracker state."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        QUALITY_PATH.write_text(json.dumps(tracker.to_dict()))
    except Exception:
        pass


def get_predictor():
    """Load or create pressure predictor."""
    from soma.predictor import PressurePredictor
    try:
        if PREDICTOR_PATH.exists():
            data = json.loads(PREDICTOR_PATH.read_text())
            return PressurePredictor.from_dict(data)
    except (json.JSONDecodeError, IOError):
        pass
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
        FINGERPRINT_PATH.write_text(json.dumps(engine.to_dict()))
    except Exception:
        pass


def get_task_tracker(cwd: str = ""):
    """Load or create task tracker for this session."""
    from soma.task_tracker import TaskTracker
    try:
        if TASK_TRACKER_PATH.exists():
            data = json.loads(TASK_TRACKER_PATH.read_text())
            tracker = TaskTracker.from_dict(data)
            if cwd:
                tracker.cwd = cwd
            return tracker
    except (json.JSONDecodeError, IOError):
        pass
    return TaskTracker(cwd=cwd)


def save_task_tracker(tracker) -> None:
    """Persist task tracker state."""
    try:
        SOMA_DIR.mkdir(parents=True, exist_ok=True)
        TASK_TRACKER_PATH.write_text(json.dumps(tracker.to_dict()))
    except Exception:
        pass
