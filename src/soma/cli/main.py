"""SOMA CLI entry point — argparse-based subcommand router."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from soma.cli.config_loader import load_config

try:
    from importlib.metadata import version as _pkg_version
    _VERSION = _pkg_version("soma-ai")
except Exception:
    _VERSION = "0.4.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _cmd_reset(args: argparse.Namespace) -> None:
    """Reset an agent's baseline directly."""
    agent_id = getattr(args, 'agent_id', None) or "claude-code"

    engine_path = Path.home() / ".soma" / "engine_state.json"
    if not engine_path.exists():
        print("  No SOMA state found.")
        return

    try:
        from soma.persistence import load_engine_state, save_engine_state
        from soma.baseline import Baseline
        from soma.types import ResponseMode

        engine = load_engine_state(str(engine_path))
        if engine is None:
            print("  Could not load engine state.")
            return

        if agent_id not in engine._agents:
            print(f"  Agent '{agent_id}' not found.")
            return

        agent = engine._agents[agent_id]
        agent.baseline = Baseline()
        agent.baseline_vector = None
        agent.mode = ResponseMode.OBSERVE
        agent.action_count = 0
        save_engine_state(engine, str(engine_path))

        # Also export for dashboard
        state_path = Path.home() / ".soma" / "state.json"
        engine.export_state(str(state_path))

        # Clean session files
        for f in ["action_log.json", "predictor.json", "quality.json", "task_tracker.json"]:
            p = Path.home() / ".soma" / f
            p.unlink(missing_ok=True)

        print(f"  Agent '{agent_id}' reset. Baseline cleared, pressure zeroed.")
    except Exception as e:
        print(f"  Error: {e}")


def _cmd_stop(_args: argparse.Namespace) -> None:
    """Disable SOMA hooks in Claude Code settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        print("  No Claude Code settings found.")
        return

    settings = json.loads(settings_path.read_text())
    changed = False

    # Remove SOMA hooks
    for hook_type in list(settings.get("hooks", {}).keys()):
        hook_list = settings["hooks"][hook_type]
        filtered = [
            entry for entry in hook_list
            if not any("soma" in str(h.get("command", "")) for h in entry.get("hooks", []))
        ]
        if len(filtered) != len(hook_list):
            settings["hooks"][hook_type] = filtered
            changed = True
        # Remove empty hook lists
        if not settings["hooks"][hook_type]:
            del settings["hooks"][hook_type]

    # Remove empty hooks dict
    if "hooks" in settings and not settings["hooks"]:
        del settings["hooks"]

    # Remove SOMA statusLine
    if "statusLine" in settings:
        cmd = settings["statusLine"].get("command", "") if isinstance(settings["statusLine"], dict) else ""
        if "soma" in cmd:
            del settings["statusLine"]
            changed = True

    if changed:
        settings_path.write_text(json.dumps(settings, indent=2))
        print("  SOMA hooks disabled. Run `soma start` to re-enable.")
    else:
        print("  No SOMA hooks found in settings.")


def _cmd_start(_args: argparse.Namespace) -> None:
    """Re-enable SOMA hooks in Claude Code settings.json."""
    from soma.cli.setup_claude import _find_soma_hook_command, _find_statusline_command, _install_hooks, _install_statusline
    settings_path = Path.home() / ".claude" / "settings.json"
    hook_cmd = _find_soma_hook_command()
    sl_cmd = _find_statusline_command()

    hooks_changed = _install_hooks(settings_path, hook_cmd)
    sl_changed = _install_statusline(settings_path, sl_cmd)

    if hooks_changed or sl_changed:
        print("  SOMA hooks enabled.")
    else:
        print("  SOMA hooks already active.")


def _cmd_uninstall_claude(args: argparse.Namespace) -> None:
    """Remove SOMA from Claude Code completely."""
    print()
    print("  Uninstalling SOMA from Claude Code...")
    print()

    # 1. Remove hooks (same as stop)
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        changed = False

        for hook_type in list(settings.get("hooks", {}).keys()):
            hook_list = settings["hooks"][hook_type]
            filtered = [
                entry for entry in hook_list
                if not any("soma" in str(h.get("command", "")) for h in entry.get("hooks", []))
            ]
            if len(filtered) != len(hook_list):
                settings["hooks"][hook_type] = filtered
                changed = True
            if not settings["hooks"].get(hook_type):
                settings["hooks"].pop(hook_type, None)

        if "hooks" in settings and not settings["hooks"]:
            del settings["hooks"]

        if "statusLine" in settings:
            cmd = settings["statusLine"].get("command", "") if isinstance(settings["statusLine"], dict) else ""
            if "soma" in cmd:
                del settings["statusLine"]
                changed = True

        if changed:
            settings_path.write_text(json.dumps(settings, indent=2))
            print("  + Removed hooks from Claude Code settings")
        else:
            print("  No hooks found.")

    # 2. Clean ~/.soma/ state
    soma_dir = Path.home() / ".soma"
    if soma_dir.exists():
        if getattr(args, 'keep_state', False):
            print("  Keeping ~/.soma/ state (--keep-state)")
        else:
            import shutil
            shutil.rmtree(soma_dir)
            print("  + Removed ~/.soma/ state directory")

    # 3. Remove SOMA section from CLAUDE.md (non-destructive)
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        content = claude_md.read_text()
        if "## SOMA Monitoring" in content:
            # Remove the SOMA section
            lines = content.split("\n")
            new_lines = []
            skip = False
            for line in lines:
                if line.strip() == "## SOMA Monitoring":
                    skip = True
                    continue
                if skip and line.startswith("## "):
                    skip = False
                if not skip:
                    new_lines.append(line)
            claude_md.write_text("\n".join(new_lines))
            print("  + Removed SOMA section from CLAUDE.md")

    print()
    print("  SOMA uninstalled. Run `soma setup-claude` to reinstall.")
    print()


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


def _cmd_mode(args: argparse.Namespace) -> None:
    from soma.cli.config_loader import (
        load_config, save_config, MODE_PRESETS, apply_mode,
    )

    if args.mode_name is None:
        # Show current mode and available modes
        config = load_config()
        current = config.get("soma", {}).get("mode", "relaxed")
        print(f"  Current mode: {current}")
        print()
        for name, preset in MODE_PRESETS.items():
            autonomy = preset["agents"]["claude-code"]["autonomy"]
            warn_threshold = preset["thresholds"]["quarantine"]
            verbosity = preset["hooks"]["verbosity"]
            marker = " <--" if name == current else ""
            print(f"  {name:<12} autonomy={autonomy}, pressure_limit={warn_threshold:.0%}, verbosity={verbosity}{marker}")
        print()
        print("  Usage: soma mode <strict|relaxed|autonomous>")
        return

    mode_name = args.mode_name
    config = load_config()
    config = apply_mode(config, mode_name)
    config.setdefault("soma", {})["mode"] = mode_name
    save_config(config)
    print(f"  Mode set to: {mode_name}")

    preset = MODE_PRESETS[mode_name]
    autonomy = preset["agents"]["claude-code"]["autonomy"]
    warn_threshold = preset["thresholds"]["quarantine"]
    print(f"  Autonomy: {autonomy}")
    print(f"  Pressure limit: {warn_threshold:.0%}")
    print(f"  Verbosity: {preset['hooks']['verbosity']}")


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
    from soma.cli.hub import run_hub
    run_hub()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="soma",
        description="SOMA — Behavioral monitoring and guidance for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Agent monitoring:\n"
            "  soma agents                     List all monitored agents\n"
            "  soma status                     Show current monitoring status\n"
            "\n"
            "Agent control:\n"
            "  soma reset [agent-id]           Reset agent baseline (default: claude-code)\n"
            "  soma stop                       Disable SOMA hooks in Claude Code\n"
            "  soma start                      Re-enable SOMA hooks in Claude Code\n"
            "\n"
            "Configuration:\n"
            "  soma config show                Print current soma.toml\n"
            "  soma config set <key> <value>   Update a config value\n"
            "  soma mode [name]                Switch operating mode\n"
            "  soma init                       Run the interactive setup wizard\n"
            "\n"
            "Session:\n"
            "  soma replay <file>              Replay a recorded session file\n"
            "\n"
            "System:\n"
            "  soma setup-claude               Set up SOMA for Claude Code projects\n"
            "  soma uninstall-claude            Remove SOMA from Claude Code\n"
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
    rst = subparsers.add_parser("reset", help="Reset an agent's pressure baseline")
    rst.add_argument("agent_id", metavar="agent-id", nargs="?", default="claude-code",
                     help="Agent ID to reset (default: claude-code)")

    subparsers.add_parser("stop", help="Disable SOMA hooks in Claude Code settings")
    subparsers.add_parser("start", help="Re-enable SOMA hooks in Claude Code settings")

    uninstall_p = subparsers.add_parser("uninstall-claude", help="Remove SOMA from Claude Code completely")
    uninstall_p.add_argument("--keep-state", action="store_true", dest="keep_state",
                             help="Keep ~/.soma/ state directory")

    # ---- Config ----
    config_parser = subparsers.add_parser("config", help="View or modify soma.toml configuration")
    config_subs = config_parser.add_subparsers(dest="config_command")
    config_subs.add_parser("show", help="Print current soma.toml")
    cs = config_subs.add_parser("set", help="Set a configuration value (e.g. thresholds.caution 0.20)")
    cs.add_argument("key", help="Dotted key path (e.g. thresholds.caution)")
    cs.add_argument("value", help="New value")

    # ---- Mode ----
    mode_parser = subparsers.add_parser("mode", help="Switch SOMA operating mode")
    mode_parser.add_argument("mode_name", nargs="?", default=None,
                             help="Mode: strict, relaxed, or autonomous")

    # ---- Session ----
    replay_parser = subparsers.add_parser("replay", help="Replay a recorded session file")
    replay_parser.add_argument("file", help="Path to the session recording file (JSON)")

    # ---- System ----
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
        "reset": _cmd_reset,
        "stop": _cmd_stop,
        "start": _cmd_start,
        "uninstall-claude": _cmd_uninstall_claude,
        "mode": _cmd_mode,
        "replay": _cmd_replay,
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
