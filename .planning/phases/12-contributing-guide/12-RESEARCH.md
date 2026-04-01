# Phase 12: Ecosystem - Research

**Researched:** 2026-03-31
**Domain:** Cross-platform AI coding tool hooks, NPM publishing, Layer SDK, community policy packs, demo generation
**Confidence:** HIGH

## Summary

Phase 12 transforms SOMA from a Claude Code-specific tool into a platform-agnostic ecosystem. The five requirements break down into: (1) HOOK-01 -- hooks for Cursor and Windsurf, (2) NPM-01 -- publishing the existing TypeScript SDK scaffold to NPM, (3) DEMO-01 -- a demo GIF for the README, (4) POL-03 -- community policy packs, and (5) LAYER-01 -- a Layer SDK that makes creating new platform integrations trivial.

The critical discovery is that all three platforms (Claude Code, Cursor, Windsurf) share the same fundamental hook contract: JSON on stdin, exit code 0/2 for allow/block, stderr for messages. The differences are in configuration file locations and event naming. This means SOMA can use a single core hook dispatcher with thin platform-specific adapter layers. The existing `soma.hooks.claude_code` module already implements the right pattern -- it just needs to be generalized.

**Primary recommendation:** Build a `soma.hooks.base` dispatcher protocol, then create `soma.hooks.cursor` and `soma.hooks.windsurf` as thin adapters that translate platform-specific event names and input formats to the common protocol. The existing Claude Code hooks become `soma.hooks.claude_code` (already named correctly). The Layer SDK (LAYER-01) formalizes this adapter pattern as a public API.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HOOK-01 | Cursor/Windsurf hooks -- same 4-hook architecture for other AI coding tools | Cross-platform hook protocol analysis (see Architecture Patterns) |
| NPM-01 | NPM publish TypeScript SDK | Existing `packages/soma-ai/` scaffold with tsup build (see Standard Stack) |
| DEMO-01 | Demo GIF/video for README | VHS tape-based terminal recording (see Architecture Patterns) |
| POL-03 | Community policy packs -- shareable rule sets | Existing `PolicyEngine.from_url()` already supports this (see Code Examples) |
| LAYER-01 | Layer SDK -- trivial creation of new platform integrations | Hook adapter Protocol class (see Architecture Patterns) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| soma (Python) | 0.5.0 | Core engine, hooks, policy | Already built |
| tsup | 8.5.1 | TypeScript SDK build (CJS + ESM + DTS) | Already in package.json |
| typescript | ~5.0 | Type checking for TS SDK | Already in devDependencies |
| vitest | ~1.0 | TS SDK tests | Already in devDependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| VHS (charmbracelet/vhs) | latest | Terminal GIF recording for DEMO-01 | Demo generation only |
| pyyaml | >=6.0 | YAML policy file parsing | Already optional dep for POL-01 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| VHS | asciinema + agg | VHS is scriptable via tape files, deterministic, better for CI |
| tsup | esbuild direct | tsup handles CJS+ESM+DTS in one command, already configured |

**Installation:** No new dependencies needed. VHS is a dev-only tool installed via `brew install vhs` or `go install`.

## Architecture Patterns

### Cross-Platform Hook Protocol

All three platforms share the same fundamental contract:

| Aspect | Claude Code | Cursor | Windsurf |
|--------|-------------|--------|----------|
| Config location | `.claude/settings.json` | `.cursor/hooks.json` | `.windsurf/hooks.json` |
| User config | `~/.claude/settings.json` | `~/.cursor/hooks.json` | `~/.codeium/windsurf/hooks.json` |
| Input format | JSON on stdin | JSON on stdin | JSON on stdin |
| Allow | exit 0 | exit 0 | exit 0 |
| Block | exit 2 | exit 2 | exit 2 |
| Messages | stderr | stdout JSON `user_message` | stderr |
| Pre-tool event | `PreToolUse` | `preToolUse` | `pre_run_command` / `pre_write_code` / `pre_read_code` / `pre_mcp_tool_use` |
| Post-tool event | `PostToolUse` | `postToolUse` | `post_run_command` / `post_write_code` / `post_read_code` / `post_mcp_tool_use` |
| Stop event | `Stop` | `stop` | N/A (use `post_cascade_response`) |
| Session start | `SessionStart` | `sessionStart` | N/A |

**Key differences:**
- **Cursor** uses camelCase event names, wraps everything in a single `preToolUse`/`postToolUse` event with tool name in the payload
- **Windsurf** splits by tool category: separate events for read/write/command/MCP
- **Claude Code** uses PascalCase, has matcher-based filtering within a single event type
- **Input fields**: Claude Code uses `tool_name`/`tool_input`, Cursor uses `tool_name` in base fields, Windsurf uses `tool_info` object with category-specific fields

### Recommended Project Structure

```
src/soma/hooks/
    __init__.py
    base.py              # HookAdapter Protocol + common dispatch logic (LAYER-01)
    common.py            # Shared utilities (existing)
    claude_code.py       # Claude Code adapter (existing, refactored)
    cursor.py            # Cursor adapter (HOOK-01)
    windsurf.py          # Windsurf adapter (HOOK-01)
    pre_tool_use.py      # Core pre-tool handler (existing)
    post_tool_use.py     # Core post-tool handler (existing)
    stop.py              # Core stop handler (existing)
    notification.py      # Core notification handler (existing)
    statusline.py        # Status line formatter (existing)
```

### Pattern 1: Hook Adapter Protocol (LAYER-01)

**What:** A `runtime_checkable` Protocol that defines what a platform adapter must implement. New integrations implement this protocol to get SOMA hooks working on their platform.

**When to use:** Any new AI coding tool integration.

**Example:**
```python
# Source: Designed based on cross-platform analysis
from typing import Protocol, runtime_checkable

@runtime_checkable
class HookAdapter(Protocol):
    """Protocol for platform-specific hook adapters (LAYER-01)."""

    @property
    def platform_name(self) -> str:
        """Human-readable platform name (e.g., 'cursor', 'windsurf')."""
        ...

    def parse_input(self, raw: dict) -> HookInput:
        """Translate platform-specific stdin JSON to common HookInput."""
        ...

    def format_output(self, result: HookResult) -> None:
        """Write platform-specific output (stderr, stdout JSON, etc.)."""
        ...

    def get_event_type(self, raw: dict) -> str:
        """Map platform event name to SOMA canonical event type."""
        ...
```

### Pattern 2: Cursor Hook Adapter

**What:** Thin adapter translating Cursor's camelCase events and `hooks.json` format to SOMA's canonical events.

**Configuration generated by `soma setup --cursor`:**
```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "command": "soma-hook PreToolUse",
        "type": "command",
        "timeout": 10
      }
    ],
    "postToolUse": [
      {
        "command": "soma-hook PostToolUse",
        "type": "command",
        "timeout": 10
      }
    ],
    "stop": [
      {
        "command": "soma-hook Stop",
        "type": "command",
        "timeout": 5
      }
    ]
  }
}
```

**Cursor-specific input translation:**
```python
# Cursor sends different field names
def parse_input(self, raw: dict) -> HookInput:
    return HookInput(
        tool_name=raw.get("tool_name", ""),
        tool_input=raw.get("tool_input", {}),
        output=raw.get("tool_response", ""),
        error=raw.get("error", False),
        session_id=raw.get("conversation_id", ""),
    )
```

### Pattern 3: Windsurf Hook Adapter

**What:** Adapter handling Windsurf's split-event model (pre_write_code, pre_run_command, etc.) by mapping them to SOMA's unified PreToolUse/PostToolUse.

**Configuration generated by `soma setup --windsurf`:**
```json
{
  "hooks": {
    "pre_run_command": [{ "command": "soma-hook PreToolUse", "show_output": true }],
    "pre_write_code": [{ "command": "soma-hook PreToolUse", "show_output": true }],
    "pre_read_code": [{ "command": "soma-hook PreToolUse", "show_output": true }],
    "post_run_command": [{ "command": "soma-hook PostToolUse", "show_output": true }],
    "post_write_code": [{ "command": "soma-hook PostToolUse", "show_output": true }],
    "post_read_code": [{ "command": "soma-hook PostToolUse", "show_output": true }],
    "post_cascade_response": [{ "command": "soma-hook Stop", "show_output": false }]
  }
}
```

**Windsurf-specific input translation:**
```python
# Windsurf puts data in tool_info, not top-level
# Tool type inferred from event name
_WINDSURF_EVENT_TO_TOOL = {
    "pre_run_command": "Bash",
    "pre_write_code": "Write",
    "pre_read_code": "Read",
    "post_run_command": "Bash",
    "post_write_code": "Write",
    "post_read_code": "Read",
}

def parse_input(self, raw: dict) -> HookInput:
    tool_info = raw.get("tool_info", {})
    event = raw.get("agent_action_name", "")
    return HookInput(
        tool_name=_WINDSURF_EVENT_TO_TOOL.get(event, "unknown"),
        tool_input=tool_info,
        output=tool_info.get("response", ""),
        error=False,
        session_id=raw.get("trajectory_id", ""),
    )
```

### Pattern 4: Community Policy Packs (POL-03)

**What:** Shareable YAML policy files loadable from URLs or local paths. The infrastructure already exists in `PolicyEngine.from_url()` and `PolicyEngine.from_file()`.

**What's missing:** (1) A `soma.toml` config key for auto-loading policy packs, (2) a `soma policy` CLI command for listing/adding/removing packs, (3) a few example packs in the repo.

**Example soma.toml:**
```toml
[policies]
packs = [
    "https://raw.githubusercontent.com/tr00x/soma-policies/main/strict.yaml",
    "./my-local-policy.yaml",
]
```

**Example policy pack (strict.yaml):**
```yaml
version: "1"
policies:
  - name: "high-error-guard"
    when:
      - field: "error_rate"
        op: ">="
        value: 0.3
    do:
      action: "warn"
      message: "Error rate exceeds 30% -- consider reviewing recent changes"
  - name: "cost-limit"
    when:
      - field: "cost"
        op: ">="
        value: 5.0
    do:
      action: "block"
      message: "Cost exceeds $5 limit"
```

### Pattern 5: NPM Publishing (NPM-01)

**What:** The TypeScript SDK scaffold at `packages/soma-ai/` is already buildable. Publishing requires: (1) verify build works, (2) add npm publish script, (3) publish to NPM.

**Pre-publish checklist:**
- `npm run build` produces `dist/` with CJS, ESM, and DTS files
- `npm run test` passes
- `npm run typecheck` passes
- package.json has correct `name`, `version`, `license`, `repository` fields
- `.npmignore` or `files` field limits published content (already `"files": ["dist"]`)

### Pattern 6: Demo GIF (DEMO-01)

**What:** A VHS tape file that records a scripted terminal session showing SOMA in action. VHS produces deterministic, reproducible GIFs from `.tape` files.

**Example tape file:**
```tape
Output demo.gif
Set FontSize 14
Set Width 1200
Set Height 600
Set Theme "Catppuccin Mocha"

Type "pip install soma-ai"
Enter
Sleep 2s

Type "soma setup --claude-code"
Enter
Sleep 1s

Type "soma status"
Enter
Sleep 3s
```

### Anti-Patterns to Avoid
- **Platform-specific logic in core hooks:** Keep `pre_tool_use.py` and `post_tool_use.py` platform-agnostic; all platform translation happens in the adapter layer.
- **Requiring platform-specific deps:** No Cursor or Windsurf SDK imports; hooks work via stdin/stdout/exit codes only.
- **Hardcoding Claude Code assumptions in engine:** The `CLAUDE_HOOK` env var pattern is Claude Code-specific; adapters should handle their own env detection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Terminal GIF recording | Custom screen capture | VHS (charmbracelet/vhs) | Deterministic, scriptable, CI-friendly |
| TS SDK bundling | Custom build pipeline | tsup | Already configured, handles CJS+ESM+DTS |
| YAML parsing for policies | Custom parser | PyYAML (already optional) | Battle-tested, safe_load prevents code injection |
| NPM publishing | Manual tarball | `npm publish` | Standard tooling |

## Common Pitfalls

### Pitfall 1: Cursor/Windsurf stdin format differences
**What goes wrong:** Assuming all platforms send the same JSON structure on stdin. Cursor sends `tool_name` at top level; Windsurf puts everything in `tool_info`.
**Why it happens:** Testing only against Claude Code's format.
**How to avoid:** Each adapter has its own `parse_input()` that normalizes to `HookInput`. Test each adapter with fixture data matching the real platform format.
**Warning signs:** KeyError or empty tool names in hook logs.

### Pitfall 2: Exit code semantics across platforms
**What goes wrong:** All three platforms use exit code 2 for blocking, but the stderr/stdout handling differs. Cursor expects JSON on stdout with `permission: "deny"` field. Claude Code reads stderr. Windsurf reads stderr.
**Why it happens:** Not reading platform docs carefully.
**How to avoid:** Each adapter's `format_output()` handles the platform-specific output format.
**Warning signs:** Hooks that block on one platform but not another.

### Pitfall 3: NPM package name conflicts
**What goes wrong:** `soma-ai` might be taken on NPM.
**Why it happens:** PyPI and NPM are separate registries.
**How to avoid:** Check `npm view soma-ai` before publishing. The package.json already uses `soma-ai`.
**Warning signs:** `npm publish` fails with 403.

### Pitfall 4: Windsurf's split event model
**What goes wrong:** Windsurf has separate events for read/write/command instead of one unified PreToolUse. If you only hook `pre_run_command`, file writes go unmonitored.
**Why it happens:** Windsurf's architecture is fundamentally different from Claude Code/Cursor.
**How to avoid:** The setup command must register hooks for ALL Windsurf events (pre_read_code, pre_write_code, pre_run_command, pre_mcp_tool_use).
**Warning signs:** SOMA only sees shell commands but misses file edits.

### Pitfall 5: Policy pack security
**What goes wrong:** Loading arbitrary YAML from URLs could be a security risk (YAML deserialization attacks).
**Why it happens:** Using `yaml.load()` instead of `yaml.safe_load()`.
**How to avoid:** Already using `yaml.safe_load()` in `policy.py`. Keep it that way. Document that only trusted URLs should be used.
**Warning signs:** N/A -- already mitigated in existing code.

## Code Examples

### Existing PolicyEngine.from_url (already implemented for POL-03)
```python
# Source: src/soma/policy.py lines 186-195
@classmethod
def from_url(cls, url: str) -> "PolicyEngine":
    """Load policy pack from a URL (POL-03)."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
    return cls.from_dict(_parse_policy_text(raw, url))
```

### Existing Claude Code Dispatcher Pattern
```python
# Source: src/soma/hooks/claude_code.py
DISPATCH = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
    "Stop": stop,
    "UserPromptSubmit": notification,
    "Notification": notification,
}

def main():
    hook_type = os.environ.get("CLAUDE_HOOK", "")
    if not hook_type and len(sys.argv) > 1:
        hook_type = sys.argv[1]
    handler = DISPATCH.get(hook_type)
    if handler is None:
        post_tool_use()
    else:
        handler()
```

### Common HookInput dataclass (new, for LAYER-01)
```python
@dataclass(frozen=True, slots=True)
class HookInput:
    """Normalized hook input from any platform."""
    tool_name: str
    tool_input: dict
    output: str = ""
    error: bool = False
    session_id: str = ""
    file_path: str = ""
    duration_ms: float = 0
    platform: str = ""
    raw: dict = field(default_factory=dict)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Claude Code only | Cursor + Windsurf both have hooks API | Cursor 1.7 (Oct 2025), Windsurf v1.12 (Nov 2025) | All major AI coding tools now support hook systems |
| Custom hook protocols | Converging on stdin JSON + exit code convention | 2025 | Platform adapters are thin translation layers |
| Manual policy files | URL-loadable policy packs | Already in SOMA | POL-03 infrastructure exists, needs UX polish |

## Open Questions

1. **Cursor stdout JSON vs stderr for messages**
   - What we know: Cursor hooks can return JSON with `user_message` and `agent_message` fields on stdout. Claude Code uses stderr for messages.
   - What's unclear: Whether Cursor also reads stderr, or only stdout JSON.
   - Recommendation: Support both -- write stderr AND return JSON. Test empirically.

2. **NPM package name availability**
   - What we know: `soma-ai` is configured in package.json.
   - What's unclear: Whether it's available on NPM registry.
   - Recommendation: Check with `npm view soma-ai` before publishing. Have `@soma-ai/sdk` as fallback.

3. **Demo GIF scope**
   - What we know: Need a demo for README (DEMO-01).
   - What's unclear: What specific workflow to demo (setup? monitoring in action? pressure escalation?).
   - Recommendation: Show the full loop: install, setup, run a session where pressure rises, show guidance output.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/test_claude_code_layer.py tests/test_policy.py tests/test_sdk.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HOOK-01 | Cursor/Windsurf adapters parse platform-specific input correctly | unit | `pytest tests/test_hook_adapters.py -x` | Wave 0 |
| HOOK-01 | Setup command generates correct config files for each platform | unit | `pytest tests/test_hook_adapters.py::test_cursor_config -x` | Wave 0 |
| NPM-01 | TypeScript SDK builds and type-checks | smoke | `cd packages/soma-ai && npm run build && npm run typecheck` | Wave 0 |
| DEMO-01 | Demo tape file exists and is valid | manual-only | Manual: `vhs demo.tape` | N/A |
| POL-03 | Policy packs load from URL and local file | unit | `pytest tests/test_policy.py -x` | Existing |
| LAYER-01 | HookAdapter protocol is implementable | unit | `pytest tests/test_hook_adapters.py::test_layer_protocol -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_claude_code_layer.py tests/test_policy.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_hook_adapters.py` -- covers HOOK-01, LAYER-01 (Cursor/Windsurf adapter parsing, config generation, Protocol compliance)
- [ ] `packages/soma-ai/src/index.test.ts` -- exists but may need NPM-01 verification tests

## Sources

### Primary (HIGH confidence)
- [Cursor Hooks Documentation](https://cursor.com/docs/hooks) -- full configuration schema, events, input/output format
- [Windsurf Cascade Hooks Documentation](https://docs.windsurf.com/windsurf/cascade/hooks) -- full configuration schema, events, input/output format
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- full configuration schema, 20+ events, JSON I/O format
- Codebase inspection: `src/soma/hooks/`, `src/soma/policy.py`, `packages/soma-ai/` -- existing implementation

### Secondary (MEDIUM confidence)
- [Charmbracelet VHS](https://github.com/charmbracelet/vhs) -- terminal GIF recording tool
- [Cursor 1.7 Hooks announcement](https://www.infoq.com/news/2025/10/cursor-hooks/) -- feature history
- [Windsurf SWE-1.5 & Cascade Hooks guide](https://www.digitalapplied.com/blog/windsurf-swe-1-5-cascade-hooks-november-2025) -- feature history

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, building on existing codebase
- Architecture: HIGH -- all three platform docs reviewed, protocol similarities confirmed
- Pitfalls: HIGH -- based on direct documentation comparison across platforms
- NPM publishing: MEDIUM -- package name availability unverified

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- hook APIs unlikely to change rapidly)
