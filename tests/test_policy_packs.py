"""Tests for community policy packs — config loading, example packs (POL-03)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from soma.policy import PolicyEngine, load_policy_packs


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "policies"


# ---------------------------------------------------------------------------
# load_policy_packs
# ---------------------------------------------------------------------------

class TestLoadPolicyPacks:
    def test_loads_single_pack_from_config(self):
        config = {"policies": {"packs": [str(_POLICIES_DIR / "strict.yaml")]}}
        engines = load_policy_packs(config)
        assert len(engines) == 1
        assert hasattr(engines[0], "rules")
        assert hasattr(engines[0], "evaluate")

    def test_empty_packs_returns_empty(self):
        config = {"policies": {"packs": []}}
        assert load_policy_packs(config) == []

    def test_missing_policies_key_returns_empty(self):
        assert load_policy_packs({}) == []

    def test_missing_packs_key_returns_empty(self):
        assert load_policy_packs({"policies": {}}) == []

    def test_invalid_path_logs_warning_no_crash(self, capsys):
        config = {"policies": {"packs": ["/nonexistent/path.yaml"]}}
        engines = load_policy_packs(config)
        assert engines == []
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "warning" in captured.err.lower()

    def test_loads_multiple_packs(self):
        config = {
            "policies": {
                "packs": [
                    str(_POLICIES_DIR / "strict.yaml"),
                    str(_POLICIES_DIR / "cost-guard.yaml"),
                ]
            }
        }
        engines = load_policy_packs(config)
        assert len(engines) == 2


# ---------------------------------------------------------------------------
# Example policy pack YAML validation
# ---------------------------------------------------------------------------

class TestStrictYaml:
    def test_file_exists(self):
        assert (_POLICIES_DIR / "strict.yaml").exists()

    def test_valid_yaml_with_version(self):
        data = yaml.safe_load((_POLICIES_DIR / "strict.yaml").read_text())
        assert data["version"] == "1"

    def test_at_least_two_policies(self):
        data = yaml.safe_load((_POLICIES_DIR / "strict.yaml").read_text())
        assert len(data["policies"]) >= 2

    def test_from_file_succeeds(self):
        pe = PolicyEngine.from_file(str(_POLICIES_DIR / "strict.yaml"))
        assert len(pe.rules) >= 2


class TestCostGuardYaml:
    def test_file_exists(self):
        assert (_POLICIES_DIR / "cost-guard.yaml").exists()

    def test_valid_yaml_with_version(self):
        data = yaml.safe_load((_POLICIES_DIR / "cost-guard.yaml").read_text())
        assert data["version"] == "1"

    def test_from_file_succeeds(self):
        pe = PolicyEngine.from_file(str(_POLICIES_DIR / "cost-guard.yaml"))
        assert len(pe.rules) >= 1
