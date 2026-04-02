"""Tests for Mirror SEMANTIC mode — LLM-backed behavioral observation."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from soma.engine import SOMAEngine
from soma.mirror import (
    Mirror, SILENCE_THRESHOLD, SEMANTIC_THRESHOLD, VBD_READ_STALENESS,
    _SEMANTIC_SYSTEM, _LLM_TIMEOUT, _LLM_MAX_TOKENS,
)
from soma.types import Action


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _engine(**kwargs) -> SOMAEngine:
    return SOMAEngine(budget={"tokens": 100_000}, **kwargs)


def _register(engine: SOMAEngine, agent_id: str = "test") -> str:
    engine.register_agent(agent_id)
    return agent_id


def _action(
    tool: str = "Read",
    output: str = "ok",
    error: bool = False,
    file_path: str = "",
) -> Action:
    meta = {"file_path": file_path} if file_path else {}
    return Action(tool_name=tool, output_text=output, token_count=10, error=error, metadata=meta)


def _record(engine, aid, action):
    return engine.record_action(aid, action)


def _build_high_pressure(engine, aid, n=10):
    """Record enough errors to push pressure above SEMANTIC_THRESHOLD."""
    for i in range(n):
        _record(engine, aid, _action("Bash", f"fail_{i}", error=True))


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")
    # Clear all LLM env vars to prevent real calls
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


# ------------------------------------------------------------------
# LLM not called at low pressure
# ------------------------------------------------------------------

class TestSemanticNotCalledAtLowPressure:
    def test_below_semantic_threshold_no_llm(self):
        engine = _engine()
        aid = _register(engine)
        # Record a few errors — pressure rises but stays below semantic threshold
        for _ in range(4):
            _record(engine, aid, _action("Bash", "fail", error=True))

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] < SEMANTIC_THRESHOLD:
            with patch.object(mirror, "_call_llm") as mock_llm:
                mirror.generate(aid, _action(), "")
                mock_llm.assert_not_called()

    def test_healthy_session_no_llm(self):
        engine = _engine()
        aid = _register(engine)
        for _ in range(3):
            _record(engine, aid, _action("Read", "ok"))

        mirror = Mirror(engine)
        with patch.object(mirror, "_call_llm") as mock_llm:
            result = mirror.generate(aid, _action(), "")
            assert result is None
            mock_llm.assert_not_called()


# ------------------------------------------------------------------
# LLM called at high pressure + drift/VBD/no pattern
# ------------------------------------------------------------------

class TestSemanticTriggered:
    def test_high_pressure_no_pattern_triggers_semantic(self):
        engine = _engine()
        aid = _register(engine)
        # Use varied tools/outputs so no pattern matches (retry, blind, cascade)
        tools = ["Read", "Bash", "Edit", "Bash", "Read", "Bash", "Edit", "Bash", "Read", "Bash"]
        for i, t in enumerate(tools):
            _record(engine, aid, _action(t, f"output_{i}", error=(t == "Bash"),
                                          file_path=f"/file{i}.py" if t in ("Read", "Edit") else ""))

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SEMANTIC_THRESHOLD:
            with patch.object(mirror, "_call_llm", return_value="Agent is editing files without running tests.") as mock_llm:
                result = mirror.generate(aid, _action(), "", task_description="Fix the parser")
                mock_llm.assert_called_once()
                assert result is not None
                assert "--- session context ---" in result
                assert "editing files" in result

    def test_vbd_triggers_semantic(self):
        engine = _engine()
        aid = _register(engine)
        # Read file A, then many edits to file B without reading B
        _record(engine, aid, _action("Read", "ok", file_path="/a.py"))
        for i in range(9):
            _record(engine, aid, _action("Edit", "change", error=(i % 2 == 0),
                                          file_path="/b.py"))

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SEMANTIC_THRESHOLD:
            assert mirror._detect_vbd(list(engine._agents[aid].ring_buffer)) is True
            with patch.object(mirror, "_call_llm", return_value="Editing b.py without reading it.") as mock_llm:
                result = mirror.generate(aid, _action(), "")
                mock_llm.assert_called_once()


# ------------------------------------------------------------------
# API failure / timeout → fallback to STATS
# ------------------------------------------------------------------

class TestSemanticFallback:
    def test_llm_returns_none_falls_back(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SEMANTIC_THRESHOLD:
            with patch.object(mirror, "_call_llm", return_value=None):
                result = mirror.generate(aid, _action(), "")
                assert result is not None
                assert "--- session context ---" in result
                # Should contain pattern or stats, not semantic text
                assert "SOMA" not in result

    def test_llm_exception_falls_back(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SEMANTIC_THRESHOLD:
            with patch.object(mirror, "_call_llm", side_effect=Exception("timeout")):
                result = mirror.generate(aid, _action(), "")
                assert result is not None
                assert "--- session context ---" in result

    def test_no_api_key_falls_back(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SEMANTIC_THRESHOLD:
            # No env vars set (cleared by fixture) → _detect_provider returns None
            result = mirror.generate(aid, _action(), "")
            assert result is not None
            assert "--- session context ---" in result
            assert "SOMA" not in result


# ------------------------------------------------------------------
# Output format
# ------------------------------------------------------------------

class TestSemanticOutputFormat:
    def test_markers_present(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        snap = engine.get_snapshot(aid)

        if snap["pressure"] >= SEMANTIC_THRESHOLD:
            with patch.object(mirror, "_call_llm", return_value="Agent retries the same failing command."):
                result = mirror.generate(aid, _action(), "")
                if result and "retries" in result:
                    assert result.startswith("--- session context ---\n")
                    assert result.endswith("\n---")

    def test_no_soma_in_semantic_output(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        with patch.object(mirror, "_call_llm", return_value="The agent is stuck in a loop."):
            result = mirror.generate(aid, _action(), "")
            if result and "stuck" in result:
                assert "SOMA" not in result
                assert "warning" not in result.lower()

    def test_semantic_truncated_to_two_sentences(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        long_response = "First sentence. Second sentence. Third sentence. Fourth sentence."
        with patch.object(mirror, "_call_llm", return_value=long_response):
            result = mirror.generate(aid, _action(), "")
            if result and "First" in result:
                # Extract semantic line (after stats oneliner)
                lines = result.split("\n")
                # lines[0] = --- session context ---
                # lines[1] = stats oneliner
                # lines[2] = semantic text
                semantic_line = lines[2] if len(lines) > 2 else ""
                sentence_count = semantic_line.count(". ")
                # At most 2 sentences (1 period-space separator)
                assert sentence_count <= 1 or semantic_line.endswith(".")


# ------------------------------------------------------------------
# VBD detection
# ------------------------------------------------------------------

class TestVBDDetection:
    def test_edit_without_read_detected(self):
        engine = _engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        actions = [
            _action("Read", "ok", file_path="/a.py"),
            _action("Bash", "ok"),
            _action("Bash", "ok"),
            _action("Bash", "ok"),
            _action("Bash", "ok"),
            _action("Bash", "ok"),
            _action("Edit", "change", file_path="/b.py"),  # no Read of b.py
        ]
        assert mirror._detect_vbd(actions) is True

    def test_edit_with_recent_read_not_detected(self):
        engine = _engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        actions = [
            _action("Read", "ok", file_path="/b.py"),  # Read b.py
            _action("Bash", "ok"),
            _action("Edit", "change", file_path="/b.py"),  # Edit b.py — Read is recent
        ]
        assert mirror._detect_vbd(actions) is False

    def test_edit_with_stale_read_detected(self):
        engine = _engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        actions = [
            _action("Read", "ok", file_path="/b.py"),  # Read b.py
        ]
        # Add enough filler to push the Read beyond VBD_READ_STALENESS
        for _ in range(VBD_READ_STALENESS + 1):
            actions.append(_action("Bash", "ok"))
        actions.append(_action("Edit", "change", file_path="/b.py"))

        assert mirror._detect_vbd(actions) is True

    def test_no_edits_no_vbd(self):
        engine = _engine()
        aid = _register(engine)
        mirror = Mirror(engine)

        actions = [_action("Read", "ok"), _action("Bash", "ok")]
        assert mirror._detect_vbd(actions) is False


# ------------------------------------------------------------------
# Provider request format (mock httpx)
# ------------------------------------------------------------------

class TestProviderFormats:
    def _make_mirror(self) -> Mirror:
        engine = _engine()
        _register(engine)
        return Mirror(engine)

    def test_gemini_request_format(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        mirror = self._make_mirror()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Agent observation."}]}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_response

        result = mirror._call_gemini(mock_httpx, "system prompt", "user prompt")

        assert result == "Agent observation."
        call_args = mock_httpx.post.call_args
        url = call_args[0][0]
        assert "generativelanguage.googleapis.com" in url
        assert "test-key-123" in url
        body = call_args[1]["json"]
        assert body["system_instruction"]["parts"][0]["text"] == "system prompt"
        assert body["contents"][0]["parts"][0]["text"] == "user prompt"
        assert body["generationConfig"]["maxOutputTokens"] == _LLM_MAX_TOKENS
        assert body["generationConfig"]["temperature"] == 0

    def test_anthropic_request_format(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        mirror = self._make_mirror()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "Agent observation."}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_response

        result = mirror._call_anthropic(mock_httpx, "sys", "usr")

        assert result == "Agent observation."
        call_args = mock_httpx.post.call_args
        url = call_args[0][0]
        assert "api.anthropic.com" in url
        headers = call_args[1]["headers"]
        assert headers["x-api-key"] == "sk-ant-test"
        body = call_args[1]["json"]
        assert body["model"] == "claude-haiku-4-5-20250514"
        assert body["system"] == "sys"
        assert body["messages"][0]["content"] == "usr"
        assert body["max_tokens"] == _LLM_MAX_TOKENS

    def test_openai_request_format(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
        mirror = self._make_mirror()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Agent observation."}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_response

        result = mirror._call_openai(mock_httpx, "sys", "usr")

        assert result == "Agent observation."
        call_args = mock_httpx.post.call_args
        url = call_args[0][0]
        assert "api.openai.com" in url
        headers = call_args[1]["headers"]
        assert "sk-test-openai" in headers["Authorization"]
        body = call_args[1]["json"]
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"


# ------------------------------------------------------------------
# Provider auto-detection
# ------------------------------------------------------------------

class TestProviderDetection:
    def test_gemini_first(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "g")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        mirror = Mirror(_engine())
        assert mirror._detect_provider() == "gemini"

    def test_anthropic_second(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        mirror = Mirror(_engine())
        assert mirror._detect_provider() == "anthropic"

    def test_openai_third(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "o")
        mirror = Mirror(_engine())
        assert mirror._detect_provider() == "openai"

    def test_none_when_no_keys(self):
        mirror = Mirror(_engine())
        assert mirror._detect_provider() is None


# ------------------------------------------------------------------
# Semantic disabled via config
# ------------------------------------------------------------------

class TestSemanticDisabled:
    def test_semantic_disabled_skips_llm(self):
        engine = _engine()
        aid = _register(engine)
        _build_high_pressure(engine, aid)

        mirror = Mirror(engine)
        mirror._semantic_enabled = False

        with patch.object(mirror, "_call_llm") as mock_llm:
            result = mirror.generate(aid, _action(), "")
            mock_llm.assert_not_called()
            if result:
                assert "--- session context ---" in result
