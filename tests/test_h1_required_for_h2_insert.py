"""
Regression for v2026.6.1 fix #4 — h=2 INSERT must drop, not NULL,
when pressure_after_h1 was never buffered.

Same bias class as B1/B2 (NULL firing_id) but on the h=1 column:
INSERTing NULL h=1 makes validate-patterns @h1 silently drop the
row, biasing the t-test population.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from soma.hooks.post_tool_use import _record_ab_outcome_at_horizon


def _pending(actions_since: int, *, h1: float | None, recorded: bool = False) -> dict:
    return {
        "ab_arm": "treatment",
        "actions_since": actions_since,
        "pressure_at_injection": 0.5,
        "pattern": "budget",
        "firing_id": "fid-test-001",
        "pressure_after_h1": h1,  # the value under test
        "ab_recorded": recorded,
    }


def test_h2_insert_drops_when_h1_missing(tmp_path: Path) -> None:
    """h=2 fires but pending has no buffered h=1 — must NOT INSERT."""
    pending = _pending(2, h1=None)
    store = MagicMock()
    with patch(
        "soma.analytics.AnalyticsStore", return_value=store
    ):
        result = _record_ab_outcome_at_horizon(
            agent_id="agent-prod-01",
            pending=pending,
            pressure_after=0.4,
            analytics_path=tmp_path / "analytics.db",
        )
    assert result is False, "should not record"
    store.record_ab_outcome.assert_not_called()


def test_h2_insert_proceeds_when_h1_present(tmp_path: Path) -> None:
    """Sanity: with h=1 buffered, the INSERT goes through."""
    pending = _pending(2, h1=0.45)
    store = MagicMock()
    with patch(
        "soma.analytics.AnalyticsStore", return_value=store
    ):
        result = _record_ab_outcome_at_horizon(
            agent_id="agent-prod-01",
            pending=pending,
            pressure_after=0.4,
            analytics_path=tmp_path / "analytics.db",
        )
    assert result is True
    store.record_ab_outcome.assert_called_once()
    kwargs = store.record_ab_outcome.call_args.kwargs
    assert kwargs["pressure_after_h1"] == 0.45


def test_h_above_2_force_insert_drops_when_h1_missing(tmp_path: Path) -> None:
    """Force-INSERT branch (timeout-forced jump past h=2) must also
    drop when pressure_after_h1 is None — same bias class."""
    pending = _pending(5, h1=None)
    pending["pressure_after_h2"] = 0.42  # h2 was buffered, but h1 was not
    store = MagicMock()
    with patch(
        "soma.analytics.AnalyticsStore", return_value=store
    ):
        result = _record_ab_outcome_at_horizon(
            agent_id="agent-prod-01",
            pending=pending,
            pressure_after=0.4,
            analytics_path=tmp_path / "analytics.db",
        )
    assert result is False, "force-INSERT must drop when h1 is None"
    store.record_ab_outcome.assert_not_called()
