"""Benchmark scenarios — deterministic action sequences for A/B testing.

Each function returns a list of ``ScenarioAction`` objects using realistic tool
names drawn from SOMA's task-tracker phase tools (Read, Edit, Bash, Grep,
Write, Glob).  All randomness comes from ``random.Random(seed)`` so runs are
reproducible yet varied across seeds.
"""

from __future__ import annotations

import random as _random_mod

from soma.benchmark.metrics import ScenarioAction


# ------------------------------------------------------------------
# Tool pools (mirroring task_tracker._PHASE_TOOLS)
# ------------------------------------------------------------------

_RESEARCH_TOOLS = ["Read", "Grep", "Glob"]
_IMPLEMENT_TOOLS = ["Write", "Edit"]
_TEST_TOOLS = ["Bash"]
_ALL_TOOLS = _RESEARCH_TOOLS + _IMPLEMENT_TOOLS + _TEST_TOOLS


def _pick(rng: _random_mod.Random, tools: list[str]) -> str:
    return rng.choice(tools)


def _normal_action(rng: _random_mod.Random, tools: list[str], token_range: tuple[int, int] = (80, 200)) -> ScenarioAction:
    """Generate a healthy action with low error probability."""
    return ScenarioAction(
        tool_name=_pick(rng, tools),
        output_text=f"output-{rng.randint(0, 9999):04d}",
        token_count=rng.randint(*token_range),
        error=False,
        retried=False,
    )


def _error_action(rng: _random_mod.Random, tools: list[str], retried: bool = False, guidance_responsive: bool = False) -> ScenarioAction:
    return ScenarioAction(
        tool_name=_pick(rng, tools),
        output_text=f"ERROR: something failed {rng.randint(0, 999)}",
        token_count=rng.randint(50, 150),
        error=True,
        retried=retried,
        guidance_responsive=guidance_responsive,
    )


# ------------------------------------------------------------------
# Scenario 1: Healthy session (baseline for false-positive measurement)
# ------------------------------------------------------------------

def healthy_session(seed: int = 42) -> list[ScenarioAction]:
    """50 actions: research(15) -> implement(20) -> test(15).

    ~5% error rate (2-3 random errors).  No guidance_responsive actions.
    Purpose: measure false positive rate.
    """
    rng = _random_mod.Random(seed)
    actions: list[ScenarioAction] = []

    # Research phase
    for _ in range(15):
        actions.append(_normal_action(rng, _RESEARCH_TOOLS))

    # Implement phase
    for _ in range(20):
        actions.append(_normal_action(rng, _IMPLEMENT_TOOLS))

    # Test phase
    for _ in range(15):
        actions.append(_normal_action(rng, _TEST_TOOLS))

    # Inject ~5% errors at random positions
    error_count = max(2, int(len(actions) * 0.05))
    positions = rng.sample(range(len(actions)), error_count)
    for pos in positions:
        old = actions[pos]
        actions[pos] = ScenarioAction(
            tool_name=old.tool_name,
            output_text=f"ERROR: minor issue {rng.randint(0, 99)}",
            token_count=old.token_count,
            error=True,
            retried=False,
        )

    return actions


# ------------------------------------------------------------------
# Scenario 2: Degrading session (errors ramp up)
# ------------------------------------------------------------------

def degrading_session(seed: int = 42) -> list[ScenarioAction]:
    """80 actions with escalating error rates.

    Phase 1 (actions 0-19):   normal, ~0% errors
    Phase 2 (actions 20-29):  errors creep in (~30%)
    Phase 3 (actions 30-49):  error-heavy with retries (~60%)
    Phase 4 (actions 50-64):  blind writes, guidance_responsive=True
    Phase 5 (actions 65-79):  recovery
    """
    rng = _random_mod.Random(seed)
    actions: list[ScenarioAction] = []

    # Phase 1: normal
    for _ in range(20):
        actions.append(_normal_action(rng, _ALL_TOOLS))

    # Phase 2: errors creep in
    for _ in range(10):
        if rng.random() < 0.3:
            actions.append(_error_action(rng, _TEST_TOOLS))
        else:
            actions.append(_normal_action(rng, _ALL_TOOLS))

    # Phase 3: error-heavy with retries
    for _ in range(20):
        if rng.random() < 0.6:
            actions.append(_error_action(rng, _TEST_TOOLS, retried=True))
        else:
            actions.append(_normal_action(rng, _IMPLEMENT_TOOLS))

    # Phase 4: blind writes (guidance_responsive — agent would skip if guided)
    for _ in range(15):
        actions.append(ScenarioAction(
            tool_name="Write",
            output_text=f"blind-write-{rng.randint(0, 999)}",
            token_count=rng.randint(100, 300),
            error=rng.random() < 0.4,
            retried=False,
            guidance_responsive=True,
        ))

    # Phase 5: recovery
    for _ in range(15):
        actions.append(_normal_action(rng, _RESEARCH_TOOLS))

    return actions


# ------------------------------------------------------------------
# Scenario 3: Multi-agent coordination
# ------------------------------------------------------------------

def multi_agent_coordination(seed: int = 42) -> tuple[list[ScenarioAction], list[ScenarioAction]]:
    """Two agents (60 actions each) interleaved.

    Agent A degrades at action 20 — errors spike.
    Agent B is healthy throughout.
    Returns (agent_a_actions, agent_b_actions).
    """
    rng = _random_mod.Random(seed)

    agent_a: list[ScenarioAction] = []
    agent_b: list[ScenarioAction] = []

    for i in range(60):
        # Agent A: degrades after action 20
        if i < 20:
            agent_a.append(_normal_action(rng, _ALL_TOOLS))
        else:
            if rng.random() < 0.5:
                agent_a.append(_error_action(rng, _TEST_TOOLS, retried=True))
            else:
                agent_a.append(_normal_action(rng, _IMPLEMENT_TOOLS))

        # Agent B: stays healthy
        agent_b.append(_normal_action(rng, _ALL_TOOLS))

    return agent_a, agent_b


# ------------------------------------------------------------------
# Scenario 4: Retry storm
# ------------------------------------------------------------------

def retry_storm(seed: int = 42) -> list[ScenarioAction]:
    """40 actions: 15 normal, 15 repeated Bash errors (retried, guidance_responsive), 10 normal.

    The retry storm is the most dramatic metric-mover — SOMA should cut it short.
    """
    rng = _random_mod.Random(seed)
    actions: list[ScenarioAction] = []

    # Normal start
    for _ in range(15):
        actions.append(_normal_action(rng, _ALL_TOOLS))

    # Retry storm: same tool, same error, retried
    for i in range(15):
        actions.append(ScenarioAction(
            tool_name="Bash",
            output_text=f"ERROR: test suite failed (attempt {i + 1})",
            token_count=rng.randint(50, 120),
            error=True,
            retried=True,
            guidance_responsive=True,
        ))

    # Recovery
    for _ in range(10):
        actions.append(_normal_action(rng, _RESEARCH_TOOLS))

    return actions


# ------------------------------------------------------------------
# Scenario 5: Context exhaustion
# ------------------------------------------------------------------

def context_exhaustion(seed: int = 42) -> list[ScenarioAction]:
    """100 actions with linearly increasing token_count from 100 to 5000.

    Tests budget pressure and context usage signals.  Errors sprinkled in
    at ~10% rate.
    """
    rng = _random_mod.Random(seed)
    actions: list[ScenarioAction] = []

    for i in range(100):
        tokens = 100 + int((5000 - 100) * i / 99)
        is_error = rng.random() < 0.10
        actions.append(ScenarioAction(
            tool_name=_pick(rng, _ALL_TOOLS),
            output_text=f"{'ERROR: ' if is_error else ''}result-{i:03d}",
            token_count=tokens,
            error=is_error,
            retried=False,
        ))

    return actions
