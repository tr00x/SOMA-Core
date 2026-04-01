"""Session report generation — Markdown summaries of agent behavior."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soma.engine import SOMAEngine


def generate_session_report(engine: SOMAEngine, agent_id: str = "default") -> str:
    """Generate a Markdown session report for the given agent."""
    if agent_id not in engine._agents:
        return f"# SOMA Session Report\n\nAgent `{agent_id}` not found.\n"

    s = engine._agents[agent_id]
    if s.action_count == 0:
        return f"# SOMA Session Report\n\nNo actions recorded for agent `{agent_id}`.\n"

    # Gather data from agent state
    actions = list(s.ring_buffer)
    mode = s.mode
    budget_health = engine._budget.health()

    # Build report sections
    lines: list[str] = []
    lines.append("# SOMA Session Report")
    lines.append("")
    lines.append(f"**Agent:** {agent_id}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Actions:** {s.action_count}")
    lines.append(f"- **Final Mode:** {mode.name}")
    lines.append(f"- **Cumulative Tokens:** {s.cumulative_tokens:,}")
    ctx_pct = (s.cumulative_tokens / engine._context_window * 100) if engine._context_window > 0 else 0
    lines.append(f"- **Context Usage:** {ctx_pct:.1f}%")
    lines.append("")

    # Vitals Timeline (from ring buffer — last N actions)
    lines.append("## Vitals Timeline")
    lines.append("")
    if actions:
        error_count = sum(1 for a in actions if a.error)
        total_tokens = sum(a.token_count for a in actions)
        total_cost = sum(a.cost for a in actions)
        lines.append(f"- **Recent errors:** {error_count}/{len(actions)} actions")
        lines.append(f"- **Recent tokens:** {total_tokens:,}")
        lines.append(f"- **Recent cost:** ${total_cost:.4f}")
    else:
        lines.append("No recent action data available.")
    lines.append("")

    # Interventions (from learning engine)
    lines.append("## Interventions")
    lines.append("")
    history = engine._learning._history.get(agent_id, [])
    pending = engine._learning._pending.get(agent_id, [])
    interventions = history + pending
    if interventions:
        for iv in interventions[-10:]:  # last 10
            lines.append(
                f"- {iv.old_level.name} -> {iv.new_level.name} "
                f"(pressure={iv.pressure:.3f})"
            )
    else:
        lines.append("No interventions recorded.")
    lines.append("")

    # Cost
    lines.append("## Cost")
    lines.append("")
    lines.append(f"- **Total tokens:** {s.cumulative_tokens:,}")
    lines.append(f"- **Budget health:** {budget_health:.1%}")
    for dim, limit in engine._budget.limits.items():
        spent = engine._budget.spent.get(dim, 0.0)
        lines.append(f"- **{dim}:** {spent:,.1f} / {limit:,.1f}")
    lines.append("")

    # Patterns (tool usage from ring buffer)
    lines.append("## Patterns")
    lines.append("")
    if actions:
        tool_counts: dict[str, int] = {}
        for a in actions:
            tool_counts[a.tool_name] = tool_counts.get(a.tool_name, 0) + 1
        for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{tool}:** {count} uses")
    else:
        lines.append("No pattern data available.")
    lines.append("")

    # Quality Score (composite 0-100)
    lines.append("## Quality Score")
    lines.append("")
    error_rate = sum(1 for a in actions if a.error) / len(actions) if actions else 0.0
    mode_penalty = {0: 0, 1: 10, 2: 25, 3: 50}.get(mode.value, 0)
    quality = max(0, int(100 - (error_rate * 100) - mode_penalty))
    lines.append(f"**Score: {quality}/100**")
    lines.append("")
    lines.append(f"- Error rate impact: -{error_rate * 100:.0f}")
    lines.append(f"- Mode penalty ({mode.name}): -{mode_penalty}")
    lines.append("")

    return "\n".join(lines)


def save_report(
    report: str,
    agent_id: str = "default",
    reports_dir: Path | None = None,
) -> Path:
    """Save report to reports directory with timestamped filename.

    Parameters
    ----------
    reports_dir:
        Override the default ``~/.soma/reports/`` directory (useful for tests).
    """
    if reports_dir is None:
        reports_dir = Path.home() / ".soma" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = reports_dir / f"{timestamp}_{agent_id}.md"
    path.write_text(report)
    return path
