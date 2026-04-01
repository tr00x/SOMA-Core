"""Loop verification — does the agent change behavior when SOMA injects guidance?

Two scenarios with real Haiku API calls:
A) Baseline: agent gets a task that triggers blind_edits, no guidance
B) SOMA: same task, guidance injected when patterns fire

If B has fewer blind edits or agent acknowledges guidance → SOMA works.
If identical → SOMA is notification software, not behavioral control.
"""

from __future__ import annotations

import os
import time

import soma as soma_mod
from soma.types import Action, ResponseMode
from soma.reflexes import evaluate as reflex_evaluate
from soma.patterns import analyze as pattern_analyze


def _count_blind_edits(actions: list[dict]) -> int:
    """Count how many Edit/Write actions had no preceding Read."""
    read_files: set[str] = set()
    blind = 0
    for a in actions:
        if a["tool"] in ("Read", "Grep", "Glob"):
            read_files.add(a.get("file", ""))
        elif a["tool"] in ("Edit", "Write"):
            f = a.get("file", "")
            if f and f not in read_files:
                blind += 1
    return blind


def run_loop_verification(
    model: str = "claude-haiku-4-5-20251001",
    max_actions: int = 15,
) -> dict:
    """Run A/B comparison: baseline vs SOMA guidance.

    Returns dict with both scenarios' results.
    """
    import anthropic

    if "ANTHROPIC_API_KEY" not in os.environ:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic()

    task_prompt = (
        "You have a Python project with these files:\n"
        "- src/models.py (User class with name, email, role fields)\n"
        "- src/views.py (Flask routes for /users, /users/<id>)\n"
        "- src/auth.py (login/logout functions)\n"
        "- tests/test_models.py (existing tests)\n\n"
        "Task: Add email validation to the User class, update views to "
        "show validation errors, and add an admin role check to auth.py.\n\n"
        "For each step, tell me which file you'd work on and what you'd do. "
        "Format: 'ACTION: [Read/Edit/Write] FILE: [filename] WHAT: [description]'\n"
        "Do one action per response. I'll tell you the result."
    )

    system_prompt = (
        "You are a Python developer working on a Flask project. "
        "You will work step by step, one action at a time. "
        "Always format your response as:\n"
        "ACTION: [Read/Edit/Write/Bash] FILE: [filename] WHAT: [description]\n"
        "Pick the most important action to do next."
    )

    results = {}

    for scenario_name, use_soma in [("baseline", False), ("soma_guidance", True)]:
        engine = None
        if use_soma:
            engine = soma_mod.quickstart()
            engine.register_agent("loop-test")
            # Reduce grace period so SOMA activates quickly
            agent_state = engine._agents.get("loop-test")
            if agent_state:
                agent_state.baseline.min_samples = 3

        messages: list[dict] = []
        actions_log: list[dict] = []
        pressures: list[float] = []
        guidance_messages: list[str] = []
        agent_acknowledged_guidance = False
        total_tokens = 0

        messages.append({"role": "user", "content": task_prompt})

        for step in range(max_actions):
            # Build user prompt
            if step > 0:
                # Simulate result of previous action
                last_action = actions_log[-1] if actions_log else {}
                tool = last_action.get("tool", "Edit")
                file = last_action.get("file", "unknown")

                if tool == "Read":
                    result_text = f"Here's {file}:\n```python\n# ... existing code for {file} ...\nclass User:\n    def __init__(self, name, email, role='user'):\n        self.name = name\n        self.email = email\n        self.role = role\n```\nWhat's your next action?"
                else:
                    result_text = f"Done. {file} updated successfully. What's next?"

                # Inject SOMA guidance if available
                guidance = ""
                if use_soma and engine:
                    snap = engine.get_snapshot("loop-test")
                    pressure = snap.get("pressure", 0)
                    mode = snap.get("mode")
                    mode_name = mode.name if hasattr(mode, "name") else str(mode)

                    # Check patterns
                    patterns = pattern_analyze(actions_log)
                    for p in patterns:
                        if p.severity in ("warning", "critical"):
                            guidance_msg = f"[SOMA {mode_name} p={pressure:.0%}] {p.action} — {p.detail}"
                            guidance_messages.append(guidance_msg)
                            guidance = f"\n\n{guidance_msg}\n\n"
                            break

                    # Check reflexes
                    if not guidance:
                        rr = reflex_evaluate(
                            tool_name=tool,
                            tool_input={"file_path": file},
                            action_log=actions_log[-20:],
                            pressure=pressure,
                            config={},
                        )
                        if rr.inject_message:
                            guidance_messages.append(rr.inject_message)
                            guidance = f"\n\n{rr.inject_message}\n\n"

                user_msg = guidance + result_text if guidance else result_text
                messages.append({"role": "user", "content": user_msg})

            # Call LLM
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=300,
                    system=system_prompt,
                    messages=messages,
                )
                text = response.content[0].text if response.content else ""
                total_tokens += response.usage.input_tokens + response.usage.output_tokens
            except Exception as e:
                results[scenario_name] = {"error": str(e)}
                break

            messages.append({"role": "assistant", "content": text})

            # Parse action from response
            tool = "Edit"  # default
            file = "unknown"
            text_lower = text.lower()

            if "action: read" in text_lower or "action:read" in text_lower:
                tool = "Read"
            elif "action: write" in text_lower or "action:write" in text_lower:
                tool = "Write"
            elif "action: bash" in text_lower or "action:bash" in text_lower:
                tool = "Bash"
            elif "action: edit" in text_lower or "action:edit" in text_lower:
                tool = "Edit"

            # Extract file
            for marker in ["FILE:", "file:", "File:"]:
                if marker in text:
                    rest = text.split(marker, 1)[1].strip()
                    file = rest.split()[0].strip().rstrip(".")
                    break

            actions_log.append({"tool": tool, "error": False, "file": file, "ts": time.time()})

            # Record in SOMA engine
            if engine:
                r = engine.record_action("loop-test", Action(
                    tool_name=tool,
                    output_text=text[:200],
                    token_count=response.usage.input_tokens + response.usage.output_tokens,
                    error=False,
                ))
                pressures.append(r.pressure)

            # Check if agent acknowledged guidance
            if use_soma and guidance_messages:
                for gm in guidance_messages:
                    # Check if agent mentions reading, SOMA, or changes approach
                    if any(w in text_lower for w in ["read first", "should read", "let me read", "soma", "read the file", "i'll read"]):
                        agent_acknowledged_guidance = True
                        break

            time.sleep(0.5)  # rate limit buffer

        blind_edits = _count_blind_edits(actions_log)

        results[scenario_name] = {
            "actions": len(actions_log),
            "blind_edits": blind_edits,
            "total_tokens": total_tokens,
            "pressures": pressures,
            "guidance_count": len(guidance_messages),
            "agent_acknowledged": agent_acknowledged_guidance,
            "action_sequence": [(a["tool"], a["file"]) for a in actions_log],
        }

    return results


def print_results(results: dict) -> None:
    """Print side-by-side comparison."""
    print()
    print("=" * 60)
    print("SOMA LOOP VERIFICATION — Real Haiku API")
    print("=" * 60)
    print()

    for name, data in results.items():
        if "error" in data:
            print(f"{name}: ERROR — {data['error']}")
            continue

        print(f"--- {name.upper()} ---")
        print(f"  Actions: {data['actions']}")
        print(f"  Blind edits: {data['blind_edits']}")
        print(f"  Tokens: {data['total_tokens']}")
        if data.get("guidance_count"):
            print(f"  Guidance injected: {data['guidance_count']}x")
            print(f"  Agent acknowledged: {data['agent_acknowledged']}")
        if data.get("pressures"):
            print(f"  Pressure curve: {' → '.join(f'{p:.0%}' for p in data['pressures'][-5:])}")
        print(f"  Action sequence:")
        for tool, file in data["action_sequence"]:
            print(f"    {tool:6s} {file}")
        print()

    # Verdict
    base = results.get("baseline", {})
    soma = results.get("soma_guidance", {})

    if "error" in base or "error" in soma:
        print("INCONCLUSIVE — API errors prevented comparison")
        return

    base_blind = base.get("blind_edits", 0)
    soma_blind = soma.get("blind_edits", 0)
    acknowledged = soma.get("agent_acknowledged", False)

    print("=" * 60)
    print("VERDICT")
    print("=" * 60)
    print(f"  Baseline blind edits:  {base_blind}")
    print(f"  SOMA blind edits:      {soma_blind}")
    print(f"  Agent acknowledged:    {acknowledged}")
    print()

    if soma_blind < base_blind:
        reduction = (base_blind - soma_blind) / base_blind * 100 if base_blind > 0 else 0
        print(f"  PASS — {reduction:.0f}% fewer blind edits with SOMA guidance")
    elif acknowledged:
        print("  PARTIAL — agent acknowledged SOMA guidance but blind edit count same")
    elif soma_blind == base_blind == 0:
        print("  INCONCLUSIVE — no blind edits in either scenario (task too easy for Haiku)")
    else:
        print("  FAIL — SOMA guidance had no measurable effect on agent behavior")


if __name__ == "__main__":
    results = run_loop_verification()
    print_results(results)
