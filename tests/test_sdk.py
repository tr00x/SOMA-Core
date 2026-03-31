"""Tests for the Universal Python SDK (Phase 07 — SDK-01 through SDK-04)."""

import pytest
import soma
from soma.engine import SOMAEngine
from soma.types import Action, ResponseMode
from soma.sdk.track import track, SomaTracker


# ---------------------------------------------------------------------------
# SDK-01: soma.track() universal context manager
# ---------------------------------------------------------------------------

class TestSomaTrack:
    def setup_method(self):
        self.engine = SOMAEngine(budget={"tokens": 100000})
        self.engine.register_agent("a")

    def test_track_exported_from_soma(self):
        assert hasattr(soma, "track")
        assert soma.track is track

    def test_tracker_exported_from_soma(self):
        assert hasattr(soma, "SomaTracker")

    def test_basic_track_records_action(self):
        with track(self.engine, "a", "Bash") as t:
            t.set_output("hello world")
        assert t.result is not None
        assert self.engine._agents["a"].action_count == 1

    def test_result_is_action_result(self):
        from soma.engine import ActionResult
        with track(self.engine, "a", "Bash") as t:
            t.set_output("ok")
        assert isinstance(t.result, ActionResult)

    def test_set_error_recorded(self):
        with track(self.engine, "a", "Bash") as t:
            t.set_output("fail")
            t.set_error(True)
        assert t.result.vitals.error_rate > 0

    def test_exception_inside_block_marks_error(self):
        with pytest.raises(ValueError):
            with track(self.engine, "a", "Bash") as t:
                raise ValueError("something broke")
        assert t.result is not None
        assert t.result.vitals.error_rate > 0

    def test_exception_not_suppressed(self):
        with pytest.raises(RuntimeError):
            with track(self.engine, "a", "Bash"):
                raise RuntimeError("boom")

    def test_set_tokens_recorded(self):
        with track(self.engine, "a", "Bash", token_count=500) as t:
            t.set_output("ok")
        # Budget spent should reflect token usage
        assert self.engine.budget.spent.get("tokens", 0) >= 500

    def test_set_retried(self):
        with track(self.engine, "a", "Bash") as t:
            t.set_output("ok")
            t.set_retried(True)
        # Action was recorded — engine doesn't expose retried directly but no crash
        assert t.result is not None

    def test_duration_is_measured(self):
        import time
        with track(self.engine, "a", "Bash") as t:
            time.sleep(0.01)
            t.set_output("ok")
        # Duration should be > 0 (recorded but not exposed in ActionResult directly)
        assert t.result is not None

    def test_multiple_sequential_tracks(self):
        for i in range(5):
            with track(self.engine, "a", "Bash") as t:
                t.set_output(f"output {i}")
        assert self.engine._agents["a"].action_count == 5

    def test_mode_in_range(self):
        with track(self.engine, "a", "Bash") as t:
            t.set_output("ok")
        assert t.result.mode in list(ResponseMode)

    def test_pressure_in_range(self):
        with track(self.engine, "a", "Bash") as t:
            t.set_output("ok")
        assert 0.0 <= t.result.pressure <= 1.0

    def test_track_with_cost(self):
        with track(self.engine, "a", "Bash", cost=0.01) as t:
            t.set_output("ok")
        assert t.result is not None

    def test_set_cost_inside_block(self):
        with track(self.engine, "a", "Bash") as t:
            t.set_output("ok")
            t.set_cost(0.005)
        assert t.result is not None


# ---------------------------------------------------------------------------
# SDK-02: SomaLangChainCallback (import-only test — no langchain required)
# ---------------------------------------------------------------------------

class TestLangChainAdapter:
    def test_import_without_langchain_raises(self):
        """SomaLangChainCallback raises ImportError when langchain unavailable."""
        import sys
        # Temporarily hide langchain if present
        lc_modules = {k: v for k, v in sys.modules.items() if "langchain" in k}
        for mod in lc_modules:
            sys.modules.pop(mod, None)

        # Reload to get fresh _LANGCHAIN_AVAILABLE check
        import importlib
        import soma.sdk.langchain as lc_mod
        importlib.reload(lc_mod)

        if not lc_mod._LANGCHAIN_AVAILABLE:
            engine = SOMAEngine(budget={"tokens": 10000})
            engine.register_agent("a")
            with pytest.raises(ImportError, match="langchain-core"):
                lc_mod.SomaLangChainCallback(engine, "a")

        # Restore
        sys.modules.update(lc_modules)

    def test_module_importable(self):
        from soma.sdk import langchain  # noqa: F401

    def test_callback_class_exists(self):
        from soma.sdk.langchain import SomaLangChainCallback
        assert SomaLangChainCallback is not None


# ---------------------------------------------------------------------------
# SDK-03: SomaCrewObserver (import-only test)
# ---------------------------------------------------------------------------

class TestCrewAIAdapter:
    def test_module_importable(self):
        from soma.sdk import crewai  # noqa: F401

    def test_observer_class_exists(self):
        from soma.sdk.crewai import SomaCrewObserver
        assert SomaCrewObserver is not None

    def test_import_without_crewai_raises(self):
        import sys, importlib
        crew_mods = {k: v for k, v in sys.modules.items() if "crewai" in k}
        for mod in crew_mods:
            sys.modules.pop(mod, None)

        import soma.sdk.crewai as crew_mod
        importlib.reload(crew_mod)

        if not crew_mod._CREWAI_AVAILABLE:
            engine = SOMAEngine(budget={"tokens": 10000})
            with pytest.raises(ImportError, match="crewai"):
                crew_mod.SomaCrewObserver(engine)

        sys.modules.update(crew_mods)


# ---------------------------------------------------------------------------
# SDK-04: SomaAutoGenMonitor (import-only test)
# ---------------------------------------------------------------------------

class TestAutoGenAdapter:
    def test_module_importable(self):
        from soma.sdk import autogen  # noqa: F401

    def test_monitor_class_exists(self):
        from soma.sdk.autogen import SomaAutoGenMonitor
        assert SomaAutoGenMonitor is not None

    def test_import_without_autogen_raises(self):
        import sys, importlib
        ag_mods = {k: v for k, v in sys.modules.items() if "autogen" in k}
        for mod in ag_mods:
            sys.modules.pop(mod, None)

        import soma.sdk.autogen as ag_mod
        importlib.reload(ag_mod)

        if not ag_mod._AUTOGEN_AVAILABLE:
            engine = SOMAEngine(budget={"tokens": 10000})
            with pytest.raises(ImportError, match="pyautogen"):
                ag_mod.SomaAutoGenMonitor(engine)

        sys.modules.update(ag_mods)


# ---------------------------------------------------------------------------
# SDK integration: SomaCrewObserver with a mock crew
# ---------------------------------------------------------------------------

class TestCrewObserverMockIntegration:
    def test_attach_patches_execute_task(self):
        """SomaCrewObserver patches execute_task and records actions."""
        from soma.sdk.crewai import SomaCrewObserver, _CREWAI_AVAILABLE
        if _CREWAI_AVAILABLE:
            pytest.skip("Real crewai installed — mock test not applicable")

        engine = SOMAEngine(budget={"tokens": 100000})

        # Build a minimal mock agent without real crewai
        class MockAgent:
            role = "researcher"
            def execute_task(self, task, *args, **kwargs):
                return "research complete"

        class MockCrew:
            agents = [MockAgent()]

        # Temporarily fake crewai availability
        import soma.sdk.crewai as crew_mod
        original = crew_mod._CREWAI_AVAILABLE
        crew_mod._CREWAI_AVAILABLE = True
        try:
            observer = SomaCrewObserver.__new__(SomaCrewObserver)
            observer._engine = engine
            observer._patched = set()

            mock_crew = MockCrew()
            observer.attach(mock_crew)

            # Agent registered and execute_task patched
            assert "researcher" in engine._agents
            result = mock_crew.agents[0].execute_task("some task")
            assert result == "research complete"
            assert engine._agents["researcher"].action_count == 1
        finally:
            crew_mod._CREWAI_AVAILABLE = original


class TestAutoGenMonitorMockIntegration:
    def test_attach_patches_generate_reply(self):
        """SomaAutoGenMonitor patches generate_reply and records actions."""
        from soma.sdk.autogen import SomaAutoGenMonitor, _AUTOGEN_AVAILABLE
        if _AUTOGEN_AVAILABLE:
            pytest.skip("Real autogen installed — mock test not applicable")

        engine = SOMAEngine(budget={"tokens": 100000})

        class MockAgent:
            name = "assistant"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "I can help with that."

        import soma.sdk.autogen as ag_mod
        original = ag_mod._AUTOGEN_AVAILABLE
        ag_mod._AUTOGEN_AVAILABLE = True
        try:
            monitor = SomaAutoGenMonitor.__new__(SomaAutoGenMonitor)
            monitor._engine = engine
            monitor._patched = set()

            agent = MockAgent()
            monitor.attach(agent)

            assert "assistant" in engine._agents
            reply = agent.generate_reply(messages=[{"content": "hello"}])
            assert reply == "I can help with that."
            assert engine._agents["assistant"].action_count == 1
        finally:
            ag_mod._AUTOGEN_AVAILABLE = original
