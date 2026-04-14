"""Typed data structures for the SOMA dashboard data layer."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    agent_id: str
    display_name: str
    level: str  # OBSERVE, GUIDE, WARN, BLOCK
    pressure: float
    action_count: int
    vitals: dict[str, float | None]
    escalation_level: int = 0
    dominant_signal: str = ""
    throttled_tool: str = ""
    consecutive_block: int = 0
    is_open: bool = False


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: str
    agent_id: str
    display_name: str
    action_count: int
    avg_pressure: float
    max_pressure: float
    total_tokens: int
    total_cost: float
    error_count: int
    start_time: float
    end_time: float
    mode: str = "OBSERVE"


@dataclass(frozen=True, slots=True)
class SessionDetail(SessionSummary):
    actions: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    tool_stats: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionEvent:
    timestamp: float
    tool_name: str
    pressure: float
    error: bool
    mode: str
    token_count: int = 0
    cost: float = 0.0


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    health: float
    tokens_limit: int
    tokens_spent: int
    cost_limit: float
    cost_spent: float


@dataclass(frozen=True, slots=True)
class OverviewStats:
    total_agents: int
    total_sessions: int
    total_actions: int
    avg_pressure: float
    top_signals: dict[str, float]
    budget: BudgetSnapshot | None = None


@dataclass(frozen=True, slots=True)
class PressurePoint:
    timestamp: float
    pressure: float
    mode: str


@dataclass(frozen=True, slots=True)
class ToolStat:
    tool_name: str
    count: int
    error_count: int
    error_rate: float


@dataclass(frozen=True, slots=True)
class HeatmapCell:
    hour: int
    day: int
    count: int


@dataclass(frozen=True, slots=True)
class QualitySnapshot:
    total_writes: int
    total_bashes: int
    syntax_errors: int
    lint_issues: int
    bash_errors: int
    write_error_rate: float
    bash_error_rate: float


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    nodes: list[dict]
    edges: list[dict]
