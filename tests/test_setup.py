"""Tests for setup-claude idempotency and wheel packaging."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

from soma.cli.setup_claude import _install_hooks, _install_skills, _install_statusline

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent


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


class TestSettingsSafety:
    """Settings.json is shared with every other Claude Code hook the user
    runs. SOMA must NEVER silently overwrite a corrupt or unreadable
    settings file — that destroys the user's config in one command. And
    every successful write must be backed up first so a bad release can
    be rolled back."""

    def test_corrupt_settings_raises_not_overwrites(self, tmp_path):
        """If settings.json has invalid JSON, refuse to write rather than
        silently zero it out. The previous behaviour silently fell back
        to ``settings = {}`` and clobbered every other hook on disk."""
        path = tmp_path / "settings.json"
        path.write_text("{ broken json /// not parseable")
        original = path.read_text()

        with pytest.raises(RuntimeError, match="settings.json"):
            _install_hooks(path, "soma-hook")

        # Original content untouched.
        assert path.read_text() == original

    def test_corrupt_settings_statusline_also_raises(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("not json")
        original = path.read_text()

        with pytest.raises(RuntimeError, match="settings.json"):
            _install_statusline(path, "soma-statusline")

        assert path.read_text() == original

    def test_install_creates_backup_before_write(self, tmp_path):
        """Successful installs must leave a .bak copy of the prior
        settings.json next to it so the user can roll back."""
        path = tmp_path / "settings.json"
        prior = {"hooks": {"PreToolUse": [
            {"hooks": [{"type": "command", "command": "my-tool", "timeout": 5}]}
        ]}}
        path.write_text(json.dumps(prior, indent=2))

        _install_hooks(path, "soma-hook")

        backup = path.with_suffix(".json.bak")
        assert backup.exists(), "must back up before write"
        assert json.loads(backup.read_text()) == prior

    def test_no_backup_when_no_prior_file(self, tmp_path):
        """First-time installs (no settings.json at all) must NOT create
        an empty .bak — that would just be noise."""
        path = tmp_path / "settings.json"
        assert not path.exists()

        _install_hooks(path, "soma-hook")

        backup = path.with_suffix(".json.bak")
        assert not backup.exists()

    def test_write_is_atomic(self, tmp_path, monkeypatch):
        """Simulate a crash between truncate and full write: the prior
        file must remain intact (atomic temp+rename, not in-place write)."""
        path = tmp_path / "settings.json"
        prior = {"hooks": {"PreToolUse": [
            {"hooks": [{"type": "command", "command": "keep-me", "timeout": 5}]}
        ]}}
        path.write_text(json.dumps(prior))
        original_bytes = path.read_bytes()

        # Make os.replace blow up partway through
        import os as _os
        original_replace = _os.replace

        def explode(*_a, **_kw):
            raise OSError("simulated disk full")

        monkeypatch.setattr(_os, "replace", explode)

        with pytest.raises(OSError):
            _install_hooks(path, "soma-hook")

        # Original file content unchanged — the write was never half-applied.
        assert path.read_bytes() == original_bytes
        # And no temp file left behind.
        leftover = list(tmp_path.glob("settings.json.*"))
        # backup may exist (.bak) but no .tmp
        for p in leftover:
            assert not p.name.endswith(".tmp"), f"leftover temp: {p}"

        monkeypatch.setattr(_os, "replace", original_replace)


class TestSkillsPackaging:
    """v2026.6.x: skills/ directory was removed in commit 804b365.
    The packaging mapping is gone too. _install_skills in
    cli/setup_claude.py returns False gracefully when no source
    exists, so this is now a "no force-include" assertion to keep the
    invariant pinned in case someone re-adds a stale path."""

    def test_pyproject_does_not_force_include_missing_skills(self):
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        fi = (
            data.get("tool", {})
            .get("hatch", {})
            .get("build", {})
            .get("targets", {})
            .get("wheel", {})
            .get("force-include", {})
        )
        assert "skills" not in fi, (
            "pyproject.toml force-includes 'skills' but the directory "
            "was deleted in 804b365. Either restore skills/ or drop "
            "the mapping."
        )

    # v2026.6.x: test_repo_skills_tree_has_expected_skills and
    # test_install_skills_copies_bundled_layout removed — the skills/
    # directory was deleted in 804b365. _install_skills now always
    # returns False at runtime (no source dir), and the wheel build
    # no longer force-includes anything. Pinning that contract via
    # test_pyproject_does_not_force_include_missing_skills above.

    # _install_skills runtime behavior is hard to test cleanly:
    # the function falls through to `Path(__file__).parent.parent.parent.parent
    # / "skills"` which resolves to wherever pytest happens to run from
    # (an arbitrary site-packages tree on CI, the repo root on dev box).
    # The contract that matters — "no skills bundled in the wheel,
    # build still succeeds" — is captured by
    # test_pyproject_does_not_force_include_missing_skills above.
