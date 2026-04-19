"""P2.9: empirical Tier 2 healing validation over analytics.db."""

from __future__ import annotations

from soma.analytics import AnalyticsStore
from soma.healing_validation import (
    format_report,
    measure_transitions,
    write_markdown_report,
)


def _seed(store: AnalyticsStore, session: str, sequence: list[tuple[str, float]]):
    ts = 1_700_000_000
    for i, (tool, pressure) in enumerate(sequence):
        store.record(
            agent_id=session, session_id=session, tool_name=tool,
            pressure=pressure, uncertainty=0.0, drift=0.0,
            error_rate=0.0, context_usage=0.0,
            token_count=0, cost=0.0, mode="GUIDE", error=False,
            source="hook",
        )
        # record sets its own timestamp via time.time(); we rely on
        # insertion order (rowid) to preserve sequence for the same
        # session in measure_transitions ORDER BY.
        _ = ts + i


def test_measure_transitions_returns_sorted_deltas(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    # 20 Bash→Read pairs with pressure drop of 0.2 each.
    for i in range(20):
        _seed(store, f"s{i}", [("Bash", 0.6), ("Read", 0.4)])
    # 20 Read→Bash pairs with pressure rise of 0.1 each.
    for i in range(20):
        _seed(store, f"t{i}", [("Read", 0.3), ("Bash", 0.4)])

    rows = measure_transitions(min_n=20, analytics=store)
    by_key = {r.transition: r for r in rows}
    assert "Bash→Read" in by_key
    assert "Read→Bash" in by_key
    assert by_key["Bash→Read"].delta < 0
    assert by_key["Read→Bash"].delta > 0
    # Sorted ascending — healing (negative) comes first.
    assert rows[0].delta <= rows[-1].delta


def test_measure_transitions_respects_min_n(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    # Only 5 pairs — below default min_n=20, should be filtered out.
    for i in range(5):
        _seed(store, f"s{i}", [("Bash", 0.6), ("Read", 0.4)])
    rows = measure_transitions(min_n=20, analytics=store)
    assert rows == []
    # With min_n=1 the pair shows up.
    rows2 = measure_transitions(min_n=1, analytics=store)
    assert any(r.transition == "Bash→Read" for r in rows2)


def test_measure_transitions_does_not_cross_sessions(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    # session A ends with Bash, session B starts with Read — must NOT
    # become a Bash→Read pair.
    _seed(store, "A", [("Edit", 0.3), ("Bash", 0.5)])
    _seed(store, "B", [("Read", 0.2), ("Edit", 0.3)])
    rows = measure_transitions(min_n=1, analytics=store)
    keys = [r.transition for r in rows]
    assert "Bash→Read" not in keys


def test_format_report_handles_empty():
    assert "No transition data" in format_report([])


def test_format_report_shows_both_sides(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    for i in range(25):
        _seed(store, f"s{i}", [("Bash", 0.7), ("Read", 0.4)])
        _seed(store, f"t{i}", [("Read", 0.3), ("Bash", 0.5)])
    rows = measure_transitions(min_n=20, analytics=store)
    report = format_report(rows)
    assert "Top healing transitions" in report
    assert "Top aggravating transitions" in report
    assert "Bash→Read" in report
    assert "Read→Bash" in report


def test_write_markdown_report(tmp_path):
    store = AnalyticsStore(path=tmp_path / "a.db")
    for i in range(25):
        _seed(store, f"s{i}", [("Bash", 0.6), ("Read", 0.4)])
    rows = measure_transitions(min_n=20, analytics=store)
    out = tmp_path / "healing.md"
    write_markdown_report(out, rows)
    content = out.read_text()
    assert "| Transition | n | Δ pressure |" in content
    assert "Bash→Read" in content
