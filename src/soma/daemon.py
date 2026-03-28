"""SOMA Daemon — background process that polls inbox, processes commands, exports state."""

from __future__ import annotations

import time
import signal
import sys

from soma.engine import SOMAEngine
from soma.inbox import process_inbox
from soma.commands import process_commands


def run_daemon(
    budget: dict[str, float] | None = None,
    poll_interval: float = 1.0,
) -> None:
    """Run SOMA as a background daemon. Polls inbox every poll_interval seconds."""

    engine = SOMAEngine(budget=budget or {"tokens": 500_000, "cost_usd": 50.0})

    running = True
    def handle_signal(sig, frame):
        nonlocal running
        running = False
        print("\nSOMA daemon shutting down...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"SOMA daemon started — polling every {poll_interval}s")
    print(f"  Inbox: ~/.soma/inbox/")
    print(f"  Commands: ~/.soma/commands/")
    print(f"  State: ~/.soma/state.json")
    print()

    while running:
        # 1. Process inbox (new actions from Claude Code hooks)
        actions_count = process_inbox(engine)

        # 2. Process commands (from Paperclip plugin UI)
        cmd_results = process_commands(engine)

        # 3. Export state for plugin to read
        engine.export_state()

        # Log activity
        if actions_count > 0 or cmd_results:
            agents = list(engine._agents.keys())
            max_p = max((engine.get_snapshot(a)["pressure"] for a in agents), default=0)
            print(f"[SOMA] {actions_count} actions | {len(cmd_results)} cmds | {len(agents)} agents | max_p={max_p:.3f}")

        time.sleep(poll_interval)

    # Final export
    engine.export_state()
    print("SOMA daemon stopped.")


if __name__ == "__main__":
    run_daemon()
