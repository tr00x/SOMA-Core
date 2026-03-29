"""SOMA config loader — reads/writes soma.toml and builds engine from config."""

from __future__ import annotations

import os
import tomllib
from typing import Any

import tomli_w

from soma.engine import SOMAEngine
from soma.types import AutonomyMode


DEFAULT_CONFIG: dict[str, Any] = {
    "soma": {
        "version": "0.2.0",
        "store": "~/.soma/state.json",
    },
    "budget": {
        "tokens": 100000,
        "cost_usd": 5.0,
    },
    "agents": {
        "default": {
            "autonomy": "human_on_the_loop",
        },
    },
    "thresholds": {
        "caution": 0.25,
        "degrade": 0.50,
        "quarantine": 0.75,
        "restart": 0.90,
    },
    "weights": {
        "uncertainty": 2.0,
        "drift": 1.8,
        "error_rate": 1.5,
        "cost": 1.0,
        "token_usage": 0.8,
    },
    "graph": {
        "damping": 0.6,
        "trust_decay_rate": 0.05,
        "trust_recovery_rate": 0.02,
    },
}


# Claude Code optimized config — tuned for long coding sessions.
#
# Key differences from default:
# - Higher budget (1M tokens / $50) — Claude Code sessions are long
# - Higher thresholds — Claude Code is naturally noisy (lots of Bash/Read/Write),
#   default thresholds cause false alarms
# - Lower uncertainty weight — tool diversity is normal for Claude Code
# - Higher error weight — errors in Claude Code matter more (broken builds, bad edits)
# - Cold start grace period built into engine (first 10 actions penalty-free)
CLAUDE_CODE_CONFIG: dict[str, Any] = {
    "soma": {
        "version": "0.3.0",
        "store": "~/.soma/state.json",
        "profile": "claude-code",
    },
    "hooks": {
        "verbosity": "normal",  # minimal, normal, verbose
        "validate_python": True,
        "validate_js": True,
        "lint_python": True,
        "predict": True,
        "fingerprint": True,
        "quality": True,
        "task_tracking": True,
    },
    "budget": {
        "tokens": 1_000_000,
        "cost_usd": 50.0,
    },
    "agents": {
        "claude-code": {
            "autonomy": "human_on_the_loop",
            "tools": [
                "Bash", "Edit", "Read", "Write", "Grep", "Glob",
                "Agent", "WebSearch", "WebFetch", "Skill", "NotebookEdit",
            ],
        },
    },
    "thresholds": {
        "caution": 0.40,
        "degrade": 0.60,
        "quarantine": 0.80,
        "restart": 0.95,
    },
    "weights": {
        "uncertainty": 1.2,
        "drift": 1.5,
        "error_rate": 2.5,
        "cost": 1.0,
        "token_usage": 0.6,
    },
    "graph": {
        "damping": 0.6,
        "trust_decay_rate": 0.03,
        "trust_recovery_rate": 0.04,
    },
}


MODE_PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "agents": {
            "claude-code": {
                "autonomy": "human_in_the_loop",
            },
        },
        "thresholds": {
            "caution": 0.20,
            "degrade": 0.40,
            "quarantine": 0.60,
            "restart": 0.80,
        },
        "hooks": {
            "verbosity": "verbose",
            "validate_python": True,
            "validate_js": True,
            "lint_python": True,
            "predict": True,
            "fingerprint": True,
            "quality": True,
            "task_tracking": True,
        },
    },
    "relaxed": {
        "agents": {
            "claude-code": {
                "autonomy": "human_on_the_loop",
            },
        },
        "thresholds": {
            "caution": 0.40,
            "degrade": 0.60,
            "quarantine": 0.80,
            "restart": 0.95,
        },
        "hooks": {
            "verbosity": "normal",
            "validate_python": True,
            "validate_js": True,
            "lint_python": True,
            "predict": True,
            "fingerprint": True,
            "quality": True,
            "task_tracking": True,
        },
    },
    "autonomous": {
        "agents": {
            "claude-code": {
                "autonomy": "fully_autonomous",
            },
        },
        "thresholds": {
            "caution": 0.60,
            "degrade": 0.80,
            "quarantine": 0.95,
            "restart": 0.99,
        },
        "hooks": {
            "verbosity": "minimal",
            "validate_python": True,
            "validate_js": False,
            "lint_python": False,
            "predict": False,
            "fingerprint": False,
            "quality": False,
            "task_tracking": False,
        },
    },
}


def apply_mode(config: dict[str, Any], mode: str) -> dict[str, Any]:
    """Deep-merge a mode preset into config. Returns the merged config."""
    import copy
    preset = MODE_PRESETS.get(mode)
    if preset is None:
        raise ValueError(f"Unknown mode: {mode!r}. Choose from: {', '.join(MODE_PRESETS)}")
    result = copy.deepcopy(config)
    _deep_merge(result, preset)
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base, mutating base."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load_config(path: str = "soma.toml") -> dict[str, Any]:
    """Read and return config from *path*. Returns DEFAULT_CONFIG if file is missing."""
    if not os.path.exists(path):
        return DEFAULT_CONFIG.copy()
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def save_config(config: dict[str, Any], path: str = "soma.toml") -> None:
    """Write *config* to *path* as TOML using tomli_w."""
    with open(path, "wb") as fh:
        tomli_w.dump(config, fh)


def create_engine_from_config(config: dict[str, Any]) -> SOMAEngine:
    """Build and return a SOMAEngine configured from *config*."""
    budget_section = config.get("budget", {})
    budget: dict[str, float] = {}
    if "tokens" in budget_section:
        budget["tokens"] = float(budget_section["tokens"])
    if "cost_usd" in budget_section:
        budget["cost_usd"] = float(budget_section["cost_usd"])

    custom_weights = config.get("weights") or None
    custom_thresholds = config.get("thresholds") or None
    engine = SOMAEngine(
        budget=budget or None,
        custom_weights=custom_weights,
        custom_thresholds=custom_thresholds,
    )

    # Register a default agent if specified in config
    agents_section = config.get("agents", {})
    default_agent = agents_section.get("default", {})
    autonomy_str = default_agent.get("autonomy", "human_on_the_loop")

    # Map config string -> AutonomyMode enum
    _autonomy_map = {
        "human_on_the_loop": AutonomyMode.HUMAN_ON_THE_LOOP,
        "human_in_the_loop": AutonomyMode.HUMAN_IN_THE_LOOP,
        "fully_autonomous": AutonomyMode.FULLY_AUTONOMOUS,
    }
    autonomy = _autonomy_map.get(autonomy_str, AutonomyMode.HUMAN_ON_THE_LOOP)

    engine.register_agent("default", autonomy=autonomy)

    return engine
