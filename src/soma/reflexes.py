"""SOMA Reflex Engine — pattern-based blocking and injection decisions.

Pure function module. Takes action context + config, returns allow/block decisions.
No side effects, no state mutation, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from soma.patterns import analyze


@dataclass(frozen=True, slots=True)
class ReflexResult:
    """Result of a reflex evaluation."""

    allow: bool
    reflex_kind: str = ""
    block_message: str | None = None
    inject_message: str | None = None
    detail: str = ""


# Reflexes that hard-block the tool call.
BLOCKING_REFLEXES: set[str] = {"blind_edits", "bash_failures", "thrashing", "retry_dedup"}

# Reflexes that inject guidance but allow the call.
INJECTION_REFLEXES: set[str] = {"error_rate", "research_stall", "agent_spam"}


def evaluate(
    tool_name: str,
    tool_input: dict,
    action_log: list[dict],
    pressure: float = 0.0,
    config: dict | None = None,
    bash_history: list[str] | None = None,
    workflow_mode: str = "",
) -> ReflexResult:
    """Evaluate reflexes for a tool call.

    Returns a ReflexResult indicating whether the call is allowed,
    and any block/inject messages to surface.
    """
    cfg = config or {}

    # ── Override check (D-27) ──
    if cfg.get("override_allowed") and "SOMA override" in _extract_command(tool_input):
        return ReflexResult(allow=True)

    # ── Retry dedup (D-10) — before patterns, needs tool_input ──
    if tool_name == "Bash" and cfg.get("retry_dedup", True):
        cmd = _extract_command(tool_input)
        normalized = _normalize_command(cmd)
        if normalized and bash_history:
            for prev in bash_history:
                if _normalize_command(prev) == normalized:
                    return ReflexResult(
                        allow=False,
                        reflex_kind="retry_dedup",
                        block_message=_format_block(
                            tool_name,
                            _target_name(tool_input),
                            "retry_dedup",
                            "identical command already executed",
                            "Change the command or fix the underlying issue",
                            pressure,
                        ),
                        detail="identical command already executed",
                    )

    # ── Run pattern analysis ──
    patterns = analyze(action_log, workflow_mode)

    for pattern in patterns:
        kind = pattern.kind

        # Blocking reflexes
        if kind in BLOCKING_REFLEXES and cfg.get(kind, True):
            if _should_block(pattern, tool_name, tool_input):
                return ReflexResult(
                    allow=False,
                    reflex_kind=kind,
                    block_message=_format_block(
                        tool_name,
                        _target_name(tool_input),
                        kind,
                        pattern.detail,
                        pattern.action,
                        pressure,
                    ),
                    detail=pattern.detail,
                )

        # Injection reflexes
        if kind in INJECTION_REFLEXES and cfg.get(kind, True):
            return ReflexResult(
                allow=True,
                reflex_kind=kind,
                inject_message=f"[SOMA] {pattern.action}\n{pattern.detail}",
                detail=pattern.detail,
            )

    return ReflexResult(allow=True)


# ── Internal helpers ─────────────────────────────────────────────────


def _should_block(pattern, tool_name: str, tool_input: dict) -> bool:
    """Check if a blocking pattern applies to the current tool call."""
    kind = pattern.kind

    if kind == "blind_edits":
        return tool_name in ("Edit", "Write", "NotebookEdit")

    if kind == "bash_failures":
        return tool_name == "Bash"

    if kind == "thrashing":
        if tool_name not in ("Edit", "Write", "NotebookEdit"):
            return False
        target = tool_input.get("file_path", "")
        pattern_file = pattern.data.get("file", "")
        if not pattern_file:
            return False
        # Pattern stores short name, target may be full path
        target_short = target.rsplit("/", 1)[-1] if "/" in target else target
        return target_short == pattern_file or target == pattern_file

    return False


def _normalize_command(cmd: str) -> str:
    """Normalize whitespace for command deduplication."""
    return " ".join(cmd.split())


def _extract_command(tool_input: dict) -> str:
    """Extract command string from tool_input."""
    return tool_input.get("command", "")


def _target_name(tool_input: dict) -> str:
    """Extract meaningful target name from tool_input."""
    if "file_path" in tool_input:
        return tool_input["file_path"]
    cmd = tool_input.get("command", "")
    if cmd:
        return cmd[:60]
    return ""


def _format_block(
    tool: str,
    target: str,
    kind: str,
    detail: str,
    suggestion: str,
    pressure: float,
) -> str:
    """Format a block message per D-16 spec."""
    return (
        f"[SOMA BLOCKED] {tool} on {target}\n"
        f"Reason: {detail}\n"
        f"Fix: {suggestion}\n"
        f"Pressure: {pressure:.0%}"
    )
