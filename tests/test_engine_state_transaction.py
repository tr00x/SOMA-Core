"""
Regression for v2026.6.x fix #18 — engine_state.json read-modify-write
must be atomic across concurrent hook invocations.

Existing save_engine_state takes flock EX around the *write*, and
load_engine_state takes flock SH around the *read*. But neither
covers the read-mutate-write window: two hooks can both load
(SH compatible), both mutate locally, then race to save — last
writer wins, first writer's updates silently lost.

The transaction primitive holds flock EX for the entire RMW so
concurrent threads serialize cleanly.
"""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

from soma.persistence import (
    engine_state_transaction,
    load_engine_state,
    save_engine_state,
)


def test_concurrent_rmw_loses_updates_without_transaction(tmp_path: Path) -> None:
    """Baseline / sanity: hammering save+load WITHOUT the transaction
    primitive demonstrates the race. (Marked xfail-style: this test
    asserts the bug exists in the legacy path.)"""
    state_path = tmp_path / "engine_state.json"
    from soma.engine import SOMAEngine

    # Initial state with one agent at action_count=0.
    engine = SOMAEngine(budget={"tokens": 100000})
    engine.register_agent("agent-1")
    save_engine_state(engine, str(state_path))

    # 4 threads each load+increment+save 25 times = expected 100 actions.
    expected = 100

    def worker():
        for _ in range(25):
            e = load_engine_state(str(state_path))
            if e is None:
                continue
            try:
                e.get_level("agent-1")
            except Exception:
                e.register_agent("agent-1")
            # increment via direct mutation (race-prone)
            e._agents["agent-1"].action_count += 1
            save_engine_state(e, str(state_path))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = load_engine_state(str(state_path))
    actual = final._agents["agent-1"].action_count
    # We DO expect data loss without the transaction — pinning the
    # bug presence so the next test can show the transaction fixes it.
    assert actual < expected, (
        f"baseline test expected race condition: actual={actual} "
        f"expected_lossless={expected}. If this passes, the race may "
        f"have been masked by another fix — re-evaluate."
    )


def test_transaction_prevents_lost_updates(tmp_path: Path) -> None:
    """With engine_state_transaction wrapping the RMW, all 100
    increments must land — none lost to the race."""
    state_path = tmp_path / "engine_state.json"
    from soma.engine import SOMAEngine

    engine = SOMAEngine(budget={"tokens": 100000})
    engine.register_agent("agent-1")
    save_engine_state(engine, str(state_path))

    def worker():
        for _ in range(25):
            with engine_state_transaction(str(state_path)) as e:
                try:
                    e.get_level("agent-1")
                except Exception:
                    e.register_agent("agent-1")
                e._agents["agent-1"].action_count += 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = load_engine_state(str(state_path))
    assert final._agents["agent-1"].action_count == 100, (
        f"transaction failed to serialize: got "
        f"{final._agents['agent-1'].action_count}, expected 100"
    )


def test_transaction_creates_engine_when_state_missing(tmp_path: Path) -> None:
    """First-time write: state file doesn't exist yet. The transaction
    must yield a fresh engine and save it on exit."""
    state_path = tmp_path / "fresh.json"
    assert not state_path.exists()

    with engine_state_transaction(str(state_path), default_budget={"tokens": 50000}) as e:
        e.register_agent("first-agent")
        e._agents["first-agent"].action_count = 7

    assert state_path.exists()
    reloaded = load_engine_state(str(state_path))
    assert reloaded._agents["first-agent"].action_count == 7
