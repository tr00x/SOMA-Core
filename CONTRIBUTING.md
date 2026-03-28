# Contributing to SOMA Core

Thank you for your interest in contributing. This document covers two distinct paths: contributing to `soma-core` itself, and building a layer on top of it.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Contributing to soma-core](#contributing-to-soma-core)
   - [Fork and branch](#fork-and-branch)
   - [Development setup](#development-setup)
   - [Running the tests](#running-the-tests)
   - [Submitting a pull request](#submitting-a-pull-request)
3. [Building a Layer](#building-a-layer)
   - [What is a layer](#what-is-a-layer)
   - [Naming convention](#naming-convention)
   - [Layer structure](#layer-structure)
   - [Minimal layer example](#minimal-layer-example)
   - [Publishing your layer](#publishing-your-layer)
4. [Code Style](#code-style)
5. [Testing Requirements](#testing-requirements)

---

## Code of Conduct

Be direct and respectful. Focus on technical substance. Assume good intent.

---

## Contributing to soma-core

### Fork and branch

1. Fork `github.com/tr00x/soma-core` to your GitHub account.
2. Clone your fork locally.
3. Create a branch with a short, descriptive name:

   ```
   git checkout -b fix/pressure-aggregation-edge-case
   git checkout -b feat/otel-exporter
   ```

   Prefix with `fix/` for bug fixes, `feat/` for new features, `docs/` for documentation, and `refactor/` for internal changes.

4. Make your changes. Commit in logical, atomic units. Write commit messages in the imperative mood ("Add", "Fix", "Remove").

5. Push your branch and open a pull request against `main`.

### Development setup

SOMA Core uses [Hatch](https://hatch.pypa.io/) for build management. You can also use a plain virtual environment.

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

To check coverage:

```bash
pytest --cov=soma --cov-report=term-missing
```

Coverage must remain above 80% on `src/soma/`. Pull requests that drop coverage below this threshold will not be merged.

### Submitting a pull request

- Every pull request must include tests that cover the changed or added code.
- If your change modifies a public API, update the relevant docstrings and examples in `README.md`.
- Keep pull requests focused. One logical change per PR.
- The PR description should explain *why* the change is needed, not just *what* it does.
- All CI checks must pass before a review is requested.

---

## Building a Layer

### What is a layer

A layer is an independent package that wraps `soma-core` and adapts it to a specific framework, runtime, or toolchain. Layers handle the framework-specific plumbing — intercepting tool calls, reading agent state, formatting context — so that integrators can drop SOMA monitoring into an existing stack without touching the core.

The public API of `soma-core` that layers should build against:

- `soma.engine.SOMAEngine` — the main pipeline
- `soma.types.Action`, `soma.types.Level`, `soma.types.AutonomyMode` — data types
- `soma.context_control.apply_context_control` — directive context rewriting
- `soma.recorder.SessionRecorder` and `soma.replay.replay_session` — session I/O
- `soma.testing.Monitor` — test harness

Do not import from internal modules (prefixed with `_` or located in `soma._*`). Internal APIs change without notice.

### Naming convention

Layer packages must follow the naming pattern:

```
soma-{framework}
```

Examples:

- `soma-langchain`
- `soma-autogen`
- `soma-crewai`
- `soma-openai`
- `soma-llamaindex`

The top-level importable package should match: `soma_langchain`, `soma_autogen`, and so on.

### Layer structure

A minimal layer repository should contain:

```
soma-{framework}/
    src/
        soma_{framework}/
            __init__.py
            wrapper.py       # framework-specific adapter
    tests/
        test_wrapper.py
    pyproject.toml
    README.md
```

`pyproject.toml` must declare `soma-core` as a dependency with a minimum version pin:

```toml
[project]
name = "soma-{framework}"
dependencies = [
    "soma-core>=0.1.0",
]
```

### Minimal layer example

The following shows the pattern for a hypothetical `soma-langchain` layer. The framework callback intercepts a tool call, constructs an `Action`, and feeds it through the engine.

```python
# src/soma_langchain/wrapper.py
from __future__ import annotations

from soma.engine import SOMAEngine
from soma.types import Action, AutonomyMode
from soma.context_control import apply_context_control


class LangChainMonitor:
    """SOMA monitoring adapter for a LangChain AgentExecutor."""

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
        result = self._engine.record_action(agent_id, action)
        return result

    def rewrite_context(self, agent_id: str, context: dict) -> dict:
        """Apply directive context control for the current escalation level."""
        level = self._engine.get_level(agent_id)
        return apply_context_control(context, level)
```

Register callbacks in your LangChain `AgentExecutor` and call `on_tool_end` from a `BaseCallbackHandler.on_tool_end` implementation.

### Publishing your layer

1. Publish to PyPI under the `soma-{framework}` name.
2. Open an issue on `github.com/tr00x/soma-core` titled "Layer: soma-{framework}" so the project README can link to your package.
3. Include a link back to `github.com/tr00x/soma-core` in your package README.

---

## Code Style

- **Python version**: 3.11 or later. Do not use syntax or stdlib features unavailable in 3.11.
- **Type hints**: All public functions and methods must have fully annotated signatures. Use `from __future__ import annotations` for forward references.
- **Data classes**: Prefer `@dataclass` (with `frozen=True` where immutability is appropriate) over plain classes for data-carrying types.
- **No external formatters are enforced**, but new code should be consistent with the surrounding module. 4-space indentation, no trailing whitespace, one blank line between methods, two blank lines between top-level definitions.
- **Docstrings**: Public classes and functions should have a one-line summary. Longer descriptions, parameters, and return values may follow using plain reStructuredText style (no third-party docstring frameworks).
- **No emojis** in source code, docstrings, or commit messages.
- **Imports**: stdlib first, then third-party, then local (`soma.*`), separated by blank lines. Use absolute imports within the package.

---

## Testing Requirements

- Test framework: `pytest` (no alternatives).
- All new code must be accompanied by tests.
- Coverage must remain above **80%** on `src/soma/`. Check with `pytest --cov=soma --cov-report=term-missing`.
- Tests live in `tests/` and are named `test_{module}.py` matching the module they cover.
- Use `@pytest.fixture` for shared setup. Do not use `setUp`/`tearDown` style.
- Tests must be deterministic. Do not rely on ordering, timing, or random seeds unless the randomness is explicitly seeded and documented.
- For layers: the same coverage and style requirements apply. Include at least one integration test that instantiates the adapter against a real (or minimally-mocked) framework object.
