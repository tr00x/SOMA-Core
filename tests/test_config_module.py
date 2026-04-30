"""
Regression for v2026.6.x fix #12 — soma.config exists at the top
level so core modules (engine, mirror, dashboard.data, hooks/*)
don't have to reach into soma.cli for configuration loading. The
old soma.cli.config_loader path stays as a backward-compat alias.

Backend Architect flagged this as the worst layer-leak in the
codebase: core importing CLI broke the documented dependency
direction.
"""
from __future__ import annotations


def test_soma_config_exposes_load_config() -> None:
    from soma.config import load_config
    assert callable(load_config)


def test_soma_config_exposes_default_config() -> None:
    from soma.config import DEFAULT_CONFIG
    assert isinstance(DEFAULT_CONFIG, dict)
    assert "soma" in DEFAULT_CONFIG


def test_soma_config_exposes_save_config() -> None:
    from soma.config import save_config
    assert callable(save_config)


def test_legacy_cli_config_loader_still_works() -> None:
    """Backwards compat — existing callers (cli/main.py, hooks/common.py,
    setup scripts) import from soma.cli.config_loader. That path must
    keep working until everyone migrates to soma.config."""
    from soma.cli.config_loader import load_config, DEFAULT_CONFIG, save_config
    from soma import config as new_path
    # Same callable, not just same name.
    assert load_config is new_path.load_config
    assert DEFAULT_CONFIG is new_path.DEFAULT_CONFIG
    assert save_config is new_path.save_config


def test_shim_attribute_access_is_live() -> None:
    """The shim must forward reads to soma.config dynamically — not
    snapshot at import time. Otherwise a test that patches
    soma.config.load_config and then imports through the shim sees the
    pre-patch original. (This was the v2026.6.2 review's NEEDS WORK
    finding — the previous static `from … import …` shim broke this.)
    """
    from soma import config as _cfg
    from soma.cli import config_loader as _cl

    sentinel = object()
    original = _cfg.load_config
    try:
        _cfg.load_config = sentinel  # type: ignore[assignment]
        assert _cl.load_config is sentinel, (
            "shim did not forward attribute access — patches to "
            "soma.config don't propagate through the legacy shim"
        )
    finally:
        _cfg.load_config = original  # type: ignore[assignment]
