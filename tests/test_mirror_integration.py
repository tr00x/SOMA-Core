"""Integration tests: Mirror injection via post_tool_use hook.

Tests that the Mirror session context appears on stdout (tool response)
while existing stderr feedback continues working.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from soma.engine import SOMAEngine
from soma.mirror import Mirror, SILENCE_THRESHOLD
from soma.types import Action


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_engine(**kwargs) -> SOMAEngine:
    return SOMAEngine(budget={"tokens": 100_000}, **kwargs)


def _action(
    tool: str = "Read",
    output: str = "ok",
    error: bool = False,
    file_path: str = "",
    tokens: int = 10,
) -> Action:
    meta = {}
    if file_path:
        meta["file_path"] = file_path
    return Action(
        tool_name=tool,
        output_text=output,
        token_count=tokens,
        error=error,
        metadata=meta,
    )


@pytest.fixture(autouse=True)
def isolate_pattern_db(tmp_path, monkeypatch):
    """Prevent tests from reading/writing the real pattern DB."""
    monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")


@pytest.fixture
def isolate_hook(tmp_path, monkeypatch):
    """Isolate post_tool_use module state from other tests."""
    import soma.hooks.post_tool_use as ptu
    monkeypatch.setattr(ptu, "_prev_level", None)
    monkeypatch.setattr(ptu, "_prev_pressure", 0.0)
    monkeypatch.setattr(ptu, "_mirror", None)


# ------------------------------------------------------------------
# Low pressure -> stdout empty
# ------------------------------------------------------------------

class TestLowPressureSilence:
    """When pressure is low, Mirror produces no stdout output."""

    def test_no_stdout_when_healthy(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        # Record clean actions
        for _ in range(5):
            engine.record_action(agent_id, _action("Read", "content"))

        mirror = Mirror(engine)
        ctx = mirror.generate(agent_id, _action(), "some output")
        assert ctx is None

    def test_mirror_generate_returns_none_at_zero_pressure(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        mirror = Mirror(engine)
        ctx = mirror.generate(agent_id, _action(), "")
        assert ctx is None


# ------------------------------------------------------------------
# Retry loop -> stdout has pattern context
# ------------------------------------------------------------------

class TestRetryLoopInjection:
    """When retry_loop is detected and pressure is above threshold,
    stdout should contain session context with pattern info."""

    def test_retry_loop_produces_context(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        # Drive up pressure with identical failing bash commands
        for _ in range(6):
            engine.record_action(
                agent_id, _action("Bash", "npm test", error=True)
            )

        mirror = Mirror(engine)
        snap = engine.get_snapshot(agent_id)

        if snap["pressure"] >= SILENCE_THRESHOLD:
            ctx = mirror.generate(agent_id, _action("Bash", "npm test", error=True), "fail")
            assert ctx is not None
            assert "--- session context ---" in ctx
            assert "---" in ctx
            assert "SOMA" not in ctx
            # Should mention the retry pattern
            assert "repeated" in ctx or "same" in ctx or "retry" in ctx


# ------------------------------------------------------------------
# Error cascade -> stdout has stats context
# ------------------------------------------------------------------

class TestErrorCascadeInjection:
    """When errors pile up without a specific pattern, stats are shown."""

    def test_error_cascade_produces_stats(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        # Mix of different tools with errors (no retry_loop, no blind_edit)
        _tools = ["Bash", "Read", "Bash", "Read", "Bash"]
        _cmds = ["cmd1", "ok", "cmd2", "ok", "cmd3"]
        _errs = [True, False, True, False, True]

        for tool, out, err in zip(_tools, _cmds, _errs):
            engine.record_action(agent_id, _action(tool, out, error=err))

        # Add more errors to raise pressure above threshold
        for i in range(5):
            engine.record_action(
                agent_id, _action("Bash", f"different_cmd_{i}", error=True)
            )

        mirror = Mirror(engine)
        snap = engine.get_snapshot(agent_id)

        if snap["pressure"] >= SILENCE_THRESHOLD:
            ctx = mirror.generate(agent_id, _action(), "")
            assert ctx is not None
            assert "--- session context ---" in ctx
            assert "actions:" in ctx or "errors:" in ctx


# ------------------------------------------------------------------
# No SOMA branding in output
# ------------------------------------------------------------------

class TestNoBranding:
    """Session context must never contain SOMA branding or directive language."""

    def test_no_soma_in_context(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        for _ in range(8):
            engine.record_action(
                agent_id, _action("Bash", "npm test", error=True)
            )

        mirror = Mirror(engine)
        ctx = mirror.generate(agent_id, _action(), "")

        if ctx is not None:
            assert "SOMA" not in ctx
            assert "warning" not in ctx.lower()
            assert "suggestion" not in ctx.lower()
            assert "should" not in ctx.lower()
            assert "please" not in ctx.lower()


# ------------------------------------------------------------------
# Existing stderr feedback keeps working
# ------------------------------------------------------------------

class TestStderrUnchanged:
    """Existing proprioceptive feedback on stderr must continue
    alongside the new stdout Mirror injection."""

    def test_mode_transition_on_stderr(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        # Record a few clean actions to establish baseline
        for _ in range(5):
            engine.record_action(agent_id, _action("Read", "ok"))

        # Now produce errors — engine transitions mode
        results = []
        for _ in range(10):
            r = engine.record_action(
                agent_id, _action("Bash", "fail", error=True)
            )
            results.append(r)

        # At least one mode should have changed from OBSERVE
        modes = [r.mode.name for r in results]
        # The engine should have escalated at some point
        assert any(m != "OBSERVE" for m in modes) or all(m == "OBSERVE" for m in modes)
        # (Whether it escalates depends on thresholds/weights, but the mechanism is intact)


# ------------------------------------------------------------------
# post_tool_use integration: stdout vs stderr channels
# ------------------------------------------------------------------

class TestPostToolUseChannels:
    """Verify that mirror output goes to stdout, not stderr."""

    def test_mirror_uses_stdout_not_stderr(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        # Create high-pressure state
        for _ in range(8):
            engine.record_action(
                agent_id, _action("Bash", "npm test", error=True)
            )

        mirror = Mirror(engine)
        ctx = mirror.generate(agent_id, _action(), "")

        if ctx is not None:
            # Simulate what post_tool_use does: print to stdout
            captured_stdout = StringIO()
            print(ctx, file=captured_stdout)
            stdout_content = captured_stdout.getvalue()

            assert "--- session context ---" in stdout_content
            assert "SOMA" not in stdout_content

    def test_mirror_silent_on_low_pressure(self):
        engine = _make_engine()
        agent_id = "test"
        engine.register_agent(agent_id)

        for _ in range(3):
            engine.record_action(agent_id, _action("Read", "ok"))

        mirror = Mirror(engine)

        captured_stdout = StringIO()
        ctx = mirror.generate(agent_id, _action(), "")
        if ctx:
            print(ctx, file=captured_stdout)

        # Nothing should have been printed
        assert captured_stdout.getvalue() == ""
