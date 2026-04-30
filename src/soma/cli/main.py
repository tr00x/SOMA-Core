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


def _cmd_healing(args: argparse.Namespace) -> None:
    """Re-derive tool-to-tool healing transitions from analytics.db."""
    from soma.healing_validation import (
        format_report, measure_transitions, write_markdown_report,
    )
    rows = measure_transitions(min_n=max(1, int(getattr(args, "min_n", 20) or 20)))
    print(format_report(rows, limit=int(getattr(args, "limit", 10) or 10)))
    out = getattr(args, "out", None)
    if out:
        try:
            write_markdown_report(Path(out), rows)
            print(f"\n  Markdown table written → {out}")
        except OSError as e:
            print(f"\n  Error: cannot write to {out}: {e}")
            sys.exit(1)


_ALLOWED_HELPED_DEFINITIONS = frozenset({
    "delta", "pressure_drop", "tool_switch", "error_resolved",
})


def _validate_definition(definition: str) -> str:
    """Defense-in-depth allowlist for the --definition flag.

    The argparse parser already restricts CLI input via ``choices=``,
    but this function is also reachable from scripts and replay tools
    that build the args namespace by hand. The f-string interpolation
    of the column name in the SELECT below makes this a SQL-identifier
    injection vector for any caller that bypasses argparse.
    """
    if not isinstance(definition, str) or definition not in _ALLOWED_HELPED_DEFINITIONS:
        raise ValueError(
            f"invalid --definition {definition!r}; "
            f"allowed: {sorted(_ALLOWED_HELPED_DEFINITIONS)}"
        )
    return definition


def _cmd_validate_patterns(args: argparse.Namespace) -> None:
    """Run the A/B validation report for contextual-guidance patterns.

    2026-04-19+. Reads from the ``ab_outcomes`` table and prints a
    per-pattern classification (treatment Δp / control Δp / p-value /
    effect size / status).

    2026-04-27 adds ``--horizon`` (1/2/5/10/all) so each pattern can be
    validated at the recovery window that fits its dynamics, and
    ``--definition`` which annotates the report with the multi-helped
    breakdown from ``guidance_outcomes`` for the chosen definition.
    """
    import json as _json
    from soma import ab_control
    from soma.analytics import AnalyticsStore

    family = getattr(args, "family", None)
    min_pairs = int(getattr(args, "min_pairs", ab_control.DEFAULT_MIN_PAIRS) or ab_control.DEFAULT_MIN_PAIRS)
    want_json = bool(getattr(args, "json", False))
    horizon_arg = str(getattr(args, "horizon", "2"))
    definition = _validate_definition(str(getattr(args, "definition", "delta")))

    if horizon_arg == "all":
        horizons: list[int] = [1, 2, 5, 10]
    else:
        horizons = [int(horizon_arg)]

    store = AnalyticsStore()
    try:
        patterns = store.list_ab_patterns(agent_family=family)
    except Exception as exc:
        print(f"  Error reading ab_outcomes table: {exc}")
        sys.exit(1)

    # rows_by_horizon[horizon] = list[ValidationResult] for that horizon.
    rows_by_horizon: dict[int, list[ab_control.ValidationResult]] = {}
    for h in horizons:
        h_rows: list[ab_control.ValidationResult] = []
        for pattern in patterns:
            outcomes = store.get_ab_outcomes(pattern=pattern, agent_family=family)
            h_rows.append(
                ab_control.validate(
                    outcomes,
                    pattern=pattern,
                    agent_family=family,
                    min_pairs=min_pairs,
                    horizon=h,
                )
            )
        rows_by_horizon[h] = h_rows

    # --definition stays report-side: pull aggregate helped-X% from
    # guidance_outcomes for each pattern and add it to the JSON / table.
    # The t-test itself is delta-based (ab_outcomes does not yet carry
    # per-firing helped_* booleans — that would need a 7th migration).
    multi_def_stats: dict[str, dict[str, float | None]] = {}
    if definition != "delta":
        column = f"helped_{definition}"
        try:
            for pattern in patterns:
                cur = store._conn.execute(
                    f"SELECT AVG({column} * 1.0), COUNT({column}) "
                    f"FROM guidance_outcomes WHERE pattern_key = ? "
                    f"AND {column} IS NOT NULL",
                    (pattern,),
                )
                avg, count = cur.fetchone()
                multi_def_stats[pattern] = {
                    "rate": None if avg is None else float(avg),
                    "n": int(count or 0),
                }
        except Exception as exc:
            print(f"  Warning: --definition stats unavailable ({exc})")

    # rows = "primary" horizon for the table (h=2 by default; first in
    # all-mode). Status colour comes from this horizon.
    primary_horizon = horizons[0]
    rows = rows_by_horizon[primary_horizon]

    if want_json:
        payload = []
        for i, r in enumerate(rows):
            entry: dict[str, Any] = {
                "pattern": r.pattern,
                "agent_family": r.agent_family,
                "fires_treatment": r.fires_treatment,
                "fires_control": r.fires_control,
                "mean_treatment_delta": r.mean_treatment_delta,
                "mean_control_delta": r.mean_control_delta,
                "delta_difference": r.delta_difference,
                "p_value": r.p_value,
                "effect_size": r.effect_size,
                "status": r.status,
                "horizon": primary_horizon,
            }
            if horizon_arg == "all":
                entry["horizons"] = {
                    str(h): {
                        "fires_treatment": rows_by_horizon[h][i].fires_treatment,
                        "fires_control": rows_by_horizon[h][i].fires_control,
                        "mean_treatment_delta": rows_by_horizon[h][i].mean_treatment_delta,
                        "mean_control_delta": rows_by_horizon[h][i].mean_control_delta,
                        "p_value": rows_by_horizon[h][i].p_value,
                        "effect_size": rows_by_horizon[h][i].effect_size,
                        "status": rows_by_horizon[h][i].status,
                    }
                    for h in horizons
                }
            if multi_def_stats:
                entry["definition"] = definition
                entry["definition_stats"] = multi_def_stats.get(r.pattern)
            payload.append(entry)
        print(_json.dumps(payload, indent=2))
        return

    if not rows:
        scope = f"family={family}" if family else "global"
        print(
            f"  No A/B outcomes recorded yet ({scope}). "
            f"After install 2026-04-19, let SOMA observe ~30 firings per pattern,\n"
            "  then re-run this command for a classification report."
        )
        return

    # Human-readable table.
    title_scope = "family=" + family if family else "all families"
    title_horizon = (
        f", horizon=all (primary h={primary_horizon})"
        if horizon_arg == "all"
        else f", horizon=h{primary_horizon}"
    )
    try:
        from rich.console import Console
        from rich.table import Table
        table = Table(
            title=f"SOMA pattern validation ({title_scope}{title_horizon})"
        )
        table.add_column("Pattern", style="bold")
        table.add_column("T n", justify="right")
        table.add_column("C n", justify="right")
        table.add_column("mean Δp (T)", justify="right")
        table.add_column("mean Δp (C)", justify="right")
        table.add_column("diff", justify="right")
        table.add_column("p", justify="right")
        table.add_column("d", justify="right")
        table.add_column("status", style="bold")
        if horizon_arg == "all":
            table.add_column("p @ horizons", justify="right")
        if multi_def_stats:
            table.add_column(f"helped_{definition}", justify="right")
        status_color = {
            "validated": "green",
            "refuted": "red",
            "inconclusive": "yellow",
            "collecting": "cyan",
        }
        for i, r in enumerate(rows):
            color = status_color.get(r.status, "white")
            cells = [
                r.pattern,
                str(r.fires_treatment),
                str(r.fires_control),
                f"{r.mean_treatment_delta:+.3f}",
                f"{r.mean_control_delta:+.3f}",
                f"{r.delta_difference:+.3f}",
                "—" if r.p_value is None else f"{r.p_value:.4f}",
                "—" if r.effect_size is None else f"{r.effect_size:+.2f}",
                f"[{color}]{r.status}[/{color}]",
            ]
            if horizon_arg == "all":
                cells.append(
                    " ".join(
                        f"h{h}:{rows_by_horizon[h][i].p_value:.3f}"
                        if rows_by_horizon[h][i].p_value is not None
                        else f"h{h}:—"
                        for h in horizons
                    )
                )
            if multi_def_stats:
                stat = multi_def_stats.get(r.pattern) or {}
                rate = stat.get("rate")
                n = stat.get("n", 0)
                if rate is None:
                    cells.append(f"— (n={n})")
                else:
                    cells.append(f"{rate * 100:.0f}% (n={n})")
            table.add_row(*cells)
        Console().print(table)
    except Exception:
        # rich is a hard dep but if something goes sideways we still
        # want a plain fallback so the CLI never crashes.
        header = f"{'pattern':<18} T  C   ΔpT      ΔpC      diff    p        d     status"
        if multi_def_stats:
            header += f"   helped_{definition}"
        print(header)
        for r in rows:
            p = "—" if r.p_value is None else f"{r.p_value:.4f}"
            d = "—" if r.effect_size is None else f"{r.effect_size:+.2f}"
            line = (
                f"{r.pattern:<18} {r.fires_treatment:>3} {r.fires_control:>3} "
                f"{r.mean_treatment_delta:+.3f}  {r.mean_control_delta:+.3f}  "
                f"{r.delta_difference:+.3f}  {p:<7} {d:<5} {r.status}"
            )
            if multi_def_stats:
                stat = multi_def_stats.get(r.pattern) or {}
                rate = stat.get("rate")
                n = stat.get("n", 0)
                line += (
                    f"   — (n={n})" if rate is None
                    else f"   {rate * 100:.0f}% (n={n})"
                )
            print(line)


def _cmd_unblock(args: argparse.Namespace) -> None:
    """Clear strict-mode blocks for an agent family.

    Modes:
        soma unblock --agent cc-92331               → clear all blocks
        soma unblock --agent cc-92331 --pattern X   → silence X for 30 min
        soma unblock --all                          → clear every family's file
    """
    from soma import blocks as _blocks

    pattern = getattr(args, "pattern", None)
    clear_all = bool(getattr(args, "all", False))
    agent_id = getattr(args, "agent_id", None) or "claude-code"

    if clear_all and pattern:
        print("  Error: --all and --pattern are mutually exclusive. "
              "Use --all (clears every family) or --pattern X "
              "(silences X for the given --agent family).")
        sys.exit(2)

    if clear_all:
        soma_dir = _blocks.SOMA_DIR
        removed = 0
        if soma_dir.exists():
            for path in soma_dir.glob("blocks_*.json"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
        print(f"  Cleared {removed} family block file(s).")
        return

    state = _blocks.load_block_state(agent_id)

    if pattern:
        deadline = state.silence_pattern(pattern)
        _blocks.save_block_state(state)
        mins = int((deadline - time_time()) / 60)
        print(f"  Silenced '{pattern}' for family {state.family} — ~{mins} min.")
        return

    removed = state.clear_block()
    _blocks.save_block_state(state)
    print(f"  Cleared {removed} block(s) for family {state.family}.")


def time_time():  # pragma: no cover — trivial indirection for testability
    import time as _t
    return _t.time()


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
        # Show current preset and available presets.
        config = load_config()
        current = config.get("soma", {}).get("mode", "relaxed")
        # `soma.mode` in config can hold either a *preset* name
        # (strict/relaxed/autonomous) or an *engine* mode
        # (observe/guide/reflex). Disambiguate so the user doesn't
        # see "Current mode: guide" then try `soma mode guide` and
        # crash.
        is_preset = current in MODE_PRESETS
        if is_preset:
            print(f"  Current preset: {current}")
        else:
            print(f"  Current engine mode: {current}")
            print("  (no preset applied — pick one below)")
        print()
        for name, preset in MODE_PRESETS.items():
            autonomy = preset["agents"]["claude-code"]["autonomy"]
            block_threshold = preset["thresholds"]["block"]
            verbosity = preset["hooks"]["verbosity"]
            marker = " <--" if (is_preset and name == current) else ""
            print(f"  {name:<12} autonomy={autonomy}, block={block_threshold:.0%}, verbosity={verbosity}{marker}")
        print()
        print("  Usage: soma mode <strict|relaxed|autonomous>")
        return

    mode_name = args.mode_name
    config = load_config()
    try:
        config = apply_mode(config, mode_name)
    except ValueError as e:
        # 2026-04-27 onward: don't crash with a traceback; print the helpful
        # message and exit non-zero so scripts can detect failure.
        print(f"  Error: {e}")
        print(f"  Usage: soma mode <{' | '.join(MODE_PRESETS)}>")
        sys.exit(1)
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
        issues.append("soma-hook not in PATH — run: uv tool install soma-ai  (or pip install soma-ai)")

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
            "  soma unblock [--agent id]       Clear strict-mode blocks (2026-04-19)\n"
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
            "  soma healing                    Measure tool-to-tool pressure deltas\n"
            "\n"
            "Session:\n"
            "  soma replay <file>              Replay a recorded session file\n"
            "  soma prune [--older-than N]     Remove stale ~/.soma/sessions entries\n"
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
    healing_parser = subparsers.add_parser(
        "healing", help="Measure tool-to-tool pressure deltas from analytics.db",
    )
    healing_parser.add_argument("--min-n", type=int, default=20, dest="min_n",
                                help="Minimum observations per transition (default 20)")
    healing_parser.add_argument("--limit", type=int, default=10,
                                help="How many transitions to show per side (default 10)")
    healing_parser.add_argument("--out", default=None,
                                help="Optional path to write a markdown table")

    validate_parser = subparsers.add_parser(
        "validate-patterns",
        help="A/B validation report for contextual-guidance patterns",
    )
    validate_parser.add_argument(
        "--family", default=None,
        help="Filter to a single agent family (e.g. 'cc'); default: all",
    )
    validate_parser.add_argument(
        "--min-pairs", type=int, default=None, dest="min_pairs",
        help="Minimum firings per arm before classifying "
             "(default: ab_control.DEFAULT_MIN_PAIRS)",
    )
    validate_parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of the human-readable table",
    )
    validate_parser.add_argument(
        "--horizon", default="2",
        choices=["1", "2", "5", "10", "all"],
        help=("Recovery horizon for the t-test: 1, 2 (default), 5, 10, "
              "or 'all' to print verdicts at every horizon side-by-side"),
    )
    validate_parser.add_argument(
        "--definition", default="delta",
        choices=["delta", "pressure_drop", "tool_switch", "error_resolved"],
        help=("Helped definition surfaced alongside the t-test: 'delta' "
              "(default, pressure-based) or one of the three orthogonal "
              "definitions from guidance_outcomes (pressure_drop / "
              "tool_switch / error_resolved). The t-test itself stays "
              "delta-based — definition flags annotate the report."),
    )

    unblock_parser = subparsers.add_parser(
        "unblock", help="Clear strict-mode blocks or silence a pattern",
    )
    unblock_parser.add_argument("--agent", dest="agent_id", default=None,
                                help="Agent id (family-derived); defaults to claude-code")
    unblock_parser.add_argument("--pattern", default=None,
                                help="Silence a single pattern for 30 min instead of clearing")
    unblock_parser.add_argument("--all", action="store_true",
                                help="Remove every family's block file")

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
        "healing": _cmd_healing,
        "validate-patterns": _cmd_validate_patterns,
        "unblock": _cmd_unblock,
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
        "dashboard": _cmd_dashboard,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
