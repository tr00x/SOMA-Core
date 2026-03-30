"""SOMA PostToolUse hook — runs AFTER every Claude Code tool call.

Records each action and feeds back proprioceptive signals.

v3: Reads Claude Code's actual data format (tool_response, not output).
Detects errors from response content. File-locked action log.
"""

from __future__ import annotations

import os
import subprocess
import sys

from soma.hooks.common import get_engine, save_state, read_stdin, append_action_log, get_predictor, save_predictor

_prev_level: str | None = None
_prev_pressure: float = 0.0


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


def main():
    global _prev_level, _prev_pressure

    engine, agent_id = get_engine()
    if engine is None:
        return

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

        append_action_log(tool_name, error=error, file_path=file_path)

        if hook_config.get("task_tracking", True):
            try:
                import os as _os
                cwd = _os.environ.get("CLAUDE_WORKING_DIRECTORY", _os.getcwd())
                from soma.hooks.common import get_task_tracker, save_task_tracker
                tracker = get_task_tracker(cwd=cwd)
                tracker.record(tool_name, file_path, error)
                save_task_tracker(tracker)
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

        level_name = result.mode.name
        pressure = result.pressure
        vitals = result.vitals

        # Quality tracking — only Write/Edit (Bash errors tracked by engine error_rate)
        if hook_config.get("quality", True) and tool_name in ("Write", "Edit", "NotebookEdit"):
            try:
                from soma.hooks.common import get_quality_tracker, save_quality_tracker
                qt = get_quality_tracker()
                qt.record_write(had_syntax_error=bool(syntax_err), had_lint_issue=bool(lint_err))
                save_quality_tracker(qt)
            except Exception:
                pass

        # Proprioceptive feedback
        if _prev_level is not None and level_name != _prev_level:
            rca_msg = ""
            try:
                from soma.rca import diagnose
                from soma.hooks.common import read_action_log
                rca = diagnose(
                    read_action_log(),
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
                predictor = get_predictor()
                predictor.update(pressure, {"tool": tool_name, "error": error, "file": file_path})
                boundaries = [0.25, 0.50, 0.75]
                next_boundary = next((b for b in boundaries if b > pressure), None)
                if next_boundary:
                    pred = predictor.predict(next_boundary)
                    if pred.will_escalate:
                        print(f"SOMA: predicted escalation in ~{pred.actions_ahead} actions (p={pred.predicted_pressure:.0%}, {pred.dominant_reason})", file=sys.stderr)
                save_predictor(predictor)
            except Exception:
                pass

        _prev_level = level_name
        _prev_pressure = pressure

    except Exception:
        pass


if __name__ == "__main__":
    main()
