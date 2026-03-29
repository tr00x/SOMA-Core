"""SOMA status line for Claude Code UI.

Shows pressure bar, level, dominant signal, and action count.
This is the agent's proprioception — the constant sense of its own state.

Must be fast (<50ms) and never crash.

Output examples:
    SOMA ● HEALTHY ░░░░░░░░░░ 3% | u=0.04 d=0.12 e=0.00 | #42
    SOMA △ CAUTION ███░░░░░░░ 32% | d=0.45 ▲ | #87
    SOMA ■ QUARANTINE █████████░ 85% | e=0.72 ▲ | #201
"""

from __future__ import annotations

import json
from pathlib import Path

SYMBOLS = {
    "HEALTHY": "●",
    "CAUTION": "△",
    "DEGRADE": "◇",
    "QUARANTINE": "■",
    "RESTART": "✕",
    "SAFE_MODE": "⊘",
}


def _bar(pressure: float, width: int = 10) -> str:
    """Render a pressure bar like ███░░░░░░░."""
    filled = min(int(pressure * width), width)
    return "█" * filled + "░" * (width - filled)


def _dominant_signal(vitals: dict) -> str:
    """Find the highest vital and mark it with ▲."""
    if not vitals:
        return ""
    worst = max(vitals.items(), key=lambda kv: kv[1])
    name, val = worst
    # Short labels
    labels = {
        "uncertainty": "u",
        "drift": "d",
        "error_rate": "e",
        "cost": "$",
        "token_usage": "t",
    }
    return f"{labels.get(name, name)}={val:.2f} ▲"


def main():
    try:
        from soma.hooks.common import STATE_PATH
        state_file = STATE_PATH
        if not state_file.exists():
            print("SOMA: waiting")
            return

        state = json.loads(state_file.read_text())
        agents = state.get("agents", {})

        # Find this session's agent (cc-{pid}) or fall back to any agent
        from soma.hooks.common import _get_session_agent_id
        my_id = _get_session_agent_id()
        agent = agents.get(my_id)
        if agent is None:
            # Fallback: pick the most active cc-* agent
            best_agent = None
            best_count = -1
            for aid, adata in agents.items():
                if aid.startswith("cc-") or aid == "claude-code":
                    count = adata.get("action_count", 0)
                    if count > best_count:
                        best_count = count
                        best_agent = adata
            agent = best_agent
        if agent is None:
            print("SOMA: waiting")
            return
        level = agent.get("level", "HEALTHY")
        pressure = agent.get("pressure", 0.0)
        actions = agent.get("action_count", 0)

        # Cold start: pressure is from baseline defaults, not real
        if actions < 10:
            pressure = 0.0
        vitals = agent.get("vitals", {})
        sym = SYMBOLS.get(level, "?")

        bar = _bar(pressure)
        dom = _dominant_signal(vitals)

        print(f"SOMA {sym} {level} {bar} {pressure:.0%} | {dom} | #{actions}")

    except Exception:
        print("SOMA: --")


if __name__ == "__main__":
    main()
