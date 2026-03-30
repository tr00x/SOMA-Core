"""Tests for config migration — old threshold keys to new names."""

from soma.cli.config_loader import migrate_config


class TestConfigMigration:
    def test_old_keys_migrated(self):
        old = {"thresholds": {"caution": 0.40, "degrade": 0.60, "quarantine": 0.80, "restart": 0.95}}
        result = migrate_config(old)
        assert result["thresholds"] == {"guide": 0.40, "warn": 0.60, "block": 0.80}
        assert "caution" not in result["thresholds"]
        assert "restart" not in result["thresholds"]

    def test_new_keys_untouched(self):
        new = {"thresholds": {"guide": 0.30, "warn": 0.55, "block": 0.80}}
        result = migrate_config(new)
        assert result["thresholds"] == {"guide": 0.30, "warn": 0.55, "block": 0.80}

    def test_empty_config(self):
        result = migrate_config({})
        assert "thresholds" not in result  # don't add what wasn't there

    def test_mixed_keys(self):
        """Config with some old and some new keys — migrate old, keep new."""
        mixed = {"thresholds": {"guide": 0.30, "degrade": 0.60, "quarantine": 0.80}}
        result = migrate_config(mixed)
        assert result["thresholds"] == {"guide": 0.30, "warn": 0.60, "block": 0.80}

    def test_preserves_other_sections(self):
        config = {
            "thresholds": {"caution": 0.40, "degrade": 0.60, "quarantine": 0.80},
            "weights": {"uncertainty": 1.2},
            "budget": {"tokens": 100000},
        }
        result = migrate_config(config)
        assert result["weights"] == {"uncertainty": 1.2}
        assert result["budget"] == {"tokens": 100000}
