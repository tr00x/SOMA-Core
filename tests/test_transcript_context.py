"""Transcript-size proxy for context_usage (P1.4).

Internal engine.cumulative_tokens only tallies tool outputs, so on long
Claude Code sessions context_usage stays near 0% and cost_spiral /
context patterns never arm. The proxy reads the transcript JSONL size
from the hook payload to produce an honest estimate.
"""

from __future__ import annotations

from pathlib import Path

from soma.contextual_guidance import ContextualGuidance
from soma.hooks.common import (
    estimate_context_tokens_from_transcript,
    estimate_context_usage_from_transcript,
)


# ── Helper: estimate_context_tokens_from_transcript ────────────────────

def test_estimate_tokens_missing_path_returns_zero():
    assert estimate_context_tokens_from_transcript(None) == 0
    assert estimate_context_tokens_from_transcript("") == 0


def test_estimate_tokens_nonexistent_file_returns_zero(tmp_path):
    ghost = tmp_path / "does-not-exist.jsonl"
    assert estimate_context_tokens_from_transcript(str(ghost)) == 0


def test_estimate_tokens_empty_file_returns_zero(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert estimate_context_tokens_from_transcript(str(empty)) == 0


def test_estimate_tokens_small_file(tmp_path):
    f = tmp_path / "s.jsonl"
    payload = "x" * 4000  # 4000 bytes → 1000 tokens at 4 chars/token
    f.write_text(payload)
    assert estimate_context_tokens_from_transcript(str(f)) == 1000


def test_estimate_tokens_large_file(tmp_path):
    f = tmp_path / "big.jsonl"
    f.write_text("x" * 800_000)  # 200_000 tokens
    assert estimate_context_tokens_from_transcript(str(f)) == 200_000


# ── Helper: estimate_context_usage_from_transcript ────────────────────

def test_estimate_usage_missing_path_is_zero():
    assert estimate_context_usage_from_transcript(None) == 0.0


def test_estimate_usage_partial_window(tmp_path):
    f = tmp_path / "mid.jsonl"
    # 400_000 bytes → 100_000 tokens → 50% of default 200_000 window
    f.write_text("x" * 400_000)
    usage = estimate_context_usage_from_transcript(str(f))
    assert abs(usage - 0.5) < 1e-6


def test_estimate_usage_clamped_to_one(tmp_path):
    f = tmp_path / "overflow.jsonl"
    # 4 MB → 1_000_000 tokens → way past 200_000 window → clamp to 1.0
    f.write_text("x" * 4_000_000)
    assert estimate_context_usage_from_transcript(str(f)) == 1.0


def test_estimate_usage_respects_custom_window(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text("x" * 400_000)  # 100_000 tokens
    # Custom 1M window → 10%
    usage = estimate_context_usage_from_transcript(str(f), context_window=1_000_000)
    assert abs(usage - 0.1) < 1e-6


def test_estimate_usage_zero_window_is_zero(tmp_path):
    f = tmp_path / "z.jsonl"
    f.write_text("x" * 4000)
    assert estimate_context_usage_from_transcript(str(f), context_window=0) == 0.0


# ── Integration: context pattern arms at high transcript usage ────────

def _diverse_log(n: int = 10) -> list[dict]:
    """Balanced tool mix so entropy_drop stays silent."""
    tools = ["Read", "Grep", "Edit", "Bash", "Glob"]
    return [{"tool": tools[i % len(tools)]} for i in range(n)]


def test_contextual_guidance_context_pattern_fires_from_transcript_proxy():
    """With transcript proxy at 85%, context pattern fires even when
    engine-computed token_usage is 0."""
    cg = ContextualGuidance()
    # Simulate the fallback cg_vitals the hook builds: engine reports
    # 0 token_usage, proxy says 0.85.
    vitals = {
        "uncertainty": 0.0,
        "drift": 0.0,
        "error_rate": 0.0,
        "token_usage": 0.85,
        "context_usage": 0.85,
    }
    msg = cg.evaluate(
        action_log=_diverse_log(10),
        current_tool="Read",
        current_input={},
        vitals=vitals,
        budget_health=1.0,
        action_number=10,
    )
    assert msg is not None, "context pattern should fire at 85% transcript fullness"
    assert msg.pattern == "context"


def test_contextual_guidance_quiet_when_proxy_low():
    cg = ContextualGuidance()
    vitals = {
        "uncertainty": 0.0,
        "drift": 0.0,
        "error_rate": 0.0,
        "token_usage": 0.10,
        "context_usage": 0.10,
    }
    msg = cg.evaluate(
        action_log=_diverse_log(10),
        current_tool="Read",
        current_input={},
        vitals=vitals,
        budget_health=1.0,
        action_number=10,
    )
    # Context pattern must NOT fire at 10% usage with no other signals.
    assert msg is None or msg.pattern != "context"
