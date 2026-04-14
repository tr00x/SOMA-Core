"""Test SOMA mode presets."""
from soma.cli.config_loader import MODE_PRESETS, apply_mode


def test_mode_presets_exist():
    assert "strict" in MODE_PRESETS
    assert "relaxed" in MODE_PRESETS
    assert "autonomous" in MODE_PRESETS


def test_strict_mode_values():
    m = MODE_PRESETS["strict"]
    assert m["agents"]["claude-code"]["autonomy"] == "human_in_the_loop"
    assert m["thresholds"]["guide"] == 0.20
    assert m["thresholds"]["block"] == 0.60
    assert m["hooks"]["verbosity"] == "verbose"


def test_relaxed_mode_values():
    m = MODE_PRESETS["relaxed"]
    assert m["agents"]["claude-code"]["autonomy"] == "human_on_the_loop"
    assert m["thresholds"]["guide"] == 0.35
    assert m["thresholds"]["block"] == 0.70
    assert m["hooks"]["verbosity"] == "normal"


def test_autonomous_mode_values():
    m = MODE_PRESETS["autonomous"]
    assert m["agents"]["claude-code"]["autonomy"] == "fully_autonomous"
    assert m["thresholds"]["guide"] == 0.60
    assert m["thresholds"]["block"] == 0.95
    assert m["hooks"]["quality"] is False
    assert m["hooks"]["verbosity"] == "minimal"


def test_apply_mode_merges():
    from soma.cli.config_loader import CLAUDE_CODE_CONFIG
    import copy
    base = copy.deepcopy(CLAUDE_CODE_CONFIG)
    result = apply_mode(base, "strict")
    assert result["thresholds"]["guide"] == 0.20
    # Original keys that aren't in the preset stay untouched
    assert "weights" in result
