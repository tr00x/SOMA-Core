"""SOMA CLI entry point — argparse-based subcommand router."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from soma.cli.config_loader import load_config

_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_command(action: str, params: dict) -> None:
    cmd_dir = Path.home() / ".soma" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    cmd_file = cmd_dir / f"{ts}.json"
    cmd_file.write_text(
        json.dumps({"action": action, "params": params, "id": str(ts)})
    )
    print(f"  Command sent: {action}")


def _load_state() -> dict[str, Any] | None:
    state_path = Path.home() / ".soma" / "state.json"
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text())


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_status(_args: argparse.Namespace) -> None:
    from soma.cli.status import print_status
    config = load_config()
    print_status(config)


def _cmd_replay(args: argparse.Namespace) -> None:
    from soma.recorder import SessionRecorder
    from soma.replay import replay_session

    recording_path: str = args.file

    try:
        from soma.cli.replay_cli import run_replay_cli
        run_replay_cli(recording_path)
    except ImportError:
        recording = SessionRecorder.load(recording_path)
        results = replay_session(recording)
        for i, result in enumerate(results, start=1):
            print(f"  [{i:>4}] level={result.level.name}  pressure={result.pressure:.3f}")


def _cmd_version(_args: argparse.Namespace) -> None:
    print(f"soma {_VERSION}")


def _cmd_init(_args: argparse.Namespace) -> None:
    try:
        from soma.cli.wizard import run_wizard  # type: ignore[import]
        run_wizard()
    except ImportError:
        print("soma init: wizard not yet available. Please create soma.toml manually.")


def _cmd_agents(_args: argparse.Namespace) -> None:
    state = _load_state()
    if state is None:
        print("No active session.")
        return

    agents = state.get("agents", {})
    if not agents:
        print("No active session.")
        return

    print("SOMA Agents:")
    for agent_id, info in agents.items():
        level = info.get("level", "UNKNOWN")
        pressure = info.get("pressure", 0.0)
        action_count = info.get("action_count", 0)
        print(f"  {agent_id:<20} {level:<12} p={pressure:.2f}  actions={action_count}")


def _cmd_quarantine(args: argparse.Namespace) -> None:
    _write_command("force_level", {"agent_id": args.agent_id, "level": "QUARANTINE"})


def _cmd_release(args: argparse.Namespace) -> None:
    _write_command("force_level", {"agent_id": args.agent_id, "level": "HEALTHY"})


def _cmd_reset(args: argparse.Namespace) -> None:
    _write_command("reset_baseline", {"agent_id": args.agent_id})


def _cmd_approve(args: argparse.Namespace) -> None:
    _write_command("approve_escalation", {"agent_id": args.agent_id})


def _cmd_config(args: argparse.Namespace) -> None:
    import tomllib
    import tomli_w

    config_path = Path("soma.toml")

    if args.config_command == "show":
        if not config_path.exists():
            print("No soma.toml found. Run `soma init`.")
            return
        with open(config_path, "rb") as fh:
            cfg = tomllib.load(fh)
        # Pretty-print as TOML
        import io
        buf = io.BytesIO()
        tomli_w.dump(cfg, buf)
        print(buf.getvalue().decode())

    elif args.config_command == "set":
        from soma.cli.config_loader import load_config, save_config
        cfg = load_config()

        # Navigate nested key (e.g. "thresholds.caution")
        key_path = args.key.split(".")
        node = cfg
        for part in key_path[:-1]:
            node = node.setdefault(part, {})

        leaf = key_path[-1]
        # Attempt type coercion: float, int, bool, then string
        raw = args.value
        coerced: Any
        if raw.lower() in ("true", "false"):
            coerced = raw.lower() == "true"
        else:
            try:
                coerced = int(raw)
            except ValueError:
                try:
                    coerced = float(raw)
                except ValueError:
                    coerced = raw

        node[leaf] = coerced
        save_config(cfg)
        print(f"  Set {args.key} = {coerced!r}")

    else:
        print(f"Unknown config command: {args.config_command}")
        sys.exit(1)


def _cmd_export(args: argparse.Namespace) -> None:
    import json as _json

    state = _load_state()
    if state is None:
        print("No active session — nothing to export.")
        return

    out_path = Path(args.path) if args.path else Path("soma_export.json")
    out_path.write_text(_json.dumps(state, indent=2))
    print(f"  Session exported to {out_path}")


def _cmd_daemon(_args: argparse.Namespace) -> None:
    print("SOMA daemon running. Ctrl+C to stop.")
    try:
        from soma.daemon import run_daemon
        run_daemon()
    except ImportError:
        print("soma.daemon not available.")
        sys.exit(1)


def _cmd_tui() -> None:
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


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="soma",
        description="SOMA — Behavioral monitoring and directive control for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Agent monitoring:\n"
            "  soma agents                     List all monitored agents\n"
            "  soma status                     Show current monitoring status\n"
            "\n"
            "Agent control:\n"
            "  soma quarantine <agent-id>      Force agent to QUARANTINE\n"
            "  soma release <agent-id>         Release agent from quarantine\n"
            "  soma reset <agent-id>           Reset agent baseline\n"
            "  soma approve <agent-id>         Approve pending escalation\n"
            "\n"
            "Configuration:\n"
            "  soma config show                Print current soma.toml\n"
            "  soma config set <key> <value>   Update a config value\n"
            "  soma init                       Run the interactive setup wizard\n"
            "\n"
            "Session:\n"
            "  soma export [--path FILE]       Export session to JSON\n"
            "  soma replay <file>              Replay a recorded session file\n"
            "\n"
            "System:\n"
            "  soma daemon                     Run SOMA daemon in foreground\n"
            "  soma setup-claude               Set up SOMA for Claude Code projects\n"
            "  soma version                    Print version and exit\n"
        ),
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"soma {_VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ---- Setup / init ----
    subparsers.add_parser("init", help="Run the interactive setup wizard")
    subparsers.add_parser("setup-claude", help="Set up SOMA for Claude Code projects")

    # ---- Monitoring ----
    subparsers.add_parser("agents", help="List all agents from state file")
    subparsers.add_parser("status", help="Show current agent monitoring status")

    # ---- Agent control ----
    q = subparsers.add_parser("quarantine", help="Force an agent to QUARANTINE level")
    q.add_argument("agent_id", metavar="agent-id", help="Agent ID to quarantine")

    r = subparsers.add_parser("release", help="Release an agent from quarantine (set to HEALTHY)")
    r.add_argument("agent_id", metavar="agent-id", help="Agent ID to release")

    rst = subparsers.add_parser("reset", help="Reset an agent's pressure baseline")
    rst.add_argument("agent_id", metavar="agent-id", help="Agent ID to reset")

    ap = subparsers.add_parser("approve", help="Approve a pending escalation for an agent")
    ap.add_argument("agent_id", metavar="agent-id", help="Agent ID to approve")

    # ---- Config ----
    config_parser = subparsers.add_parser("config", help="View or modify soma.toml configuration")
    config_subs = config_parser.add_subparsers(dest="config_command")
    config_subs.add_parser("show", help="Print current soma.toml")
    cs = config_subs.add_parser("set", help="Set a configuration value (e.g. thresholds.caution 0.20)")
    cs.add_argument("key", help="Dotted key path (e.g. thresholds.caution)")
    cs.add_argument("value", help="New value")

    # ---- Session ----
    export_p = subparsers.add_parser("export", help="Export current session state to JSON")
    export_p.add_argument(
        "--path", metavar="FILE", default=None,
        help="Output file path (default: soma_export.json)",
    )

    replay_parser = subparsers.add_parser("replay", help="Replay a recorded session file")
    replay_parser.add_argument("file", help="Path to the session recording file (JSON)")

    # ---- System ----
    subparsers.add_parser("daemon", help="Run SOMA daemon in foreground (Ctrl+C to stop)")
    subparsers.add_parser("version", help="Print the SOMA version and exit")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point. Running `soma` with no subcommand launches the TUI hub."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        _cmd_tui()
        return

    if args.command == "config":
        if not getattr(args, "config_command", None):
            parser.parse_args(["config", "--help"])
            return
        _cmd_config(args)
        return

    dispatch = {
        "init": _cmd_init,
        "status": _cmd_status,
        "agents": _cmd_agents,
        "quarantine": _cmd_quarantine,
        "release": _cmd_release,
        "reset": _cmd_reset,
        "approve": _cmd_approve,
        "export": _cmd_export,
        "replay": _cmd_replay,
        "daemon": _cmd_daemon,
        "setup-claude": lambda _: __import__(
            "soma.cli.setup_claude", fromlist=["run_setup_claude"]
        ).run_setup_claude(),
        "version": _cmd_version,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
