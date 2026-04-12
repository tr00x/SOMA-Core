# Contributing to SOMA

## Development Setup

Prerequisites: Python 3.11+, uv (recommended) or pip

```bash
# Clone the repo
git clone https://github.com/tr00x/SOMA-Core.git
cd SOMA-Core

# Install with dev dependencies (using uv)
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -x -v

# Run with coverage
python -m pytest tests/ --cov=soma --cov-report=term-missing

# Run a specific test file
python -m pytest tests/test_engine.py -x -v

# Run integration tests (requires API keys)
ANTHROPIC_API_KEY=sk-... OPENAI_API_KEY=sk-... python -m pytest tests/test_integration_api.py -x -v
```

## Linting

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Project Structure

```
src/soma/
  __init__.py          # Public API exports
  engine.py            # Main pipeline: record_action() -> vitals -> pressure -> mode
  types.py             # Action, VitalsSnapshot, ResponseMode, AgentConfig
  vitals.py            # Signal computation (uncertainty, drift, error_rate)
  pressure.py          # Aggregate pressure from signals
  baseline.py          # EMA baselines with cold-start blending
  guidance.py          # Pressure -> response mode mapping
  mirror.py            # Proprioceptive feedback (PATTERN/STATS/SEMANTIC)
  wrap.py              # soma.wrap() universal client wrapper
  proxy.py             # SOMAProxy universal tool wrapper
  audit.py             # JSON Lines audit logging
  budget.py            # Multi-dimensional budget tracking
  graph.py             # Trust-weighted pressure propagation
  halflife.py          # Temporal success rate modeling
  learning.py          # Adaptive threshold learning
  policy.py            # YAML/TOML policy engine
  predictor.py         # Pressure prediction and forecasting
  quality.py           # Quality scoring (A/B/C/D/F)
  rca.py               # Root cause analysis
  patterns.py          # Pattern detection (blind edits, thrashing, etc.)
  findings.py          # Aggregated monitoring insights
  fingerprint.py       # Cross-session behavioral fingerprinting
  reliability.py       # Calibration, VBD detection
  recorder.py          # Session recording
  persistence.py       # Engine state save/load (atomic writes)
  context.py           # Session context and workflow detection
  session_memory.py    # Cross-session memory
  subagent_monitor.py  # Multi-agent child tracking
  task_tracker.py      # Phase detection and scope drift
  reflexes.py          # Reflex system (hard safety blocks)
  ring_buffer.py       # Fixed-capacity action buffer
  events.py            # Event bus for engine events
  errors.py            # Custom exception hierarchy
  models.py            # Data models
  state.py             # Transient subsystem state management
  report.py            # Session report generation
  analytics.py         # Historical analytics
  sdk/                 # Framework adapters (LangChain, CrewAI, AutoGen)
  cli/                 # CLI commands and TUI dashboard
  hooks/               # Hook integration (Claude Code, Cursor, Windsurf)
  dashboard/           # Web dashboard (FastAPI + SSE, port 7777)
  exporters/           # OpenTelemetry, webhooks
  benchmark/           # Behavioral benchmarks
tests/                 # 74 test files
```

## How to Contribute

1. Fork the repo and create a feature branch
2. Write tests first (TDD encouraged)
3. Make your changes
4. Run `python -m pytest tests/ -x` and `ruff check src/ tests/`
5. Submit a PR with a clear description

## Code Style

- Python 3.11+ with full type hints
- Ruff for linting (F + E rules)
- Line length: 88 chars (formatter)
- Frozen dataclasses for immutable types
- Explicit `__all__` in public modules
- snake_case for functions/variables, PascalCase for classes

## Architecture

SOMA is a behavioral monitoring pipeline:

```
Action -> Vitals -> Pressure -> Mode -> Guidance
```

Core principle: Actions flow through the engine, vitals are computed, pressure is aggregated, a response mode is determined, and guidance is emitted. The engine never modifies the agent directly -- it observes and advises.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture document.

## License

MIT. All contributions are under the same license.
