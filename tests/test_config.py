"""Tests for config migration — old threshold keys to new names."""

import tomli_w

from soma.cli.config_loader import migrate_config, load_config, create_engine_from_config


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


class TestLoadConfigIsolation:
    def test_default_config_not_mutated_by_caller(self):
        """Mutating the returned config should not corrupt DEFAULT_CONFIG."""
        from soma.cli.config_loader import DEFAULT_CONFIG
        original_tokens = DEFAULT_CONFIG["budget"]["tokens"]

        c1 = load_config("nonexistent_file.toml")
        c1["budget"]["tokens"] = 999999

        c2 = load_config("nonexistent_file.toml")
        assert c2["budget"]["tokens"] == original_tokens
        assert DEFAULT_CONFIG["budget"]["tokens"] == original_tokens


class TestMigrationEndToEnd:
    def test_load_config_with_old_keys_returns_new(self, tmp_path):
        """load_config auto-migrates old threshold keys."""
        old_config = {
            "thresholds": {"caution": 0.35, "degrade": 0.55, "quarantine": 0.75, "restart": 0.90},
            "budget": {"tokens": 100000},
        }
        path = str(tmp_path / "soma.toml")
        with open(path, "wb") as f:
            tomli_w.dump(old_config, f)

        result = load_config(path)
        assert "guide" in result["thresholds"]
        assert "caution" not in result["thresholds"]
        assert "restart" not in result["thresholds"]
        assert result["thresholds"]["guide"] == 0.35

    def test_engine_from_migrated_config(self, tmp_path):
        """Engine created from migrated config uses new threshold keys."""
        old_config = {
            "thresholds": {"caution": 0.35, "degrade": 0.55, "quarantine": 0.75, "restart": 0.90},
            "budget": {"tokens": 100000},
        }
        path = str(tmp_path / "soma.toml")
        with open(path, "wb") as f:
            tomli_w.dump(old_config, f)

        config = load_config(path)
        engine = create_engine_from_config(config)
        assert engine._custom_thresholds["guide"] == 0.35
        assert "caution" not in engine._custom_thresholds
