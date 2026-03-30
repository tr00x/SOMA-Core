"""SOMA Root Cause Analysis — explain WHY pressure is elevated in plain English.

Analyzes action log, vitals, and patterns to produce a single-sentence
diagnosis that tells the agent (or human) exactly what's going wrong.

Examples:
- "Agent stuck in Edit→Bash→Edit loop on config.py since action #12 (3 cycles)"
- "Error cascade: 4 consecutive Bash failures, error_rate=40%"
- "Blind mutation: 5 writes without reading — drift rising"
- "Budget burn: 60% of tokens used in 30% of expected actions"
"""

from __future__ import annotations


def diagnose(
    action_log: list[dict],
    vitals: dict,
    pressure: float,
    level: str,
    action_count: int,
) -> str | None:
    """Produce a plain-English root cause diagnosis.

    Returns None if pressure is low and nothing interesting is happening.
    Returns a single sentence explaining the dominant problem.
    """
    if pressure < 0.15 and level in ("OBSERVE", "HEALTHY"):
        return None

    findings: list[tuple[float, str]] = []  # (severity, explanation)

    # ── 1. Loop detection ──
    loop = _detect_loop(action_log)
    if loop:
        findings.append(loop)

    # ── 2. Error cascade ──
    cascade = _detect_error_cascade(action_log, vitals)
    if cascade:
        findings.append(cascade)

    # ── 3. Blind mutation ──
    blind = _detect_blind_mutation(action_log, vitals)
    if blind:
        findings.append(blind)

    # ── 4. Stall detection ──
    stall = _detect_stall(action_log, action_count)
    if stall:
        findings.append(stall)

    # ── 5. Drift explanation ──
    drift = _explain_drift(vitals)
    if drift:
        findings.append(drift)

    if not findings:
        return None

    # Return the most severe finding
    findings.sort(key=lambda x: -x[0])
    return findings[0][1]


def _detect_loop(log: list[dict]) -> tuple[float, str] | None:
    """Detect repetitive tool sequences (agent stuck in a loop).

    Looks for sequences of 2-3 tools that repeat 3+ times.
    """
    if len(log) < 6:
        return None

    tools = [e.get("tool", "?") for e in log[-12:]]

    # Check for 2-tool loops (A→B→A→B→A→B)
    for seq_len in (2, 3):
        if len(tools) < seq_len * 3:
            continue
        # Take the last seq_len tools as the pattern
        pattern = tools[-seq_len:]
        repeats = 0
        for i in range(len(tools) - seq_len, -1, -seq_len):
            chunk = tools[i:i + seq_len]
            if chunk == pattern:
                repeats += 1
            else:
                break

        if repeats >= 3:
            cycle = "→".join(pattern)
            # Find which file is involved
            files = set()
            for e in log[-seq_len * repeats:]:
                if e.get("file"):
                    files.add(e["file"].rsplit("/", 1)[-1])
            file_str = f" on {', '.join(files)}" if files else ""
            start_idx = len(log) - seq_len * repeats
            return (
                0.9,
                f"stuck in {cycle} loop{file_str} "
                f"({repeats} cycles starting from action #{start_idx + 1})"
            )

    return None


def _detect_error_cascade(log: list[dict], vitals: dict) -> tuple[float, str] | None:
    """Detect consecutive errors building up."""
    if len(log) < 3:
        return None

    consecutive = 0
    error_tools: list[str] = []
    for entry in reversed(log):
        if entry.get("error"):
            consecutive += 1
            error_tools.append(entry.get("tool", "?"))
        else:
            break

    if consecutive < 2:
        return None

    error_rate = vitals.get("error_rate", 0)
    tool_str = error_tools[0] if len(set(error_tools)) == 1 else "mixed tools"

    severity = min(0.5 + consecutive * 0.1, 1.0)
    return (
        severity,
        f"error cascade: {consecutive} consecutive {tool_str} failures"
        f" (error_rate={error_rate:.0%})"
    )


def _detect_blind_mutation(log: list[dict], vitals: dict) -> tuple[float, str] | None:
    """Detect writes without reads."""
    if len(log) < 3:
        return None

    writes_since_read = 0
    written_files: list[str] = []
    for entry in reversed(log):
        if entry.get("tool") in ("Write", "Edit", "NotebookEdit"):
            writes_since_read += 1
            if entry.get("file"):
                written_files.append(entry["file"].rsplit("/", 1)[-1])
        elif entry.get("tool") == "Read":
            break

    if writes_since_read < 3:
        return None

    drift = vitals.get("drift", 0)
    file_str = f" ({', '.join(set(written_files[:3]))})" if written_files else ""
    drift_str = f", drift={drift:.2f}" if drift > 0.1 else ""

    return (
        0.6 + writes_since_read * 0.05,
        f"blind mutation: {writes_since_read} writes without reading{file_str}{drift_str}"
    )


def _detect_stall(log: list[dict], action_count: int) -> tuple[float, str] | None:
    """Detect agent doing lots of reads/greps but no writes (stuck researching)."""
    if len(log) < 8:
        return None

    recent = log[-8:]
    read_tools = {"Read", "Grep", "Glob", "WebSearch"}
    reads = sum(1 for e in recent if e.get("tool") in read_tools)
    writes = sum(1 for e in recent if e.get("tool") in ("Write", "Edit"))

    if reads >= 7 and writes == 0:
        return (
            0.5,
            f"possible stall: {reads}/8 recent actions are reads with no writes "
            f"(#{action_count} total) — may be stuck researching"
        )

    return None


def _explain_drift(vitals: dict) -> tuple[float, str] | None:
    """Explain what's driving drift if it's the dominant signal."""
    drift = vitals.get("drift", 0)
    uncertainty = vitals.get("uncertainty", 0)
    error_rate = vitals.get("error_rate", 0)

    if drift < 0.2:
        return None

    # Drift is high — explain what's different
    parts = []
    if uncertainty > 0.2:
        parts.append(f"uncertainty={uncertainty:.2f}")
    if error_rate > 0.1:
        parts.append(f"errors={error_rate:.0%}")

    cause = f" driven by {', '.join(parts)}" if parts else ""
    return (
        0.4 + drift * 0.5,
        f"behavioral drift={drift:.2f}{cause} — tool patterns diverging from baseline"
    )
