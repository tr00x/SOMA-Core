"""SOMA Pattern Analysis — detect behavioral patterns in agent action logs.

Core module: layer-agnostic. Returns structured PatternResult objects.
Layers format these for their specific output channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PatternResult:
    """A detected behavioral pattern."""
    kind: str           # "blind_edits", "bash_failures", "error_rate", "thrashing",
                        # "agent_spam", "research_stall", "no_checkin",
                        # "good_read_edit", "good_clean_streak"
    severity: str       # "positive", "info", "warning", "critical"
    action: str         # What the agent should DO
    detail: str         # Context about the pattern
    data: dict = field(default_factory=dict)


def analyze(
    action_log: list[dict],
    workflow_mode: str = "",
) -> list[PatternResult]:
    """Analyze action log for behavioral patterns.

    Args:
        action_log: List of action dicts with keys: tool, error, file, ts
        workflow_mode: "" (default), "plan", "execute", "discuss", "fast"

    Returns:
        List of PatternResult, max 3, sorted by severity.
    """
    if not action_log:
        return []

    results: list[PatternResult] = []
    recent = action_log[-10:]

    # ── Pattern 1: Blind edits ──
    read_context: set[str] = set()
    read_dirs: set[str] = set()
    for entry in action_log[-30:]:
        if entry["tool"] in ("Read", "Grep", "Glob"):
            f = entry.get("file", "")
            if f:
                read_context.add(f)
                if "/" in f:
                    read_dirs.add(f.rsplit("/", 1)[0])

    blind_edits = 0
    blind_files: list[str] = []
    for entry in reversed(recent):
        if entry["tool"] in ("Edit", "NotebookEdit"):
            f = entry.get("file", "")
            if not f:
                continue
            if f in read_context:
                continue
            parent = f.rsplit("/", 1)[0] if "/" in f else ""
            if parent and parent in read_dirs:
                continue
            blind_edits += 1
            blind_files.append(f.rsplit("/", 1)[-1])
        elif entry["tool"] == "Read":
            break
    if blind_edits >= 3:
        results.append(PatternResult(
            kind="blind_edits",
            severity="warning",
            action=f"Read before editing ({', '.join(dict.fromkeys(blind_files[:3]))})"
                   if blind_files else "Read before editing",
            detail=f"you made {blind_edits} edits to files you haven't read",
            data={"count": blind_edits, "files": blind_files[:3]},
        ))

    # ── Pattern 2: Consecutive Bash failures ──
    consecutive_bash_errors = 0
    for entry in reversed(recent):
        if entry["tool"] == "Bash" and entry.get("error"):
            consecutive_bash_errors += 1
        elif entry["tool"] == "Bash":
            break
        else:
            continue
    if consecutive_bash_errors >= 2:
        results.append(PatternResult(
            kind="bash_failures",
            severity="warning",
            action=f"Stop retrying — {consecutive_bash_errors} Bash failures in a row",
            detail="Read the error, check assumptions, try a different approach",
            data={"count": consecutive_bash_errors},
        ))

    # ── Pattern 3: High error rate ──
    if len(recent) >= 5:
        error_count = sum(1 for e in recent if e.get("error"))
        error_rate = error_count / len(recent)
        if error_rate >= 0.3:
            error_tools: dict[str, int] = {}
            for e in recent:
                if e.get("error"):
                    t = e["tool"]
                    error_tools[t] = error_tools.get(t, 0) + 1
            worst_tool = max(error_tools, key=error_tools.get) if error_tools else "?"
            results.append(PatternResult(
                kind="error_rate",
                severity="warning",
                action=f"Pause and rethink — {error_count}/{len(recent)} actions failed (mostly {worst_tool})",
                detail="Change approach, don't repeat",
                data={"error_count": error_count, "total": len(recent), "worst_tool": worst_tool},
            ))

    # ── Pattern 4: File thrashing ──
    if len(recent) >= 4:
        edit_files = [
            e["file"] for e in recent
            if e["tool"] in ("Write", "Edit") and e.get("file")
        ]
        if edit_files:
            from collections import Counter
            file_counts = Counter(edit_files)
            thrashed = [(f, c) for f, c in file_counts.items() if c >= 3]
            if thrashed:
                fname, count = thrashed[0]
                short = fname.rsplit("/", 1)[-1] if "/" in fname else fname
                results.append(PatternResult(
                    kind="thrashing",
                    severity="warning",
                    action=f"Collect changes for {short} — you've edited it {count}x",
                    detail="Read it, plan all changes, one edit",
                    data={"file": short, "count": count},
                ))

    # ── Pattern 5: Agent spam (suppressed in plan/discuss) ──
    if workflow_mode not in ("plan", "discuss"):
        agent_calls = sum(1 for e in recent if e["tool"] == "Agent")
        if agent_calls >= 3:
            results.append(PatternResult(
                kind="agent_spam",
                severity="info",
                action=f"Check agent results — {agent_calls} spawned in {len(recent)} actions",
                detail="Are they producing? Consider doing it directly",
                data={"count": agent_calls},
            ))

    # ── Pattern 6: Research stall (suppressed in plan/discuss) ──
    if workflow_mode not in ("plan", "discuss"):
        if len(recent) >= 8:
            read_tools = {"Read", "Grep", "Glob", "WebSearch", "WebFetch"}
            reads = sum(1 for e in recent if e["tool"] in read_tools)
            writes = sum(1 for e in recent if e["tool"] in ("Write", "Edit"))
            if reads >= 7 and writes == 0:
                results.append(PatternResult(
                    kind="research_stall",
                    severity="info",
                    action=f"Start implementing — {reads} reads, 0 writes",
                    detail="You have enough context. Write code or ask the user",
                    data={"reads": reads},
                ))

    # ── Pattern 7: No user check-in (suppressed in execute/plan) ──
    if workflow_mode not in ("execute", "plan"):
        if len(action_log) >= 30:
            last_30 = action_log[-30:]
            user_tools = {"AskUserQuestion"}
            user_interactions = sum(1 for e in last_30 if e["tool"] in user_tools)
            edits = sum(1 for e in last_30 if e["tool"] in ("Write", "Edit", "Bash"))
            if user_interactions == 0 and edits >= 15:
                results.append(PatternResult(
                    kind="no_checkin",
                    severity="info",
                    action=f"Check in with user — {edits} mutations without asking",
                    detail="Verify you're on track before continuing",
                    data={"mutations": edits},
                ))

    # ── Positive patterns (only if no negative results) ──
    if not results:
        read_files_set: set[str] = set()
        read_edit_pairs = 0
        for entry in action_log[-20:]:
            if entry["tool"] in ("Read", "Grep"):
                f = entry.get("file", "")
                if f:
                    read_files_set.add(f)
            elif entry["tool"] in ("Edit", "Write") and entry.get("file", "") in read_files_set:
                read_edit_pairs += 1

        if read_edit_pairs >= 3:
            results.append(PatternResult(
                kind="good_read_edit",
                severity="positive",
                action=f"read-before-edit maintained ({read_edit_pairs} pairs)",
                detail="",
            ))
        elif len(action_log) >= 10:
            recent_errors = sum(1 for e in action_log[-10:] if e.get("error"))
            if recent_errors == 0:
                results.append(PatternResult(
                    kind="good_clean_streak",
                    severity="positive",
                    action=f"clean streak — {min(len(action_log), 10)} actions, 0 errors",
                    detail="",
                ))

    return results[:3]
