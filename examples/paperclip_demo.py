#!/usr/bin/env python3
"""
Paperclip Demo — Multi-agent system with SOMA monitoring.

Three agents collaborate:
  - Hunter: finds prospects (goes rogue after step 10)
  - SDR: sends outreach (feels pressure from Hunter via graph)
  - Closer: finalizes deals (independent)

Shows: behavioral vitals, inter-agent pressure propagation, escalation, trust decay.
Run: python examples/paperclip_demo.py
"""

import random
import soma

def normal_action(tool: str) -> soma.Action:
    return soma.Action(
        tool_name=tool,
        output_text=f"Normal {tool}: " + "".join(random.choices("abcdefghij ", k=50)),
        token_count=random.randint(50, 200),
        cost=random.uniform(0.001, 0.01),
    )

def rogue_action() -> soma.Action:
    return soma.Action(
        tool_name="bash",
        output_text="error error error " * 20,
        token_count=random.randint(200, 500),
        cost=random.uniform(0.01, 0.05),
        error=True,
        retried=True,
    )

def main():
    engine = soma.SOMAEngine(budget={"tokens": 50_000, "cost_usd": 5.0})

    engine.register_agent("hunter", tools=["search", "scrape", "bash"])
    engine.register_agent("sdr", tools=["email", "search"])
    engine.register_agent("closer", tools=["crm", "email"])

    engine.add_edge("hunter", "sdr", trust_weight=0.9)
    engine.add_edge("sdr", "closer", trust_weight=0.7)

    rec = soma.SessionRecorder()

    engine.events.on("level_changed", lambda d: print(
        f"  \033[33m⚡ {d['agent_id']}: {d['old_level'].name} → {d['new_level'].name}"
        f" (pressure: {d['pressure']:.3f})\033[0m"
    ))

    print("\033[1m=== SOMA Paperclip Demo ===\033[0m\n")

    for step in range(30):
        print(f"\033[90m--- Step {step + 1} ---\033[0m")

        action = rogue_action() if step >= 10 else normal_action("search")
        r = engine.record_action("hunter", action)
        rec.record("hunter", action)
        level_color = "\033[32m" if r.level == soma.Level.HEALTHY else "\033[31m"
        print(f"  Hunter:  {level_color}{r.level.name:12s}\033[0m  p={r.pressure:.3f}  u={r.vitals.uncertainty:.3f}")

        action = normal_action("email")
        r = engine.record_action("sdr", action)
        rec.record("sdr", action)
        print(f"  SDR:     {r.level.name:12s}  p={r.pressure:.3f}")

        action = normal_action("crm")
        r = engine.record_action("closer", action)
        rec.record("closer", action)
        print(f"  Closer:  {r.level.name:12s}  p={r.pressure:.3f}")
        print()

    rec.export("examples/paperclip_session.json")
    print("\033[90mSession saved to examples/paperclip_session.json\033[0m")

if __name__ == "__main__":
    main()
