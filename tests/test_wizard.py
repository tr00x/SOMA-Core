"""Tests for the SOMA setup wizard."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from soma.cli.wizard import run_wizard, get_sensitivity_thresholds


# ---------------------------------------------------------------------------
# Sensitivity mapping tests
# ---------------------------------------------------------------------------


def test_sensitivity_aggressive():
    thresholds = get_sensitivity_thresholds("aggressive")
    assert thresholds["caution"] == 0.15
    assert thresholds["degrade"] == 0.35
    assert thresholds["quarantine"] == 0.55
    assert thresholds["restart"] == 0.75


def test_sensitivity_balanced():
    thresholds = get_sensitivity_thresholds("balanced")
    assert thresholds["caution"] == 0.25
    assert thresholds["degrade"] == 0.50
    assert thresholds["quarantine"] == 0.75
    assert thresholds["restart"] == 0.90


def test_sensitivity_relaxed():
    thresholds = get_sensitivity_thresholds("relaxed")
    assert thresholds["caution"] == 0.35
    assert thresholds["degrade"] == 0.60
    assert thresholds["quarantine"] == 0.85
    assert thresholds["restart"] == 0.95


def test_sensitivity_all_presets_have_required_keys():
    required = {"caution", "degrade", "quarantine", "restart"}
    for name in ("aggressive", "balanced", "relaxed"):
        thresholds = get_sensitivity_thresholds(name)
        assert required == set(thresholds.keys()), (
            f"Preset '{name}' is missing keys"
        )


def test_sensitivity_thresholds_are_ordered():
    """For every preset, thresholds must be monotonically increasing."""
    for name in ("aggressive", "balanced", "relaxed"):
        t = get_sensitivity_thresholds(name)
        values = [t["caution"], t["degrade"], t["quarantine"], t["restart"]]
        assert values == sorted(values), (
            f"Preset '{name}' thresholds are not in ascending order: {values}"
        )


# ---------------------------------------------------------------------------
# Wizard creates soma.toml — helper
# ---------------------------------------------------------------------------


def _run_wizard_with_inputs(inputs: list[str], tmp_path: Path) -> dict:
    """Run the wizard with mocked input() responses, writing soma.toml to tmp_path."""
    input_iter = iter(inputs)
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        with patch("builtins.input", side_effect=lambda: next(input_iter)):
            run_wizard()
    finally:
        os.chdir(original_cwd)

    toml_path = tmp_path / "soma.toml"
    assert toml_path.exists(), "soma.toml was not created"
    with open(toml_path, "rb") as fh:
        return tomllib.load(fh)


# ---------------------------------------------------------------------------
# Claude Code wizard flow
# ---------------------------------------------------------------------------


def test_wizard_claude_code_creates_toml(tmp_path):
    """Wizard option 1 (Claude Code) should produce a valid soma.toml."""
    inputs = [
        "1",          # project type: Claude Code
        "",           # token budget: default 100000
        "",           # cost limit: default 5.0
        "",           # sensitivity: default balanced
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)

    assert config["project"]["type"] == "claude_code"
    assert config["budget"]["tokens"] == 100_000
    assert config["budget"]["cost_usd"] == 5.0
    assert config["sensitivity"] == "balanced"
    assert config["thresholds"]["caution"] == 0.25


def test_wizard_claude_code_custom_sensitivity(tmp_path):
    """Wizard option 1 with aggressive sensitivity uses correct thresholds."""
    inputs = [
        "1",
        "50000",      # custom token budget
        "2.5",        # custom cost limit
        "aggressive",
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)

    assert config["budget"]["tokens"] == 50_000
    assert config["budget"]["cost_usd"] == 2.5
    assert config["sensitivity"] == "aggressive"
    assert config["thresholds"]["caution"] == 0.15
    assert config["thresholds"]["degrade"] == 0.35


# ---------------------------------------------------------------------------
# Python SDK wizard flow
# ---------------------------------------------------------------------------


def test_wizard_python_sdk_creates_toml(tmp_path):
    """Wizard option 2 (Python SDK) should produce a valid soma.toml."""
    inputs = [
        "2",          # project type: Python SDK
        "3",          # num agents
        "",           # agent names: default
        "y",          # chain
        "",           # token budget: default
        "balanced",   # sensitivity
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)

    assert config["project"]["type"] == "python_sdk"
    assert config["agents"]["count"] == 3
    assert len(config["agents"]["names"]) == 3
    assert config["agents"]["chain"] is True
    assert config["budget"]["tokens"] == 100_000
    assert config["sensitivity"] == "balanced"


def test_wizard_python_sdk_custom_agents(tmp_path):
    """Wizard option 2 with custom agent names stores them correctly."""
    inputs = [
        "2",
        "2",                         # 2 agents
        "Alpha, Beta",               # custom names
        "n",                         # no chain
        "50000",
        "relaxed",
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)

    assert config["agents"]["names"] == ["Alpha", "Beta"]
    assert config["agents"]["chain"] is False
    assert config["sensitivity"] == "relaxed"
    assert config["thresholds"]["caution"] == 0.35


# ---------------------------------------------------------------------------
# CI wizard flow
# ---------------------------------------------------------------------------


def test_wizard_ci_creates_toml(tmp_path):
    """Wizard option 3 (CI) should produce a valid soma.toml."""
    inputs = [
        "3",          # project type: CI
        "",           # max level: default caution
        "",           # token budget: default 10000
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)

    assert config["project"]["type"] == "ci"
    assert config["ci"]["max_level"] == "caution"
    assert config["budget"]["tokens"] == 10_000


def test_wizard_ci_custom_values(tmp_path):
    """Wizard option 3 with custom values stores them correctly."""
    inputs = [
        "3",
        "healthy",    # stricter max level
        "5000",       # lower token budget
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)

    assert config["ci"]["max_level"] == "healthy"
    assert config["budget"]["tokens"] == 5_000


# ---------------------------------------------------------------------------
# Invalid input re-prompting
# ---------------------------------------------------------------------------


def test_wizard_invalid_project_type_reprompts(tmp_path):
    """Wizard re-prompts when an invalid project type is entered."""
    inputs = [
        "5",          # invalid — should re-ask
        "9",          # still invalid
        "3",          # valid: CI
        "",           # max level default
        "",           # token budget default
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)
    assert config["project"]["type"] == "ci"


def test_wizard_invalid_sensitivity_reprompts(tmp_path):
    """Wizard re-prompts when an invalid sensitivity is entered."""
    inputs = [
        "1",          # Claude Code
        "",           # token budget default
        "",           # cost limit default
        "extreme",    # invalid sensitivity
        "balanced",   # valid
    ]
    config = _run_wizard_with_inputs(inputs, tmp_path)
    assert config["sensitivity"] == "balanced"
