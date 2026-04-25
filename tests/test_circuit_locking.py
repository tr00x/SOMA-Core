"""Race-condition coverage for circuit_{aid}.json read-modify-write writers.

All four writers (state, signal_pressures, followthrough, cooldowns) hit the
same JSON file. Without the fcntl lock added in 2026-04-25, two concurrent
PostToolUse hooks lose each other's increments — exactly the silent-failure
class that masked the v2026.5.5 silence-cache regression for two days.
"""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

import pytest

from soma.hooks import common as hc


def _writer_worker(soma_dir: str, agent_id: str, key_prefix: str, n: int):
    """Each worker adds N distinct keys via circuit_transaction.

    Real hooks need read-modify-write atomicity. The transaction helper
    holds the lock across the read and the write so concurrent workers
    can't lose each other's contributions.
    """
    import importlib
    from soma.hooks import common as _hc
    importlib.reload(_hc)
    _hc.SOMA_DIR = Path(soma_dir)
    for i in range(n):
        with _hc.circuit_transaction(agent_id) as data:
            cooldowns = data.get("guidance_cooldowns", {})
            cooldowns[f"{key_prefix}_{i}"] = i
            data["guidance_cooldowns"] = cooldowns


@pytest.fixture
def isolated_soma_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "SOMA_DIR", tmp_path)
    return tmp_path


class TestCircuitLocking:
    def test_concurrent_writers_preserve_all_keys(self, isolated_soma_dir):
        """Two processes each adding 20 distinct keys must end with all 40."""
        ctx = mp.get_context("spawn")
        p1 = ctx.Process(
            target=_writer_worker,
            args=(str(isolated_soma_dir), "raceagent", "alpha", 20),
        )
        p2 = ctx.Process(
            target=_writer_worker,
            args=(str(isolated_soma_dir), "raceagent", "beta", 20),
        )
        p1.start()
        p2.start()
        p1.join(timeout=30)
        p2.join(timeout=30)
        assert p1.exitcode == 0 and p2.exitcode == 0

        data = hc.read_guidance_cooldowns("raceagent")
        alpha_keys = {k for k in data if k.startswith("alpha_")}
        beta_keys = {k for k in data if k.startswith("beta_")}
        assert len(alpha_keys) == 20, f"lost alpha writes: {len(alpha_keys)}/20"
        assert len(beta_keys) == 20, f"lost beta writes: {len(beta_keys)}/20"

    def test_lock_released_on_exception(self, isolated_soma_dir, monkeypatch):
        """An exception inside the locked block must still release the lock,
        otherwise the next hook invocation deadlocks for the EX wait."""
        path = hc._circuit_path("locktest")

        # First call succeeds and writes data.
        hc.write_guidance_cooldowns({"k1": 1}, "locktest")
        assert json.loads(path.read_text())["guidance_cooldowns"] == {"k1": 1}

        # Force an exception in write_text — the lock should still be released.
        original_write = Path.write_text

        def boom(self, *_a, **_kw):
            if self == path:
                raise OSError("simulated mid-lock failure")
            return original_write(self, *_a, **_kw)

        monkeypatch.setattr(Path, "write_text", boom)
        # write_guidance_cooldowns swallows exceptions internally — must not deadlock.
        hc.write_guidance_cooldowns({"k2": 2}, "locktest")
        monkeypatch.setattr(Path, "write_text", original_write)

        # Subsequent write must succeed (lock was released).
        hc.write_guidance_cooldowns({"k3": 3}, "locktest")
        assert json.loads(path.read_text())["guidance_cooldowns"] == {"k3": 3}

    def test_followthrough_and_cooldowns_share_file_safely(self, isolated_soma_dir):
        """The followthrough writer and cooldowns writer touch the same file
        with different keys. Sequential writes must not erase each other."""
        hc.write_guidance_cooldowns({"context": 5}, "shareagent")
        hc.write_guidance_followthrough(
            {"pattern": "context", "actions_since": 1}, "shareagent",
        )

        data = json.loads(hc._circuit_path("shareagent").read_text())
        assert data["guidance_cooldowns"] == {"context": 5}
        assert data["guidance_followthrough"]["pattern"] == "context"
