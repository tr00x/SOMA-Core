"""SOMA Core — Behavioral monitoring and directive control for AI agents."""

__version__ = "0.4.0"

from soma.types import (
    Action, Level, ResponseMode, AutonomyMode, DriftMode,
    VitalsSnapshot, AgentConfig, InterventionOutcome,
)
from soma.engine import SOMAEngine, ActionResult
from soma.budget import MultiBudget
from soma.events import EventBus
from soma.recorder import SessionRecorder
from soma.replay import replay_session
from soma.wrap import wrap, WrappedClient, SomaBlocked, SomaBudgetExhausted
from soma.persistence import save_engine_state, load_engine_state

def quickstart(budget=None, agents=None):
    """Fastest way to start. Returns a configured engine.

    Usage:
        engine = soma.quickstart(budget={"tokens": 50000}, agents=["agent-1", "agent-2"])
    """
    if budget is None:
        try:
            from soma.cli.config_loader import load_config
            config = load_config()
            budget_cfg = config.get("budget", {})
            budget = {k: v for k, v in budget_cfg.items() if v}
        except Exception:
            pass
    engine = SOMAEngine(budget=budget or {"tokens": 100_000}, auto_export=True)
    for agent_id in (agents or ["default"]):
        engine.register_agent(agent_id)
    return engine


__all__ = [
    "SOMAEngine", "Action", "ActionResult", "Level", "ResponseMode",
    "AutonomyMode", "DriftMode", "VitalsSnapshot", "AgentConfig",
    "InterventionOutcome", "MultiBudget", "EventBus",
    "SessionRecorder", "replay_session",
    "wrap", "WrappedClient", "SomaBlocked", "SomaBudgetExhausted",
    "quickstart",
    "save_engine_state", "load_engine_state",
]
