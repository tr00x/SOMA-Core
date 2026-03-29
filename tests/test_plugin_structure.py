"""Verify plugin structure is valid for Claude Code."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_plugin_json_exists_and_valid():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["name"] == "soma-core"
    assert "version" in data
    assert "description" in data


def test_marketplace_json_exists():
    p = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert "plugins" in data
    assert len(data["plugins"]) >= 1


def test_hooks_json_valid():
    p = REPO_ROOT / "hooks" / "hooks.json"
    assert p.exists()
    data = json.loads(p.read_text())
    hooks = data["hooks"]
    for required in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"):
        assert required in hooks, f"Missing hook: {required}"


def test_run_hook_sh_executable():
    p = REPO_ROOT / "hooks" / "run-hook.sh"
    assert p.exists()
    import os
    assert os.access(p, os.X_OK), "run-hook.sh must be executable"


def test_skill_dirs_exist():
    skills = REPO_ROOT / "skills"
    for name in ("soma-status", "soma-config", "soma-control", "soma-help"):
        skill_file = skills / name / "SKILL.md"
        assert skill_file.exists(), f"Missing skill: {skill_file}"
