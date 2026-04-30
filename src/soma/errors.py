"""SOMA custom exceptions with helpful error messages."""

from __future__ import annotations

import os
import sys


class SOMAError(Exception):
    """Base SOMA error with helpful message."""
    pass


def log_silent_failure(component: str, exc: BaseException) -> None:
    """Stderr-log a non-fatal error that the caller is otherwise
    swallowing.

    SOMA hooks have to never crash the agent's terminal, so most error
    paths end in ``except Exception: pass``. That made every
    silent-failure site look identical to "everything's fine" for the
    next person debugging. This helper prints a one-line marker so a
    maintainer running with ``SOMA_DEBUG=1`` can see what's actually
    blowing up.

    Honors ``SOMA_HOOK_QUIET=1`` (used in tests / CI to suppress
    expected noise) — same gating convention as the rest of the
    codebase.
    """
    if os.environ.get("SOMA_HOOK_QUIET"):
        return
    if not os.environ.get("SOMA_DEBUG"):
        return
    try:
        print(
            f"[SOMA debug] {component}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    except Exception:
        pass


class AgentNotFound(SOMAError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Agent '{agent_id}' not found. "
            f"Register it first: engine.register_agent('{agent_id}')"
        )


class NoBudget(SOMAError):
    def __init__(self) -> None:
        super().__init__(
            "No budget configured. "
            "Set one: SOMAEngine(budget={'tokens': 100000})"
        )
