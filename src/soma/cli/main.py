"""SOMA CLI entry point — argparse-based subcommand router."""

from __future__ import annotations

import argparse
import sys

from soma.cli.config_loader import load_config

_VERSION = "0.1.0"


def _cmd_status(_args: argparse.Namespace) -> None:
    from soma.cli.status import print_status
    config = load_config()
    print_status(config)


def _cmd_replay(args: argparse.Namespace) -> None:
    import json
    from soma.recorder import SessionRecorder
    from soma.replay import replay_session

    recording_path: str = args.file

    try:
        from soma.cli.replay_cli import run_replay_cli
        run_replay_cli(recording_path)
    except ImportError:
        # Fallback: basic replay
        recording = SessionRecorder.load(recording_path)
        results = replay_session(recording)
        for i, result in enumerate(results, start=1):
            print(f"  [{i:>4}] level={result.level.name}  pressure={result.pressure:.3f}")


def _cmd_version(_args: argparse.Namespace) -> None:
    print(f"soma {_VERSION}")


def _cmd_init(_args: argparse.Namespace) -> None:
    # Wizard will be created by another agent; stub for now
    try:
        from soma.cli.wizard import run_wizard  # type: ignore[import]
        run_wizard()
    except ImportError:
        print("soma init: wizard not yet available. Please create soma.toml manually.")


def _cmd_tui() -> None:
    from pathlib import Path
    # First run? Auto-wizard
    if not Path("soma.toml").exists() and not (Path.home() / ".soma" / "state.json").exists():
        print()
        print("  Welcome to SOMA!")
        print("  The nervous system for AI agents.")
        print()
        print("  Looks like this is your first time. Let's set things up.")
        print()
        from soma.cli.wizard import run_wizard
        run_wizard()
        return
    # Otherwise open hub
    try:
        from soma.cli.hub import run_hub
        run_hub()
    except ImportError:
        print("Install dashboard: pip install soma-core[dashboard]")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="soma",
        description="SOMA — Behavioral monitoring and directive control for AI agents",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"soma {_VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command")

    # init
    subparsers.add_parser("init", help="Run the interactive setup wizard")

    # status
    subparsers.add_parser("status", help="Show current agent monitoring status")

    # replay
    replay_parser = subparsers.add_parser("replay", help="Replay a recorded session file")
    replay_parser.add_argument("file", help="Path to the session recording file (JSON)")

    # setup-claude
    subparsers.add_parser("setup-claude", help="Set up SOMA for Claude Code projects")

    # version
    subparsers.add_parser("version", help="Print the SOMA version and exit")

    return parser


def main() -> None:
    """CLI entry point. Running `soma` with no subcommand launches the TUI hub."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        # No subcommand → launch TUI
        _cmd_tui()
        return

    dispatch = {
        "init": _cmd_init,
        "status": _cmd_status,
        "replay": _cmd_replay,
        "setup-claude": lambda _: __import__("soma.cli.setup_claude", fromlist=["run_setup_claude"]).run_setup_claude(),
        "version": _cmd_version,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
