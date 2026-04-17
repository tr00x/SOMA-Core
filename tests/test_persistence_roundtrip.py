"""Tests for guidance cooldown and followthrough persistence round-trips."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def soma_dir(tmp_path):
    """Patch SOMA_DIR to an isolated temp directory."""
    with patch("soma.hooks.common.SOMA_DIR", tmp_path):
        yield tmp_path


# ---------------------------------------------------------------------------
# Cooldown persistence
# ---------------------------------------------------------------------------


def test_cooldown_persistence_roundtrip(soma_dir):
    """Write cooldowns, read back, verify match."""
    from soma.hooks.common import read_guidance_cooldowns, write_guidance_cooldowns

    cooldowns = {"retry_storm": 10, "blind_edit": 25, "error_cascade": 42}
    write_guidance_cooldowns(cooldowns, "test-agent")

    loaded = read_guidance_cooldowns("test-agent")
    assert loaded == cooldowns


def test_cooldown_empty_on_missing_file(soma_dir):
    """Reading cooldowns from nonexistent file returns empty dict."""
    from soma.hooks.common import read_guidance_cooldowns

    loaded = read_guidance_cooldowns("nonexistent-agent")
    assert loaded == {}


# ---------------------------------------------------------------------------
# Followthrough persistence
# ---------------------------------------------------------------------------


def test_followthrough_persistence_roundtrip(soma_dir):
    """Write followthrough, read back, verify match."""
    from soma.hooks.common import read_guidance_followthrough, write_guidance_followthrough

    pending = {
        "pattern": "blind_edit",
        "suggestion": "Read foo.py before editing",
        "actions_since": 0,
        "file": "/src/foo.py",
    }
    write_guidance_followthrough(pending, "test-agent")

    loaded = read_guidance_followthrough("test-agent")
    assert loaded is not None
    assert loaded["pattern"] == "blind_edit"
    assert loaded["suggestion"] == "Read foo.py before editing"
    assert loaded["file"] == "/src/foo.py"
    assert loaded["actions_since"] == 0


def test_followthrough_clear(soma_dir):
    """Writing None clears followthrough."""
    from soma.hooks.common import read_guidance_followthrough, write_guidance_followthrough

    # First write a pending followthrough
    pending = {"pattern": "retry_storm", "suggestion": "Try another tool", "actions_since": 1, "tool": "Bash"}
    write_guidance_followthrough(pending, "clear-agent")
    assert read_guidance_followthrough("clear-agent") is not None

    # Clear it
    write_guidance_followthrough(None, "clear-agent")
    assert read_guidance_followthrough("clear-agent") is None


def test_followthrough_actions_since_increment(soma_dir):
    """Write with actions_since=3, read back, verify 3."""
    from soma.hooks.common import read_guidance_followthrough, write_guidance_followthrough

    pending = {
        "pattern": "entropy_drop",
        "suggestion": "Diversify your tools",
        "actions_since": 3,
        "tool": "Bash",
    }
    write_guidance_followthrough(pending, "increment-agent")

    loaded = read_guidance_followthrough("increment-agent")
    assert loaded is not None
    assert loaded["actions_since"] == 3
