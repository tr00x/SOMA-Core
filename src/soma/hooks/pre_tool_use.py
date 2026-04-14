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

    # ── Smart Guidance v2: signal-specific messages + cooldown/escalation ──
    thresholds = get_guidance_thresholds()
    gsd_active = False
    try:
        cwd = os.environ.get("CLAUDE_WORKING_DIRECTORY", os.getcwd())
        gsd_active = os.path.isdir(os.path.join(cwd, ".planning"))
    except Exception:
        pass

    from soma.hooks.common import (
        read_guidance_state, write_guidance_state,
        read_signal_pressures,
    )
    from soma.guidance import evaluate, find_dominant_signal, build_signal_message
    from soma.guidance_state import INVESTIGATION_TOOLS

    guidance_state = read_guidance_state(agent_id)
    action_count = snap.get("action_count", 0)

    # Load guidance config from soma.toml
    try:
        from soma.cli.config_loader import load_config
        guidance_cfg = load_config().get("guidance", {})
    except Exception:
        guidance_cfg = {}
    cooldown_actions = guidance_cfg.get("cooldown_actions", 5)
    escalation_enabled = guidance_cfg.get("escalation_enabled", True)
    throttle_enabled = guidance_cfg.get("throttle_enabled", True)
    max_escalation = guidance_cfg.get("max_escalation_level", 3)

    # Throttle enforcement (level 3): block offending tool
    if (throttle_enabled
            and guidance_state.throttle_remaining > 0
            and guidance_state.throttled_tool == tool_name
            and tool_name not in INVESTIGATION_TOOLS):
        msg = build_signal_message(
            guidance_state.dominant_signal, "throttle",
            {"throttled_tool": tool_name},
        )
        guidance_state = guidance_state.decrement_throttle()
        if guidance_state.throttle_remaining == 0:
            guidance_state = guidance_state.reset_after_throttle()
        write_guidance_state(guidance_state, agent_id)
        print(msg, file=sys.stderr)
        sys.exit(2)

    # Cooldown: suppress guidance for N actions after last guidance
    if guidance_state.in_cooldown(action_count, cooldown_actions):
        return

    # Core guidance evaluation (unchanged mode/allow decisions)
    response = evaluate(
        pressure=pressure,
        tool_name=tool_name,
        tool_input=tool_input,
        action_log=action_log,
        gsd_active=gsd_active,
        thresholds=thresholds,
    )

    if response.mode.name == "OBSERVE":
        # Signal improved → reset escalation
        if escalation_enabled and guidance_state.escalation_level > 0:
            guidance_state = guidance_state.reset_escalation()
            write_guidance_state(guidance_state, agent_id)
        return

    # Build signal-specific message
    signal_pressures = read_signal_pressures(agent_id)
    dominant = find_dominant_signal(signal_pressures)

    if dominant:
        msg_context: dict = {}
        if dominant == "error_rate":
            recent = action_log[-10:] if action_log else []
            consecutive = 0
            for entry in reversed(recent):
                if entry.get("tool") == "Bash" and entry.get("error"):
                    consecutive += 1
                elif entry.get("tool") == "Bash":
                    break
            msg_context["consecutive_failures"] = consecutive
            msg_context["total_actions"] = len(action_log)
        elif dominant in ("token_usage", "context_exhaustion"):
            msg_context["context_pct"] = int(signal_pressures.get("token_usage", 0) * 100)

        level = "warn" if response.mode.name == "WARN" else "guide"
        msg = build_signal_message(
            dominant, level, msg_context,
            escalation_level=guidance_state.escalation_level,
            ignore_count=guidance_state.ignore_count,
        )
    else:
        msg = response.message

    # Escalation: if same signal persists, escalate
    if escalation_enabled and guidance_state.dominant_signal and guidance_state.dominant_signal == dominant:
        guidance_state = guidance_state.escalate(max_level=max_escalation)

    # Record guidance sent
    guidance_state = guidance_state.after_guidance(action_count, dominant)
    write_guidance_state(guidance_state, agent_id)

    if msg:
        print(msg, file=sys.stderr)

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
