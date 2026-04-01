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
