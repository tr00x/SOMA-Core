"""SOMA PostToolUse hook — runs AFTER every Claude Code tool call.

Records each action and feeds back proprioceptive signals.

v3: Reads Claude Code's actual data format (tool_response, not output).
Detects errors from response content. File-locked action log.
"""

from __future__ import annotations

import os
import subprocess
import sys

from soma.hooks.common import get_engine, save_state, read_stdin, append_action_log, get_predictor, save_predictor, append_pressure_trajectory

_prev_level: str | None = None
_prev_pressure: float = 0.0
_mirror = None  # Lazy-initialized Mirror instance


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


def main():
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

        data = read_stdin()
        tool_name = data.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", "unknown"))

        # Claude Code sends tool_response (not output)
        raw_response = data.get("tool_response") or data.get("output") or ""
        if isinstance(raw_response, (dict, list)):
            import json
            output = json.dumps(raw_response)[:500]
        else:
            output = str(raw_response)[:500]

        # Error detection — only from Claude Code's own error signaling
        # Claude Code wraps errors in specific format, don't heuristic-match content
        error = data.get("error", False) or data.get("is_error", False)

        # Claude Code tool_response starts with "Exit code N\n" for failed Bash
        if not error and tool_name == "Bash" and isinstance(raw_response, str):
            if raw_response.startswith("Exit code ") or raw_response.startswith("\nExit code "):
                # Extract exit code — only non-zero is an error
                try:
                    code_str = raw_response.split("Exit code ")[1].split("\n")[0].strip()
                    if code_str != "0":
                        error = True
                except (IndexError, ValueError):
                    pass

        duration = float(data.get("duration_ms", 0)) / 1000.0
        file_path = _extract_file_path(data)

        from soma.hooks.common import get_hook_config
        hook_config = get_hook_config()

        append_action_log(tool_name, error=error, file_path=file_path, agent_id=agent_id)

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

        _prev_level = level_name
        _prev_pressure = pressure

    except Exception:
        pass


if __name__ == "__main__":
    main()
