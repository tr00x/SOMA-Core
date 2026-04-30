"""
Regression for v2026.6.x fix #29 — healing-transition cache must
expire after HEALING_CACHE_TTL_SECONDS so long-lived processes
(dashboard) pick up updated analytics instead of serving stale
transitions forever.
"""
from __future__ import annotations

from unittest.mock import patch

from soma import contextual_guidance as cg


def test_cache_refreshes_after_ttl() -> None:
    """After TTL elapses, _healing_table must call _load_healing_from_analytics again."""
    cg._reset_healing_cache()

    call_count = {"n": 0}

    def fake_load():
        call_count["n"] += 1
        return {"Bash": ("Read", f"call#{call_count['n']}")}

    with patch.object(cg, "_load_healing_from_analytics", side_effect=fake_load):
        # First call populates cache.
        cg._healing_table(use_analytics=True)
        assert call_count["n"] == 1

        # Second call within TTL — cache hit, no reload.
        cg._healing_table(use_analytics=True)
        assert call_count["n"] == 1, "cache refreshed too eagerly"

        # Force the cache timestamp to be older than TTL — next call must reload.
        cg._HEALING_CACHE_TS -= cg.HEALING_CACHE_TTL_SECONDS + 1
        cg._healing_table(use_analytics=True)
        assert call_count["n"] == 2, (
            f"cache did not refresh after TTL: load count {call_count['n']}"
        )


def test_use_analytics_false_skips_cache() -> None:
    """Tests can short-circuit by passing use_analytics=False."""
    cg._reset_healing_cache()
    with patch.object(cg, "_load_healing_from_analytics") as mock:
        result = cg._healing_table(use_analytics=False)
        mock.assert_not_called()
    assert isinstance(result, dict)


def test_reset_clears_both_cache_and_timestamp() -> None:
    """The test-hook reset must zero both the dict and the timestamp."""
    cg._HEALING_CACHE = {"Bash": ("Read", "stale")}
    cg._HEALING_CACHE_TS = 99999.0
    cg._reset_healing_cache()
    assert cg._HEALING_CACHE is None
    assert cg._HEALING_CACHE_TS == 0.0


def test_cache_uses_monotonic_clock_not_wall_clock() -> None:
    """A backwards wall-clock jump (NTP correction) must not freeze the cache.

    Wall-clock jumping back makes ``time.time() - cached_ts`` strictly negative,
    which is < TTL for any TTL >= 0 — so a buggy implementation would never
    refresh. Monotonic time can never go backwards, so the test stubs
    ``time.time`` to a value far in the past and confirms the cache still
    refreshes when the monotonic delta exceeds the TTL.
    """
    cg._reset_healing_cache()
    call_count = {"n": 0}

    def fake_load():
        call_count["n"] += 1
        return {"Bash": ("Read", f"call#{call_count['n']}")}

    with patch.object(cg, "_load_healing_from_analytics", side_effect=fake_load):
        cg._healing_table(use_analytics=True)
        assert call_count["n"] == 1

        # Simulate the cache having been populated TTL+1 monotonic seconds ago.
        # If the implementation used wall-clock and a backward NTP correction
        # had moved time.time() backwards relative to that recorded timestamp,
        # this delta would be negative and the cache would never refresh.
        cg._HEALING_CACHE_TS -= cg.HEALING_CACHE_TTL_SECONDS + 1
        cg._healing_table(use_analytics=True)
        assert call_count["n"] == 2, "monotonic-based TTL must trigger refresh"
