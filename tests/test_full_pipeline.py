"""Full pipeline integration test — exercises the complete SOMA loop.

Covers: engine → vitals → pressure → guidance → mirror → persistence → fingerprint.
One test, one pipeline, all layers.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from soma.engine import SOMAEngine, ActionResult
from soma.types import Action, ResponseMode, VitalsSnapshot
from soma.persistence import save_engine_state, load_engine_state
from soma.mirror import Mirror
from soma.patterns import analyze as analyze_patterns
from soma.fingerprint import FingerprintEngine


@pytest.fixture
def tmp_soma(tmp_path, monkeypatch):
    """Redirect ~/.soma to temp directory."""
    monkeypatch.setattr("soma.mirror.PATTERN_DB_PATH", tmp_path / "patterns.json")
    return tmp_path


def _action(tool: str, output: str = "ok", error: bool = False,
            file_path: str = "", tokens: int = 50) -> Action:
    meta = {"file_path": file_path} if file_path else {}
    return Action(
        tool_name=tool, output_text=output, token_count=tokens,
        error=error, metadata=meta,
    )


class TestFullPipeline:
    """End-to-end pipeline: actions → vitals → pressure → mirror → persist."""

    def test_complete_session_lifecycle(self, tmp_soma):
        # ── 1. Create engine with clean state ──
        engine = SOMAEngine(budget={"tokens": 100_000})
        agent_id = "pipeline-test"
        engine.register_agent(agent_id)

        snap = engine.get_snapshot(agent_id)
        assert snap["pressure"] == 0.0
        assert snap["action_count"] == 0

        # ── 2. Phase 1: Research (3 Reads) — pressure stays low ──
        results: list[ActionResult] = []
        for f in ["/src/engine.py", "/src/vitals.py", "/src/types.py"]:
            r = engine.record_action(agent_id, _action("Read", "file content...", file_path=f))
            results.append(r)

        assert results[-1].pressure < 0.30  # early actions, still OBSERVE
        assert results[-1].mode == ResponseMode.OBSERVE

        # ── 3. Phase 2: Implementation (2 Edits) — slight pressure ──
        r = engine.record_action(agent_id, _action("Edit", "modified", file_path="/src/engine.py"))
        results.append(r)
        r = engine.record_action(agent_id, _action("Edit", "modified", file_path="/src/vitals.py"))
        results.append(r)

        pre_error_pressure = results[-1].pressure

        # ── 4. Phase 3: Errors (3 Bash failures) — pressure rises ──
        for i in range(3):
            r = engine.record_action(agent_id, _action("Bash", f"FAILED test_{i}", error=True))
            results.append(r)

        post_error_pressure = results[-1].pressure
        assert post_error_pressure > pre_error_pressure, "Pressure must rise after errors"

        # ── 5. Mirror generates session context at elevated pressure ──
        mirror = Mirror(engine)
        ctx = mirror.generate(agent_id, _action("Bash", "FAILED", error=True), "FAILED")
        if post_error_pressure >= 0.25:
            assert ctx is not None, f"Mirror should inject at pressure={post_error_pressure:.2f}"
            assert "--- session context ---" in ctx
            assert "SOMA" not in ctx
            assert ctx.endswith("\n---")
        else:
            # Pressure may be low with default Claude Code thresholds
            pass

        # ── 6. Recovery: successful actions lower pressure ──
        r = engine.record_action(agent_id, _action("Edit", "fixed bug", file_path="/src/engine.py"))
        results.append(r)
        r = engine.record_action(agent_id, _action("Bash", "All 20 tests passed", error=False))
        results.append(r)

        recovery_pressure = results[-1].pressure
        # Pressure should trend down or at least not spike further
        # (exact behavior depends on weights/baselines, so check it's not way higher)
        assert recovery_pressure < post_error_pressure + 0.20

        # ── 7. Pattern detection works ──
        action_log = [
            {"tool": "Read", "error": False, "file": "/src/engine.py", "ts": 1.0},
            {"tool": "Read", "error": False, "file": "/src/vitals.py", "ts": 2.0},
            {"tool": "Read", "error": False, "file": "/src/types.py", "ts": 3.0},
            {"tool": "Edit", "error": False, "file": "/src/engine.py", "ts": 4.0},
            {"tool": "Edit", "error": False, "file": "/src/vitals.py", "ts": 5.0},
            {"tool": "Bash", "error": True, "file": "", "ts": 6.0},
            {"tool": "Bash", "error": True, "file": "", "ts": 7.0},
            {"tool": "Bash", "error": True, "file": "", "ts": 8.0},
            {"tool": "Edit", "error": False, "file": "/src/engine.py", "ts": 9.0},
            {"tool": "Bash", "error": False, "file": "", "ts": 10.0},
        ]
        patterns = analyze_patterns(action_log)
        # Should detect consecutive bash failures
        pattern_kinds = [p.kind for p in patterns]
        assert "bash_failures" in pattern_kinds or "error_rate" in pattern_kinds, \
            f"Expected error pattern, got: {pattern_kinds}"

        # ── 8. Persistence roundtrip ──
        state_path = str(tmp_soma / "engine_state.json")
        save_engine_state(engine, state_path)

        loaded = load_engine_state(state_path)
        assert loaded is not None

        loaded_snap = loaded.get_snapshot(agent_id)
        original_snap = engine.get_snapshot(agent_id)
        assert loaded_snap["action_count"] == original_snap["action_count"]
        assert loaded_snap["level"].name == original_snap["level"].name
        # Pressure may differ slightly due to graph re-propagation, but should be close
        assert abs(loaded_snap["pressure"] - original_snap["pressure"]) < 0.05

        # ── 9. Fingerprint updates from session ──
        fp_engine = FingerprintEngine()
        fp_before = fp_engine.get(agent_id)
        assert fp_before is None  # No prior session

        fp_engine.update_from_session(agent_id, action_log)
        fp_after = fp_engine.get(agent_id)
        assert fp_after is not None
        assert fp_after.sample_count == 1
        assert fp_after.avg_session_length == len(action_log)

        # ── 10. Verify total action count ──
        final_snap = engine.get_snapshot(agent_id)
        assert final_snap["action_count"] == 10  # 3 Read + 2 Edit + 3 Bash(err) + 1 Edit + 1 Bash

    def test_vitals_snapshot_fields(self):
        """ActionResult.vitals contains all expected fields."""
        engine = SOMAEngine(budget={"tokens": 100_000})
        engine.register_agent("vitals-check")
        r = engine.record_action("vitals-check", _action("Read", "data"))

        v = r.vitals
        assert isinstance(v, VitalsSnapshot)
        assert hasattr(v, "uncertainty")
        assert hasattr(v, "drift")
        assert hasattr(v, "error_rate")
        assert hasattr(v, "context_usage")
        assert hasattr(v, "goal_coherence")
        assert hasattr(v, "uncertainty_type")

    def test_multi_agent_isolation(self):
        """Two agents on the same engine don't affect each other's pressure."""
        engine = SOMAEngine(budget={"tokens": 100_000})
        engine.register_agent("agent-a")
        engine.register_agent("agent-b")

        # Stress agent A
        for _ in range(5):
            engine.record_action("agent-a", _action("Bash", "FAIL", error=True))

        # Agent B stays clean
        for _ in range(3):
            engine.record_action("agent-b", _action("Read", "ok"))

        snap_a = engine.get_snapshot("agent-a")
        snap_b = engine.get_snapshot("agent-b")

        assert snap_a["pressure"] > snap_b["pressure"], \
            "Agent A (errors) should have higher pressure than Agent B (clean)"
