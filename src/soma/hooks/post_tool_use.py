"""SOMA PostToolUse hook — runs AFTER every Claude Code tool call.

Records each action and feeds back proprioceptive signals.

v3: Reads Claude Code's actual data format (tool_response, not output).
Detects errors from response content. File-locked action log.
"""

from __future__ import annotations

import os
import subprocess
import sys

from soma.hooks.common import (
    get_engine, save_state, read_stdin, append_action_log, get_predictor,
    save_predictor, append_pressure_trajectory,
    estimate_context_usage_from_transcript,
)

_prev_level: str | None = None
_prev_pressure: float = 0.0
_mirror = None  # Lazy-initialized Mirror instance

# Catch-all / fixture agent ids never persisted to analytics from hook layer
# — they contaminate ROI metrics (missing SOMA_AGENT_ID, test scripts).
_BLOCKED_AGENT_IDS = frozenset({"claude-code", "test", "nonexistent-agent"})


def _is_real_production_agent(agent_id: str) -> bool:
    if not agent_id or agent_id in _BLOCKED_AGENT_IDS:
        return False
    if agent_id.startswith("test-"):
        return False
    return True


def _record_outcome_if_resolved(
    agent_id: str,
    pending: dict,
    followed: bool,
    pressure_after: float,
    analytics_path=None,
) -> None:
    """Persist a contextual-guidance outcome to analytics.db.

    Bridges the gap between audit.jsonl firings and the dashboard's
    guidance_outcomes table so ROI metrics reflect real production patterns.
    """
    if not _is_real_production_agent(agent_id):
        return
    try:
        from soma.analytics import AnalyticsStore
        store = AnalyticsStore(path=analytics_path) if analytics_path else AnalyticsStore()
        store.record_guidance_outcome(
            agent_id=agent_id,
            session_id=agent_id,
            pattern_key=pending.get("pattern", ""),
            helped=bool(followed),
            pressure_at_injection=float(pending.get("pressure_at_injection", 0.0)),
            pressure_after=float(pressure_after),
        )
    except Exception:
        pass  # Never crash the hook for analytics


def _validate_python_file(file_path: str) -> str | None:
    if not file_path or not file_path.endswith(".py"):
        return None
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import py_compile; py_compile.compile({file_path!r}, doraise=True)"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            for line in stderr.split("\n"):
                if "SyntaxError" in line or "Error" in line:
                    return line.strip()
            return stderr.split("\n")[-1].strip() if stderr else "syntax error"
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _lint_python_file(file_path: str) -> str | None:
    if not file_path or not file_path.endswith(".py"):
        return None
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "F", "--no-fix", "--quiet", file_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _validate_js_file(file_path: str) -> str | None:
    if not file_path:
        return None
    if not any(file_path.endswith(ext) for ext in (".js", ".mjs", ".cjs")):
        return None
    try:
        result = subprocess.run(
            ["node", "--check", file_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            for line in stderr.split("\n"):
                if "SyntaxError" in line or "Error" in line:
                    return line.strip()
            return stderr.split("\n")[-1].strip() if stderr else "syntax error"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _extract_file_path(data: dict) -> str:
    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, dict):
        return tool_input.get("file_path", "") or tool_input.get("path", "")
    return ""


def _persist_mirror_stats(mirror, agent_id: str) -> None:
    """Write mirror effectiveness stats to session dir for the dashboard.

    Writes to ~/.soma/sessions/{agent_id}/mirror_stats.json atomically
    (write tmp → rename) so partial writes never corrupt the file.
    """
    import json
    import tempfile
    from soma.hooks.common import SESSIONS_DIR

    session_dir = SESSIONS_DIR / agent_id
    session_dir.mkdir(parents=True, exist_ok=True)
    mirror_path = session_dir / "mirror_stats.json"

    # Aggregate stats from pattern_db
    total_injections = 0
    successful_injections = 0
    patterns: list[dict] = []
    for key, record in mirror.pattern_db.items():
        total_injections += record.total
        successful_injections += record.success_count
        patterns.append({
            "key": key,
            "context_text": record.context_text[:200],
            "success_count": record.success_count,
            "fail_count": record.fail_count,
            "success_rate": round(record.success_rate, 3),
            "last_used": record.last_used,
        })

    effectiveness = (
        round(successful_injections / total_injections, 3)
        if total_injections > 0
        else 0.0
    )

    # Count pending evaluations for this agent
    pending_count = sum(
        1 for p in mirror._pending if p.agent_id == agent_id
    )

    # Check if semantic mode is active
    semantic_enabled = getattr(mirror, "_semantic_enabled", False)

    mirror_data = {
        "effectiveness": effectiveness,
        "total_injections": total_injections,
        "successful_injections": successful_injections,
        "pending_evaluations": pending_count,
        "semantic_enabled": semantic_enabled,
        "patterns": patterns,
    }

    # Atomic write: tmp file → rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(session_dir), suffix=".tmp", prefix="mirror_stats_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(mirror_data, f)
        os.replace(tmp_path, str(mirror_path))
    except Exception:
        # Clean up tmp on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main_failure():
    """Handle PostToolUseFailure — tool errors that Claude Code sends to a separate event.

    PostToolUseFailure payload differs from PostToolUse:
    - No tool_response field
    - Has error (string describing failure)
    - Has is_interrupt (boolean — user cancelled)
    """
    data = read_stdin()
    # User interrupts are not real errors — skip them
    if data.get("is_interrupt", False):
        return
    # Normalize: put error message into tool_response so main() can process it
    error_msg = data.get("error", "Tool execution failed")
    data["tool_response"] = f"Error: {error_msg}"
    main(_data=data, _force_error=True)


def main(*, _data: dict | None = None, _force_error: bool = False):
    global _prev_level, _prev_pressure

    global _mirror

    engine, agent_id = get_engine()
    if engine is None:
        return

    # Lazy-init Mirror once per process
    if _mirror is None:
        try:
            from soma.mirror import Mirror
            _mirror = Mirror(engine)
        except Exception:
            pass  # Mirror is optional — never crash

    try:
        from soma.types import Action

        data = _data if _data is not None else read_stdin()
        tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", "unknown"))

        # Claude Code sends tool_response (not output)
        raw_response = data.get("tool_response") or data.get("output") or ""
        if isinstance(raw_response, (dict, list)):
            import json
            output = json.dumps(raw_response)[:500]
        else:
            output = str(raw_response)[:500]

        # Error detection — multiple strategies for robustness
        if _force_error:
            # PostToolUseFailure: Claude Code already told us this is an error
            error = True
        else:
            # Strategy 1: Claude Code's explicit error fields
            raw_error = data.get("error", False)
            raw_is_error = data.get("is_error", False)
            # Handle string "true"/"false" (some Claude Code versions send strings)
            if isinstance(raw_error, str):
                raw_error = raw_error.lower() in ("true", "1", "yes")
            if isinstance(raw_is_error, str):
                raw_is_error = raw_is_error.lower() in ("true", "1", "yes")
            error = bool(raw_error) or bool(raw_is_error)

            # Strategy 2: Bash exit code detection — search anywhere in response
            if not error and tool_name == "Bash" and isinstance(raw_response, str):
                import re
                # Match "Exit code N" anywhere in the first 500 chars
                m = re.search(r"Exit code (\d+)", raw_response[:500])
                if m and m.group(1) != "0":
                    error = True
                # Also catch common error prefixes
                elif raw_response.lstrip().startswith("Error:") or raw_response.lstrip().startswith("error:"):
                    error = True

            # Strategy 3: Edit/Write tool errors (file not found, permission denied)
            if not error and tool_name in ("Edit", "Write") and isinstance(raw_response, str):
                lower_resp = raw_response[:300].lower()
                if any(p in lower_resp for p in ("error", "failed", "not found", "permission denied")):
                    error = True

        duration = float(data.get("duration_ms", 0)) / 1000.0
        file_path = _extract_file_path(data)

        from soma.hooks.common import get_hook_config
        hook_config = get_hook_config()

        # Transcript-size proxy for real context fullness. Claude Code's
        # hook payload carries `transcript_path` → JSONL file that grows
        # with the live conversation. Internal cumulative_tokens only
        # tracks tool outputs, so context_usage from engine is lowballed
        # by 10-20× on long sessions. Stat-based estimate fixes this.
        transcript_path = data.get("transcript_path") or ""
        ctx_window = getattr(engine, "_context_window", 200_000) or 200_000
        transcript_context_usage = estimate_context_usage_from_transcript(
            transcript_path, context_window=ctx_window,
        )

        append_action_log(tool_name, error=error, file_path=file_path, agent_id=agent_id, output=output if error else "")

        # Record lesson when error streak breaks (success after errors)
        try:
            from soma.hooks.common import read_action_log
            recent = read_action_log(agent_id)[-5:]
            if not error and len(recent) >= 2:
                prev_errors = []
                for entry in reversed(recent[:-1]):
                    if entry.get("error"):
                        prev_errors.append(entry)
                    else:
                        break
                if len(prev_errors) >= 2:
                    from soma.lessons import LessonStore
                    store = LessonStore()
                    # Use output from action log, fall back to tool response from current context
                    last_err = prev_errors[0].get("output", "") or prev_errors[0].get("tool_response", "") or prev_errors[0].get("tool", "")
                    store.record(
                        pattern="error_resolved",
                        error_text=last_err[:200],
                        fix_text=f"Resolved by {tool_name} on {file_path or 'unknown'}",
                        tool=prev_errors[0].get("tool", ""),
                    )
        except Exception:
            pass  # Never crash for lesson recording

        if hook_config.get("task_tracking", True):
            try:
                import os as _os
                cwd = _os.environ.get("CLAUDE_WORKING_DIRECTORY", _os.getcwd())
                from soma.hooks.common import get_task_tracker, save_task_tracker
                tracker = get_task_tracker(cwd=cwd, agent_id=agent_id)
                tracker.record(tool_name, file_path, error)
                save_task_tracker(tracker, agent_id=agent_id)
            except Exception:
                pass

        # Pre-record validation: check written code BEFORE recording action
        # If syntax error found, mark action as error so engine pressure rises
        syntax_err = None
        lint_err = None
        if tool_name in ("Write", "Edit", "NotebookEdit") and file_path and not error:
            short_name = file_path.rsplit("/", 1)[-1]
            if hook_config.get("validate_python", True):
                syntax_err = _validate_python_file(file_path)
                if syntax_err:
                    print(f"SOMA: syntax error in {short_name}: {syntax_err}", file=sys.stderr)
            if hook_config.get("lint_python", True) and not syntax_err:
                lint_err = _lint_python_file(file_path)
                if lint_err:
                    print(f"SOMA: lint issue in {short_name}: {lint_err}", file=sys.stderr)
            if hook_config.get("validate_js", True):
                js_err = _validate_js_file(file_path)
                if js_err:
                    print(f"SOMA: syntax error in {short_name}: {js_err}", file=sys.stderr)
                    syntax_err = syntax_err or js_err

        # Syntax error = action error (makes engine pressure rise)
        if syntax_err:
            error = True

        # Record action with engine (AFTER validation so errors are counted)
        action = Action(
            tool_name=tool_name,
            output_text=output,
            token_count=len(output) // 4,
            error=error,
            duration_sec=duration,
        )

        result = engine.record_action(agent_id, action)
        save_state(engine)

        # Persist signal pressures for pre_tool_use guidance
        try:
            if result.pressure_vector:
                pv = result.pressure_vector
                _signal_pressures = {
                    "uncertainty": pv.uncertainty,
                    "drift": pv.drift,
                    "error_rate": pv.error_rate,
                    "cost": pv.cost,
                }
                from soma.hooks.common import write_signal_pressures
                write_signal_pressures(_signal_pressures, agent_id)
        except Exception:
            pass  # Never crash for signal persistence

        # Record to analytics SQLite for cross-session trends.
        # Skip catch-all agent ids (missing SOMA_AGENT_ID) to keep production
        # metrics clean.
        if _is_real_production_agent(agent_id):
            try:
                from soma.analytics import AnalyticsStore
                analytics = AnalyticsStore()
                vitals = result.vitals
                engine_ctx = getattr(vitals, 'context_usage', 0) or 0
                analytics.record(
                    agent_id=agent_id,
                    session_id=agent_id,  # use agent_id as session for now
                    tool_name=tool_name,
                    pressure=result.pressure,
                    uncertainty=getattr(vitals, 'uncertainty', 0),
                    drift=getattr(vitals, 'drift', 0),
                    error_rate=getattr(vitals, 'error_rate', 0),
                    context_usage=max(engine_ctx, transcript_context_usage),
                    token_count=action.token_count,
                    cost=action.cost,
                    mode=result.mode.name,
                    error=error,
                    source="hook",
                )
            except Exception:
                pass  # Never crash for analytics

        # Append pressure to per-session trajectory for cross-session intelligence
        append_pressure_trajectory(result.pressure, agent_id)

        # Mirror: evaluate pending injections, then generate new context
        if _mirror is not None:
            try:
                _mirror.evaluate_pending(agent_id, result.pressure)
            except Exception:
                pass  # Never crash for learning evaluation
            try:
                session_ctx = _mirror.generate(agent_id, action, output)
                if session_ctx:
                    print(session_ctx)  # stdout → appended to tool response
            except Exception:
                pass  # Mirror is optional — never crash

            # Persist mirror stats to disk for dashboard consumption
            try:
                _persist_mirror_stats(_mirror, agent_id)
            except Exception:
                pass  # Never crash for dashboard persistence

        # Subagent cascade: propagate subagent error pressure to parent
        try:
            from soma.subagent_monitor import get_cascade_risk
            cascade = get_cascade_risk(agent_id)
            if cascade > 0:
                # Boost parent pressure via graph — subagent errors cascade up
                graph = engine._graph
                if agent_id in graph.agents:
                    current_internal = graph._nodes[agent_id].internal_pressure
                    boosted = min(1.0, current_internal + cascade * 0.3)
                    graph.set_internal_pressure(agent_id, boosted)
                    graph.propagate()
        except Exception:
            pass  # Never crash for subagent cascade

        level_name = result.mode.name
        pressure = result.pressure
        vitals = result.vitals

        # Contextual guidance follow-through tracking (runs after pressure is
        # known so pressure-delta resolution works for drift/cost_spiral/etc.)
        try:
            from soma.hooks.common import read_guidance_followthrough, write_guidance_followthrough
            pending = read_guidance_followthrough(agent_id)
            if pending:
                from soma.contextual_guidance import check_followthrough
                _tool_input = data.get("tool_input", {})
                if not isinstance(_tool_input, dict):
                    _tool_input = {}
                followed = check_followthrough(
                    pending, tool_name, _tool_input, file_path, error,
                    pressure_after=pressure,
                )
                if followed is None:
                    pending["actions_since"] = pending.get("actions_since", 0) + 1
                    write_guidance_followthrough(pending, agent_id)
                else:
                    try:
                        from soma.audit import AuditLogger
                        AuditLogger().append(
                            agent_id=agent_id,
                            tool_name=tool_name,
                            error=False,
                            pressure=pressure,
                            mode="followthrough",
                            type="contextual_guidance",
                            detail=f"pattern={pending.get('pattern')}, followed={followed}",
                            pattern=pending.get("pattern", ""),
                            guidance_followed=followed,
                        )
                    except Exception:
                        pass
                    _record_outcome_if_resolved(
                        agent_id=agent_id,
                        pending=pending,
                        followed=bool(followed),
                        pressure_after=pressure,
                    )
                    write_guidance_followthrough(None, agent_id)
        except Exception:
            pass  # Never crash for follow-through tracking

        # Quality tracking — only Write/Edit (Bash errors tracked by engine error_rate)
        if hook_config.get("quality", True) and tool_name in ("Write", "Edit", "NotebookEdit"):
            try:
                from soma.hooks.common import get_quality_tracker, save_quality_tracker
                qt = get_quality_tracker(agent_id=agent_id)
                qt.record_write(had_syntax_error=bool(syntax_err), had_lint_issue=bool(lint_err))
                save_quality_tracker(qt, agent_id=agent_id)
            except Exception:
                pass

        # Proprioceptive feedback
        if _prev_level is not None and level_name != _prev_level:
            rca_msg = ""
            try:
                from soma.rca import diagnose
                from soma.hooks.common import read_action_log
                rca = diagnose(
                    read_action_log(agent_id),
                    {"uncertainty": vitals.uncertainty, "drift": vitals.drift, "error_rate": vitals.error_rate},
                    pressure, level_name, 0,
                )
                if rca:
                    rca_msg = f" — {rca}"
            except Exception:
                pass
            print(f"SOMA: {_prev_level} → {level_name} (p={pressure:.0%}){rca_msg}", file=sys.stderr)

        elif _prev_pressure > 0 and (pressure - _prev_pressure) > 0.10:
            signals = {"uncertainty": vitals.uncertainty, "drift": vitals.drift, "error_rate": vitals.error_rate}
            worst = max(signals, key=signals.get)
            print(f"SOMA: pressure +{pressure - _prev_pressure:.0%} ({worst}={signals[worst]:.2f}) after {tool_name}", file=sys.stderr)

        elif error and vitals.error_rate > 0.15:
            print(f"SOMA: error_rate={vitals.error_rate:.0%} after {tool_name} failure", file=sys.stderr)

        # Prediction
        if hook_config.get("predict", True):
            try:
                predictor = get_predictor(agent_id=agent_id)
                predictor.update(pressure, {"tool": tool_name, "error": error, "file": file_path})
                boundaries = [0.25, 0.50, 0.75]
                next_boundary = next((b for b in boundaries if b > pressure), None)
                if next_boundary:
                    pred = predictor.predict(next_boundary)
                    if pred.will_escalate:
                        print(f"SOMA: predicted escalation in ~{pred.actions_ahead} actions (p={pred.predicted_pressure:.0%}, {pred.dominant_reason})", file=sys.stderr)
                save_predictor(predictor, agent_id=agent_id)
            except Exception:
                pass

        # ── Contextual Guidance: pattern-based messages via stdout (tool result injection) ──
        # stdout in PostToolUse is appended to the tool result, so the LLM
        # reads it as part of the tool's response — impossible to ignore.
        try:
            from soma.contextual_guidance import ContextualGuidance
            from soma.hooks.common import read_action_log, write_guidance_followthrough

            lesson_store = None
            try:
                from soma.lessons import LessonStore
                lesson_store = LessonStore()
            except Exception:
                pass
            baseline = None
            try:
                baseline = engine.get_baseline(agent_id)
            except Exception:
                pass
            # Self-calibration: load (or create) the family profile so
            # warmup silences guidance and adaptive phase can auto-silence
            # noisy patterns. Advance counter per action so phase
            # transitions happen at 100/500.
            profile = None
            try:
                from soma import calibration as _cal
                profile = _cal.load_profile(agent_id)
                prev_phase = profile.phase
                profile.advance(1)
                # On phase transitions, refresh personal distributions
                # from recent audit history so the next action evaluates
                # against the calibrated thresholds, not legacy floors.
                if profile.phase != prev_phase:
                    try:
                        _cal.recompute_from_audit(profile)
                    except Exception:
                        pass
                _cal.save_profile(profile)
            except Exception:
                pass  # Calibration is additive — never break guidance.

            cg = ContextualGuidance(
                lesson_store=lesson_store, baseline=baseline, profile=profile,
            )
            # Restore cooldown state from disk so patterns don't spam
            from soma.hooks.common import read_guidance_cooldowns
            cg._last_fired = read_guidance_cooldowns(agent_id)
            cg_action_log = read_action_log(agent_id)
            engine_token_usage = (
                getattr(vitals, "token_usage", 0) or getattr(vitals, "context_usage", 0) or 0
            )
            cg_vitals = {
                "uncertainty": vitals.uncertainty,
                "drift": vitals.drift,
                "error_rate": vitals.error_rate,
                # Prefer whichever is higher: engine's internal tally or the
                # transcript-size proxy. Without a configured budget the
                # engine value is effectively 0; the proxy keeps
                # context/cost_spiral patterns armed for long sessions.
                "token_usage": max(engine_token_usage, transcript_context_usage),
                "context_usage": max(
                    getattr(vitals, "context_usage", 0) or 0, transcript_context_usage,
                ),
            }
            budget_health = 1.0
            try:
                budget_health = engine.get_budget_health()
            except Exception:
                pass

            cg_msg = cg.evaluate(
                action_log=cg_action_log,
                current_tool=tool_name,
                current_input=data.get("tool_input", {}),
                vitals=cg_vitals,
                budget_health=budget_health,
                action_number=len(cg_action_log),
            )
            # Persist cooldown state so patterns don't re-fire across hook calls
            from soma.hooks.common import write_guidance_cooldowns
            write_guidance_cooldowns(cg._last_fired, agent_id)
            if cg_msg:
                # stdout → appended to tool response (deep injection)
                print(f"\n{cg_msg.message}")
                # Record follow-through for next action evaluation
                followthrough_data = {
                    "pattern": cg_msg.pattern,
                    "suggestion": cg_msg.suggestion,
                    "actions_since": 0,
                    "pressure_at_injection": pressure,
                }
                if cg_msg.pattern == "blind_edit":
                    followthrough_data["file"] = file_path
                elif cg_msg.pattern in ("entropy_drop", "bash_retry"):
                    followthrough_data["tool"] = tool_name
                write_guidance_followthrough(followthrough_data, agent_id)
                # Audit
                try:
                    from soma.audit import AuditLogger
                    logger = AuditLogger()
                    logger.append(
                        agent_id=agent_id,
                        tool_name=tool_name,
                        error=False,
                        pressure=pressure,
                        mode=cg_msg.severity,
                        type="contextual_guidance",
                        detail=cg_msg.message,
                        pattern=cg_msg.pattern,
                    )
                except Exception:
                    pass
        except Exception:
            pass  # Never crash for contextual guidance

        _prev_level = level_name
        _prev_pressure = pressure

    except Exception:
        pass


if __name__ == "__main__":
    main()
