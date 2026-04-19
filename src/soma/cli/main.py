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
    from soma import __version__ as _VERSION


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
    # Check if session store shortcuts are used
    use_last = getattr(args, "last", False)
    use_worst = getattr(args, "worst", False)
    session_idx = getattr(args, "session", None)

    if use_last or use_worst or session_idx is not None:
        _cmd_replay_session(args)
        return

    from soma.recorder import SessionRecorder
    from soma.replay import replay_session

    recording_path: str | None = args.file
    if recording_path is None:
        print("  Usage: soma replay <file> or soma replay --last/--worst/--session N")
        return

    try:
        from soma.cli.replay_cli import run_replay_cli
        run_replay_cli(recording_path)
    except ImportError:
        recording = SessionRecorder.load(recording_path)
        results = replay_session(recording)
        for i, result in enumerate(results, start=1):
            print(f"  [{i:>4}] level={result.level.name}  pressure={result.pressure:.3f}")


def _cmd_replay_session(args: argparse.Namespace) -> None:
    """Replay a session from session_store (--last, --worst, --session N)."""
    from soma.session_store import load_sessions

    sessions = load_sessions()
    if not sessions:
        print("  No sessions found in session store.")
        return

    # Sort by ended time descending (most recent first)
    sessions_sorted = sorted(sessions, key=lambda s: s.ended, reverse=True)

    if getattr(args, "worst", False):
        target = max(sessions, key=lambda s: s.max_pressure)
    elif getattr(args, "session", None) is not None:
        idx = args.session
        if idx < 0 or idx >= len(sessions_sorted):
            print(f"  Session index {idx} out of range (0-{len(sessions_sorted) - 1}).")
            return
        target = sessions_sorted[idx]
    else:
        # --last (default)
        target = sessions_sorted[0]

    # Print session header
    import datetime
    started = datetime.datetime.fromtimestamp(target.started).strftime("%Y-%m-%d %H:%M") if target.started > 0 else "?"
    duration = int(target.ended - target.started) if target.started > 0 else 0
    duration_min = duration // 60

    print()
    print(f"  Session: {target.agent_id}")
    print(f"  Started: {started}  Duration: {duration_min}min  Actions: {target.action_count}")
    print(f"  Pressure: avg={target.avg_pressure:.0%}  peak={target.max_pressure:.0%}  final={target.final_pressure:.0%}")
    print(f"  Errors: {target.error_count}/{target.action_count}")
    print()

    traj = target.pressure_trajectory or []

    # Print action-by-action
    n_actions = max(len(traj), target.action_count)
    if n_actions == 0:
        print("  No action data to replay.")
        return

    # Detect patterns: >60% single tool usage
    patterns = set()
    if target.tool_distribution:
        total_t = sum(target.tool_distribution.values())
        for t, c in target.tool_distribution.items():
            if total_t > 5 and c / total_t > 0.6:
                patterns.add(t)

    tool_order = list(target.tool_distribution.keys()) if target.tool_distribution else []
    tool_counts_remaining = dict(target.tool_distribution) if target.tool_distribution else {}

    for i in range(n_actions):
        pressure = traj[i] if i < len(traj) else 0.0

        # Pick tool name from distribution (approximate order)
        tool = "?"
        for t in tool_order:
            if tool_counts_remaining.get(t, 0) > 0:
                tool = t
                tool_counts_remaining[t] -= 1
                break

        # Status marker
        is_error = i < target.error_count  # approximate: errors first
        is_pattern = tool in patterns
        if is_error:
            marker = "\u2717"
        elif is_pattern:
            marker = "\u26a1"
        else:
            marker = "\u2713"

        pattern_note = f"[{tool} heavy]" if is_pattern and i == 0 else ""

        print(f"  #{i:<4} {tool:12s}  p={pressure:.0%}  {marker}  {pattern_note}")


def _cmd_version(_args: argparse.Namespace) -> None:
    print(f"soma {_VERSION}")


def _cmd_setup(args: argparse.Namespace) -> None:
    """Route soma setup --<platform> to the correct setup function."""
    if getattr(args, "setup_claude_code", False):
        from soma.cli.setup_claude import run_setup_claude
        run_setup_claude()
    elif getattr(args, "setup_cursor", False):
        from soma.cli.setup_claude import run_setup_cursor
        run_setup_cursor()
    elif getattr(args, "setup_windsurf", False):
        from soma.cli.setup_claude import run_setup_windsurf
        run_setup_windsurf()


def _cmd_install(args: argparse.Namespace) -> None:
    """Install (or update) SOMA for Claude Code with mode and profile."""
    from soma.cli.setup_claude import run_setup_claude
    from soma.cli.config_loader import load_config, save_config, apply_mode, CLAUDE_CODE_CONFIG

    # 1. Run setup (hooks, statusline, engine state, soma.toml, skills)
    run_setup_claude()

    # 2. Apply mode and profile to soma.toml
    mode = getattr(args, "mode", "reflex")
    profile = getattr(args, "profile", "claude-code")

    config = load_config()

    # Set mode
    config.setdefault("soma", {})["mode"] = mode

    # Set profile
    config["soma"]["profile"] = profile

    # Apply profile defaults if claude-code
    if profile == "claude-code":
        for section in ("weights", "hooks", "vitals"):
            if section in CLAUDE_CODE_CONFIG and section not in config:
                config[section] = CLAUDE_CODE_CONFIG[section]

    # Apply mode preset (strict/autonomous map to thresholds)
    if mode in ("strict",):
        config = apply_mode(config, "strict")
    elif mode in ("autonomous",):
        config = apply_mode(config, "autonomous")

    save_config(config)

    print(f"  Mode: {mode}")
    print(f"  Profile: {profile}")
    print()


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


def _find_stale_sessions(sessions_dir: Path, cutoff_ts: float) -> list[Path]:
    """Return session subdirectories whose mtime is older than `cutoff_ts`.

    Missing directory → empty list. Non-directory entries skipped.
    """
    if not sessions_dir.exists():
        return []
    stale: list[Path] = []
    for entry in sessions_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime < cutoff_ts:
                stale.append(entry)
        except OSError:
            continue
    return stale


def _dir_size_bytes(path: Path) -> int:
    """Recursive size in bytes; unreachable entries ignored."""
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _cmd_prune(args: argparse.Namespace) -> None:
    """Delete session directories older than --older-than days.

    Dry-run by default. Pass --yes to actually remove them.
    """
    import shutil
    import time

    raw_days = getattr(args, "older_than", 30)
    if raw_days is None:
        raw_days = 30
    days = max(1, int(raw_days))
    sessions_dir = Path.home() / ".soma" / "sessions"
    cutoff_ts = time.time() - (days * 86_400)

    stale = _find_stale_sessions(sessions_dir, cutoff_ts)
    if not stale:
        print(f"  No sessions older than {days}d in {sessions_dir}.")
        return

    total_bytes = sum(_dir_size_bytes(p) for p in stale)
    mb = total_bytes / (1024 * 1024)

    apply = bool(getattr(args, "yes", False))
    verb = "Would remove" if not apply else "Removing"
    print(f"  {verb} {len(stale)} session(s) older than {days}d "
          f"(~{mb:.1f} MB) from {sessions_dir}.")

    if not apply:
        preview = stale[:5]
        for p in preview:
            print(f"    - {p.name}")
        if len(stale) > len(preview):
            print(f"    ... and {len(stale) - len(preview)} more")
        print("  Re-run with --yes to actually delete.")
        return

    removed = 0
    failed = 0
    for p in stale:
        try:
            shutil.rmtree(p)
            removed += 1
        except OSError as e:
            print(f"  ! failed to remove {p.name}: {e}")
            failed += 1
    print(f"  Removed {removed} session(s)."
          + (f" {failed} failed." if failed else ""))


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


def _cmd_stats(args: argparse.Namespace) -> None:
    """Show session statistics from session_store."""
    import time as _time
    from rich.console import Console
    from rich.table import Table
    from soma.session_store import load_sessions

    console = Console()
    sessions = load_sessions()

    if not sessions:
        console.print("  No session data found. Sessions are recorded when Claude Code exits.")
        return

    now = _time.time()
    day_seconds = 86400

    # Filter by time range
    if getattr(args, "all", False):
        filtered = sessions
        label = "All time"
    elif getattr(args, "week", False):
        cutoff = now - 7 * day_seconds
        filtered = [s for s in sessions if s.ended >= cutoff]
        label = "Last 7 days"
    else:
        # Today (since midnight)
        import datetime
        midnight = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        filtered = [s for s in sessions if s.ended >= midnight]
        label = "Today"

    if not filtered:
        console.print(f"  No sessions found for: {label}")
        return

    # Compute stats
    total_actions = sum(s.action_count for s in filtered)
    total_errors = sum(s.error_count for s in filtered)
    avg_pressure = sum(s.avg_pressure for s in filtered) / len(filtered)

    # Peak pressure and which session
    peak_session = max(filtered, key=lambda s: s.max_pressure)
    peak_pressure = peak_session.max_pressure

    # Error rate
    error_rate = total_errors / total_actions if total_actions > 0 else 0.0

    # Patterns caught (heuristic: sessions where tool_distribution has > 60% single tool)
    patterns_caught = 0
    for s in filtered:
        if s.tool_distribution:
            total_tools = sum(s.tool_distribution.values())
            max_tool = max(s.tool_distribution.values()) if s.tool_distribution else 0
            if total_tools > 5 and max_tool / total_tools > 0.6:
                patterns_caught += 1

    # Best/worst sessions
    best_session = min(filtered, key=lambda s: s.error_count)
    worst_session = max(filtered, key=lambda s: s.max_pressure)

    # Grade from pressure
    def _grade(p: float) -> str:
        if p < 0.15:
            return "A"
        if p < 0.30:
            return "B"
        if p < 0.50:
            return "C"
        if p < 0.70:
            return "D"
        return "F"

    console.print()
    console.print(f"  [bold]SOMA Stats[/bold] -- {label}")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("metric", style="dim")
    table.add_column("value")

    table.add_row("Sessions", str(len(filtered)))
    table.add_row("Total actions", str(total_actions))
    table.add_row("Avg pressure", f"{avg_pressure:.0%}")
    table.add_row("Peak pressure", f"{peak_pressure:.0%}")
    table.add_row("Errors", f"{total_errors}/{total_actions} ({error_rate:.0%})")
    table.add_row("Patterns caught", str(patterns_caught))
    table.add_row("Best session", f"{best_session.action_count} actions, {best_session.error_count} errors, grade {_grade(best_session.avg_pressure)}")
    table.add_row("Worst session", f"{worst_session.action_count} actions, peak {worst_session.max_pressure:.0%}, grade {_grade(worst_session.avg_pressure)}")

    console.print(table)

    # Week-over-week comparison
    if getattr(args, "week", False) and len(sessions) > len(filtered):
        prev_cutoff = now - 14 * day_seconds
        this_cutoff = now - 7 * day_seconds
        prev_week = [s for s in sessions if prev_cutoff <= s.ended < this_cutoff]
        if prev_week:
            prev_avg_p = sum(s.avg_pressure for s in prev_week) / len(prev_week)
            curr_avg_p = avg_pressure
            delta = curr_avg_p - prev_avg_p
            direction = "up" if delta > 0 else "down"
            console.print()
            console.print(f"  Week-over-week: pressure {direction} {abs(delta):.0%} ({len(prev_week)} prev sessions vs {len(filtered)} this week)")

    console.print()


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
            block_threshold = preset["thresholds"]["block"]
            verbosity = preset["hooks"]["verbosity"]
            marker = " <--" if name == current else ""
            print(f"  {name:<12} autonomy={autonomy}, block={block_threshold:.0%}, verbosity={verbosity}{marker}")
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
    block_threshold = preset["thresholds"]["block"]
    print(f"  Autonomy: {autonomy}")
    print(f"  Block threshold: {block_threshold:.0%}")
    print(f"  Verbosity: {preset['hooks']['verbosity']}")


def _cmd_doctor(_args: argparse.Namespace) -> None:
    """Check SOMA installation health."""
    import shutil

    issues = []
    ok = []

    # 1. Check soma-hook is available
    soma_hook = shutil.which("soma-hook")
    if soma_hook:
        ok.append(f"soma-hook found: {soma_hook}")
    else:
        issues.append("soma-hook not in PATH — run: pip install soma-ai")

    # 2. Check settings.json hooks
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})
        expected = ["PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop", "UserPromptSubmit"]
        for hook_type in expected:
            hook_list = hooks.get(hook_type, [])
            has_soma = any(
                "soma" in str(h.get("command", ""))
                for entry in hook_list
                for h in entry.get("hooks", [])
            )
            if has_soma:
                ok.append(f"{hook_type} hook: installed")
            else:
                issues.append(f"{hook_type} hook: MISSING — run: soma setup-claude")

        # Check statusLine
        sl = settings.get("statusLine", {})
        if isinstance(sl, dict) and "soma" in sl.get("command", ""):
            ok.append("Status line: installed")
        else:
            issues.append("Status line: MISSING — run: soma setup-claude")
    else:
        issues.append("~/.claude/settings.json not found")

    # 3. Check ~/.soma/ state
    soma_dir = Path.home() / ".soma"
    if soma_dir.exists():
        engine_state = soma_dir / "engine_state.json"
        if engine_state.exists():
            ok.append(f"Engine state: {engine_state}")
        else:
            issues.append("Engine state missing — run: soma reset")
    else:
        issues.append("~/.soma/ directory missing — run: soma setup-claude")

    # 4. Check version consistency
    try:
        from importlib.metadata import version as pkg_version
        installed = pkg_version("soma-ai")
        ok.append(f"Version: {installed}")
    except Exception:
        issues.append("soma-ai package not found")

    # Print results
    print()
    if ok:
        for item in ok:
            print(f"  ✓ {item}")
    if issues:
        print()
        for item in issues:
            print(f"  ✗ {item}")
        print()
        print(f"  {len(issues)} issue(s) found.")
    else:
        print()
        print("  All good. SOMA is healthy.")
    print()


def _cmd_report(args: argparse.Namespace) -> None:
    """Generate and display a session report."""
    from soma.persistence import load_engine_state
    from soma.report import generate_session_report, save_report

    engine_path = Path.home() / ".soma" / "engine_state.json"
    if not engine_path.exists():
        print("  No SOMA state found. Run some actions first.")
        return

    engine = load_engine_state(str(engine_path))
    if engine is None:
        print("  Could not load engine state.")
        return

    agent_id = getattr(args, "agent_id", None) or "claude-code"
    report = generate_session_report(engine, agent_id)
    print(report)

    if not getattr(args, "no_save", False):
        path = save_report(report, agent_id)
        print(f"\n  Report saved to: {path}")


def _cmd_analytics(args: argparse.Namespace) -> None:
    """Show historical analytics for an agent."""
    from soma.analytics import AnalyticsStore

    store = AnalyticsStore()
    agent_id = getattr(args, "agent_id", None) or "claude-code"

    trends = store.get_agent_trends(agent_id, last_n_sessions=10)
    if not trends:
        print(f"  No analytics data for agent '{agent_id}'.")
        store.close()
        return

    print(f"\n  SOMA Analytics — {agent_id}")
    print(f"  {'Session':<12} {'Actions':>8} {'Avg P':>8} {'Max P':>8} {'Tokens':>10} {'Cost':>10} {'Errors':>7}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*7}")
    for t in trends:
        print(
            f"  {t['session_id']:<12} {t['total_actions']:>8} "
            f"{t['avg_pressure']:>8.3f} {t['max_pressure']:>8.3f} "
            f"{t['total_tokens']:>10,.0f} ${t['total_cost']:>9.4f} "
            f"{t['error_count']:>7.0f}"
        )

    tool_stats = store.get_tool_stats(agent_id)
    if tool_stats:
        print("\n  Tool Usage:")
        for tool, count in tool_stats.items():
            print(f"    {tool}: {count}")

    store.close()
    print()


def _cmd_policy(args: argparse.Namespace) -> None:
    """Manage community policy packs."""
    from soma.cli.config_loader import load_config, save_config
    from soma.policy import load_policy_packs

    sub = getattr(args, "policy_command", None)
    if sub is None or sub == "list":
        config = load_config()
        packs = config.get("policies", {}).get("packs", [])
        if not packs:
            print("  No policy packs configured.")
            print("  Add one with: soma policy add <path-or-url>")
            return
        engines = load_policy_packs(config)
        print(f"  {len(packs)} policy pack(s) configured:\n")
        for i, entry in enumerate(packs):
            rule_count = len(engines[i].rules) if i < len(engines) else 0
            status = f"{rule_count} rules" if i < len(engines) else "failed to load"
            print(f"    {entry}")
            print(f"      {status}")
        print()

    elif sub == "add":
        entry = args.pack_path
        config = load_config()
        packs = config.setdefault("policies", {}).setdefault("packs", [])
        if entry in packs:
            print(f"  Already configured: {entry}")
            return
        packs.append(entry)
        save_config(config)
        print(f"  Added policy pack: {entry}")

    elif sub == "remove":
        entry = args.pack_path
        config = load_config()
        packs = config.get("policies", {}).get("packs", [])
        if entry not in packs:
            print(f"  Not found: {entry}")
            return
        packs.remove(entry)
        save_config(config)
        print(f"  Removed policy pack: {entry}")


def _cmd_dashboard(args: argparse.Namespace) -> None:
    """Launch the SOMA web dashboard."""
    import uvicorn

    host = args.host
    port = args.port
    print(f"SOMA Dashboard → http://{host}:{port}")
    uvicorn.run("soma.dashboard.app:app", host=host, port=port)


def _cmd_benchmark(args: argparse.Namespace) -> None:
    """Run SOMA behavioral benchmarks with A/B comparison."""
    from dataclasses import asdict

    # A/B verdict mode — the definitive test
    if getattr(args, "ab", False):
        from soma.benchmark.live import run_live_benchmark
        from soma.benchmark.ab_report import (
            analyze_ab_results,
            generate_ab_report,
            render_ab_terminal,
        )
        model = getattr(args, "model", "claude-haiku-4-5-20251001")
        runs = getattr(args, "runs", 3)
        tasks_arg = getattr(args, "tasks", None)

        # Optional task filter
        task_defs = None
        if tasks_arg:
            from soma.benchmark.tasks import get_task_by_name
            task_defs = []
            for name in tasks_arg:
                t = get_task_by_name(name)
                if t:
                    task_defs.append(t)
                else:
                    print(f"  Warning: unknown task '{name}', skipping")
            if not task_defs:
                print("  Error: no valid tasks specified")
                return

        n_tasks = len(task_defs) if task_defs else 10
        est_calls = n_tasks * runs * 2 * 8  # tasks × runs × modes × ~steps
        print("  SOMA A/B Benchmark — the definitive test")
        print(f"  Model: {model} | Tasks: {n_tasks} | Runs: {runs}/task")
        print(f"  Estimated API calls: ~{est_calls}")
        print()

        result = run_live_benchmark(runs_per_task=runs, model=model, tasks=task_defs)
        verdict = analyze_ab_results(result)
        render_ab_terminal(result, verdict)

        output_path = Path(getattr(args, "output", "docs/AB-VERDICT.md"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generate_ab_report(result, verdict))
        print(f"  Full report: {output_path}")

        # JSON for reproducibility
        json_path = getattr(args, "json", None)
        if json_path:
            jp = Path(json_path)
            jp.parent.mkdir(parents=True, exist_ok=True)
            jp.write_text(json.dumps(asdict(verdict), indent=2, default=str))
            print(f"  Verdict JSON: {jp}")
        return

    # Live benchmark mode — real LLM API calls
    if getattr(args, "live", False):
        from soma.benchmark.live import (
            run_live_benchmark,
            generate_live_report,
            render_live_terminal,
        )
        model = getattr(args, "model", "claude-haiku-4-5-20251001")
        runs = getattr(args, "runs", 3)
        print(f"  Running live benchmark with {model}...")
        print(f"  {runs} run(s) per task, estimated cost: ~$0.05")
        print()
        result = run_live_benchmark(runs_per_task=runs, model=model)
        render_live_terminal(result)

        output_path = Path(getattr(args, "output", "docs/LIVE-BENCHMARK.md"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generate_live_report(result))
        print(f"  Live benchmark report: {output_path}")
        return

    from soma.benchmark import run_benchmark
    from soma.benchmark.report import generate_markdown, render_terminal

    runs = getattr(args, "runs", 5)

    if not getattr(args, "no_terminal", False):
        from rich.console import Console
        console = Console()
        console.print()
        console.print("[bold magenta]SOMA Benchmark[/bold magenta]")
        console.print(f"  Running {runs} run(s) per scenario...")
        console.print()

    result = run_benchmark(runs_per_scenario=runs)

    if not getattr(args, "no_terminal", False):
        render_terminal(result)

    # Write markdown report
    output_path = Path(getattr(args, "output", "docs/BENCHMARK.md"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_markdown(result))
    print(f"  Benchmark report written to: {output_path}")

    # Optional JSON output
    json_path = getattr(args, "json", None)
    if json_path:
        jp = Path(json_path)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(asdict(result), indent=2, default=str))
        print(f"  JSON results written to: {jp}")

    # Optional threshold tuning
    if getattr(args, "tune_thresholds", False):
        from soma.threshold_tuner import compute_optimal_thresholds

        # Collect per-action data from all SOMA runs
        all_runs: list[dict] = []
        for scenario in result.scenarios:
            for run in scenario.soma_runs:
                all_runs.append({"per_action": run.per_action})

        thresholds = compute_optimal_thresholds(all_runs)
        print()
        print("  Optimized thresholds from benchmark data:")
        for key, val in thresholds.items():
            print(f"    {key}: {val:.3f}")
        print()


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
            "Reports:\n"
            "  soma report [agent-id]          Generate session report\n"
            "  soma analytics [agent-id]       Show historical analytics\n"
            "\n"
            "Session:\n"
            "  soma replay <file>              Replay a recorded session file\n"
            "\n"
            "System:\n"
            "  soma setup-claude               Set up SOMA for Claude Code projects\n"
            "  soma uninstall-claude            Remove SOMA from Claude Code\n"
            "  soma doctor                     Check installation health\n"
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

    install_parser = subparsers.add_parser("install", help="Install SOMA for Claude Code")
    install_parser.add_argument("--mode", choices=["observe", "guide", "reflex"], default="reflex")
    install_parser.add_argument("--profile", choices=["claude-code", "strict", "relaxed", "autonomous"], default="claude-code")

    update_parser = subparsers.add_parser("update", help="Update SOMA configuration (alias for install)")
    update_parser.add_argument("--mode", choices=["observe", "guide", "reflex"], default="reflex")
    update_parser.add_argument("--profile", choices=["claude-code", "strict", "relaxed", "autonomous"], default="claude-code")

    setup_parser = subparsers.add_parser("setup", help="Set up SOMA for a specific platform")
    setup_group = setup_parser.add_mutually_exclusive_group(required=True)
    setup_group.add_argument("--claude-code", action="store_true", dest="setup_claude_code",
                             help="Set up SOMA for Claude Code")
    setup_group.add_argument("--cursor", action="store_true", dest="setup_cursor",
                             help="Set up SOMA for Cursor")
    setup_group.add_argument("--windsurf", action="store_true", dest="setup_windsurf",
                             help="Set up SOMA for Windsurf")

    # ---- Monitoring ----
    dash_parser = subparsers.add_parser("dashboard", help="Launch the SOMA web dashboard")
    dash_parser.add_argument("--port", type=int, default=7777, help="Port (default: 7777)")
    dash_parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")

    subparsers.add_parser("agents", help="List all agents from state file")
    subparsers.add_parser("status", help="Show current agent monitoring status")

    # ---- Stats ----
    stats_parser = subparsers.add_parser("stats", help="Session statistics")
    stats_parser.add_argument("--week", action="store_true", help="Show last 7 days")
    stats_parser.add_argument("--all", action="store_true", help="Show all time")

    # ---- Agent control ----
    prune_parser = subparsers.add_parser(
        "prune", help="Delete old session directories from ~/.soma/sessions"
    )
    prune_parser.add_argument(
        "--older-than", type=int, default=30, metavar="DAYS",
        help="Remove sessions whose last-modified time is older than DAYS (default: 30)",
    )
    prune_parser.add_argument(
        "--yes", action="store_true",
        help="Actually delete (default is dry-run, preview only)",
    )

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
    cs = config_subs.add_parser("set", help="Set a configuration value (e.g. thresholds.guide 0.20)")
    cs.add_argument("key", help="Dotted key path (e.g. thresholds.guide)")
    cs.add_argument("value", help="New value")

    # ---- Policy packs ----
    policy_parser = subparsers.add_parser("policy", help="Manage community policy packs")
    policy_subs = policy_parser.add_subparsers(dest="policy_command")
    policy_subs.add_parser("list", help="List configured policy packs")
    pa = policy_subs.add_parser("add", help="Add a policy pack (local path or URL)")
    pa.add_argument("pack_path", metavar="path-or-url", help="Path or URL to policy pack")
    pr = policy_subs.add_parser("remove", help="Remove a policy pack")
    pr.add_argument("pack_path", metavar="path-or-url", help="Path or URL to remove")

    # ---- Mode ----
    mode_parser = subparsers.add_parser("mode", help="Switch SOMA operating mode")
    mode_parser.add_argument("mode_name", nargs="?", default=None,
                             help="Mode: strict, relaxed, or autonomous")

    # ---- Reports / Analytics ----
    report_parser = subparsers.add_parser("report", help="Generate session report")
    report_parser.add_argument("agent_id", metavar="agent-id", nargs="?", default="claude-code",
                               help="Agent ID (default: claude-code)")
    report_parser.add_argument("--no-save", action="store_true", dest="no_save",
                               help="Print report without saving to file")

    analytics_parser = subparsers.add_parser("analytics", help="Show historical analytics")
    analytics_parser.add_argument("agent_id", metavar="agent-id", nargs="?", default="claude-code",
                                  help="Agent ID (default: claude-code)")

    # ---- Session ----
    replay_parser = subparsers.add_parser("replay", help="Replay a recorded session file")
    replay_parser.add_argument("file", nargs="?", default=None, help="Path to the session recording file (JSON)")
    replay_parser.add_argument("--last", action="store_true", help="Replay most recent session from session store")
    replay_parser.add_argument("--worst", action="store_true", help="Replay session with highest peak pressure")
    replay_parser.add_argument("--session", type=int, default=None, metavar="N",
                               help="Replay Nth session (0=most recent)")

    # ---- Benchmark ----
    benchmark_parser = subparsers.add_parser("benchmark", help="Run SOMA behavioral benchmarks")
    benchmark_parser.add_argument("--scenarios", nargs="*", default=None,
                                  help="Specific scenarios to run (default: all)")
    benchmark_parser.add_argument("--runs", type=int, default=5,
                                  help="Runs per scenario (default: 5)")
    benchmark_parser.add_argument("--output", type=str, default="docs/BENCHMARK.md",
                                  help="Markdown output path")
    benchmark_parser.add_argument("--json", type=str, default=None,
                                  help="JSON output path")
    benchmark_parser.add_argument("--no-terminal", action="store_true", dest="no_terminal",
                                  help="Skip rich terminal output")
    benchmark_parser.add_argument("--tune-thresholds", action="store_true", dest="tune_thresholds",
                                  help="Run threshold tuner on results")
    benchmark_parser.add_argument("--live", action="store_true",
                                  help="Run live benchmark with real LLM API calls")
    benchmark_parser.add_argument("--ab", action="store_true",
                                  help="Run A/B verdict benchmark — the definitive SOMA vs no-SOMA test")
    benchmark_parser.add_argument("--tasks", nargs="*", default=None,
                                  help="Task names to run (default: all 10). Use 'soma benchmark --ab --tasks linked_list_with_bugs state_machine'")
    benchmark_parser.add_argument("--model", type=str, default="claude-haiku-4-5-20251001",
                                  help="Model for live/ab benchmark (default: claude-haiku-4-5-20251001)")

    # ---- System ----
    subparsers.add_parser("version", help="Print the SOMA version and exit")
    subparsers.add_parser("doctor", help="Check SOMA installation health")

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

    if args.command == "policy":
        _cmd_policy(args)
        return

    if args.command == "setup":
        _cmd_setup(args)
        return

    dispatch = {
        "init": _cmd_init,
        "install": _cmd_install,
        "update": _cmd_install,
        "stats": _cmd_stats,
        "status": _cmd_status,
        "agents": _cmd_agents,
        "prune": _cmd_prune,
        "reset": _cmd_reset,
        "stop": _cmd_stop,
        "start": _cmd_start,
        "uninstall-claude": _cmd_uninstall_claude,
        "mode": _cmd_mode,
        "replay": _cmd_replay,
        "setup-claude": lambda _: __import__(
            "soma.cli.setup_claude", fromlist=["run_setup_claude"]
        ).run_setup_claude(),
        "report": _cmd_report,
        "analytics": _cmd_analytics,
        "version": _cmd_version,
        "doctor": _cmd_doctor,
        "benchmark": _cmd_benchmark,
        "dashboard": _cmd_dashboard,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
