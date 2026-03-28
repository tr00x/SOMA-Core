"""Context Control for SOMA Core.

Applies context reduction strategies based on the current escalation Level,
trimming message history and/or restricting available tools to keep the agent
within safe operational bounds.
"""

from __future__ import annotations

import math
from typing import Any

from soma.types import Level


def apply_context_control(context: dict[str, Any], level: Level) -> dict[str, Any]:
    """Return a modified copy of *context* appropriate for *level*.

    Parameters
    ----------
    context:
        A dict with the following keys:

        ``messages``      – list of message objects (ordered oldest → newest).
        ``tools``         – list[str] of currently available tool names.
        ``system_prompt`` – str; always preserved unchanged.
        ``expensive_tools`` – (optional) list[str] of tool names to drop under
                              DEGRADE.
        ``minimal_tools`` – (optional) list[str] of the minimal tool set used
                            under QUARANTINE and SAFE_MODE.

    level:
        The current :class:`~soma.types.Level`.

    Returns
    -------
    dict
        A shallow-to-deep copy of *context* with adjustments applied; the
        original dict is never mutated.
    """
    messages: list = list(context.get("messages", []))
    tools: list[str] = list(context.get("tools", []))
    system_prompt: str = context.get("system_prompt", "")
    expensive_tools: list[str] = list(context.get("expensive_tools") or [])
    minimal_tools: list[str] = list(context.get("minimal_tools") or [])

    if level == Level.HEALTHY:
        # Return unchanged (still a copy so callers cannot mutate the original).
        pass

    elif level == Level.CAUTION:
        # Keep the newest 80 % of messages; keep all tools.
        messages = _keep_newest(messages, fraction=0.80)

    elif level == Level.DEGRADE:
        # Keep the newest 50 % of messages; remove expensive tools.
        messages = _keep_newest(messages, fraction=0.50)
        tools = [t for t in tools if t not in expensive_tools]

    elif level == Level.QUARANTINE:
        # Clear message history; restrict to minimal tools only.
        messages = []
        tools = list(minimal_tools)

    elif level == Level.RESTART:
        # Clear message history; restore full tool list (unchanged from input).
        messages = []
        # tools stay as-is (full list passed by caller)

    elif level == Level.SAFE_MODE:
        # Clear message history; restrict to minimal tools only.
        messages = []
        tools = list(minimal_tools)

    result = dict(context)  # shallow copy to preserve any extra keys
    result["messages"] = messages
    result["tools"] = tools
    result["system_prompt"] = system_prompt
    if "expensive_tools" in context:
        result["expensive_tools"] = list(context["expensive_tools"] or [])
    if "minimal_tools" in context:
        result["minimal_tools"] = list(context["minimal_tools"] or [])
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _keep_newest(messages: list, *, fraction: float) -> list:
    """Return the newest *fraction* of *messages* (rounded up)."""
    total = len(messages)
    if total == 0:
        return []
    keep = math.ceil(total * fraction)
    return messages[total - keep:]
