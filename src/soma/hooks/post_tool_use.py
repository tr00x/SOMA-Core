"""SOMA PostToolUse hook — runs AFTER every Claude Code tool call.

Records each action and feeds back proprioceptive signals.

v3: Reads Claude Code's actual data format (tool_response, not output).
Detects errors from response content. File-locked action log.
"""

from __future__ import annotations

import os
import subprocess  # noqa: F401  (kept for legacy test patch sites)
import sys
import time

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

# Patterns that strict mode converts into hard PreToolUse blocks. Kept
# narrow on purpose — firing `context` or `entropy_drop` shouldn't gate
# the next tool call; those remain advisory.
#
# v2026.6.x: removed "retry_storm" — it's a predictor reason code and a
# calibration baseline metric, NOT a contextual_guidance pattern.
# evaluate() never emits a GuidanceMessage with pattern="retry_storm",
# so its presence here was dead config that could never block anything.
_STRICT_BLOCK_PATTERNS = frozenset({
    "blind_edit", "bash_retry", "error_cascade", "cost_spiral",
})


def _is_real_production_agent(agent_id: str) -> bool:
    if not agent_id or agent_id in _BLOCKED_AGENT_IDS:
        return False
    if agent_id.startswith("test-"):
        return False
    return True


# Fixed horizon for A/B measurement — both arms record pressure_after at
# exactly this many actions after the firing, regardless of whether the
# strict followthrough semantic has resolved. Critical for unbiased
# treatment-vs-control comparison: the old design recorded treatment
# at +1 action (fast resolution on recovery signal) and control at +5
# (timeout fallback), which let pressure decay alone make control
# look better than treatment.
#
# v2026.6.x: AB_MEASUREMENT_HORIZON / AB_RECOVERED_DELTA moved to
# soma.tunables. Module-level underscore aliases preserved for the
# internal callers that referenced them by their private name.
from soma.tunables import (  # noqa: E402
    AB_MEASUREMENT_HORIZON as _AB_MEASUREMENT_HORIZON,
    AB_RECOVERED_DELTA as _AB_RECOVERED_DELTA,
)


def _record_guidance_outcome(
    agent_id: str,
    pending: dict,
    followed: bool,
    pressure_after: float,
    analytics_path=None,
    next_actions: list[dict] | None = None,
) -> None:
    """Persist a contextual-guidance outcome to ``guidance_outcomes``.

    Bridges the gap between audit.jsonl firings and the dashboard's
    guidance_outcomes table so ROI metrics reflect real production
    patterns. This is the *strict* resolution path — it only fires when
    ``check_followthrough`` returns True / False.

    ``next_actions`` is the post-firing slice of the action log used to
    compute the three orthogonal multi-helped definitions. Caller
    passes ``_recent_actions`` already in scope; if absent we fall
    back to None for the new columns (legacy / test paths).

    Control-arm firings are deliberately skipped here: the guidance
    message was computed but never shown to the agent, so asking "did
    the agent follow the guidance?" is ill-defined. Writing them
    anyway would contaminate dashboard queries that predate A/B and
    aggregate ``helped`` across all rows. The A/B table has its own
    columns for the control-arm measurement.
    """
    if not _is_real_production_agent(agent_id):
        return
    if pending.get("ab_arm") == "control":
        return

    multi: dict[str, bool] | dict[str, None] = {
        "helped_pressure_drop": None,
        "helped_tool_switch": None,
        "helped_error_resolved": None,
    }
    if next_actions is not None:
        try:
            from soma.contextual_guidance import compute_multi_helped
            multi = compute_multi_helped(
                pending=pending,
                pressure_after=float(pressure_after),
                next_actions=next_actions,
            )
        except Exception:
            # Multi-helped is additive analytics — never block the
            # canonical helped row on its failure.
            pass

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
            helped_pressure_drop=multi["helped_pressure_drop"],
            helped_tool_switch=multi["helped_tool_switch"],
            helped_error_resolved=multi["helped_error_resolved"],
        )
    except Exception:
        pass  # Never crash the hook for analytics


def _record_ab_outcome_at_horizon(
    agent_id: str,
    pending: dict,
    pressure_after: float,
    analytics_path=None,
) -> bool:
    """Capture pressure at h=1/2/5/10 horizons; INSERT at h=2, UPDATE later.

    Multi-horizon flow (v2026.6.0):

    - **h=1**: buffer ``pressure_after`` into ``pending["pressure_after_h1"]``
      and return False (no row yet — h=1 fires before the h=2 INSERT).
    - **h=2**: INSERT the row, carrying ``firing_id`` and the buffered
      h=1 sample. Sets ``pending["ab_recorded"] = True``. Returns True.
    - **h=5 / h=10**: UPDATE the existing row's ``pressure_after_h<N>``
      column via ``firing_id``. Returns True on a successful UPDATE.

    The h=2 INSERT is the data-loss-safe checkpoint — even if the
    session ends before h=10, the prior single-horizon analysis still
    works. Multi-horizon data is purely additive.

    ``followed`` is the simple pressure-drop check at h=2 — *not* the
    strict v2026.5.3 recovery-action semantic. Mixing in pattern-
    specific "recovery" semantics here would bias against the control
    arm, which by construction cannot "follow" guidance it never saw.
    The strict semantic still lives in ``guidance_outcomes``.
    """
    if not _is_real_production_agent(agent_id):
        return False
    arm = pending.get("ab_arm")
    if arm not in ("treatment", "control"):
        return False
    actions_since = int(pending.get("actions_since", 0) or 0)

    # Below h=1: nothing to do. h=0 hits on the very first follow-up
    # action increment that runs before we can sample anything useful.
    if actions_since < 1:
        return False

    # h=1: buffer the sample for the upcoming h=2 INSERT. No row yet.
    if actions_since == 1:
        pending["pressure_after_h1"] = float(pressure_after)
        return False

    # h>=2: arm the analytics path lazily once.
    try:
        from soma.analytics import AnalyticsStore
        from soma.calibration import calibration_family
        store = AnalyticsStore(path=analytics_path) if analytics_path else AnalyticsStore()
    except Exception:
        return False

    firing_id = pending.get("firing_id")

    # h=2: INSERT the canonical row. This is the idempotency boundary —
    # ab_recorded gates re-entry from a same-cycle hook re-run.
    #
    # v2026.6.1 (review I3): we ALWAYS buffer the h=2 sample into
    # pending["pressure_after_h2"] so the timeout-path forced INSERT
    # below can use it instead of the (wrong) current pressure. Buffer
    # even on INSERT failure so a transient sqlite hiccup doesn't
    # erase the sample.
    if actions_since == _AB_MEASUREMENT_HORIZON:
        pending["pressure_after_h2"] = float(pressure_after)
        if pending.get("ab_recorded"):
            return False
        if pending.get("pressure_after_h1") is None:
            # Same bias class as B1/B2 (NULL firing_id), now on the
            # h=1 column. INSERTing NULL h=1 silently biases the
            # validate-patterns @h1 population because that filter
            # drops NULLs. Drop the row instead — losing one paired
            # observation is strictly safer than poisoning the
            # horizon-1 t-test.
            pending["ab_recorded"] = True  # don't retry forever
            return False
        pressure_before = float(pending.get("pressure_at_injection", 0.0))
        delta = pressure_before - float(pressure_after)
        recovered = delta >= _AB_RECOVERED_DELTA
        try:
            store.record_ab_outcome(
                agent_family=calibration_family(agent_id),
                pattern=pending.get("pattern", ""),
                arm=arm,
                pressure_before=pressure_before,
                pressure_after=float(pressure_after),
                followed=recovered,
                firing_id=firing_id,
                pressure_after_h1=pending.get("pressure_after_h1"),
            )
            pending["ab_recorded"] = True
            return True
        except Exception:
            # Retryable write failure — leave ab_recorded unset so a
            # later hook can try again with the same pending state.
            return False

    # h>2 path. The "force INSERT" branch (review I3): if we never
    # captured h=2 because the timeout path forced actions_since past
    # 2 in one jump, prefer the buffered h=2 sample over the caller's
    # current pressure (which is "now-pressure", not h=2-pressure).
    if not pending.get("ab_recorded"):
        buffered_h2 = pending.get("pressure_after_h2")
        if buffered_h2 is None:
            # No h=2 sample was ever buffered — better to drop than to
            # silently write today's pressure into the h=2 column and
            # bias future verdicts. Return False so the caller knows.
            return False
        if pending.get("pressure_after_h1") is None:
            # Same h1 bias guard as the h=2 branch — never INSERT a row
            # with NULL pressure_after_h1, which would silently bias
            # validate-patterns @h1 (its filter drops NULLs).
            pending["ab_recorded"] = True
            return False
        pressure_before = float(pending.get("pressure_at_injection", 0.0))
        delta = pressure_before - float(buffered_h2)
        recovered = delta >= _AB_RECOVERED_DELTA
        try:
            store.record_ab_outcome(
                agent_family=calibration_family(agent_id),
                pattern=pending.get("pattern", ""),
                arm=arm,
                pressure_before=pressure_before,
                pressure_after=float(buffered_h2),
                followed=recovered,
                firing_id=firing_id,
                pressure_after_h1=pending.get("pressure_after_h1"),
            )
            pending["ab_recorded"] = True
        except Exception:
            return False

    # h>2: UPDATE one of the horizon columns. Pick the closest tracked
    # horizon (5 or 10). Anything in between is captured at the next
    # tracked horizon to keep the column set fixed.
    if actions_since < 5:
        return False
    horizon = 10 if actions_since >= 10 else 5
    horizon_key = f"_ab_h{horizon}_recorded"
    if pending.get(horizon_key):
        return False
    if not firing_id:
        # Without firing_id we can't UPDATE — happens for legacy pending
        # dicts captured pre-v2026.6.0. Skip silently.
        return False
    try:
        rowcount = store.update_ab_outcome_horizon(
            firing_id=firing_id,
            horizon=horizon,
            pressure_after=float(pressure_after),
        )
        # Mark even if rowcount == 0 (firing_id never INSERTed) so we
        # don't keep retrying every action. The horizon is past either
        # way.
        pending[horizon_key] = True
        return rowcount > 0
    except Exception:
        return False


# v2026.6.x: extracted to soma/validators/. These thin shims keep the
# existing private-name imports working (tests, monkeypatch sites) so
# the refactor is transparent.
from soma.validators import (  # noqa: E402
    lint_python_file as _lint_python_file,
    validate_js_file as _validate_js_file,
    validate_python_file as _validate_python_file,
)


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

    try:
        engine, agent_id = get_engine()
        if engine is None:
            return

        # v2026.6.x: opportunistic GC of stale circuit_*.json files. ~1%
        # sample so ~100 hooks per session triggers a sweep on average,
        # which is plenty given mtime-based 48h retention. Best-effort —
        # failures inside gc_stale_circuit_files never propagate.
        try:
            import secrets
            if secrets.randbelow(100) == 0:
                from soma.hooks.common import gc_stale_circuit_files
                gc_stale_circuit_files(max_age_hours=48.0)
        except Exception:
            pass

        # Lazy-init Mirror once per process
        if _mirror is None:
            try:
                from soma.mirror import Mirror
                _mirror = Mirror(engine)
            except Exception:
                pass  # Mirror is optional — never crash

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

        # record_action + save_state must be treated as atomic from the
        # hook's point of view — action_log was already appended upstream,
        # so if record_action raises we must *still* persist whatever
        # engine state survived. Without this, action_log.json drifts
        # ahead of engine_state.json and cross-session vitals lose sync.
        try:
            result = engine.record_action(agent_id, action)
        except Exception:
            save_state(engine)
            raise
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
        #
        # The whole read-mutate-write block runs inside circuit_transaction
        # so concurrent subagent hooks can't lose each other's
        # ``actions_since`` increments or ``ab_recorded`` / ``strict_resolved``
        # flags. Without this lock the v2026.5.5 "1 of 2 increments lost"
        # race produces silent A/B contamination.
        try:
            from soma.hooks.common import circuit_transaction
            with circuit_transaction(agent_id) as _circuit_data:
                pending = _circuit_data.get("guidance_followthrough")
                if isinstance(pending, dict) and pending.get("pattern"):
                    from soma.contextual_guidance import check_followthrough
                    _tool_input = data.get("tool_input", {})
                    if not isinstance(_tool_input, dict):
                        _tool_input = {}
                    from soma.hooks.common import read_action_log as _read_al
                    _recent_actions = _read_al(agent_id)[-10:]
                    # Increment BEFORE the strict check so both the
                    # A/B horizon gate and the followthrough branch see
                    # the same ``actions_since`` value.
                    pending["actions_since"] = int(pending.get("actions_since", 0) or 0) + 1

                    # v2026.5.4: A/B and strict-followthrough are tracked
                    # *independently*. The old code cleared pending as
                    # soon as strict resolved, which meant fast treatment
                    # resolutions (strict True at +1) wrote the A/B row
                    # with pressure_after from +1 — smaller window than
                    # control arms which always sat till timeout. Now we
                    # keep pending alive until BOTH have resolved; each
                    # lands at its own correct horizon. No more mixed
                    # measurement windows.
                    _record_ab_outcome_at_horizon(
                        agent_id=agent_id, pending=pending, pressure_after=pressure,
                    )

                    # Strict path — resolve at most once per pending.
                    strict_resolved = bool(pending.get("strict_resolved"))
                    if not strict_resolved:
                        followed = check_followthrough(
                            pending, tool_name, _tool_input, file_path, error,
                            pressure_after=pressure,
                            recent_actions=_recent_actions,
                        )
                        if followed is not None:
                            pending["strict_resolved"] = True
                            pending["strict_followed"] = bool(followed)
                            strict_resolved = True
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
                            # v2026.6.1 (review C1): slice the action
                            # log by firing_ts instead of by
                            # ``actions_since`` count. The previous
                            # ``_recent_actions[-actions_since:]``
                            # silently overshot when actions_since > 10
                            # (the log was capped at the last 10), and
                            # compute_multi_helped[:3] then read PRE-
                            # firing actions as if they were post-
                            # firing. Timestamp filter is robust to log
                            # rotation: entries older than firing_ts
                            # never enter the slice. If firing_ts is
                            # missing (legacy pending from < v2026.6.1),
                            # we pass None and skip multi-helped.
                            _firing_ts = pending.get("firing_ts")
                            if _firing_ts is None:
                                _next_actions = None
                            else:
                                _next_actions = [
                                    a for a in _recent_actions
                                    if float(a.get("ts", 0) or 0) > float(_firing_ts)
                                ]
                            _record_guidance_outcome(
                                agent_id=agent_id,
                                pending=pending,
                                followed=bool(followed),
                                pressure_after=pressure,
                                next_actions=_next_actions,
                            )
                            # Strict mode: clear the matching block on a
                            # real recovery so the agent can proceed
                            # without manual `soma unblock`.
                            if followed:
                                try:
                                    from soma.blocks import load_block_state, save_block_state
                                    bs = load_block_state(agent_id)
                                    removed = bs.clear_block(pattern=pending.get("pattern"))
                                    if removed:
                                        save_block_state(bs)
                                except Exception:
                                    pass

                    # Terminal conditions: either both tracks landed (A/B
                    # h=10 + strict resolution), or we've waited too long.
                    # Timeout extended to >12 (was >5) to let the h=10
                    # horizon land. The h=2 INSERT still happens at
                    # actions_since=2, so the prior single-horizon
                    # verdict is unaffected by a late timeout.
                    ab_recorded = bool(pending.get("ab_recorded"))
                    h10_done = bool(pending.get("_ab_h10_recorded"))
                    timed_out = pending.get("actions_since", 0) > 12

                    if ab_recorded and h10_done and strict_resolved:
                        # All three tracks done — discard pending cleanly.
                        _circuit_data.pop("guidance_followthrough", None)
                    elif timed_out:
                        # Timed out. Best-effort close: write whichever
                        # track hasn't landed yet so no row is lost.
                        if not strict_resolved:
                            # v2026.6.1 (review C1): on timeout we don't
                            # trust multi-helped — the action log may
                            # have rotated past firing_ts entries we'd
                            # need, and the timeout window itself spans
                            # 13+ cycles where compute_multi_helped[:3]
                            # bias would be most pronounced. Pass None
                            # so the legacy `helped` row still lands
                            # but the multi-helped columns stay NULL.
                            _record_guidance_outcome(
                                agent_id=agent_id, pending=pending,
                                followed=False, pressure_after=pressure,
                                next_actions=None,
                            )
                        if not ab_recorded:
                            # Force horizon so the h=2 row lands on this
                            # last attempt. Late sample but unbiased
                            # against the other arm — both arms time out
                            # the same way.
                            pending["actions_since"] = max(
                                pending.get("actions_since", 0), _AB_MEASUREMENT_HORIZON,
                            )
                            _record_ab_outcome_at_horizon(
                                agent_id=agent_id, pending=pending, pressure_after=pressure,
                            )
                        if not h10_done:
                            # Best-effort late h=10 update so the column
                            # gets *something*. Force actions_since past
                            # the h=10 threshold; UPDATE is no-op if h=2
                            # row never made it in.
                            pending["actions_since"] = max(
                                pending.get("actions_since", 0), 10,
                            )
                            _record_ab_outcome_at_horizon(
                                agent_id=agent_id, pending=pending, pressure_after=pressure,
                            )
                        _circuit_data.pop("guidance_followthrough", None)
                    else:
                        # Still waiting on at least one track. Persist
                        # the mutated pending back into the transaction.
                        _circuit_data["guidance_followthrough"] = pending
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
                # Serialize the read-modify-write so parallel hooks
                # (e.g. Claude Code subagents) don't both load the same
                # count and overwrite each other's increments.
                family = _cal.calibration_family(agent_id)
                with _cal.profile_lock(family):
                    profile = _cal.load_profile(agent_id)
                    prev_phase = profile.phase
                    profile.advance(1)
                    try:
                        _cal.save_profile(profile)
                    except Exception:
                        pass
                    # On phase transitions, refresh personal distributions.
                    # Retry every hook only while audit is actually populated
                    # so we don't infinite-loop an empty-audit install; the
                    # refresh_attempted_at field paces the retry.
                    needs_refresh = (
                        profile.phase != prev_phase
                        or (not profile.is_warmup()
                            and profile.drift_p75 == 0.0
                            and profile.typical_success_rate == 0.0
                            and (profile.action_count
                                 - getattr(profile, "_last_refresh_try", 0)) >= 10)
                    )
                    if needs_refresh:
                        try:
                            _cal.recompute_from_audit(profile)
                            profile._last_refresh_try = profile.action_count  # type: ignore[attr-defined]
                            _cal.save_profile(profile)
                        except Exception:
                            pass
                    # Adaptive phase: rotate analytics-driven silence list
                    # every SILENCE_REFRESH_INTERVAL actions.
                    try:
                        if _cal.maybe_refresh_silence(profile):
                            _cal.save_profile(profile)
                    except Exception:
                        pass
                    # Auto-retire (P1.1): rerun A/B validation every
                    # REFUTED_REFRESH_INTERVAL actions and persist any
                    # verdict changes. Fires in every phase.
                    try:
                        if _cal.maybe_refresh_refuted(profile):
                            _cal.save_profile(profile)
                    except Exception:
                        pass
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
                # v2026.5.3 A/B gate. Split 50/50 so we can later measure
                # whether injection actually causes a pressure drop vs
                # just correlates with agent recovery. Warmup stays in
                # treatment arm — the gate's there to validate patterns,
                # not to suppress the first 30 actions' worth of signal.
                from soma import ab_control
                arm = "treatment"
                # firing_id is computed unconditionally so the
                # multi-horizon UPDATE key exists for warmup firings too
                # (warmup skips the A/B gate but still records ab_outcomes
                # in the treatment arm).
                #
                # v2026.6.1 (review I1): use time.time_ns() instead of
                # len(cg_action_log). The action log is clamped at
                # ACTION_LOG_MAX=20, so after 20 actions every firing
                # of pattern X produced the same firing_id — same
                # rebias class as the MD5 collision bug we fixed in
                # 2378faa. ns-precision timestamp is monotonic and
                # collision-free within a hook process.
                _firing_id = (
                    f"{agent_id}|{cg_msg.pattern}|{time.time_ns()}"
                )
                try:
                    from soma.calibration import calibration_family
                    family = calibration_family(agent_id)
                    # Skip A/B entirely while warming up so the first 30
                    # actions always see guidance if a pattern fires — it
                    # keeps the install demo-visible.
                    if profile is not None and not profile.is_warmup():
                        # firing_id makes should_inject idempotent under
                        # retry / re-entry: the same firing always returns
                        # the same arm without bumping the counter.
                        # Without it, the prior every-call-rebumps path
                        # silently biased the A/B verdict.
                        arm = ab_control.should_inject(
                            cg_msg.pattern, family, len(cg_action_log),
                            firing_id=_firing_id,
                        )
                except Exception:
                    arm = "treatment"

                if arm == "treatment":
                    # stdout → appended to tool response (deep injection)
                    print(f"\n{cg_msg.message}")
                # Strict mode: turn the firing pattern into a persistent
                # block against this tool so the next PreToolUse gates
                # the retry. Only registered in strict + non-warmup so
                # a fresh install never hard-gates. Control arm skips
                # the block too — it's part of the "as if not injected"
                # contract.
                try:
                    from soma.hooks.common import get_soma_mode
                    if (
                        arm == "treatment"
                        and get_soma_mode(agent_id) == "strict"
                        and profile is not None and not profile.is_warmup()
                        and cg_msg.pattern in _STRICT_BLOCK_PATTERNS
                    ):
                        from soma.blocks import load_block_state, save_block_state
                        bs = load_block_state(agent_id)
                        # blind_edit is about writing code without reading;
                        # block the whole family of edit-class tools or the
                        # agent just switches Write→Edit→NotebookEdit and
                        # bypasses the gate.
                        tools_to_block = [tool_name]
                        if cg_msg.pattern == "blind_edit":
                            tools_to_block = ["Write", "Edit", "NotebookEdit"]
                        for t in tools_to_block:
                            bs.add_block(
                                pattern=cg_msg.pattern, tool=t,
                                reason=cg_msg.suggestion or cg_msg.pattern,
                            )
                        save_block_state(bs)
                except Exception:
                    pass
                # Record follow-through for next action evaluation — for
                # BOTH arms. We need control's pressure_after to compare
                # against treatment's.
                followthrough_data = {
                    "pattern": cg_msg.pattern,
                    "suggestion": cg_msg.suggestion,
                    "actions_since": 0,
                    "pressure_at_injection": pressure,
                    "ab_arm": arm,
                    # firing_id is the UPDATE key for multi-horizon
                    # recording. Same string as the should_inject token
                    # so a single firing has one stable identifier
                    # across the lifetime of the followthrough.
                    "firing_id": _firing_id,
                    # v2026.6.1 (review C1): firing timestamp is the
                    # marker for slicing the post-firing tail of the
                    # action log. Absolute index doesn't work because
                    # the log is truncated at ACTION_LOG_MAX=20 and
                    # rotates as new actions append; timestamp is
                    # stable across rotations.
                    "firing_ts": time.time(),
                }
                if cg_msg.pattern == "blind_edit":
                    followthrough_data["file"] = file_path
                elif cg_msg.pattern == "bash_retry":
                    # v2026.6.x: dropped `entropy_drop` from this branch —
                    # the pattern is retired and never reaches followthrough.
                    followthrough_data["tool"] = tool_name
                elif cg_msg.pattern == "error_cascade":
                    # Track which tools were failing so stricter
                    # followthrough can demand a tool *switch*.
                    failing: list[str] = []
                    for entry in reversed(cg_action_log[-10:]):
                        if entry.get("error"):
                            tn = entry.get("tool")
                            if tn and tn not in failing:
                                failing.append(tn)
                        else:
                            break
                    followthrough_data["failing_tools"] = failing
                write_guidance_followthrough(followthrough_data, agent_id)
                # Audit — still log both arms (with the arm tag) so
                # audit.jsonl stays the source of truth.
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
                        detail=f"[{arm}] {cg_msg.message}",
                        pattern=cg_msg.pattern,
                    )
                except Exception:
                    pass
        except Exception:
            pass  # Never crash for contextual guidance

        _prev_level = level_name
        _prev_pressure = pressure

    except Exception as _outer_exc:
        # Bare `pass` here silenced a 2-day production regression
        # (silence-cache stuck post-v2026.5.5). Stderr is safe — Claude
        # Code's hook contract uses stdout for JSON; stderr surfaces in
        # the user-visible debug stream without breaking the protocol.
        # Suppressible via SOMA_HOOK_QUIET=1 for CI / known-noisy runs.
        if os.environ.get("SOMA_HOOK_QUIET") != "1":
            try:
                print(
                    f"SOMA hook error: {type(_outer_exc).__name__}: {_outer_exc}",
                    file=sys.stderr,
                )
            except Exception:
                pass


if __name__ == "__main__":
    main()
