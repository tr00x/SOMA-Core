import pytest
from soma.guidance import (
    GuidanceResponse, pressure_to_mode, evaluate,
    is_destructive_bash, is_sensitive_file,
)
from soma.types import ResponseMode


class TestPressureToMode:
    def test_observe(self):
        assert pressure_to_mode(0.0) == ResponseMode.OBSERVE
        assert pressure_to_mode(0.24) == ResponseMode.OBSERVE

    def test_guide(self):
        assert pressure_to_mode(0.25) == ResponseMode.GUIDE
        assert pressure_to_mode(0.49) == ResponseMode.GUIDE

    def test_warn(self):
        assert pressure_to_mode(0.50) == ResponseMode.WARN
        assert pressure_to_mode(0.74) == ResponseMode.WARN

    def test_block(self):
        assert pressure_to_mode(0.75) == ResponseMode.BLOCK
        assert pressure_to_mode(1.0) == ResponseMode.BLOCK


class TestIsDestructiveBash:
    def test_rm_rf(self):
        assert is_destructive_bash("rm -rf /tmp/foo")
        assert is_destructive_bash("rm -r ./build")
        assert is_destructive_bash("rm --recursive --force .")

    def test_git_destructive(self):
        assert is_destructive_bash("git reset --hard")
        assert is_destructive_bash("git push --force origin main")
        assert is_destructive_bash("git push -f")
        assert is_destructive_bash("git clean -f")
        assert is_destructive_bash("git checkout .")

    def test_chmod_kill(self):
        assert is_destructive_bash("chmod 777 /etc/passwd")
        assert is_destructive_bash("kill -9 1234")

    def test_safe_commands(self):
        assert not is_destructive_bash("ls -la")
        assert not is_destructive_bash("git status")
        assert not is_destructive_bash("git push origin main")
        assert not is_destructive_bash("rm file.txt")
        assert not is_destructive_bash("python -m pytest")
        assert not is_destructive_bash("git log --oneline")


class TestIsSensitiveFile:
    def test_env_files(self):
        assert is_sensitive_file(".env")
        assert is_sensitive_file("/app/.env.local")
        assert is_sensitive_file(".env.production")

    def test_credentials(self):
        assert is_sensitive_file("credentials.json")
        assert is_sensitive_file("/home/user/credentials")

    def test_keys(self):
        assert is_sensitive_file("server.pem")
        assert is_sensitive_file("private.key")

    def test_secrets(self):
        assert is_sensitive_file("secret.yaml")
        assert is_sensitive_file("/app/secrets/db.json")

    def test_normal_files(self):
        assert not is_sensitive_file("main.py")
        assert not is_sensitive_file("README.md")
        assert not is_sensitive_file("package.json")


class TestEvaluate:
    def test_observe_mode_silent(self):
        r = evaluate(pressure=0.10, tool_name="Write", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.OBSERVE
        assert r.allow is True
        assert r.message is None

    def test_guide_mode_allows_everything(self):
        r = evaluate(pressure=0.30, tool_name="Bash", tool_input={"command": "rm -rf /"}, action_log=[])
        assert r.mode == ResponseMode.GUIDE
        assert r.allow is True

    def test_warn_mode_allows_everything(self):
        r = evaluate(pressure=0.60, tool_name="Agent", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.WARN
        assert r.allow is True

    def test_block_mode_blocks_destructive_bash(self):
        r = evaluate(pressure=0.80, tool_name="Bash", tool_input={"command": "rm -rf /"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is False
        assert r.message is not None

    def test_block_mode_allows_normal_bash(self):
        r = evaluate(pressure=0.80, tool_name="Bash", tool_input={"command": "ls -la"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_block_mode_blocks_sensitive_write(self):
        r = evaluate(pressure=0.80, tool_name="Write",
                     tool_input={"file_path": "/app/.env"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is False

    def test_block_mode_allows_normal_write(self):
        r = evaluate(pressure=0.80, tool_name="Write",
                     tool_input={"file_path": "/app/main.py"}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_block_mode_allows_agent(self):
        r = evaluate(pressure=0.80, tool_name="Agent", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_block_mode_allows_read(self):
        r = evaluate(pressure=0.99, tool_name="Read", tool_input={}, action_log=[])
        assert r.mode == ResponseMode.BLOCK
        assert r.allow is True

    def test_gsd_context(self):
        r = evaluate(pressure=0.30, tool_name="Agent", tool_input={},
                     action_log=[], gsd_active=True)
        assert r.mode == ResponseMode.GUIDE
        assert r.allow is True


class TestConfigurableThresholds:
    def test_custom_thresholds(self):
        thresholds = {"guide": 0.40, "warn": 0.60, "block": 0.80}
        assert pressure_to_mode(0.35, thresholds) == ResponseMode.OBSERVE
        assert pressure_to_mode(0.45, thresholds) == ResponseMode.GUIDE
        assert pressure_to_mode(0.65, thresholds) == ResponseMode.WARN
        assert pressure_to_mode(0.85, thresholds) == ResponseMode.BLOCK

    def test_default_thresholds(self):
        assert pressure_to_mode(0.20) == ResponseMode.OBSERVE
        assert pressure_to_mode(0.30) == ResponseMode.GUIDE

    def test_evaluate_with_thresholds(self):
        thresholds = {"guide": 0.40, "warn": 0.60, "block": 0.80}
        r = evaluate(0.35, "Write", {}, [], thresholds=thresholds)
        assert r.mode == ResponseMode.OBSERVE  # 35% is below custom guide=40%


class TestGsdActive:
    def test_gsd_active_no_warn_on_agents(self):
        """When GSD is active, agent spawns don't generate suggestions."""
        action_log = [{"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)]
        r = evaluate(0.30, "Agent", {}, action_log, gsd_active=True)
        assert r.mode == ResponseMode.GUIDE
        assert not any("agents spawned" in s for s in r.suggestions)

    def test_gsd_inactive_warns_on_agents(self):
        """Without GSD, many agents triggers a suggestion."""
        action_log = [{"tool": "Agent", "error": False, "file": "", "ts": i} for i in range(5)]
        r = evaluate(0.30, "Agent", {}, action_log, gsd_active=False)
        assert r.mode == ResponseMode.GUIDE
        assert any("agents spawned" in s for s in r.suggestions)
