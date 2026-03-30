# Technology Stack

**Analysis Date:** 2026-03-30

## Languages

**Primary:**
- Python 3.11+ - Core implementation language. Package requires `>=3.11` with explicit support for Python 3.11, 3.12, 3.13

**Secondary:**
- TOML - Configuration format for `soma.toml`

## Runtime

**Environment:**
- Python 3.11, 3.12, 3.13 - All three versions tested in CI

**Package Manager:**
- uv (UV package manager) - Used for dependency management
- pip - Fallback installation method
- Lockfile: `uv.lock` (present)

## Frameworks

**Core:**
- No external framework for core logic - Architecture is built on Python stdlib + carefully selected dependencies

**CLI/TUI:**
- Textual 3.0+ - Terminal user interface for interactive dashboard (`src/soma/cli/hub.py`, `src/soma/cli/tabs/`)
  - Provides rich text rendering, tabbed interfaces, interactive widgets
  - Used for real-time monitoring dashboard with agents, config, replay, and dashboard tabs

**Build/Dev:**
- Hatchling - Build backend and package builder
- pytest 8.0+ - Testing framework with coverage support
- ruff - Linter for Python code quality (F and E error codes)
- pytest-cov - Coverage measurement plugin

## Key Dependencies

**Core/Required:**
- `rich>=13.0` - Rich text and formatting for CLI output, progress bars, tables
- `textual>=3.0` - TUI framework for interactive monitoring dashboard
- `tomli-w>=1.0` - TOML serialization library for writing `soma.toml` config files
- Built-in `tomllib` - Standard library TOML parsing (Python 3.11+)

**Optional:**
- `opentelemetry-api>=1.20` - OpenTelemetry API for observability integration (optional `otel` extra)
- `opentelemetry-sdk>=1.20` - OpenTelemetry SDK for exporting metrics (optional `otel` extra)

**Development:**
- `pytest>=8.0` - Test runner
- `pytest-cov` - Coverage plugin
- `ruff` - Linter
- `build` - Package building tool (used in CI)

**Transitive (from `textual` and `rich`):**
- `colorama` - Cross-platform colored terminal output
- `iniconfig` - INI file parsing (pytest dependency)
- Various other support libraries

## Configuration

**Environment:**
- Configuration stored in `soma.toml` (TOML format)
- Default config returned if `soma.toml` is missing: `src/soma/cli/config_loader.py`
- Session state stored in JSON: `~/.soma/state.json` and `~/.soma/engine_state.json`
- Environment variables: `CLAUDE_WORKING_DIRECTORY` (optional, for GSD workflow detection)
- Environment variables: `CLAUDE_HOOK` (for hook dispatcher routing)

**Build:**
- `pyproject.toml` - Standard Python project metadata and dependencies
  - Package name: `soma-ai`
  - Current version: 0.4.12
  - Build backend: hatchling
  - Wheel package location: `src/soma`
  - Included skills: `skills/` directory bundled as `soma/_skills`

**Config File Locations:**
- `soma.toml` - Main configuration file (in project root or current directory)
- `~/.soma/state.json` - User session state (default location)
- `~/.soma/engine_state.json` - Engine persistence (atomic write with file locking)
- `.coveragerc` - Coverage configuration for pytest-cov

## Platform Requirements

**Development:**
- Python 3.11+ (interpreter)
- pip or uv (package installation)
- Unix/POSIX systems for file locking in persistence (`fcntl` module with fallback)
- Optional: Node.js for JavaScript validation (if `validate_js` enabled in hooks)

**Production:**
- Python 3.11+ runtime
- No external service dependencies required
- Optional: OpenTelemetry collector for observability integration
- Deployment: PyPI package (`soma-ai`), installable via `pip install soma-ai`

## Entry Points

**CLI:**
- `soma` - Main CLI tool (from `soma.cli.main:main`)
- `soma-hook` - Hook dispatcher for Claude Code (from `soma.hooks.claude_code:main`)
- `soma-statusline` - Status line formatter (from `soma.hooks.statusline:main`)

**Python API:**
- `soma.quickstart()` - Fastest way to initialize engine
- `soma.wrap()` - Wrap any LLM client (e.g., `anthropic.Anthropic()`)
- `soma.SOMAEngine` - Core engine class
- `soma.replay_session()` - Replay recording for analysis

---

*Stack analysis: 2026-03-30*
