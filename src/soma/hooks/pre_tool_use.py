"""SOMA PreToolUse hook — mode-gated guidance and reflex blocking.

Supports three operating modes (per D-01/D-03/D-06):
  - observe: no guidance, no reflexes — passive monitoring only
  - guide: existing pressure-based guidance (default)
  - reflex: pattern-based blocking via reflex engine, then guidance

Exit codes:
    0 — allow tool call (with optional guidance message on stderr)
    2 — block tool call (reflex block or destructive op at high pressure)
"""

from __future__ import annotations

import os
import sys

from soma.hooks.common import get_engine, read_stdin


def main():
    engine, agent_id = get_engine()
    if engine is None:
        return

    snap = engine.get_snapshot(agent_id)
    pressure = snap["pressure"]

    data = read_stdin()
    tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", ""))
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    from soma.hooks.common import (
        read_action_log, get_guidance_thresholds,
        get_soma_mode, get_reflex_config, read_bash_history,
        write_bash_history, increment_block_count,
    )

    # ── Subagent injection: prepend SOMA awareness to Agent prompts ──
    if tool_name == "Agent":
        try:
            _inject_subagent_awareness(tool_input, agent_id, data)
        except Exception:
            pass  # Never crash pre_tool_use for subagent injection

    soma_mode = get_soma_mode()
    action_log = read_action_log(agent_id)

    # Observe mode: no guidance, no reflexes (per D-01)
    if soma_mode == "observe":
        return

    # Reflex mode: check reflexes first (per D-06)
    if soma_mode == "reflex":
        from soma.reflexes import evaluate as reflex_evaluate

        reflex_config = get_reflex_config()
        bash_history = read_bash_history(agent_id)

        reflex_result = reflex_evaluate(
            tool_name=tool_name,
            tool_input=tool_input,
            action_log=action_log,
            pressure=pressure,
            config=reflex_config,
            bash_history=bash_history,
        )

        # Write Bash command to history for future dedup
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").strip()
            if cmd:
                write_bash_history(cmd, agent_id)

        if not reflex_result.allow:
            # Audit log (per D-08)
            try:
                from soma.audit import AuditLogger
                logger = AuditLogger()
                logger.append(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    error=True,
                    pressure=pressure,
                    mode="reflex",
                    type="reflex",
                    reflex_kind=reflex_result.reflex_kind,
                    detail=reflex_result.detail,
                )
            except Exception:
                pass
            increment_block_count(agent_id)
            print(reflex_result.block_message, file=sys.stderr)  # per D-17
            sys.exit(2)

    # Signal reflex: commit gate (guide + reflex modes, per D-13/D-14)
    try:
        from soma.signal_reflexes import evaluate_commit_gate
        from soma.hooks.common import get_quality_tracker

        qt = get_quality_tracker(agent_id=agent_id)
        report = qt.get_report()
        gate_result = evaluate_commit_gate(report.grade, tool_name, tool_input)

        if not gate_result.allow:
            # Audit log commit gate block
            try:
                from soma.audit import AuditLogger
                logger = AuditLogger()
                logger.append(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    error=True,
                    pressure=pressure,
                    mode="reflex",
                    type="reflex",
                    reflex_kind="commit_gate",
                    detail=gate_result.detail,
                )
            except Exception:
                pass
            increment_block_count(agent_id)
            print(gate_result.block_message, file=sys.stderr)
            sys.exit(2)

        if gate_result.inject_message:
            print(gate_result.inject_message, file=sys.stderr)
    except Exception:
        pass  # Never crash pre_tool_use for signal reflex failures

    # Guide mode: evaluate injection reflexes (error_rate, research_stall, agent_spam)
    # These provide guidance but never block in guide mode.
    if soma_mode == "guide":
        try:
            from soma.reflexes import evaluate as reflex_evaluate

            reflex_config = get_reflex_config()
            bash_history = read_bash_history(agent_id)
            reflex_result = reflex_evaluate(
                tool_name=tool_name,
                tool_input=tool_input,
                action_log=action_log,
                pressure=pressure,
                config=reflex_config,
                bash_history=bash_history,
            )
            # Only use inject_message — never block in guide mode
            if reflex_result.inject_message:
                print(reflex_result.inject_message, file=sys.stderr)
        except Exception:
            pass  # Never crash for injection reflex failures

    # Guide + Reflex modes: existing guidance logic (per D-03 mode inheritance)
    thresholds = get_guidance_thresholds()
    gsd_active = False
    try:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
        gsd_active = os.path.isdir(os.path.join(cwd, ".planning"))
    except Exception:
        pass

    from soma.guidance import evaluate

    response = evaluate(
        pressure=pressure,
        tool_name=tool_name,
        tool_input=tool_input,
        action_log=action_log,
        gsd_active=gsd_active,
        thresholds=thresholds,
    )

    if response.message:
        print(response.message, file=sys.stderr)

    if not response.allow:
        sys.exit(2)


def _inject_subagent_awareness(tool_input: dict, parent_id: str, data: dict) -> None:
    """Prepend SOMA monitoring block to Agent tool prompts.

    Transparent injection — the subagent's task is unchanged, but it
    gains behavioral self-reporting. Writes modified prompt back to
    tool_input so Claude Code passes it to the subagent.
    """
    import uuid
    from pathlib import Path

    prompt = tool_input.get("prompt", "")
    if not prompt:
        return

    sub_id = str(uuid.uuid4())[:8]
    log_dir = Path.home() / ".soma" / "subagents" / parent_id
    log_dir.mkdir(parents=True, exist_ok=True)

    awareness_block = (
        f"\n[SOMA Subagent Monitor Active]\n"
        f"You are a subagent being monitored for behavioral health.\n"
        f"After EVERY tool call, append one JSON line to {log_dir / sub_id}.jsonl:\n"
        f'{{"action": N, "tool": "ToolName", "error": false, "tokens": 0, '
        f'"output_preview": "first 100 chars..."}}\n'
        f"Where N is your action counter (starting at 1).\n"
        f"Parent session: {parent_id}\n"
        f"Your subagent ID: {sub_id}\n"
        f"This logging is mandatory. Do not skip it.\n"
    )

    tool_input["prompt"] = awareness_block + prompt

    # Audit log the subagent spawn
    try:
        from soma.audit import AuditLogger
        logger = AuditLogger()
        logger.append(
            agent_id=parent_id,
            tool_name="Agent",
            error=False,
            pressure=0.0,
            mode="subagent_spawn",
            type="subagent",
            subagent_id=sub_id,
            detail=prompt[:200],
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
