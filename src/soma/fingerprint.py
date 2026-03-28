"""SOMA Agent Fingerprinting — learn and detect deviations from normal behavior.

Each agent develops a behavioral fingerprint over time:
- Tool distribution (what % of actions use each tool)
- Error rate baseline
- Average action duration
- Read/Write ratio
- Session length patterns

When current behavior diverges significantly from the fingerprint,
SOMA flags it as a potential corruption or mode shift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Fingerprint:
    """Behavioral fingerprint for an agent."""
    tool_distribution: dict[str, float] = field(default_factory=dict)  # tool → fraction
    avg_error_rate: float = 0.0
    avg_duration: float = 0.0
    read_write_ratio: float = 1.0  # reads / max(writes, 1)
    avg_session_length: float = 50.0  # actions per session
    sample_count: int = 0

    def divergence(self, current: "Fingerprint") -> float:
        """Compute divergence score [0, 1] between this fingerprint and current behavior.

        Uses Jensen-Shannon-like divergence for tool distribution + weighted
        deltas for scalar signals.
        """
        if self.sample_count < 10:
            return 0.0  # Not enough data to judge

        scores: list[float] = []

        # Tool distribution divergence (simplified JS divergence)
        all_tools = set(self.tool_distribution) | set(current.tool_distribution)
        if all_tools:
            kl_sum = 0.0
            for tool in all_tools:
                p = self.tool_distribution.get(tool, 0.001)
                q = current.tool_distribution.get(tool, 0.001)
                m = (p + q) / 2
                if p > 0 and m > 0:
                    kl_sum += p * math.log2(p / m)
                if q > 0 and m > 0:
                    kl_sum += q * math.log2(q / m)
            # Normalize: JS divergence is in [0, 1] for base-2 log
            js = min(kl_sum / 2, 1.0)
            scores.append(js * 2.0)  # Weight: tool distribution matters most

        # Error rate delta
        if self.avg_error_rate > 0:
            err_delta = abs(current.avg_error_rate - self.avg_error_rate) / max(self.avg_error_rate, 0.01)
            scores.append(min(err_delta, 1.0))

        # Read/Write ratio delta
        if self.read_write_ratio > 0:
            rw_delta = abs(current.read_write_ratio - self.read_write_ratio) / max(self.read_write_ratio, 0.1)
            scores.append(min(rw_delta * 0.5, 1.0))

        if not scores:
            return 0.0

        return min(sum(scores) / len(scores), 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_distribution": dict(self.tool_distribution),
            "avg_error_rate": self.avg_error_rate,
            "avg_duration": self.avg_duration,
            "read_write_ratio": self.read_write_ratio,
            "avg_session_length": self.avg_session_length,
            "sample_count": self.sample_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fingerprint":
        return cls(
            tool_distribution=dict(data.get("tool_distribution", {})),
            avg_error_rate=data.get("avg_error_rate", 0.0),
            avg_duration=data.get("avg_duration", 0.0),
            read_write_ratio=data.get("read_write_ratio", 1.0),
            avg_session_length=data.get("avg_session_length", 50.0),
            sample_count=data.get("sample_count", 0),
        )


class FingerprintEngine:
    """Builds and maintains agent fingerprints across sessions.

    The fingerprint is an EMA (exponential moving average) of behavioral
    signals — it adapts slowly so sudden shifts are detectable.
    """

    def __init__(self, alpha: float = 0.1) -> None:
        self.alpha = alpha
        self._fingerprints: dict[str, Fingerprint] = {}

    def get(self, agent_id: str) -> Fingerprint | None:
        return self._fingerprints.get(agent_id)

    def update_from_session(self, agent_id: str, action_log: list[dict]) -> Fingerprint:
        """Update fingerprint from a completed (or in-progress) session's action log.

        Returns the updated fingerprint.
        """
        if not action_log:
            return self._fingerprints.get(agent_id, Fingerprint())

        current = self._compute_current(action_log)

        if agent_id not in self._fingerprints:
            self._fingerprints[agent_id] = current
            return current

        fp = self._fingerprints[agent_id]
        alpha = self.alpha

        # EMA update for tool distribution
        all_tools = set(fp.tool_distribution) | set(current.tool_distribution)
        new_dist = {}
        for tool in all_tools:
            old_val = fp.tool_distribution.get(tool, 0.0)
            cur_val = current.tool_distribution.get(tool, 0.0)
            new_dist[tool] = alpha * cur_val + (1 - alpha) * old_val
        fp.tool_distribution = new_dist

        # EMA update for scalars
        fp.avg_error_rate = alpha * current.avg_error_rate + (1 - alpha) * fp.avg_error_rate
        fp.avg_duration = alpha * current.avg_duration + (1 - alpha) * fp.avg_duration
        fp.read_write_ratio = alpha * current.read_write_ratio + (1 - alpha) * fp.read_write_ratio
        fp.avg_session_length = alpha * len(action_log) + (1 - alpha) * fp.avg_session_length
        fp.sample_count += 1

        return fp

    def check_divergence(self, agent_id: str, action_log: list[dict]) -> tuple[float, str]:
        """Check if current behavior diverges from fingerprint.

        Returns (divergence_score, explanation).
        """
        fp = self._fingerprints.get(agent_id)
        if fp is None or fp.sample_count < 5:
            return 0.0, ""

        current = self._compute_current(action_log)
        div = fp.divergence(current)

        if div < 0.2:
            return div, ""

        # Find what changed most
        changes: list[str] = []

        # Tool distribution shift
        for tool in set(fp.tool_distribution) | set(current.tool_distribution):
            expected = fp.tool_distribution.get(tool, 0)
            actual = current.tool_distribution.get(tool, 0)
            if abs(actual - expected) > 0.15:
                direction = "↑" if actual > expected else "↓"
                changes.append(f"{tool} {direction}{abs(actual - expected):.0%}")

        # Error rate shift
        if abs(current.avg_error_rate - fp.avg_error_rate) > 0.1:
            changes.append(f"errors {current.avg_error_rate:.0%} vs normal {fp.avg_error_rate:.0%}")

        # R/W ratio shift
        if fp.read_write_ratio > 0:
            rw_change = abs(current.read_write_ratio - fp.read_write_ratio) / max(fp.read_write_ratio, 0.1)
            if rw_change > 0.5:
                changes.append(f"read/write ratio shifted ({current.read_write_ratio:.1f} vs {fp.read_write_ratio:.1f})")

        explanation = "; ".join(changes[:3]) if changes else "behavioral pattern changed"
        return div, explanation

    def _compute_current(self, action_log: list[dict]) -> Fingerprint:
        """Compute a fingerprint snapshot from current action log."""
        n = len(action_log)
        if n == 0:
            return Fingerprint()

        # Tool distribution
        tool_counts: dict[str, int] = {}
        errors = 0
        total_duration = 0.0
        reads = 0
        writes = 0

        for entry in action_log:
            tool = entry.get("tool", "?")
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            if entry.get("error"):
                errors += 1
            reads += 1 if tool in ("Read", "Grep", "Glob") else 0
            writes += 1 if tool in ("Write", "Edit") else 0

        tool_dist = {t: c / n for t, c in tool_counts.items()}

        return Fingerprint(
            tool_distribution=tool_dist,
            avg_error_rate=errors / n,
            avg_duration=total_duration / n if n > 0 else 0,
            read_write_ratio=reads / max(writes, 1),
            avg_session_length=float(n),
            sample_count=1,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "fingerprints": {
                aid: fp.to_dict() for aid, fp in self._fingerprints.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FingerprintEngine":
        obj = cls(alpha=data.get("alpha", 0.1))
        for aid, fp_data in data.get("fingerprints", {}).items():
            obj._fingerprints[aid] = Fingerprint.from_dict(fp_data)
        return obj
