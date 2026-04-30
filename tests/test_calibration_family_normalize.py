"""
Regression for v2026.6.x fix #19 — calibration_family() must collapse
'claude-code' (the CLI default agent_id) into 'cc' (the hook session
prefix). Otherwise the user ends up with two profile files for the
same conceptual agent: ~/.soma/calibration_cc.json (from hook
sessions) and ~/.soma/calibration_claude-code.json (from `soma reset`
or other CLI commands using the literal default).
"""
from __future__ import annotations

from soma.calibration import calibration_family


def test_claude_code_literal_collapses_to_cc() -> None:
    """The CLI default 'claude-code' must merge with the hook 'cc-N' family."""
    assert calibration_family("claude-code") == "cc", (
        "calibration_family('claude-code') should return 'cc' so CLI- and "
        "hook-derived agent ids share the same calibration profile"
    )


def test_session_style_ids_still_collapse_to_cc() -> None:
    """Sanity — the existing numeric-tail strip is unchanged."""
    assert calibration_family("cc-12345") == "cc"
    assert calibration_family("cc-99") == "cc"


def test_other_known_alias_collapses() -> None:
    """If we add 'claude' as an alias too, it should also collapse."""
    # Currently only claude-code is aliased; this test pins that
    # 'claude' (without -code) does NOT auto-collapse — explicit
    # alias only.
    assert calibration_family("claude") == "claude"


def test_unrelated_ids_kept_intact() -> None:
    """User-chosen agent ids without a numeric tail must not be merged."""
    assert calibration_family("my-custom-bot") == "my-custom-bot"
    assert calibration_family("swe-bench") == "swe-bench"
    assert calibration_family("swe-bench-48") == "swe-bench"


def test_empty_falls_back_to_default() -> None:
    assert calibration_family("") == "default"


def test_legacy_calibration_file_migrated_on_load(tmp_path, monkeypatch) -> None:
    """Users with calibration_claude-code.json from before the alias
    must not lose accumulated calibration. load_profile renames the
    stale file into place on first hit."""
    import json

    monkeypatch.setattr("soma.calibration.SOMA_DIR", tmp_path)

    # Plant a legacy file under the pre-alias name with non-default state.
    legacy = tmp_path / "calibration_claude-code.json"
    legacy.write_text(json.dumps({
        "family": "claude-code",
        "action_count": 250,
        "phase": "calibrated",
        "drift_p25": 0.1, "drift_p75": 0.5,
        "entropy_p25": 0.0, "entropy_p75": 1.0,
        "typical_error_burst": 1, "typical_retry_burst": 1,
        "typical_success_rate": 0.9,
        "silenced_patterns": [], "last_silence_check_action": 0,
        "pattern_precision_cache": {},
        "refuted_patterns": [], "last_refuted_check_action": 0,
        "validated_patterns": [],
        "created_at": 0.0, "updated_at": 0.0,
        "schema_version": 1,
    }))

    from soma.calibration import load_profile, save_profile
    profile = load_profile("cc-12345")

    # Family is COERCED to the canonical alias target after migration.
    # Otherwise the next save_profile would re-create the legacy
    # calibration_claude-code.json file we just migrated away from.
    assert profile.family == "cc"
    # action_count survived the rename — 250, not 0.
    assert profile.action_count == 250
    # File now lives at the canonical path.
    assert (tmp_path / "calibration_cc.json").exists()
    assert not legacy.exists()

    # Sanity: saving the profile back lands on calibration_cc.json,
    # not calibration_claude-code.json — migration is durable.
    save_profile(profile)
    assert (tmp_path / "calibration_cc.json").exists()
    assert not (tmp_path / "calibration_claude-code.json").exists()


def test_alias_applies_after_regex_strip(tmp_path, monkeypatch) -> None:
    """A wrapper sending agent_id='claude-code-12345' (numeric tail)
    must collapse via the regex AND alias map together: regex strips
    tail → 'claude-code', alias maps → 'cc'. Otherwise the same bug
    class re-opens for any future wrapper that adds a numeric suffix
    to the literal id."""
    assert calibration_family("claude-code-12345") == "cc"
    assert calibration_family("claude-code-1") == "cc"
    assert calibration_family("claude-code_77") == "cc"
