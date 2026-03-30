"""Tests for setup-claude idempotency."""

import json
import tempfile
from pathlib import Path

from soma.cli.setup_claude import _install_hooks


class TestIdempotentSetup:
    def test_no_duplicate_hooks(self):
        """Running _install_hooks twice should not create duplicate entries."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            path = Path(f.name)

        _install_hooks(path, "soma-hook")
        _install_hooks(path, "soma-hook")  # second time

        settings = json.loads(path.read_text())
        for hook_type in ["PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit"]:
            entries = settings["hooks"][hook_type]
            soma_count = sum(
                1 for e in entries
                for h in e.get("hooks", [])
                if "soma" in str(h.get("command", ""))
            )
            assert soma_count == 1, f"Duplicate SOMA hooks in {hook_type}"

        path.unlink()

    def test_installs_all_hooks(self):
        """First install should add all 4 hook types."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            path = Path(f.name)

        _install_hooks(path, "soma-hook")

        settings = json.loads(path.read_text())
        for hook_type in ["PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit"]:
            assert hook_type in settings["hooks"]
            assert len(settings["hooks"][hook_type]) >= 1

        path.unlink()

    def test_preserves_existing_hooks(self):
        """SOMA hooks should not remove existing non-SOMA hooks."""
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": "my-tool", "timeout": 5}]}
                ]
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(existing, f)
            path = Path(f.name)

        _install_hooks(path, "soma-hook")

        settings = json.loads(path.read_text())
        pre_hooks = settings["hooks"]["PreToolUse"]
        # Should have both: existing + SOMA
        assert len(pre_hooks) == 2
        commands = [
            h.get("command", "")
            for e in pre_hooks
            for h in e.get("hooks", [])
        ]
        assert any("my-tool" in c for c in commands)
        assert any("soma" in c for c in commands)

        path.unlink()
