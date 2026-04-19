"""Empirical validation for tool-to-tool healing transitions.

The Tier 2 claim is that certain transitions (Bash→Read, Write→Grep,
Edit→Read) reliably drop pressure. We measured this on internal data in
April 2026 and quoted −7% / −5%. This module re-derives the numbers
from ``~/.soma/analytics.db`` so the figure on the README is always the
current one, not a frozen snapshot.

Usage::

    from soma.healing_validation import measure_transitions
    rows = measure_transitions()
    for r in rows:
        print(r["transition"], r["delta"], r["n"])

Measurement: for every chronological pair ``(prev_tool, next_tool)`` in
``actions`` scoped to the same session_id, we compute
``delta = next.pressure - prev.pressure``. Positive delta = pressure up,
negative = healing. We keep only pairs with n >= 20 so the mean isn't
dominated by outliers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from soma.analytics import AnalyticsStore


@dataclass(frozen=True)
class TransitionStat:
    transition: str  # "Bash→Read"
    n: int
    delta: float  # mean pressure delta (negative = healing)

    def as_dict(self) -> dict:
        return {"transition": self.transition, "n": self.n, "delta": self.delta}


def measure_transitions(
    min_n: int = 20, analytics: AnalyticsStore | None = None,
) -> list[TransitionStat]:
    """Return per-pair pressure deltas for every sufficiently-common transition.

    Sorted ascending by delta (biggest healing first). Uses the real
    analytics DB by default; pass a custom ``AnalyticsStore`` for tests.
    """
    store = analytics or AnalyticsStore()
    cursor = store._conn.execute(
        """
        SELECT session_id, tool_name, pressure, timestamp
        FROM actions
        WHERE pressure IS NOT NULL
        ORDER BY session_id, timestamp, rowid
        """
    )
    rows = cursor.fetchall()

    # Bucket deltas keyed by "prev→next".
    buckets: dict[str, list[float]] = {}
    prev_sid: str | None = None
    prev_tool: str | None = None
    prev_pressure: float | None = None

    for sid, tool, pressure, _ts in rows:
        if sid != prev_sid:
            prev_sid = sid
            prev_tool = tool
            prev_pressure = pressure
            continue
        if prev_tool is not None and prev_pressure is not None:
            key = f"{prev_tool}→{tool}"
            buckets.setdefault(key, []).append(pressure - prev_pressure)
        prev_tool = tool
        prev_pressure = pressure

    results = [
        TransitionStat(
            transition=key, n=len(deltas), delta=mean(deltas),
        )
        for key, deltas in buckets.items()
        if len(deltas) >= min_n
    ]
    results.sort(key=lambda r: r.delta)
    return results


def format_report(rows: list[TransitionStat], limit: int = 10) -> str:
    """Human-readable CLI report: top healing + top aggravating transitions."""
    if not rows:
        return "  No transition data yet (need >= 20 observations per pair)."

    healing = [r for r in rows if r.delta < 0][:limit]
    aggravating = [r for r in rows if r.delta > 0][-limit:][::-1]

    lines = ["  Top healing transitions (pressure drops):"]
    for r in healing or []:
        lines.append(f"    {r.transition:<30s} Δ={r.delta:+.3f}  n={r.n}")
    if not healing:
        lines.append("    (none observed)")

    lines.append("")
    lines.append("  Top aggravating transitions (pressure rises):")
    for r in aggravating or []:
        lines.append(f"    {r.transition:<30s} Δ={r.delta:+.3f}  n={r.n}")
    if not aggravating:
        lines.append("    (none observed)")
    return "\n".join(lines)


def write_markdown_report(path: Path, rows: list[TransitionStat]) -> None:
    """Emit a README-ready markdown table of the measured deltas."""
    lines = ["| Transition | n | Δ pressure |", "|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.transition} | {r.n} | {r.delta:+.3f} |")
    path.write_text("\n".join(lines) + "\n")
