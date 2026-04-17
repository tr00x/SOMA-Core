# Contributing to SOMA

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management

## Setup

```bash
git clone https://github.com/tr00x/SOMA-Core.git
cd SOMA-Core
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
    # The `cg` fixture creates ContextualGuidance(cooldown_actions=5)
    # Pass action_number to avoid cooldown in tests.
    action_log = [
        {"tool": "Bash", "error": True, "file": "", "output": "error msg"},
        {"tool": "Bash", "error": True, "file": "", "output": "error msg"},
        {"tool": "Bash", "error": True, "file": "", "output": "error msg"},
    ]
    msg = cg.evaluate(
        action_log=action_log,
        current_tool="Bash",
        current_input={},
        vitals={},
    )
    assert msg is not None
    assert msg.pattern == "my_pattern"
    assert "expected keyword" in msg.message
```

### 2. Implement the pattern

In `src/soma/contextual_guidance.py`:

- Add a `_check_my_pattern()` method that inspects the action_log
- Return a `GuidanceMessage` with pattern, severity, message, evidence, suggestion — or `None`

### 3. Wire it into evaluate()

Add your detector to the `evaluate()` method's pattern check list.

### 4. Set priority

Update `_PATTERN_PRIORITY` to control firing order when multiple patterns match at the same severity. Higher number = wins ties.

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
