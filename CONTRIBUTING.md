# Contributing to SOMA

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management

## Setup

```bash
git clone https://github.com/your-org/soma.git
cd soma
uv sync --all-extras
```

## Running Tests

```bash
uv run pytest tests/ -x -q          # fast, stop on first failure
uv run pytest tests/ --cov=soma     # with coverage
uv run ruff check src/              # lint
```

## Linting

Ruff is configured in `pyproject.toml`:
- Rules: `F` (Pyflakes) and `E` (pycodestyle)
- Line length: 88 (E501 ignored -- formatter handles wrapping)
- Tests allow unused imports (F401, F811, F841)

## Adding a New Guidance Pattern

SOMA uses contextual guidance patterns to detect specific agent behaviors and inject targeted advice. Follow TDD:

### 1. Write the test first

In `tests/test_contextual_guidance.py`:

```python
def test_my_new_pattern(cg):
    # The `cg` fixture creates ContextualGuidance(cooldown_actions=0)
    # so patterns fire immediately without cooldown delays.

    # Simulate the actions that should trigger the pattern
    for i in range(3):
        cg.record_action("Bash", success=False, error_output="error msg")

    result = cg.evaluate("Bash", context={})
    assert result is not None
    assert "expected keyword" in result.guidance
```

### 2. Implement the pattern

In `src/soma/contextual_guidance.py`:

- Add a `_detect_my_pattern()` method that inspects the action history
- Return a `GuidanceResult` with the guidance text, or `None` if the pattern does not match

### 3. Wire it into evaluate()

Add your detector to the `evaluate()` method's pattern check list.

### 4. Set priority

Update `_PATTERN_PRIORITY` to control firing order when multiple patterns match simultaneously. Lower number = higher priority.

## Architecture Notes

- `src/soma/contextual_guidance.py` -- all pattern detection and guidance generation
- `tests/test_contextual_guidance.py` -- pattern tests using the `cg` fixture
- `src/soma/guidance.py` -- pressure-to-mode mapping and destructive tool evaluation
- `src/soma/hooks/` -- Claude Code integration layer

## Code Style

- Type hints on all function signatures
- Union types use `|` syntax: `str | None`
- Frozen dataclasses for immutable values, mutable for config
- `from __future__ import annotations` at top of files
- Keep functions focused: 10-30 lines typical
