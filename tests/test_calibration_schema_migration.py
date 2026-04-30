"""
Regression for v2026.6.x fix #30 — CalibrationProfile.from_dict
must handle schema_version mismatches gracefully:

- Equal version: load normally.
- Older version: walk registered migrators up to current version.
- Newer version: refuse to misinterpret, return default profile.
"""
from __future__ import annotations

from soma.calibration import (
    CalibrationProfile,
    SCHEMA_VERSION,
    _SCHEMA_MIGRATORS,
)


def _base_dict(**overrides):
    base = {
        "family": "cc",
        "action_count": 50,
        "phase": "calibrated",
        "drift_p25": 0.0, "drift_p75": 0.5,
        "entropy_p25": 0.0, "entropy_p75": 1.0,
        "typical_error_burst": 1, "typical_retry_burst": 1,
        "typical_success_rate": 0.9,
        "silenced_patterns": [], "last_silence_check_action": 0,
        "pattern_precision_cache": {},
        "refuted_patterns": [], "last_refuted_check_action": 0,
        "validated_patterns": [],
        "created_at": 0.0, "updated_at": 0.0,
        "schema_version": SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


def test_current_version_loads_normally():
    p = CalibrationProfile.from_dict(_base_dict())
    assert p.family == "cc"
    assert p.action_count == 50


def test_future_version_returns_defaults():
    """A profile written by a newer SOMA than this build must NOT be
    silently misinterpreted. We return a fresh default profile so the
    caller proceeds safely; the on-disk file is untouched (caller is
    not asked to overwrite)."""
    future_data = _base_dict(schema_version=SCHEMA_VERSION + 5, family="cc")
    p = CalibrationProfile.from_dict(future_data)
    # Coerced to defaults — but family is preserved so the caller's
    # path-keyed lookup still has the right slot.
    assert p.family == "cc"
    assert p.action_count == 0  # default, NOT 50 from the future-version dict


def test_older_version_walks_migrator_chain(monkeypatch):
    """Plant a fake v0→v1 migrator, simulate a v0 profile, and verify
    the migrator runs."""
    calls = {"n": 0}

    def fake_v0_to_v1(d: dict) -> dict:
        calls["n"] += 1
        d = dict(d)
        d["schema_version"] = 1
        # Pretend v0 didn't have action_count yet — migrator backfills.
        d["action_count"] = 999
        return d

    # Register temporarily.
    monkeypatch.setitem(_SCHEMA_MIGRATORS, 0, fake_v0_to_v1)

    v0_data = _base_dict(schema_version=0)
    v0_data.pop("action_count")
    p = CalibrationProfile.from_dict(v0_data)

    assert calls["n"] == 1
    assert p.action_count == 999


def test_missing_migrator_falls_through():
    """If we're at v3 but nobody registered v0→v1, from_dict must not
    crash — it falls through and lets the dataclass dropper handle
    unknown fields."""
    # No migrators registered for v-1. Construct pre-v0 data.
    bad_data = _base_dict(schema_version=-1)
    # Should NOT raise.
    p = CalibrationProfile.from_dict(bad_data)
    # Old fields still loaded.
    assert p.family == "cc"


def test_v1_to_v2_strips_resurrected_patterns_from_silenced():
    """Resurrected 2026-04-30: a v1 profile that auto-silenced or
    auto-refuted any of {_stats, drift, entropy_drop, context} under
    the old behavior must NOT carry that state forward — otherwise
    ``evaluate()`` would silently drop the resurrected candidates and
    the resurrection would ship dead-on-arrival.
    """
    v1_data = _base_dict(
        schema_version=1,
        silenced_patterns=["entropy_drop", "blind_edit", "context"],
        refuted_patterns=["drift", "_stats"],
        validated_patterns=["bash_retry", "context"],
    )
    p = CalibrationProfile.from_dict(v1_data)
    assert p.schema_version == 2
    # Resurrected keys stripped, foreign keys preserved.
    assert "entropy_drop" not in p.silenced_patterns
    assert "context" not in p.silenced_patterns
    assert "blind_edit" in p.silenced_patterns
    assert "drift" not in p.refuted_patterns
    assert "_stats" not in p.refuted_patterns
    assert "context" not in p.validated_patterns
    assert "bash_retry" in p.validated_patterns


def test_v1_to_v2_no_op_when_lists_already_clean():
    """Profiles that never silenced/refuted resurrected patterns get
    upgraded with empty migrations — no field corruption."""
    v1_data = _base_dict(
        schema_version=1,
        silenced_patterns=["blind_edit"],
        refuted_patterns=[],
        validated_patterns=["bash_retry"],
    )
    p = CalibrationProfile.from_dict(v1_data)
    assert p.schema_version == 2
    assert p.silenced_patterns == ["blind_edit"]
    assert p.refuted_patterns == []
    assert p.validated_patterns == ["bash_retry"]
