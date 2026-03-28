# Contributing to SOMA Core

Two paths: contribute to `soma-core` itself, or build a layer on top of it.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Contributing to soma-core](#contributing-to-soma-core)
- [Building a Layer](#building-a-layer)
- [Code Style](#code-style)
- [Testing Requirements](#testing-requirements)

---

## Code of Conduct

Be direct and respectful. Focus on technical substance. Assume good intent.

---

## Contributing to soma-core

### Fork and branch

1. Fork `github.com/tr00x/SOMA-Core` to your account.
2. Clone your fork locally.
3. Create a branch:

   ```bash
   git checkout -b fix/pressure-aggregation-edge-case
   git checkout -b feat/otel-exporter
   ```

   Prefixes: `fix/` bug fixes, `feat/` features, `docs/` documentation, `refactor/` internal.

4. Commit in logical, atomic units. Imperative mood ("Add", "Fix", "Remove").
5. Push and open a PR against `main`.

### Development setup

```bash
# with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# or with hatch
pip install hatch
hatch shell
```

### Running the tests

```bash
pytest
```

Coverage check:

```bash
pytest --cov=soma --cov-report=term-missing
```

Coverage must stay above **80%** on `src/soma/`. PRs that drop below will not be merged.

### Submitting a pull request

- Every PR must include tests covering the changed/added code
- If your change modifies a public API, update docstrings and `README.md` examples
- One logical change per PR
- PR description explains *why*, not just *what*
- All CI checks must pass before review

---

## Building a Layer

### What is a layer

A layer is an independent package that wraps `soma-core` for a specific framework, runtime, or toolchain. It handles framework-specific plumbing — intercepting tool calls, reading agent state, formatting context — so integrators can add SOMA without touching the core.

**Public API that layers should build against:**

| Module | What |
|:-------|:-----|
| `soma.engine.SOMAEngine` | Main pipeline |
| `soma.types.Action`, `Level`, `AutonomyMode` | Data types |
| `soma.context_control.apply_context_control` | Directive context rewriting |
| `soma.recorder.SessionRecorder` | Session I/O |
| `soma.replay.replay_session` | Replay |
| `soma.testing.Monitor` | Test harness |

Do not import from internal modules (`_`-prefixed or `soma._*`). Internal APIs change without notice.

### Naming convention

```
soma-{framework}
```

Examples: `soma-langchain`, `soma-autogen`, `soma-crewai`, `soma-openai`, `soma-llamaindex`

Top-level importable package: `soma_langchain`, `soma_autogen`, etc.

### Layer structure

```
soma-{framework}/
├── src/
│   └── soma_{framework}/
│       ├── __init__.py
│       └── wrapper.py       # framework-specific adapter
├── tests/
│   └── test_wrapper.py
├── pyproject.toml
└── README.md
```

`pyproject.toml` must pin `soma-core`:

```toml
[project]
name = "soma-{framework}"
dependencies = [
    "soma-core>=0.1.0",
]
```

### Minimal layer example

Pattern for a `soma-langchain` layer:

```python
# src/soma_langchain/wrapper.py
from __future__ import annotations

from soma.engine import SOMAEngine
from soma.types import Action, AutonomyMode
from soma.context_control import apply_context_control


class LangChainMonitor:
    """SOMA monitoring adapter for LangChain AgentExecutor."""

    def __init__(self, budget: dict | None = None) -> None:
        self._engine = SOMAEngine(budget=budget or {"tokens": 100_000})

    def register(self, agent_id: str, tools: list[str] | None = None) -> None:
        self._engine.register_agent(
            agent_id,
            autonomy=AutonomyMode.HUMAN_ON_THE_LOOP,
            tools=tools,
        )

    def on_tool_end(
        self,
        agent_id: str,
        tool_name: str,
        output: str,
        token_count: int = 0,
        cost: float = 0.0,
        error: bool = False,
    ) -> None:
        action = Action(
            tool_name=tool_name,
            output_text=output,
            token_count=token_count,
            cost=cost,
            error=error,
        )
        return self._engine.record_action(agent_id, action)

    def rewrite_context(self, agent_id: str, context: dict) -> dict:
        """Apply directive context control for the current escalation level."""
        level = self._engine.get_level(agent_id)
        return apply_context_control(context, level)
```

Register callbacks in your `AgentExecutor` and call `on_tool_end` from a `BaseCallbackHandler.on_tool_end` implementation.

### Publishing your layer

1. Publish to PyPI as `soma-{framework}`
2. Open an issue on `github.com/tr00x/SOMA-Core` titled "Layer: soma-{framework}" — we'll link it from the README
3. Include a link back to `github.com/tr00x/SOMA-Core` in your README

---

## Code Style

- **Python:** 3.11+. No syntax/stdlib features unavailable in 3.11.
- **Type hints:** All public functions must have fully annotated signatures. Use `from __future__ import annotations`.
- **Data classes:** Prefer `@dataclass(frozen=True)` for data-carrying types.
- **Formatting:** Consistent with surrounding module. 4-space indent. No trailing whitespace. One blank between methods, two between top-level definitions.
- **Docstrings:** Public classes/functions get a one-line summary. Plain reStructuredText for longer docs.
- **No emojis** in source, docstrings, or commits.
- **Imports:** stdlib → third-party → local (`soma.*`), separated by blank lines. Absolute imports within package.

---

## Testing Requirements

- **Framework:** `pytest` only
- **Coverage:** > 80% on `src/soma/`
- **Location:** `tests/test_{module}.py`
- **Fixtures:** `@pytest.fixture`, not `setUp`/`tearDown`
- **Deterministic:** No ordering, timing, or unseeded randomness
- **Layers:** Same rules. Include at least one integration test with a real (or minimally-mocked) framework object.
