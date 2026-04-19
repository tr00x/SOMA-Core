"""Tests for setup-claude idempotency and wheel packaging."""

import json
import sys
import tempfile
from pathlib import Path

from soma.cli.setup_claude import _install_hooks, _install_skills

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


class TestSkillsPackaging:
    """P2.10 — slash-command skills must ship inside the wheel."""

    def test_pyproject_force_includes_skills(self):
        """pyproject.toml must map skills/ into src/soma/_skills in the wheel.

        Without this mapping `pip install soma-ai` leaves /soma:* slash
        commands uninstallable — `_install_skills` silently no-ops on the
        bundled-location check and the dev-repo fallback never matches.
        """
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        fi = (
            data.get("tool", {})
            .get("hatch", {})
            .get("build", {})
            .get("targets", {})
            .get("wheel", {})
            .get("force-include", {})
        )
        assert fi.get("skills") == "src/soma/_skills", (
            "wheel build must force-include skills/ into src/soma/_skills — "
            "otherwise pip users have no slash commands"
        )

    def test_repo_skills_tree_has_expected_skills(self):
        """Repo skills/ dir must contain the canonical four skills so the
        force-include mapping actually ships something."""
        skills_root = REPO_ROOT / "skills"
        assert skills_root.is_dir()
        names = {
            p.name for p in skills_root.iterdir()
            if p.is_dir() and p.name.startswith("soma-")
        }
        expected = {"soma-status", "soma-config", "soma-control", "soma-help"}
        missing = expected - names
        assert not missing, f"missing skill dirs: {sorted(missing)}"

    def test_install_skills_copies_bundled_layout(self, tmp_path, monkeypatch):
        """Simulate the pip-install layout (`<soma_pkg>/_skills/soma-*`) and
        verify _install_skills writes SKILL.md into ~/.claude/skills."""
        # Fake soma package location with skills bundled alongside it.
        fake_pkg = tmp_path / "soma_pkg"
        fake_pkg.mkdir()
        (fake_pkg / "__init__.py").write_text("")
        skill_src = fake_pkg / "_skills" / "soma-status"
        skill_src.mkdir(parents=True)
        (skill_src / "SKILL.md").write_text("---\nname: soma:status\n---\nbody")

        # Monkeypatch Path.home so skills_target lands in tmp, and point
        # soma.__file__ at the fake layout so the bundled-check wins.
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        import soma as soma_mod
        monkeypatch.setattr(
            soma_mod, "__file__", str(fake_pkg / "__init__.py"), raising=True,
        )

        assert _install_skills() is True
        installed = tmp_path / "home" / ".claude" / "skills" / "soma-status" / "SKILL.md"
        assert installed.exists()
        assert "soma:status" in installed.read_text()
