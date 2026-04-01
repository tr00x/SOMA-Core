"""SOMA Advanced Signal Reflexes — smart throttle, anomaly, context overflow.

Pure function evaluators. Each takes computed state and returns a ReflexResult.
No I/O, no side effects. All evaluators are injection-only (never block).
"""

from __future__ import annotations

from soma.reflexes import ReflexResult
from soma.types import ResponseMode


# ── Smart throttle ───────────────────────────────────────────────────


def evaluate_smart_throttle(
    mode: ResponseMode,
    pressure: float = 0.0,
) -> ReflexResult:
    """Progressively stronger response-length guidance by mode.

    OBSERVE -> silent. GUIDE/WARN/BLOCK -> increasingly strict injection.
    Never blocks — injection only.
    """
    if mode == ResponseMode.OBSERVE:
        return ReflexResult(allow=True)

    messages = {
        ResponseMode.GUIDE: "[SOMA] Keep responses focused. Pressure rising.",
        ResponseMode.WARN: "[SOMA] Max 500 tokens per response. Pressure elevated.",
        ResponseMode.BLOCK: "[SOMA] One sentence only. Critical pressure.",
    }

    msg = messages.get(mode)
    if msg is None:
        return ReflexResult(allow=True)

    return ReflexResult(
        allow=True,
        reflex_kind="smart_throttle",
        inject_message=msg,
        detail=f"mode={mode.name}",
    )


# ── Fingerprint anomaly ─────────────────────────────────────────────


def evaluate_fingerprint_anomaly(
    divergence: float,
    baseline_divergence: float = 0.2,
    explanation: str = "",
) -> ReflexResult:
    """Detect behavioral anomaly when JSD divergence exceeds 2x baseline.

    Never blocks — injection only.
    """
    threshold = 2.0 * baseline_divergence

    if divergence <= threshold:
        return ReflexResult(allow=True)

    desc = f" {explanation}" if explanation else ""

    return ReflexResult(
        allow=True,
        reflex_kind="fingerprint_anomaly",
        inject_message=(
            f"[SOMA] Behavioral anomaly -- agent pattern changed "
            f"significantly.{desc}"
        ),
        detail=f"divergence={divergence:.2f}, threshold={threshold:.2f}",
    )


# ── Context overflow ─────────────────────────────────────────────────


def evaluate_context_overflow(context_usage: float) -> ReflexResult:
    """Warn at 80% and critical at 95% context window usage.

    Never blocks — injection only.
    """
    pct = int(context_usage * 100)

    if context_usage >= 0.95:
        return ReflexResult(
            allow=True,
            reflex_kind="context_overflow",
            inject_message=(
                f"[SOMA] CRITICAL: Context nearly full ({pct}%). "
                "Commit and /clear NOW."
            ),
            detail=f"context_usage={context_usage:.0%}",
        )

    if context_usage >= 0.80:
        return ReflexResult(
            allow=True,
            reflex_kind="context_overflow",
            inject_message=(
                f"[SOMA] Context {pct}% full. Checkpoint your work."
            ),
            detail=f"context_usage={context_usage:.0%}",
        )

    return ReflexResult(allow=True)
