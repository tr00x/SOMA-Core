# SOMA

The nervous system for AI agents — proprioceptive behavioral monitoring.

```
Tool Call ──> SOMA ──> Vitals/Pressure/Patterns ──> Mirror ──> Tool Response
                                                      |
                                              --- session context ---
                                              actions: 14 | errors: 4/6
                                              pattern: same cmd repeated 3x
                                              ---
```

## The problem

AI agents are blind to their own behavior. They retry the same failing command five times. They edit files they never read. Their error rate climbs for ten actions straight and they don't notice.

This isn't anecdotal:
- **41-86% failure rate** across agent benchmarks (MAST, Berkeley NeurIPS 2025)
- **Reliability lags capability by 2-3x** (Kapoor et al., Princeton 2026)
- Agents degrade predictably — error cascades, retry loops, scope drift — but have no signal to self-correct

Every existing tool monitors agents *externally for humans*. Dashboards and alerts for the operator. The agent itself never sees the data.

## How SOMA works

SOMA intercepts every tool call, computes behavioral state from five vital signals, and injects factual observations directly into the tool response. The agent sees its own state as part of the environment.

**Key insight:** LLMs ignore instructions but cannot ignore environmental data. SOMA exploits this by embedding behavioral telemetry into tool responses.

What the agent sees after a failing Bash command:

```
--- session context ---
actions: 14 | errors: 4/6
pattern: same cmd repeated 3x
last_successful: action #8 (Read)
---
```

No warnings. No suggestions. No "please stop". Just facts — the agent processes them like any other tool output and adjusts.

### Mirror: three modes of self-reflection

v0.6.0 introduces Mirror — proprioceptive feedback via environment augmentation.

| Mode | Cost | When | Output |
|------|------|------|--------|
| PATTERN | 0 | Known behavioral pattern | `pattern: same bash cmd repeated 5x` |
| STATS | 0 | Elevated pressure, no pattern | `errors: 3/8 | error_rate: 0.41` |
| SEMANTIC | ~$0.001 | High pressure + drift | LLM-generated behavioral observation |

Mirror learns from outcomes. After each injection, it watches the next 3 actions. If pressure drops >=10%, the context helped — that pattern gets cached. Ineffective patterns are pruned after 5 failures.

## Quick start

```bash
pip install soma-ai
```

Configure Claude Code hooks in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{ "type": "command", "command": "soma-hook" }],
    "PostToolUse": [{ "type": "command", "command": "soma-hook" }],
    "Stop": [{ "type": "command", "command": "soma-hook" }]
  }
}
```

Or run the wizard: `soma setup-claude`

SOMA is silent when the agent is healthy. When behavioral pressure rises above 15%, session context appears in tool responses.

For semantic mode (optional): `export GEMINI_API_KEY=...` (free tier).

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full setup guide.

## Architecture

```
                     +--------------------------------------------+
                     |              SOMA Engine                    |
Tool Call --> Pre    |                                             |
           (reflex  |  Vitals --> Pressure --> Response Mode       |
            block)  |    |           |              |              |
                    |  baseline    graph          guidance          |
                    |  (EMA)    (propagation)   (thresholds)       |
                     +--------------------+-----------------------+
                                          |
Tool Response <-- Post <------------------+
                    |
              +-----+------+
              |   Mirror   |
              |  PATTERN   |-->  stdout (agent sees as tool output)
              |  STATS     |
              |  SEMANTIC  |
              +-----+------+
                    |
              +-----+------+
              | Self-learn |-->  ~/.soma/patterns.json
              +------------+
```

**Delivery:** stdout = tool response content (agent sees). stderr = system diagnostics (operator sees). Claude Code hooks route stdout into the conversation.

**Escalation:** OBSERVE (silent) -> GUIDE (suggestions) -> WARN (insistent) -> BLOCK (destructive ops only). Normal tools are never blocked.

**Reflexes:** Separate from Mirror. Hard blocks for irreversible operations: retry dedup, blind edits without reads, bash failure cascades.

## Programmatic API

```python
import soma

engine = soma.quickstart()
client = soma.wrap(anthropic.Anthropic())

# Universal proxy for any framework
proxy = soma.SOMAProxy(engine, "my-agent")
safe_tool = proxy.wrap_tool(my_function)
child = proxy.spawn_subagent("child-agent")
```

## Research foundation

SOMA addresses gaps identified in recent agent reliability research:

| Paper | Finding | SOMA response |
|-------|---------|---------------|
| Kapoor et al. (Princeton 2026) | Reliability lags capability 2-3x | Real-time behavioral feedback |
| MAST (Berkeley NeurIPS 2025) | 41-86% failure, error cascades | Pattern detection + pressure signal |
| METR (2025) | Silent failures, no self-correction | Proprioceptive session context |
| Anthropic (2025) | Tool errors propagate unchecked | Pre/post tool use interception |

All prior work measures behavior *post-hoc for human review*. SOMA provides *real-time proprioceptive feedback to the agent itself*.

See [docs/RESEARCH.md](docs/RESEARCH.md) for the full research mapping.

## Stats

86 modules | 1208 tests | 0 dead code | Python 3.11+ | MIT license

## Links

- [Quick Start](docs/QUICKSTART.md) | [Architecture](docs/ARCHITECTURE.md) | [Research](docs/RESEARCH.md)
- [Changelog](CHANGELOG.md) | [PyPI](https://pypi.org/project/soma-ai/)
