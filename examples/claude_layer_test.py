#!/usr/bin/env python3
"""
Claude Layer Test — runs REAL Claude calls and writes state for the dashboard.

SETUP:
  Terminal 1:  soma          (opens dashboard, watches ~/.soma/state.json)
  Terminal 2:  python examples/claude_layer_test.py   (this script)

Watch Terminal 1 — agents will appear as Claude responds.
"""

import subprocess
import time
import sys

import soma
from soma.types import Action

# ── Config ──────────────────────────────────────────────────────

TASKS = {
    "Researcher": [
        "What is behavioral drift in AI agents? Answer in 2 sentences.",
        "Name 3 ways to detect when an AI agent is stuck in a loop.",
        "What is the difference between monitoring and observability for AI agents? Brief.",
        "How does inter-agent pressure propagation work? 2 sentences.",
        "What are the top 3 risks of unmonitored AI agents in production?",
    ],
    "Coder": [
        "Write a Python function that computes Shannon entropy of a string. Just code, no explanation.",
        "Write a Python function for cosine similarity between two float lists. Just code.",
        "Write a Python dataclass called AgentVitals with fields: uncertainty, drift, error_rate. Just code.",
        "Write a Python function that detects if a string is repetitive (e.g. 'aaa' or 'abcabc'). Just code.",
        "Write a Python function for exponential moving average with alpha parameter. Just code.",
    ],
    "Reviewer": [
        "Is sigmoid(x) = 1/(1+exp(-x+3)) a good activation for pressure mapping? Brief pros/cons.",
        "Review: using min(remaining/limit) across budget dimensions for health score. Good idea?",
        "Is EMA with alpha=0.15 too fast or too slow for baseline tracking? Brief opinion.",
        "Should an AI monitoring system cut agent context physically, or just alert? Brief opinion.",
        "Is 70/30 weighted-mean/max a good formula for aggregating multiple pressure signals?",
    ],
}


def call_claude(prompt: str) -> tuple[str, float, bool]:
    """Run a real Claude call. Returns (output, duration, error)."""
    start = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=60,
        )
        duration = time.time() - start
        output = result.stdout.strip() if result.stdout else ""
        error = result.returncode != 0 or not output
        return output, duration, error
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.time() - start, True
    except Exception as e:
        return str(e), time.time() - start, True


def main():
    print("\033[1mSOMA Claude Layer Test\033[0m")
    print("Real Claude calls via `claude -p`. Dashboard watches ~/.soma/state.json\n")

    # Create engine
    engine = soma.SOMAEngine(budget={"tokens": 100_000, "cost_usd": 2.0})

    for agent_id in TASKS:
        engine.register_agent(agent_id, tools=["claude"])

    # Connect: Researcher -> Coder -> Reviewer
    engine.add_edge("Researcher", "Coder", trust_weight=0.8)
    engine.add_edge("Coder", "Reviewer", trust_weight=0.7)

    engine.events.on("level_changed", lambda d: print(
        f"  \033[33m{d['agent_id']}: {d['old_level'].name} -> {d['new_level'].name} "
        f"(p={d['pressure']:.3f})\033[0m"
    ))

    # Export initial state
    engine.export_state()
    print("State file created. Open `soma` in another terminal to watch.\n")
    print("─" * 60)

    recorder = soma.SessionRecorder()
    total_calls = 0

    for round_num in range(len(list(TASKS.values())[0])):
        print(f"\n\033[1mRound {round_num + 1}\033[0m\n")

        for agent_id, tasks in TASKS.items():
            if round_num >= len(tasks):
                continue

            task = tasks[round_num]
            print(f"  {agent_id}: {task[:60]}...")
            sys.stdout.flush()

            output, duration, error = call_claude(task)
            total_calls += 1

            # Estimate tokens
            tokens = (len(task) + len(output)) // 4
            cost = tokens * 0.5 / 1_000_000

            action = Action(
                tool_name="claude",
                output_text=output[:500],
                token_count=tokens,
                cost=cost,
                error=error,
                duration_sec=duration,
            )

            result = engine.record_action(agent_id, action)
            recorder.record(agent_id, action)

            # Write state for dashboard
            engine.export_state()

            status = "\033[32mOK\033[0m" if not error else "\033[31mERR\033[0m"
            print(f"    {status}  {tokens}tok  {duration:.1f}s  "
                  f"level={result.level.name}  p={result.pressure:.3f}")

    print(f"\n{'─' * 60}")
    print(f"\033[1mDone.\033[0m {total_calls} real Claude calls.")
    print(f"Session saved to soma_layer_session.json")

    recorder.export("soma_layer_session.json")

    # Final state
    engine.export_state()

    # Print summary
    print(f"\n\033[1mAgent Summary:\033[0m")
    for agent_id in TASKS:
        snap = engine.get_snapshot(agent_id)
        level = snap["level"]
        pressure = snap["pressure"]
        print(f"  {agent_id:12s}  {level.name:12s}  p={pressure:.3f}  "
              f"actions={snap['action_count']}")


if __name__ == "__main__":
    main()
