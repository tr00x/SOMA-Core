"""Tests for SOMA setup wizard — sensitivity presets."""

from soma.cli.wizard import get_sensitivity_thresholds


def test_sensitivity_aggressive():
    thresholds = get_sensitivity_thresholds("aggressive")
    assert thresholds["guide"] == 0.15
    assert thresholds["warn"] == 0.35
    assert thresholds["block"] == 0.55


def test_sensitivity_balanced():
    thresholds = get_sensitivity_thresholds("balanced")
    assert thresholds["guide"] == 0.25
    assert thresholds["warn"] == 0.50
    assert thresholds["block"] == 0.75


def test_sensitivity_relaxed():
    thresholds = get_sensitivity_thresholds("relaxed")
    assert thresholds["guide"] == 0.35
    assert thresholds["warn"] == 0.60
    assert thresholds["block"] == 0.85


def test_sensitivity_all_presets_have_required_keys():
    required = {"guide", "warn", "block"}
    for name in ("aggressive", "balanced", "relaxed"):
        thresholds = get_sensitivity_thresholds(name)
        assert required == set(thresholds.keys()), (
            f"Preset '{name}' is missing keys"
        )


def test_sensitivity_thresholds_are_ordered():
    """For every preset, thresholds must be monotonically increasing."""
    for name in ("aggressive", "balanced", "relaxed"):
        t = get_sensitivity_thresholds(name)
        values = [t["guide"], t["warn"], t["block"]]
        assert values == sorted(values), (
            f"Preset '{name}' thresholds are not in ascending order: {values}"
        )
