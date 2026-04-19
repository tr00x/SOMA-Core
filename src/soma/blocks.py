"""Strict-mode block state — one file per agent family.

Strict mode turns pattern guidance into hard PreToolUse gates. This
module owns the persisted state: which patterns currently block which
tools for which family, plus the CLI-facing primitives to clear them.

State shape (``~/.soma/blocks_{family}.json``):

    {
      "family": "cc",
      "blocks": [
        {"pattern": "retry_storm", "tool": "Bash", "created_at": 1760..., "reason": "3 consecutive fails"}
      ],
      "silenced_until": {"retry_storm": 1760...}   # one-shot silences
    }

Design notes:

- A "block" is tool-scoped — blocking Bash doesn't block Read, so the
  agent always has a way forward (Read/Grep usually clears the streak).
- ``silenced_until`` is separate from ``blocks`` because a 30-minute
  per-pattern silence is CLI-driven, not automatic pattern-driven.
- Persistence is atomic (tempfile → rename). Corrupt files fall back
  to fresh state so a broken block file never stops the agent.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from soma.calibration import calibration_family
from soma.state import SOMA_DIR

# One-shot silence duration when user runs `soma unblock --pattern X`.
DEFAULT_SILENCE_SECONDS = 30 * 60  # 30 min


@dataclass(frozen=True)
class Block:
    pattern: str
    tool: str
    created_at: float
    reason: str = ""


@dataclass
class BlockState:
    family: str
    blocks: list[Block] = field(default_factory=list)
    silenced_until: dict[str, float] = field(default_factory=dict)

    # ── Mutations ──────────────────────────────────────────────────

    def add_block(self, pattern: str, tool: str, reason: str = "") -> Block:
        """Register a new block, replacing any existing (pattern, tool) pair.

        Keeping the latest instance matters so ``reason`` and ``created_at``
        reflect the most recent trigger, not a stale one.
        """
        self.blocks = [b for b in self.blocks if not (b.pattern == pattern and b.tool == tool)]
        block = Block(pattern=pattern, tool=tool, created_at=time.time(), reason=reason)
        self.blocks.append(block)
        return block

    def clear_block(self, pattern: str | None = None, tool: str | None = None) -> int:
        """Drop blocks matching the filter; return count removed.

        ``clear_block()`` with no args clears everything (soma unblock --all).
        """
        before = len(self.blocks)
        self.blocks = [
            b for b in self.blocks
            if not (
                (pattern is None or b.pattern == pattern)
                and (tool is None or b.tool == tool)
            )
        ]
        return before - len(self.blocks)

    def is_blocked(self, pattern: str, tool: str) -> bool:
        return any(b.pattern == pattern and b.tool == tool for b in self.blocks)

    def any_block_for_tool(self, tool: str) -> Block | None:
        """Return the newest active block for ``tool``, or None."""
        matches = [b for b in self.blocks if b.tool == tool]
        if not matches:
            return None
        return max(matches, key=lambda b: b.created_at)

    # ── Silences (one-shot) ────────────────────────────────────────

    def silence_pattern(self, pattern: str, seconds: int = DEFAULT_SILENCE_SECONDS) -> float:
        """Silence ``pattern`` for ``seconds`` and return the deadline."""
        deadline = time.time() + max(1, seconds)
        self.silenced_until[pattern] = deadline
        return deadline

    def is_silenced(self, pattern: str) -> bool:
        """True iff the pattern is within its silence window."""
        deadline = self.silenced_until.get(pattern)
        if deadline is None:
            return False
        if time.time() >= deadline:
            # Lazy cleanup on read.
            del self.silenced_until[pattern]
            return False
        return True

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = asdict(self)
        # dataclasses nested in list are auto-expanded by asdict; leave as-is.
        return d

    @classmethod
    def from_dict(cls, data: dict) -> BlockState:
        family = data.get("family", "default")
        raw_blocks = data.get("blocks") or []
        blocks = [
            Block(
                pattern=b.get("pattern", ""),
                tool=b.get("tool", ""),
                created_at=float(b.get("created_at", 0.0)),
                reason=b.get("reason", ""),
            )
            for b in raw_blocks if isinstance(b, dict) and b.get("pattern") and b.get("tool")
        ]
        silenced = data.get("silenced_until") or {}
        # Filter expired entries on load.
        now = time.time()
        silenced = {k: float(v) for k, v in silenced.items() if float(v) > now}
        return cls(family=family, blocks=blocks, silenced_until=silenced)


# ── Persistence ────────────────────────────────────────────────────

def _block_path(family: str) -> Path:
    return SOMA_DIR / f"blocks_{family}.json"


def load_block_state(agent_id: str) -> BlockState:
    family = calibration_family(agent_id)
    path = _block_path(family)
    if path.exists():
        try:
            return BlockState.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return BlockState(family=family)


def save_block_state(state: BlockState) -> None:
    path = _block_path(state.family)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state.to_dict(), f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clear_all_blocks(agent_id: str) -> bool:
    """Delete the block file entirely (one-shot full reset)."""
    path = _block_path(calibration_family(agent_id))
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
