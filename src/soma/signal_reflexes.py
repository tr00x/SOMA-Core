"""SOMA Signal Reflexes — pure-function evaluators for signal-based reflexes.

Each evaluator takes computed state (predictions, drift scores, quality grades,
etc.) and returns a ReflexResult decision. No I/O, no side effects.

Signal reflexes are separate from pattern reflexes (reflexes.py). Pattern reflexes
detect action sequences (blind edits, thrashing). Signal reflexes react to computed
metrics (predictions, drift, error rate, quality grade).
"""

from __future__ import annotations

import re

from soma.reflexes import ReflexResult


# ── Priority order for evaluate_all_signals (highest first) ──
_SIGNAL_PRIORITY = [
    "rca_injection",
    "drift_guardian",
    "handoff_suggestion",
    "predictor_checkpoint",
    "predictor_warning",
]

_MAX_INJECTIONS = 2

_GIT_COMMIT_RE = re.compile(r"^\s*git\s+commit\b")


def evaluate_predictor_checkpoint(
    prediction: object | None,
    mode: str = "reflex",
) -> ReflexResult:
    """Evaluate predictor checkpoint reflex.

    Fires when prediction confidence > 0.7 AND actions_ahead <= 3.
    Mode gating: reflex = checkpoint action, guide = warning only.
    """
    if prediction is None:
        return ReflexResult(allow=True)

    confidence = getattr(prediction, "confidence", 0.0)
    actions_ahead = getattr(prediction, "actions_ahead", 999)

    if confidence <= 0.7 or actions_ahead > 3:
        return ReflexResult(allow=True)

    reason = getattr(prediction, "dominant_reason", "trend")

    context = {
        "error_streak": "consecutive failures detected",
        "blind_writes": "writes without reading first",
        "thrashing": "repeated edits to same file",
        "retry_storm": "retrying same failing approach",
        "trend": "steady pressure increase",
    }.get(reason, "pressure climbing")
    msg = (
        f"[SOMA] escalation in ~{actions_ahead} actions, "
        f"confidence={confidence:.0%}, trigger={reason} — {context}"
    )
    kind = "predictor_checkpoint" if mode == "reflex" else "predictor_warning"

    return ReflexResult(
        allow=True,
        reflex_kind=kind,
        inject_message=msg,
        detail=f"confidence={confidence:.2f}, actions_ahead={actions_ahead}",
    )


def evaluate_drift_guardian(
    drift: float,
    original_task: str | None = None,
    current_activity: str = "",
) -> ReflexResult:
    """Evaluate drift guardian reflex.

    Fires when drift > 0.4 and original_task is available.
    Gracefully degrades when no original task is set.
    """
    if drift <= 0.4 or not original_task:
        return ReflexResult(allow=True)

    activity = current_activity or "something else"

    similarity = max(0, 1.0 - drift)
    return ReflexResult(
        allow=True,
        reflex_kind="drift_guardian",
        inject_message=(
            f"[SOMA] drift={drift:.2f}, original='{original_task}', "
            f"current='{activity}' — {similarity:.0%} goal similarity"
        ),
        detail=f"drift={drift:.2f}",
    )


def evaluate_handoff(
    success_rate: float,
    handoff_text: str = "",
    agent_id: str = "",
) -> ReflexResult:
    """Evaluate handoff suggestion reflex.

    Fires when predicted success rate < 40%.
    """
    if success_rate >= 0.4:
        return ReflexResult(allow=True)

    return ReflexResult(
        allow=True,
        reflex_kind="handoff_suggestion",
        inject_message=f"[SOMA] success_rate={success_rate:.0%} — session approaching limits",
        detail=f"success_rate={success_rate:.2f}, agent='{agent_id}'",
    )


def evaluate_rca_injection(
    error_rate: float,
    rca_text: str | None = None,
) -> ReflexResult:
    """Evaluate RCA injection reflex.

    Fires when error_rate > 0.3 and rca_text is available.
    Always allows (injection only, never blocks).
    """
    if error_rate <= 0.3 or not rca_text:
        return ReflexResult(allow=True)

    return ReflexResult(
        allow=True,
        reflex_kind="rca_injection",
        inject_message=f"[SOMA] errors={error_rate:.0%}, root_cause: {rca_text}",
        detail=f"error_rate={error_rate:.2f}",
    )


def evaluate_commit_gate(
    grade: str,
    tool_name: str = "",
    tool_input: dict | None = None,
) -> ReflexResult:
    """Evaluate commit gate reflex.

    Only applies to git commit commands (Bash tool with git commit).
    Grade D/F -> block. Grade C -> warn. Grade A/B -> allow.
    """
    inp = tool_input or {}

    # Only gate git commit commands
    if tool_name != "Bash" or not _GIT_COMMIT_RE.search(inp.get("command", "")):
        return ReflexResult(allow=True)

    if grade in ("D", "F"):
        return ReflexResult(
            allow=False,
            reflex_kind="commit_gate",
            block_message=(
                f"[SOMA BLOCKED] Commit blocked — quality grade {grade}. "
                "Fix outstanding issues before committing."
            ),
            detail=f"grade={grade}",
        )

    if grade == "C":
        return ReflexResult(
            allow=True,
            reflex_kind="commit_gate",
            inject_message=(
                f"[SOMA WARNING] Quality grade {grade} — consider fixing "
                "issues before committing."
            ),
            detail=f"grade={grade}",
        )

    return ReflexResult(allow=True)


def evaluate_all_signals(
    *,
    prediction: object | None = None,
    soma_mode: str = "reflex",
    drift: float = 0.0,
    original_task: str = "",
    current_activity: str = "",
    error_rate: float = 0.0,
    rca_text: str | None = None,
    success_rate: float = 1.0,
    handoff_text: str = "",
    agent_id: str = "",
) -> list[ReflexResult]:
    """Evaluate all signal reflexes and return prioritized results.

    Caps to max 2 injections. Commit gate is handled separately in
    pre_tool_use (not included here).

    Priority order: rca > drift > handoff > checkpoint.
    """
    candidates: list[tuple[int, ReflexResult]] = []

    # Evaluate each signal reflex
    rca = evaluate_rca_injection(error_rate, rca_text)
    if rca.reflex_kind:
        candidates.append((_priority_rank(rca.reflex_kind), rca))

    drift_r = evaluate_drift_guardian(drift, original_task, current_activity)
    if drift_r.reflex_kind:
        candidates.append((_priority_rank(drift_r.reflex_kind), drift_r))

    handoff = evaluate_handoff(success_rate, handoff_text, agent_id)
    if handoff.reflex_kind:
        candidates.append((_priority_rank(handoff.reflex_kind), handoff))

    checkpoint = evaluate_predictor_checkpoint(prediction, soma_mode)
    if checkpoint.reflex_kind:
        candidates.append((_priority_rank(checkpoint.reflex_kind), checkpoint))

    # Sort by priority (lower rank = higher priority)
    candidates.sort(key=lambda x: x[0])

    # Cap to max injections
    return [r for _, r in candidates[:_MAX_INJECTIONS]]


def _priority_rank(kind: str) -> int:
    """Return priority rank for a reflex kind (lower = higher priority)."""
    try:
        return _SIGNAL_PRIORITY.index(kind)
    except ValueError:
        return len(_SIGNAL_PRIORITY)
