"""
Regression for v2026.6.x fix #22 — ``ab_outcomes`` (the live table)
must have exactly one INSERT writer in the source tree:
``AnalyticsStore.record_ab_outcome``. Other INSERT statements may
reference *archive* tables (``ab_outcomes_pre_firing_id_legacy``,
``ab_outcomes_biased_pre_v2026_5_5``) but never the live table.

Pinning the invariant so a future maintainer adding a backfill
script or replay tool doesn't silently re-introduce the bias-class
the v2026.6.x trigger and Python guards close at the canonical
writer.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "soma"

# Match `INSERT INTO ab_outcomes ...` but NOT
# `INSERT INTO ab_outcomes_<archive_suffix>`.
_LIVE_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+ab_outcomes(?!_)\b",
    re.IGNORECASE,
)


def _scan_for_live_inserts() -> dict[Path, list[int]]:
    """Return {file: [line_numbers]} of every `INSERT INTO ab_outcomes`
    that targets the live table (not an archive)."""
    hits: dict[Path, list[int]] = {}
    for py in SRC.rglob("*.py"):
        try:
            text = py.read_text()
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _LIVE_INSERT_RE.search(line):
                hits.setdefault(py, []).append(lineno)
    return hits


def test_only_record_ab_outcome_inserts_into_live_table() -> None:
    """The single live INSERT must live in analytics.py.
    record_ab_outcome's body. Anywhere else is a structural defect:
    the bias-class defenses (h1 dropguard, firing_id NOT NULL trigger)
    only apply if writes funnel through record_ab_outcome.
    """
    hits = _scan_for_live_inserts()
    # Allowed location: src/soma/analytics.py
    analytics = SRC / "analytics.py"
    extra = {f: lines for f, lines in hits.items() if f != analytics}
    assert not extra, (
        f"INSERT INTO ab_outcomes found outside analytics.py — "
        f"violates single-writer invariant: {extra}"
    )
    # Inside analytics.py: must be exactly one INSERT statement.
    analytics_hits = hits.get(analytics, [])
    assert len(analytics_hits) == 1, (
        f"Expected exactly 1 live INSERT in analytics.py "
        f"(record_ab_outcome). Got {len(analytics_hits)} at lines "
        f"{analytics_hits}. Adding a second writer re-opens the "
        f"bias class — funnel through record_ab_outcome instead."
    )
