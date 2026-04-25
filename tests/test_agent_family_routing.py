"""Cross-IDE agent_id family discipline.

Pre-2026-04-25 cursor and windsurf hooks dispatched through
post_tool_use.main like claude-code, but agent_id was hardcoded to
``cc-{ppid}`` in _get_session_agent_id. That meant every cursor /
windsurf session landed in the ``cc`` calibration family and
contaminated:
- per-user calibration profiles (mixed cursor + cc data)
- ROI dashboard pattern hit rates (one bucket for everything)
- A/B counters (one (cc, pattern) row even when arms came from
  different platforms with different baseline behaviour)

The fix is a SOMA_AGENT_FAMILY env var set by each adapter's main()
before dispatch.
"""

from __future__ import annotations

from soma.hooks import common as hc


class TestAgentFamilyRouting:
    def test_default_family_is_cc(self, monkeypatch):
        monkeypatch.delenv("SOMA_AGENT_FAMILY", raising=False)
        aid = hc._get_session_agent_id()
        assert aid.startswith("cc-") or aid == "cc"

    def test_cursor_family_overrides_default(self, monkeypatch):
        monkeypatch.setenv("SOMA_AGENT_FAMILY", "cursor")
        aid = hc._get_session_agent_id()
        assert aid.startswith("cursor-") or aid == "cursor"
        assert "cc-" not in aid

    def test_windsurf_family_overrides_default(self, monkeypatch):
        monkeypatch.setenv("SOMA_AGENT_FAMILY", "windsurf")
        aid = hc._get_session_agent_id()
        assert aid.startswith("windsurf-") or aid == "windsurf"

    def test_calibration_family_extracts_correctly(self, monkeypatch):
        from soma.calibration import calibration_family
        monkeypatch.setenv("SOMA_AGENT_FAMILY", "cursor")
        aid = hc._get_session_agent_id()
        assert calibration_family(aid) == "cursor"

    def test_cursor_main_sets_family(self, monkeypatch):
        """cursor.main() must set SOMA_AGENT_FAMILY=cursor BEFORE
        dispatch — verified by inspecting the source string (no need
        to actually invoke main which reads stdin)."""
        import inspect
        from soma.hooks import cursor
        src = inspect.getsource(cursor.main)
        assert 'SOMA_AGENT_FAMILY' in src
        assert '"cursor"' in src

    def test_windsurf_main_sets_family(self, monkeypatch):
        import inspect
        from soma.hooks import windsurf
        src = inspect.getsource(windsurf.main)
        assert 'SOMA_AGENT_FAMILY' in src
        assert '"windsurf"' in src
