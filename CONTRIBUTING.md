# Contributing

## Setup

```bash
git clone https://github.com/tr00x/SOMA-Core.git
cd SOMA-Core
uv sync --all-extras
```

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

---

## Tests & Lint

```bash
uv run pytest tests/ -x -q          # fast, stop on first failure
uv run pytest tests/ --cov=soma     # with coverage
uv run ruff check src/              # lint
```

All PRs must pass tests and lint. Currently 1438 tests.

---

## Code Style

- Type hints on all function signatures (`str | None`, not `Optional[str]`)
- `from __future__ import annotations` at top of files
- Frozen dataclasses for immutable values, mutable for config
- Functions: 10-30 lines typical, single responsibility
- Ruff rules: `F` (Pyflakes) + `E` (pycodestyle), line length 88

---

## Adding a Guidance Pattern

SOMA's contextual guidance lives in `src/soma/contextual_guidance.py`. Follow TDD.

### 1. Write the test

In `tests/test_contextual_guidance.py`:

```python
def test_my_new_pattern(cg):
    # cg fixture creates ContextualGuidance(cooldown_actions=5)
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

### 2. Implement

In `contextual_guidance.py`:
- Add `_check_my_pattern()` method inspecting the action log
- Return `GuidanceMessage(pattern, severity, message, evidence, suggestion)` or `None`

### 3. Wire into evaluate()

Add your detector to the `evaluate()` pattern check list.

### 4. Set priority

Update `_PATTERN_PRIORITY` dict. Higher number wins ties when multiple patterns match at the same severity.

---

## Key Files

| File | What it does |
|:-----|:-------------|
| `src/soma/contextual_guidance.py` | All 9 pattern detectors + guidance generation |
| `src/soma/guidance.py` | Pressure-to-mode mapping, destructive tool evaluation |
| `src/soma/engine.py` | Core pipeline orchestration |
| `src/soma/hooks/` | Claude Code integration layer |
| `tests/test_contextual_guidance.py` | Pattern tests using the `cg` fixture |
| `docs/ARCHITECTURE.md` | Full technical architecture doc |
