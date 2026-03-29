"""Tests for soma.cli — config_loader, status, main, create_engine_from_config."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from soma.cli.config_loader import (
    DEFAULT_CONFIG,
    create_engine_from_config,
    load_config,
    save_config,
)
from soma.engine import SOMAEngine


# ---------------------------------------------------------------------------
# config_loader tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_default_when_file_missing(self, tmp_path: Path) -> None:
        """load_config returns DEFAULT_CONFIG when the file does not exist."""
        missing = str(tmp_path / "nonexistent.toml")
        cfg = load_config(missing)
        assert cfg["soma"]["version"] == DEFAULT_CONFIG["soma"]["version"]
        assert cfg["budget"]["tokens"] == DEFAULT_CONFIG["budget"]["tokens"]

    def test_load_existing_file(self, tmp_path: Path) -> None:
        """load_config reads a TOML file written by save_config."""
        path = str(tmp_path / "soma.toml")
        custom = {
            "soma": {"version": "9.9.9", "store": "/tmp/test.json"},
            "budget": {"tokens": 9999, "cost_usd": 1.0},
        }
        save_config(custom, path)
        loaded = load_config(path)
        assert loaded["soma"]["version"] == "9.9.9"
        assert loaded["budget"]["tokens"] == 9999


class TestSaveConfig:
    def test_roundtrip(self, tmp_path: Path) -> None:
        """save_config + load_config roundtrip preserves all values."""
        path = str(tmp_path / "soma.toml")
        save_config(DEFAULT_CONFIG, path)
        assert os.path.exists(path)
        loaded = load_config(path)
        # Check all top-level sections round-trip
        assert loaded["soma"] == DEFAULT_CONFIG["soma"]
        assert loaded["budget"]["tokens"] == DEFAULT_CONFIG["budget"]["tokens"]
        assert abs(loaded["budget"]["cost_usd"] - DEFAULT_CONFIG["budget"]["cost_usd"]) < 1e-9
        assert loaded["thresholds"] == DEFAULT_CONFIG["thresholds"]
        assert loaded["weights"] == DEFAULT_CONFIG["weights"]
        assert loaded["graph"] == DEFAULT_CONFIG["graph"]

    def test_creates_file(self, tmp_path: Path) -> None:
        """save_config creates the file at the specified path."""
        path = str(tmp_path / "new_config.toml")
        assert not os.path.exists(path)
        save_config(DEFAULT_CONFIG, path)
        assert os.path.exists(path)


# ---------------------------------------------------------------------------
# create_engine_from_config tests
# ---------------------------------------------------------------------------


class TestCreateEngineFromConfig:
    def test_returns_soma_engine(self) -> None:
        """create_engine_from_config returns a SOMAEngine instance."""
        engine = create_engine_from_config(DEFAULT_CONFIG)
        assert isinstance(engine, SOMAEngine)

    def test_budget_applied(self) -> None:
        """Engine budget limits come from the config."""
        cfg = dict(DEFAULT_CONFIG)
        cfg["budget"] = {"tokens": 42000, "cost_usd": 3.5}
        engine = create_engine_from_config(cfg)
        assert engine.budget.limits.get("tokens") == 42000.0
        assert abs(engine.budget.limits.get("cost_usd", 0) - 3.5) < 1e-9

    def test_default_agent_registered(self) -> None:
        """create_engine_from_config registers a 'default' agent."""
        engine = create_engine_from_config(DEFAULT_CONFIG)
        # SOMAEngine._agents is internal but we can call get_level without error
        level = engine.get_level("default")
        assert level is not None


# ---------------------------------------------------------------------------
# status tests
# ---------------------------------------------------------------------------


class TestPrintStatus:
    def test_no_state_file_message(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """print_status prints a 'no session' message when state file is absent."""
        cfg = {
            "soma": {"version": "0.1.0", "store": str(tmp_path / "state.json")},
            "budget": {"tokens": 100000},
        }
        from soma.cli.status import print_status
        print_status(cfg)
        out = capsys.readouterr().out
        assert "No SOMA session active" in out

    def test_with_state_file(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """print_status prints agent rows when state file exists."""
        state = {
            "agents": [
                {
                    "id": "Agent 1",
                    "level": "HEALTHY",
                    "pressure": 0.03,
                    "vitals": {"uncertainty": 0.11, "drift": 0.00, "error_rate": 0.00},
                    "action_count": 42,
                },
                {
                    "id": "Agent 2",
                    "level": "CAUTION",
                    "pressure": 0.31,
                    "vitals": {"uncertainty": 0.28, "drift": 0.05, "error_rate": 0.10},
                    "action_count": 38,
                },
            ],
            "budget": {"tokens_spent": 27000},
        }
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")

        cfg = {
            "soma": {"version": "0.1.0", "store": str(state_path)},
            "budget": {"tokens": 100000},
        }
        from soma.cli.status import print_status
        print_status(cfg)
        out = capsys.readouterr().out
        assert "SOMA" in out
        assert "2 agents monitored" in out

    def test_prints_something(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """print_status always writes something to stdout."""
        cfg = {
            "soma": {"version": "0.1.0", "store": str(tmp_path / "missing.json")},
            "budget": {"tokens": 100000},
        }
        from soma.cli.status import print_status
        print_status(cfg)
        out = capsys.readouterr().out
        assert len(out.strip()) > 0


# ---------------------------------------------------------------------------
# main / argparse tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_version_flag(self, capsys: pytest.CaptureFixture) -> None:
        """soma --version prints the version string and exits."""
        from soma.cli.main import _build_parser
        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_version_subcommand(self, capsys: pytest.CaptureFixture) -> None:
        """soma version subcommand prints version."""
        from soma.cli.main import main
        with mock.patch("sys.argv", ["soma", "version"]):
            main()
        out = capsys.readouterr().out
        assert "soma" in out
        assert "0.3.0" in out

    def test_status_subcommand(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """soma status subcommand runs without error."""
        cfg = {
            "soma": {"version": "0.1.0", "store": str(tmp_path / "missing.json")},
            "budget": {"tokens": 100000},
        }
        from soma.cli.main import main
        with mock.patch("sys.argv", ["soma", "status"]):
            with mock.patch("soma.cli.main.load_config", return_value=cfg):
                main()
        out = capsys.readouterr().out
        assert len(out.strip()) > 0

    def test_no_args_calls_tui(self, capsys: pytest.CaptureFixture) -> None:
        """soma with no subcommand attempts to launch the TUI (or prints a fallback)."""
        from soma.cli.main import main
        with mock.patch("sys.argv", ["soma"]):
            # Patch dashboard.run so we don't actually open a TUI
            with mock.patch("soma.cli.main._cmd_tui") as mock_tui:
                main()
        mock_tui.assert_called_once()
