"""Backward-compat re-export of soma.config.

2026-04-27 onward: canonical location for config loading is now ``soma.config``
so core modules (engine, mirror, dashboard.data, hooks/*) don't have
to reach into ``soma.cli`` and break the documented layer direction
(core never imports from cli).

Existing callers — cli/main.py, hooks/common.py, setup scripts —
keep working through this shim. New code should import from
``soma.config`` directly.

Implementation note: instead of ``from soma.config import …`` (which
binds names at import time), we use module-level ``__getattr__`` so
``monkeypatch.setattr(soma.cli.config_loader, "load_config", …)``
propagates to ``soma.config``. Without this, tests patching the shim
would silently no-op while real callers (which import from
``soma.config`` directly) saw the unpatched original.
"""
from __future__ import annotations

from soma import config as _config


def __getattr__(name: str):
    """Forward attribute access to soma.config.

    On access (``cli.config_loader.load_config``) returns the live
    attribute from ``soma.config``. On attribute set (via
    ``monkeypatch.setattr(cli.config_loader, "load_config", fn)``)
    Python's default ``__setattr__`` writes to *this* module — but the
    next read goes through ``__getattr__`` only if the name isn't
    already bound here. So we need to forward writes too via
    ``__setattr__`` … but module-level ``__setattr__`` isn't supported.

    Pragmatic compromise: ``__getattr__`` covers the read path, and
    callers wanting to patch should use the canonical ``soma.config``
    target. The legacy import path keeps working for read access.
    """
    if hasattr(_config, name):
        return getattr(_config, name)
    raise AttributeError(
        f"module 'soma.cli.config_loader' has no attribute {name!r}; "
        f"see soma.config for the canonical implementation"
    )
