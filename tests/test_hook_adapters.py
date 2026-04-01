"""Tests for SOMA cross-platform hook adapters (LAYER-01, HOOK-01)."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock


# ------------------------------------------------------------------
# Task 1: HookAdapter protocol, HookInput, HookResult, dispatch_hook
# ------------------------------------------------------------------

class TestHookInput:
    """HookInput frozen dataclass with sensible defaults."""

    def test_construction_with_defaults(self):
        from soma.hooks.base import HookInput
        hi = HookInput(tool_name="Bash", tool_input={"command": "ls"})
        assert hi.tool_name == "Bash"
        assert hi.tool_input == {"command": "ls"}
        assert hi.output == ""
        assert hi.error is False
        assert hi.session_id == ""
        assert hi.file_path == ""
        assert hi.duration_ms == 0
        assert hi.platform == ""
        assert hi.raw == {}

    def test_construction_with_all_fields(self):
        from soma.hooks.base import HookInput
        hi = HookInput(
            tool_name="Write",
            tool_input={"file_path": "/tmp/x.py"},
            output="ok",
            error=True,
            session_id="sess-1",
            file_path="/tmp/x.py",
            duration_ms=42.5,
            platform="cursor",
            raw={"extra": "data"},
        )
        assert hi.tool_name == "Write"
        assert hi.error is True
        assert hi.platform == "cursor"
        assert hi.raw == {"extra": "data"}

    def test_frozen(self):
        from soma.hooks.base import HookInput
        import dataclasses
        hi = HookInput(tool_name="Bash", tool_input={})
        assert dataclasses.is_dataclass(hi)
        # Frozen: cannot assign
        try:
            hi.tool_name = "Write"  # type: ignore[misc]
            assert False, "Should have raised"
        except (AttributeError, TypeError, dataclasses.FrozenInstanceError):
            pass


class TestHookResult:
    """HookResult frozen dataclass with defaults."""

    def test_construction_with_defaults(self):
        from soma.hooks.base import HookResult
        hr = HookResult()
        assert hr.allow is True
        assert hr.message == ""
        assert hr.exit_code == 0

    def test_construction_with_values(self):
        from soma.hooks.base import HookResult
        hr = HookResult(allow=False, message="blocked", exit_code=2)
        assert hr.allow is False
        assert hr.message == "blocked"
        assert hr.exit_code == 2

    def test_frozen(self):
        from soma.hooks.base import HookResult
        import dataclasses
        hr = HookResult()
        try:
            hr.allow = False  # type: ignore[misc]
            assert False, "Should have raised"
        except (AttributeError, TypeError, dataclasses.FrozenInstanceError):
            pass


class TestHookAdapterProtocol:
    """HookAdapter is a runtime_checkable Protocol."""

    def test_isinstance_check_on_conforming_class(self):
        from soma.hooks.base import HookAdapter, HookInput, HookResult

        class StubAdapter:
            @property
            def platform_name(self) -> str:
                return "test"

            def parse_input(self, raw: dict) -> HookInput:
                return HookInput(tool_name="", tool_input={})

            def format_output(self, result: HookResult) -> None:
                pass

            def get_event_type(self, raw: dict) -> str:
                return "PreToolUse"

        assert isinstance(StubAdapter(), HookAdapter)

    def test_isinstance_check_fails_for_nonconforming(self):
        from soma.hooks.base import HookAdapter

        class BadAdapter:
            pass

        assert not isinstance(BadAdapter(), HookAdapter)


class TestDispatchHook:
    """dispatch_hook routes to correct handler based on adapter output."""

    def test_routes_pre_tool_use(self):
        from soma.hooks.base import HookInput, HookResult, dispatch_hook

        adapter = MagicMock()
        adapter.get_event_type.return_value = "PreToolUse"
        adapter.parse_input.return_value = HookInput(
            tool_name="Bash", tool_input={"command": "ls"}
        )

        with patch("soma.hooks.base._DISPATCH") as mock_dispatch:
            mock_handler = MagicMock()
            mock_dispatch.get.return_value = mock_handler
            dispatch_hook(adapter, {"tool_name": "Bash"})
            adapter.get_event_type.assert_called_once()
            adapter.parse_input.assert_called_once()

    def test_routes_post_tool_use(self):
        from soma.hooks.base import HookInput, dispatch_hook

        adapter = MagicMock()
        adapter.get_event_type.return_value = "PostToolUse"
        adapter.parse_input.return_value = HookInput(
            tool_name="Bash", tool_input={}
        )

        with patch("soma.hooks.base._DISPATCH") as mock_dispatch:
            mock_handler = MagicMock()
            mock_dispatch.get.return_value = mock_handler
            dispatch_hook(adapter, {})
            mock_dispatch.get.assert_called_with("PostToolUse")


# ------------------------------------------------------------------
# Task 2: Cursor, Windsurf, and Claude Code adapters
# ------------------------------------------------------------------

class TestCursorAdapter:
    """CursorAdapter translates Cursor's camelCase events to SOMA canonical."""

    def test_platform_name(self):
        from soma.hooks.cursor import CursorAdapter
        adapter = CursorAdapter()
        assert adapter.platform_name == "cursor"

    def test_isinstance_hook_adapter(self):
        from soma.hooks.base import HookAdapter
        from soma.hooks.cursor import CursorAdapter
        assert isinstance(CursorAdapter(), HookAdapter)

    def test_parse_input_basic(self):
        from soma.hooks.cursor import CursorAdapter
        adapter = CursorAdapter()
        hi = adapter.parse_input({
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "conversation_id": "abc",
        })
        assert hi.tool_name == "Bash"
        assert hi.tool_input == {"command": "ls"}
        assert hi.session_id == "abc"
        assert hi.platform == "cursor"

    def test_get_event_type_pre_tool_use(self):
        from soma.hooks.cursor import CursorAdapter
        adapter = CursorAdapter()
        assert adapter.get_event_type({"hook_type": "preToolUse"}) == "PreToolUse"

    def test_get_event_type_post_tool_use(self):
        from soma.hooks.cursor import CursorAdapter
        adapter = CursorAdapter()
        assert adapter.get_event_type({"hook_type": "postToolUse"}) == "PostToolUse"

    def test_get_event_type_stop(self):
        from soma.hooks.cursor import CursorAdapter
        adapter = CursorAdapter()
        assert adapter.get_event_type({"hook_type": "stop"}) == "Stop"

    def test_parse_input_with_response(self):
        from soma.hooks.cursor import CursorAdapter
        adapter = CursorAdapter()
        hi = adapter.parse_input({
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": "file written",
            "error": True,
            "conversation_id": "sess-42",
        })
        assert hi.tool_name == "Write"
        assert hi.output == "file written"
        assert hi.error is True
        assert hi.session_id == "sess-42"


class TestWindsurfAdapter:
    """WindsurfAdapter translates Windsurf's split events to SOMA canonical."""

    def test_platform_name(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        assert adapter.platform_name == "windsurf"

    def test_isinstance_hook_adapter(self):
        from soma.hooks.base import HookAdapter
        from soma.hooks.windsurf import WindsurfAdapter
        assert isinstance(WindsurfAdapter(), HookAdapter)

    def test_parse_input_run_command(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        hi = adapter.parse_input({
            "tool_info": {"command": "ls"},
            "agent_action_name": "pre_run_command",
            "trajectory_id": "xyz",
        })
        assert hi.tool_name == "Bash"
        assert hi.tool_input == {"command": "ls"}
        assert hi.session_id == "xyz"
        assert hi.platform == "windsurf"

    def test_get_event_type_pre_run_command(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        assert adapter.get_event_type({"agent_action_name": "pre_run_command"}) == "PreToolUse"

    def test_get_event_type_pre_write_code(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        assert adapter.get_event_type({"agent_action_name": "pre_write_code"}) == "PreToolUse"

    def test_get_event_type_post_run_command(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        assert adapter.get_event_type({"agent_action_name": "post_run_command"}) == "PostToolUse"

    def test_get_event_type_post_cascade_response(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        assert adapter.get_event_type({"agent_action_name": "post_cascade_response"}) == "Stop"

    def test_parse_input_write_code(self):
        from soma.hooks.windsurf import WindsurfAdapter
        adapter = WindsurfAdapter()
        hi = adapter.parse_input({
            "tool_info": {"file_path": "/tmp/x.py", "content": "print('hi')"},
            "agent_action_name": "pre_write_code",
            "trajectory_id": "traj-1",
        })
        assert hi.tool_name == "Write"
        assert hi.tool_input == {"file_path": "/tmp/x.py", "content": "print('hi')"}


class TestCursorConfig:
    """generate_cursor_config produces valid hooks.json structure."""

    def test_generates_valid_config(self):
        from soma.hooks.cursor import generate_cursor_config
        config = generate_cursor_config()
        assert "hooks" in config
        hooks = config["hooks"]
        assert "preToolUse" in hooks
        assert "postToolUse" in hooks
        assert "stop" in hooks
        # Each hook entry has command field
        for entries in hooks.values():
            assert len(entries) >= 1
            assert "command" in entries[0]
            assert "soma-hook" in entries[0]["command"]


class TestWindsurfConfig:
    """generate_windsurf_config produces valid hooks config."""

    def test_generates_valid_config(self):
        from soma.hooks.windsurf import generate_windsurf_config
        config = generate_windsurf_config()
        assert "hooks" in config
        hooks = config["hooks"]
        # Must have all windsurf events
        expected_events = [
            "pre_run_command", "pre_write_code", "pre_read_code",
            "post_run_command", "post_write_code", "post_read_code",
            "post_cascade_response",
        ]
        for event in expected_events:
            assert event in hooks, f"Missing event: {event}"
            entries = hooks[event]
            assert len(entries) >= 1
            assert "command" in entries[0]
            assert "soma-hook" in entries[0]["command"]


class TestSetupCommands:
    """Setup commands for Cursor and Windsurf."""

    def test_run_setup_cursor_exists(self):
        from soma.cli.setup_claude import run_setup_cursor
        assert callable(run_setup_cursor)

    def test_run_setup_windsurf_exists(self):
        from soma.cli.setup_claude import run_setup_windsurf
        assert callable(run_setup_windsurf)


class TestClaudeCodeAdapter:
    """ClaudeCodeAdapter implements HookAdapter without breaking existing main()."""

    def test_platform_name(self):
        from soma.hooks.claude_code import ClaudeCodeAdapter
        adapter = ClaudeCodeAdapter()
        assert adapter.platform_name == "claude-code"

    def test_isinstance_hook_adapter(self):
        from soma.hooks.base import HookAdapter
        from soma.hooks.claude_code import ClaudeCodeAdapter
        assert isinstance(ClaudeCodeAdapter(), HookAdapter)

    def test_get_event_type_from_env(self):
        from soma.hooks.claude_code import ClaudeCodeAdapter
        adapter = ClaudeCodeAdapter()
        with patch.dict("os.environ", {"CLAUDE_HOOK": "PreToolUse"}):
            assert adapter.get_event_type({}) == "PreToolUse"

    def test_parse_input(self):
        from soma.hooks.claude_code import ClaudeCodeAdapter
        adapter = ClaudeCodeAdapter()
        hi = adapter.parse_input({
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        })
        assert hi.tool_name == "Bash"
        assert hi.platform == "claude-code"

    def test_existing_dispatch_unchanged(self):
        """The existing DISPATCH dict must still be present."""
        from soma.hooks.claude_code import DISPATCH
        assert "PreToolUse" in DISPATCH
        assert "PostToolUse" in DISPATCH
        assert "Stop" in DISPATCH

    def test_existing_main_unchanged(self):
        """The existing main() function must still be importable."""
        from soma.hooks.claude_code import main
        assert callable(main)


class TestHooksInit:
    """hooks/__init__.py exports adapter classes."""

    def test_exports_hook_adapter(self):
        from soma.hooks import HookAdapter
        assert HookAdapter is not None

    def test_exports_hook_input(self):
        from soma.hooks import HookInput
        assert HookInput is not None

    def test_exports_hook_result(self):
        from soma.hooks import HookResult
        assert HookResult is not None

    def test_exports_cursor_adapter(self):
        from soma.hooks import CursorAdapter
        assert CursorAdapter is not None

    def test_exports_windsurf_adapter(self):
        from soma.hooks import WindsurfAdapter
        assert WindsurfAdapter is not None

    def test_exports_claude_code_adapter(self):
        from soma.hooks import ClaudeCodeAdapter
        assert ClaudeCodeAdapter is not None
