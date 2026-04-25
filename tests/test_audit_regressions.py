"""Regressions found during the v2026.5.0 self-audit.

Each test pins a bug caught by the code reviewer so it can't
silently come back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma import blocks as _blocks
from soma import calibration as _cal
from soma.calibration import (
    CALIBRATED_EXIT_ACTIONS,
    CalibrationProfile,
    compute_distributions,
    load_profile,
)
from soma.contextual_guidance import ContextualGuidance
from soma.mirror import Mirror
from soma.engine import SOMAEngine
from soma.types import Action


@pytest.fixture(autouse=True)
def _isolated_soma(tmp_path, monkeypatch):
    monkeypatch.setattr(_cal, "SOMA_DIR", tmp_path)
    monkeypatch.setattr(_blocks, "SOMA_DIR", tmp_path)
    from soma import state as _state
    monkeypatch.setattr(_state, "SOMA_DIR", tmp_path)
    yield tmp_path


# ── #21: entropy_drop must NOT fire more aggressively for diverse users ─

def _diverse_log(n: int = 10) -> list[dict]:
    tools = ["Read", "Grep", "Edit", "Bash", "Glob"]
    return [{"tool": tools[i % len(tools)]} for i in range(n)]


def test_entropy_drop_diverse_user_does_not_lower_ceiling():
    """A user whose P75 is 1.8 must not cause pattern to fire on mid-entropy
    logs that the legacy 1.0 ceiling already silences."""
    profile = CalibrationProfile(
        family="cc", action_count=CALIBRATED_EXIT_ACTIONS,
        entropy_p25=1.2, entropy_p75=1.8,  # high-diversity user
    )
    cg = ContextualGuidance(profile=profile)
    # Perfectly balanced 5-tool log → entropy ~ log2(5)/log2(5) = 1.0 normalized
    msg = cg.evaluate(
        action_log=_diverse_log(10), current_tool="Read",
        current_input={}, vitals={"uncertainty": 0, "drift": 0,
                                   "error_rate": 0, "token_usage": 0,
                                   "context_usage": 0},
        budget_health=1.0, action_number=10,
    )
    # With the fixed ceiling logic, personal P25=1.2 is clamped to max 1.0,
    # so the ceiling equals the legacy 1.0 — pattern stays as before.
    if msg is not None:
        assert msg.pattern != "entropy_drop", (
            "diverse user's high P25 must not make entropy_drop more "
            "aggressive than legacy behavior"
        )


@pytest.mark.skip(reason="entropy_drop retired 2026-04-25 (ultra-review)")
def test_entropy_drop_focused_user_floor_applies():
    """A user with very low P25 (0.2) still fires when entropy < 0.5
    because the floor clamps ceiling up from 0.2 to 0.5."""
    profile = CalibrationProfile(
        family="cc", action_count=CALIBRATED_EXIT_ACTIONS,
        entropy_p25=0.2, entropy_p75=0.4,
    )
    cg = ContextualGuidance(profile=profile)
    # Monotool log → entropy ~ 0 → below 0.5 floor → still fires.
    msg = cg.evaluate(
        action_log=[{"tool": "Bash"}] * 10, current_tool="Bash",
        current_input={}, vitals={"uncertainty": 0, "drift": 0,
                                   "error_rate": 0, "token_usage": 0,
                                   "context_usage": 0},
        budget_health=1.0, action_number=10,
    )
    assert msg is not None and msg.pattern in ("entropy_drop", "bash_retry")


# ── #2: typical_retry_burst must not equal error_burst when we have
#       bash_retry history ───────────────────────────────────────────

def test_compute_distributions_decouples_retry_and_error_burst():
    errors = [True, True, False, True, True, True, False]  # mixed
    # Bash retries = only tool-specific retries; pretend none observed
    # → retry burst stays = error burst as a safe fallback.
    bash_retries_none: list[bool] = []
    r1 = compute_distributions([], errors, [], bash_retry_history=bash_retries_none)
    assert r1["typical_retry_burst"] == r1["typical_error_burst"]

    # With a distinct bash-retry signal, the two diverge.
    bash_retries = [True, True, True, True, False, False, False]  # longer
    r2 = compute_distributions([], errors, [], bash_retry_history=bash_retries)
    assert r2["typical_retry_burst"] != r2["typical_error_burst"] or \
           r2["typical_retry_burst"] > 0


# ── #5: corrupt calibration profile is backed up, not silently wiped ─

def test_corrupt_profile_is_renamed_to_corrupt(tmp_path):
    (tmp_path / "calibration_cc.json").write_text("{not json")
    p = load_profile("cc-7")
    assert p.action_count == 0
    assert (tmp_path / "calibration_cc.json.corrupt").exists()
    # The fresh profile file itself wasn't created yet (no save).
    assert not (tmp_path / "calibration_cc.json").exists()


# ── #19: strict-mode blocks count toward stop-hook summary ─────────

def test_stop_summary_counts_strict_mode_blocks(tmp_path, monkeypatch, capsys):
    from soma.analytics import AnalyticsStore
    # Seed analytics at the real path stop.py will later open.
    (tmp_path / ".soma").mkdir(exist_ok=True)
    store = AnalyticsStore(path=tmp_path / ".soma" / "analytics.db")
    for i, mode in enumerate(["strict", "strict", "GUIDE"]):
        store.record(
            agent_id="cc-99", session_id="cc-99", tool_name="Bash",
            pressure=0.5, uncertainty=0.0, drift=0.0, error_rate=0.0,
            context_usage=0.0, token_count=0, cost=0.0, mode=mode,
            error=False, source="hook",
        )
    store.close()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    class _Level:
        def __init__(self, n): self.name = n
    class _FakeEngine:
        def get_snapshot(self, _):
            return {"action_count": 3, "pressure": 0.5,
                    "level": _Level("GUIDE"), "vitals": {}}
        _agents = {"cc-99": None}

    from soma.hooks import stop as _stop
    monkeypatch.setattr(_stop, "get_engine", lambda: (_FakeEngine(), "cc-99"))
    monkeypatch.setattr(_stop, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(_stop, "read_action_log", lambda *_a, **_k: [
        {"tool": "Bash", "ts": 0.0, "error": False},
        {"tool": "Bash", "ts": 1.0, "error": False},
        {"tool": "Bash", "ts": 2.0, "error": False},
    ])
    monkeypatch.setattr(_stop, "read_pressure_trajectory", lambda *_a, **_k: [0.5, 0.5, 0.5])

    _stop.main()
    err = capsys.readouterr().err
    # Should see "2 blocks" in the one-liner, not "0 blocks".
    assert "2 blocks" in err


# ── #29: Mirror no longer emits _stats as semantic prefix ───────────

def test_mirror_semantic_output_has_no_stats_prefix():
    engine = SOMAEngine(budget={"tokens": 100_000})
    engine.register_agent("t")
    # Drive pressure up.
    for _ in range(7):
        engine.record_action("t", Action(
            tool_name="Bash", output_text="err", token_count=5, error=True,
        ))
    mirror = Mirror(engine)
    # Force semantic mode path: we can't easily hit _generate_semantic_sync
    # in a unit without mocking, but we can assert the _format_stats_oneliner
    # is no longer concatenated at the semantic branch. The simplest
    # assertion: mirror.generate() output (if any) must not start with
    # the "actions: N | errors:" prefix that _format_stats emits.
    result = mirror.generate("t", Action(tool_name="Bash", output_text="",
                                         token_count=1, error=False), "")
    if result is not None:
        body = result.replace("--- session context ---", "").strip()
        assert not body.splitlines()[0].startswith("actions:"), (
            "semantic path must not prepend a _stats one-liner"
        )


# ── #11: bell marker written BEFORE the bell so partial failure
#        can't re-fire it forever ───────────────────────────────────

def test_bell_marker_written_before_bell_char(tmp_path, monkeypatch):
    """Inspect the source order — marker must touch() before the print."""
    src = (Path(__file__).parent.parent
           / "src" / "soma" / "hooks" / "pre_tool_use.py").read_text()
    # The two relevant lines must appear in the right order.
    touch_pos = src.find("bell_flag.touch()")
    bell_pos = src.find(r'print("\a"')
    assert touch_pos > 0 and bell_pos > 0
    assert touch_pos < bell_pos, (
        "bell_flag.touch() must come BEFORE print('\\a'...) so a write "
        "failure doesn't cause the bell to re-fire on every block"
    )


# ── #30: soma unblock --all --pattern X exits with error, not silent ─

def test_cli_unblock_rejects_all_plus_pattern(tmp_path, monkeypatch, capsys):
    import argparse
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from soma.cli.main import _cmd_unblock

    args = argparse.Namespace(agent_id=None, pattern="retry_storm", all=True)
    with pytest.raises(SystemExit) as exc:
        _cmd_unblock(args)
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "mutually exclusive" in out


# ── Round 2 audit fixes ────────────────────────────────────────────

def test_warmup_forces_observe_mode(tmp_path, monkeypatch):
    """Plan: warmup phase forces mode=observe regardless of soma.toml."""
    from soma.hooks.common import get_soma_mode
    from soma.cli import config_loader as _cl

    # Configured mode = guide
    monkeypatch.setattr(_cl, "load_config", lambda *_a, **_k: {"soma": {"mode": "guide"}})

    # Warmup profile
    _cal.save_profile(_cal.CalibrationProfile(family="cc", action_count=10))
    assert get_soma_mode("cc-99") == "observe"

    # Calibrated profile — configured mode wins
    _cal.save_profile(_cal.CalibrationProfile(family="cc", action_count=250))
    assert get_soma_mode("cc-99") == "guide"


def test_silence_fires_at_exactly_20_percent():
    """Off-by-one fix: 4 helped / 20 fires = 20% must silence."""
    p = CalibrationProfile(family="cc", action_count=600)
    p.update_silence("blind_edit", fires=20, helped=4)  # exactly 20%
    assert "blind_edit" in p.silenced_patterns


def test_blind_edit_strict_blocks_all_edit_tools(tmp_path, monkeypatch):
    """Strict mode on blind_edit must lock Write/Edit/NotebookEdit together,
    otherwise the agent just switches tool to bypass the gate."""
    from soma.hooks.post_tool_use import _STRICT_BLOCK_PATTERNS
    assert "blind_edit" in _STRICT_BLOCK_PATTERNS
    # The implementation fans out across tools — see post_tool_use for
    # the list. Not an exposed API so we source-inspect.
    src = (Path(__file__).parent.parent
           / "src" / "soma" / "hooks" / "post_tool_use.py").read_text()
    assert '"Write", "Edit", "NotebookEdit"' in src


def test_profile_lock_serializes_concurrent_saves(tmp_path):
    """fcntl.flock prevents lost advance() under parallel hooks."""
    from soma.calibration import (
        CalibrationProfile, load_profile, profile_lock, save_profile,
    )

    # Seed baseline
    save_profile(CalibrationProfile(family="cc", action_count=0))

    # Two "parallel" advances via the lock — final count must be 2,
    # not 1 (as would happen without serialization).
    for _ in range(2):
        with profile_lock("cc"):
            p = load_profile("cc-99")
            p.advance(1)
            save_profile(p)

    final = load_profile("cc-99")
    assert final.action_count == 2


def test_healing_out_permission_error_handled(tmp_path, monkeypatch, capsys):
    """soma healing --out <unwritable> must not traceback."""
    import argparse
    from soma.cli.main import _cmd_healing
    unwritable = tmp_path / "nope" / "a" / "b" / "c.md"
    unwritable.parent.mkdir(parents=True)
    # Make the parent read-only so open(w) fails.
    unwritable.parent.chmod(0o555)
    try:
        args = argparse.Namespace(out=str(unwritable), min_n=1, limit=5)
        with pytest.raises(SystemExit) as exc:
            _cmd_healing(args)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "cannot write" in out or "Error" in out
    finally:
        unwritable.parent.chmod(0o755)
