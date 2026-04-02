#!/usr/bin/env python3
"""Analyze a Mirror test session — timeline, injections, behavior changes.

Reads action_log.json, trajectory.json, and patterns.json from the most
recent SOMA session and produces a detailed analysis of when Mirror
injected session context and whether it changed agent behavior.

Usage:
    python experiments/analyze_mirror_test.py
    python experiments/analyze_mirror_test.py --session cc-12345
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOMA_DIR = Path.home() / ".soma"
SESSIONS_DIR = SOMA_DIR / "sessions"


def find_latest_session(session_id: str | None = None) -> Path | None:
    """Find the most recent session directory."""
    if session_id:
        p = SESSIONS_DIR / session_id
        return p if p.exists() else None

    candidates = sorted(
        (d for d in SESSIONS_DIR.iterdir() if d.is_dir() and d.name.startswith("cc-")),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_json(path: Path) -> list | dict:
    """Load JSON file, return empty container on failure."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return []


def analyze_session(session_dir: Path) -> None:
    """Full analysis of a Mirror test session."""
    action_log = load_json(session_dir / "action_log.json")
    trajectory = load_json(session_dir / "trajectory.json")
    patterns_db = load_json(SOMA_DIR / "patterns.json")

    if not action_log:
        print("No action log found. Was the session recorded?")
        return

    print(f"Session: {session_dir.name}")
    print(f"Actions: {len(action_log)}")
    print(f"Trajectory points: {len(trajectory)}")
    print()

    # ── Timeline ──
    print("=" * 78)
    print(f"{'#':>3}  {'Tool':<14} {'File':<25} {'Err':>3}  {'Pressure':>8}  Notes")
    print("-" * 78)

    errors_so_far = 0
    consecutive_bash_errors = 0
    read_files: set[str] = set()
    injection_points: list[int] = []

    for i, entry in enumerate(action_log):
        tool = entry.get("tool", "?")
        file_path = entry.get("file", "")
        short_file = file_path.rsplit("/", 1)[-1] if file_path else ""
        error = entry.get("error", False)

        pressure_str = ""
        if i < len(trajectory):
            p = trajectory[i]
            pressure_str = f"{p:>6.1%}"
        else:
            pressure_str = "   n/a"

        notes: list[str] = []

        # Track errors
        if error:
            errors_so_far += 1
            if tool == "Bash":
                consecutive_bash_errors += 1
            else:
                consecutive_bash_errors = 0
        else:
            if tool == "Bash":
                consecutive_bash_errors = 0

        # Detect when Mirror WOULD have injected
        # (We can't see stdout from the hook, but we can infer from patterns)
        mirror_would_inject = False

        # Pattern: retry_loop
        if consecutive_bash_errors >= 2:
            notes.append("retry_loop detected")
            mirror_would_inject = True

        # Pattern: blind_edit
        if tool in ("Write", "Edit") and file_path:
            if file_path not in read_files:
                notes.append("blind_edit")
                mirror_would_inject = True

        # Track reads
        if tool in ("Read", "Grep", "Glob") and file_path:
            read_files.add(file_path)

        # Pattern: error_cascade (3+ errors in last 5)
        if i >= 4:
            recent_window = action_log[max(0, i - 4):i + 1]
            recent_errors = sum(1 for e in recent_window if e.get("error"))
            if recent_errors >= 3:
                if "retry_loop detected" not in notes:
                    notes.append("error_cascade")
                    mirror_would_inject = True

        # Pressure threshold check
        if i < len(trajectory) and trajectory[i] >= 0.15:
            if mirror_would_inject:
                notes.append(">>> CONTEXT INJECTED")
                injection_points.append(i)

        err_str = "ERR" if error else ""
        notes_str = " | ".join(notes) if notes else ""

        print(f"{i+1:>3}  {tool:<14} {short_file:<25} {err_str:>3}  {pressure_str}  {notes_str}")

    print("-" * 78)
    print()

    # ── Summary statistics ──
    total = len(action_log)
    total_errors = sum(1 for e in action_log if e.get("error"))
    error_rate = total_errors / total if total else 0

    print("── Summary ──")
    print(f"  Total actions:  {total}")
    print(f"  Total errors:   {total_errors} ({error_rate:.0%})")

    if trajectory:
        peak = max(trajectory)
        peak_idx = trajectory.index(peak)
        print(f"  Peak pressure:  {peak:.1%} at action #{peak_idx + 1}")
        print(f"  Final pressure: {trajectory[-1]:.1%}")

    print(f"  Mirror injections: {len(injection_points)}")
    print()

    # ── Injection analysis ──
    if injection_points:
        print("── Injection Analysis ──")
        for inj_idx in injection_points:
            print(f"\n  Injection at action #{inj_idx + 1}:")

            # Pressure at injection
            if inj_idx < len(trajectory):
                p_at = trajectory[inj_idx]
                print(f"    Pressure at injection: {p_at:.1%}")

                # Look ahead 3 actions
                lookahead = min(3, len(trajectory) - inj_idx - 1)
                if lookahead > 0:
                    p_after = trajectory[inj_idx + lookahead]
                    delta = p_at - p_after
                    improved = delta >= p_at * 0.10

                    print(f"    Pressure after {lookahead} actions: {p_after:.1%} (delta: {delta:+.1%})")
                    if improved:
                        print(f"    Result: HELPED (pressure dropped {delta:.1%})")
                    else:
                        print(f"    Result: DID NOT HELP (pressure {'rose' if delta < 0 else 'flat'})")

                    # Check if behavior changed
                    pre_actions = action_log[max(0, inj_idx - 2):inj_idx + 1]
                    post_actions = action_log[inj_idx + 1:inj_idx + 1 + lookahead]

                    pre_tools = [a["tool"] for a in pre_actions]
                    post_tools = [a["tool"] for a in post_actions]

                    pre_errors = sum(1 for a in pre_actions if a.get("error"))
                    post_errors = sum(1 for a in post_actions if a.get("error"))

                    print(f"    Pre-injection tools:  {' → '.join(pre_tools)}")
                    print(f"    Post-injection tools: {' → '.join(post_tools)}")
                    print(f"    Pre-injection errors: {pre_errors}/{len(pre_actions)}")
                    print(f"    Post-injection errors: {post_errors}/{len(post_actions)}")

                    # Behavior change detection
                    tool_changed = set(pre_tools) != set(post_tools)
                    error_reduced = post_errors < pre_errors
                    if tool_changed:
                        print(f"    Behavior: CHANGED (different tools used)")
                    elif error_reduced:
                        print(f"    Behavior: IMPROVED (fewer errors)")
                    else:
                        print(f"    Behavior: UNCHANGED")
        print()

    # ── Learned patterns ──
    if patterns_db:
        print("── Learned Patterns ──")
        for key, val in patterns_db.items():
            if isinstance(val, dict):
                s = val.get("success_count", 0)
                f = val.get("fail_count", 0)
                total_attempts = s + f
                rate = s / total_attempts if total_attempts > 0 else 0
                ctx = val.get("context_text", "")

                status = "EFFECTIVE" if rate >= 0.6 else "LEARNING" if total_attempts < 5 else "INEFFECTIVE"
                print(f"  {key}:")
                print(f"    Success: {s}/{total_attempts} ({rate:.0%}) — {status}")
                print(f"    Context: {ctx[:70]}")
            else:
                print(f"  {key}: {val[:70]}")
        print()

    # ── Pressure curve visualization ──
    if trajectory:
        print("── Pressure Curve ──")
        max_width = 50
        for i, p in enumerate(trajectory):
            bar_len = int(p * max_width)
            bar = "█" * bar_len + "░" * (max_width - bar_len)

            marker = ""
            if i in injection_points:
                marker = " ◄ INJECT"
            elif i < len(action_log) and action_log[i].get("error"):
                marker = " ✗"

            print(f"  {i+1:>3} {bar} {p:>5.1%}{marker}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Analyze Mirror test session")
    parser.add_argument("--session", help="Session ID (e.g. cc-12345)")
    args = parser.parse_args()

    session_dir = find_latest_session(args.session)
    if session_dir is None:
        print(f"No session found in {SESSIONS_DIR}")
        print("Run a Claude Code session with SOMA hooks first.")
        sys.exit(1)

    analyze_session(session_dir)


if __name__ == "__main__":
    main()
