"""Backward-compat re-export of soma.config.

v2026.6.x: canonical location for config loading is now ``soma.config``
so core modules (engine, mirror, dashboard.data, hooks/*) don't have
to reach into ``soma.cli`` and break the documented layer direction
(core never imports from cli).

Existing callers — cli/main.py, hooks/common.py, setup scripts —
keep working through this shim. New code should import from
``soma.config`` directly.
"""
from __future__ import annotations

from soma.config import (  # noqa: F401
    CLAUDE_CODE_CONFIG,
    DEFAULT_CONFIG,
    MODE_PRESETS,
    apply_mode,
    create_engine_from_config,
    create_exporters_from_config,
    load_config,
    migrate_config,
    save_config,
)
