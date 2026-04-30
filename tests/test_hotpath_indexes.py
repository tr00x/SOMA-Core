"""
Regression for v2026.6.x fix #10 — dashboard + release-gate hot
path needs indexes that match the actual queries:

- guidance_outcomes is read by `pattern_key` filter in 5+ dashboard
  call sites; full-table scan at 80k+ rows wrecks every page load.
- ab_outcomes is read with `WHERE pattern = ? AND firing_id IS NOT NULL`
  by both validate-patterns and the release coverage gate; partial
  index keyed on (pattern, arm) WHERE firing_id IS NOT NULL is the
  exact match.
"""
from __future__ import annotations

from pathlib import Path

from soma.analytics import AnalyticsStore


def _index_names(store: AnalyticsStore, table: str) -> set[str]:
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND tbl_name=?",
        (table,),
    ).fetchall()
    return {r[0] for r in rows}


def test_guidance_outcomes_pattern_key_index(tmp_path: Path) -> None:
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        idx = _index_names(store, "guidance_outcomes")
        assert any("pattern_key" in n.lower() for n in idx), (
            f"no index on guidance_outcomes.pattern_key — got {idx}"
        )
    finally:
        store.close()


def test_ab_outcomes_partial_index_on_firing_id(tmp_path: Path) -> None:
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        idx = _index_names(store, "ab_outcomes")
        # Look for the new (pattern, arm) partial index.
        assert any("pattern_arm" in n.lower() for n in idx), (
            f"no (pattern, arm) index on ab_outcomes — got {idx}"
        )
    finally:
        store.close()


def test_partial_index_actually_used_for_arm_count_query(tmp_path: Path) -> None:
    """EXPLAIN QUERY PLAN must show an index scan, not SCAN TABLE."""
    store = AnalyticsStore(path=tmp_path / "a.db")
    try:
        # Plant enough rows so the planner picks index over scan.
        for i in range(50):
            store._conn.execute(
                "INSERT INTO ab_outcomes(timestamp, agent_family, pattern, arm, "
                "pressure_before, pressure_after, followed, firing_id) "
                "VALUES (?, 'cc', 'budget', 'treatment', 0, 0, 0, ?)",
                (float(i), f"fid-t-{i}"),
            )
        store._conn.commit()
        store._conn.execute("ANALYZE")
        plan_rows = store._conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT arm, COUNT(*) FROM ab_outcomes "
            "WHERE pattern = ? AND firing_id IS NOT NULL "
            "GROUP BY arm",
            ("budget",),
        ).fetchall()
        plan_text = " ".join(str(r) for r in plan_rows).lower()
        # Either USING INDEX or USING COVERING INDEX is fine; just not SCAN TABLE.
        assert "using" in plan_text and "index" in plan_text, (
            f"query planner not using an index: {plan_text}"
        )
    finally:
        store.close()
