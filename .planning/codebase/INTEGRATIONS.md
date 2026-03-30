# External Integrations

**Analysis Date:** 2026-03-30

## APIs & External Services

**LLM Client Integration:**
- Anthropic (Claude) - Via `soma.wrap()` wrapper
  - SDK: `anthropic` (not vendored, consumer brings their own)
  - Integration point: `src/soma/wrap.py` - Universal API client wrapper that intercepts `client.messages.create()` calls
  - Also supports: OpenAI SDK (`openai`), Bedrock runtime (AWS), and other compatible clients
  - No direct HTTP calls - SOMA wraps existing client objects
  - Auth: Delegated to consumer's client initialization

**Observability (Optional):**
- OpenTelemetry - Optional integration for metrics export
  - SDK packages: `opentelemetry-api>=1.20`, `opentelemetry-sdk>=1.20` (optional `otel` extra)
  - Usage: Optional integration point in codebase (packages listed but not actively used in current codebase inspection)
  - Consumer responsibility: Set up OTEL exporter to actual monitoring backend

## Data Storage

**Databases:**
- None - No database integration

**File Storage:**
- Local filesystem only
  - Session state: `~/.soma/state.json` (JSON file)
  - Engine persistence: `~/.soma/engine_state.json` (atomic write via `src/soma/persistence.py`)
  - Session recordings: JSON format (via `src/soma/recorder.py`)
  - Atomic write mechanism: Uses file locking (`fcntl`) on POSIX systems with fallback to direct write

**Caching:**
- None - No caching service integration

## Authentication & Identity

**Auth Provider:**
- Custom/Delegated - SOMA does not handle authentication
  - Consumer provides authenticated LLM client (e.g., `anthropic.Anthropic(api_key=...)`)
  - SOMA wraps the client and monitors calls
  - No credential storage in SOMA
  - No token management

## Monitoring & Observability

**Error Tracking:**
- None built-in - Consumer can use OpenTelemetry optional integration
  - No direct error tracking service integration
  - Errors are recorded in session state and can be analyzed via replay

**Logs:**
- Local logging approach
  - CLI uses `rich` console output for formatted logging
  - Hook system (`src/soma/hooks/`) outputs to stdout/stderr
  - Session recorder captures all agent actions as JSON
  - Real-time monitoring via Textual TUI dashboard

**Trace Collection (Optional):**
- OpenTelemetry SDK (if `otel` extra installed)
- No automatic instrumentation - Consumer responsibility to export

## CI/CD & Deployment

**Hosting:**
- PyPI - Package published to Python Package Index
  - Package: `soma-ai`
  - URL: https://pypi.org/project/soma-ai/
  - Authentication: GitHub trusted publishing (no API tokens stored)

**CI Pipeline:**
- GitHub Actions (`.github/workflows/`)
  - `ci.yml`: Tests on Python 3.11, 3.12, 3.13 (via `actions/setup-python`)
  - `publish.yml`: Publishes to PyPI on release (via `pypa/gh-action-pypi-publish`)
  - No external API calls in CI
  - Linting via ruff, testing via pytest

**Release Process:**
- Manual release trigger via GitHub release creation
- Build: `python -m build` (hatchling)
- Publish: `pypa/gh-action-pypi-publish@release/v1` (uses OIDC trusted publishing)

## Environment Configuration

**Required env vars:**
- None required - All configuration via `soma.toml`
- Optional: `CLAUDE_WORKING_DIRECTORY` - Workflow mode detection
- Optional: `CLAUDE_HOOK` - Hook dispatcher routing

**Secrets location:**
- No secrets stored in SOMA itself
- Consumer responsibility: Manage LLM API keys, credentials for wrapped clients
- No `.env` files in repository
- Recommendation: Use OS environment for sensitive config

**Configuration Sources:**
- `soma.toml` - Primary configuration (human-readable)
- CLI defaults in `src/soma/cli/config_loader.py`
- Mode presets: `strict`, `relaxed`, `autonomous` (configuration templates)

## Webhooks & Callbacks

**Incoming:**
- None - SOMA is a library/tool, not a server

**Outgoing:**
- None - No webhooks sent by SOMA itself
- Optional: Consumer can integrate with OpenTelemetry exporters to send metrics

## Hook Integration Points

**Hook System:**
- Location: `src/soma/hooks/`
- Purpose: Integration with Claude Code environment (MCP server hooks)

**Hooks Available:**
- `PreToolUse` - Fires before tool execution (`src/soma/hooks/pre_tool_use.py`)
- `PostToolUse` - Fires after tool execution (`src/soma/hooks/post_tool_use.py`)
- `Stop` - Fires on session stop (`src/soma/hooks/stop.py`)
- `Notification` / `UserPromptSubmit` - User interaction hooks (`src/soma/hooks/notification.py`)

**Hook Responsibilities:**
- Validation: Python syntax check (py_compile), JavaScript check (node --check), lint (ruff)
- Monitoring: Record action metrics, update pressure scores
- Prediction: Anomaly detection before state escalation
- Quality scoring: Session grade calculation
- Task tracking: Scope drift detection

## Runtime Integration

**How SOMA Integrates with Agents:**
1. Consumer creates LLM client (e.g., `anthropic.Anthropic()`)
2. Consumer wraps client: `soma.wrap(client, budget=...)`
3. SOMA intercepts all `client.messages.create()` calls
4. Each call is monitored, recorded, analyzed
5. If pressure too high or budget exhausted → call blocked with `SomaBlocked` or `SomaBudgetExhausted` exception
6. Session data exported as JSON for analysis/replay

**Integration Pattern:**
```python
import anthropic
import soma

client = anthropic.Anthropic(api_key="sk-...")
wrapped = soma.wrap(client, budget={"tokens": 50000})

# Every call through wrapped client is monitored
response = wrapped.messages.create(model="claude-3-sonnet", messages=[...])
```

---

*Integration audit: 2026-03-30*
